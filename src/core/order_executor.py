"""
Order execution module.
Handles trade execution and position tracking in the database.
"""

from typing import Dict, Any, Optional
from datetime import datetime
import structlog
from sqlalchemy.orm import Session

from src.api.alpaca_client import alpaca_client
from src.database.models import Position, Trade, Signal, PositionStatus, TradeSide, SignalType
from src.core.risk_manager import risk_manager
from config.settings import settings

logger = structlog.get_logger(__name__)


class OrderExecutor:
    """
    Executes trading orders and maintains database records.
    """

    def __init__(self):
        self.paper_trading = settings.is_paper_trading

    def execute_buy_signal(
        self,
        signal: Signal,
        db: Session
    ) -> Optional[Position]:
        """
        Execute a buy signal by opening a position.

        Args:
            signal: Buy signal to execute
            db: Database session

        Returns:
            Position object if successful, None otherwise
        """
        try:
            symbol = signal.symbol
            confidence = signal.confidence

            # Get current price
            bars = alpaca_client.get_bars(symbol, timeframe="1Min", limit=1)
            if not bars:
                logger.error("no_price_data", symbol=symbol)
                return None

            current_price = bars[-1]['close']

            # Calculate position size
            quantity = risk_manager.calculate_position_size(
                symbol, current_price, confidence
            )

            if quantity <= 0:
                logger.warning(
                    "invalid_quantity",
                    symbol=symbol,
                    quantity=quantity
                )
                return None

            # Check risk limits
            can_trade, reason = risk_manager.can_open_position(
                symbol, quantity, current_price, db
            )

            if not can_trade:
                logger.warning(
                    "trade_rejected_by_risk_manager",
                    symbol=symbol,
                    reason=reason
                )
                return None

            # Place order
            order = alpaca_client.place_market_order(
                symbol=symbol,
                qty=quantity,
                side="buy"
            )

            logger.info(
                "buy_order_placed",
                symbol=symbol,
                quantity=quantity,
                price=current_price,
                order_id=order['id']
            )

            # Wait briefly for fill (in production, use webhooks)
            import time
            time.sleep(2)

            # Get order status
            order_status = alpaca_client.get_order(order['id'])

            filled_price = order_status.get('filled_avg_price') or current_price
            filled_qty = order_status.get('filled_qty', quantity)

            # Calculate stop loss and take profit
            stop_loss = filled_price * (1 - settings.default_stop_loss_pct / 100)
            take_profit = filled_price * (1 + (settings.default_stop_loss_pct * 2) / 100)

            # Create position record
            position = Position(
                symbol=symbol,
                platform="alpaca",
                quantity=filled_qty,
                entry_price=filled_price,
                entry_date=datetime.utcnow(),
                strategy=signal.strategy_name,
                confidence_score=confidence,
                stop_loss=stop_loss,
                take_profit=take_profit,
                status=PositionStatus.OPEN,
                alpaca_order_id=order['id']
            )

            db.add(position)
            db.flush()  # Get position ID

            # Create trade record
            trade = Trade(
                position_id=position.id,
                symbol=symbol,
                side=TradeSide.BUY,
                quantity=filled_qty,
                price=filled_price,
                filled_at=datetime.utcnow(),
                alpaca_order_id=order['id']
            )

            db.add(trade)

            # Update signal as executed
            db_signal = db.query(Signal).filter(Signal.id == signal.id).first()
            if db_signal:
                db_signal.executed = True
                db_signal.execution_time = datetime.utcnow()
                db_signal.position_id = position.id

            db.commit()

            logger.info(
                "position_opened",
                position_id=position.id,
                symbol=symbol,
                quantity=filled_qty,
                entry_price=filled_price,
                stop_loss=stop_loss,
                take_profit=take_profit
            )

            return position

        except Exception as e:
            logger.error(
                "failed_to_execute_buy_signal",
                symbol=signal.symbol,
                error=str(e)
            )
            db.rollback()
            return None

    def close_position(
        self,
        position: Position,
        reason: str,
        db: Session
    ) -> bool:
        """
        Close a position.

        Args:
            position: Position to close
            reason: Reason for closing
            db: Database session

        Returns:
            True if successful
        """
        try:
            symbol = position.symbol

            # Get current price
            bars = alpaca_client.get_bars(symbol, timeframe="1Min", limit=1)
            if not bars:
                logger.error("no_price_data_for_close", symbol=symbol)
                return False

            current_price = bars[-1]['close']

            # Place sell order
            order = alpaca_client.close_position(symbol)

            logger.info(
                "sell_order_placed",
                symbol=symbol,
                quantity=position.quantity,
                price=current_price,
                order_id=order['id'],
                reason=reason
            )

            # Wait briefly for fill
            import time
            time.sleep(2)

            # Get order status
            order_status = alpaca_client.get_order(order['id'])
            filled_price = order_status.get('filled_avg_price') or current_price
            filled_qty = order_status.get('filled_qty', position.quantity)

            # Update position
            position.exit_price = filled_price
            position.exit_date = datetime.utcnow()
            position.status = PositionStatus.CLOSED
            position.notes = reason

            # Create trade record
            trade = Trade(
                position_id=position.id,
                symbol=symbol,
                side=TradeSide.SELL,
                quantity=filled_qty,
                price=filled_price,
                filled_at=datetime.utcnow(),
                alpaca_order_id=order['id'],
                notes=reason
            )

            db.add(trade)
            db.commit()

            # Calculate P&L
            pnl = (filled_price - position.entry_price) * filled_qty
            pnl_pct = ((filled_price - position.entry_price) / position.entry_price) * 100

            logger.info(
                "position_closed",
                position_id=position.id,
                symbol=symbol,
                entry_price=position.entry_price,
                exit_price=filled_price,
                pnl=pnl,
                pnl_pct=pnl_pct,
                reason=reason
            )

            return True

        except Exception as e:
            logger.error(
                "failed_to_close_position",
                position_id=position.id,
                symbol=position.symbol,
                error=str(e)
            )
            db.rollback()
            return False

    def sync_positions_with_alpaca(self, db: Session) -> None:
        """
        Sync database positions with Alpaca positions.
        Useful for ensuring consistency.

        Args:
            db: Database session
        """
        try:
            # Get positions from Alpaca
            alpaca_positions = alpaca_client.get_positions()
            alpaca_symbols = {pos['symbol'] for pos in alpaca_positions}

            # Get open positions from database
            db_positions = db.query(Position).filter(
                Position.status == PositionStatus.OPEN
            ).all()

            # Close positions that are no longer in Alpaca
            for position in db_positions:
                if position.symbol not in alpaca_symbols:
                    logger.warning(
                        "position_missing_in_alpaca",
                        position_id=position.id,
                        symbol=position.symbol
                    )
                    # Mark as closed (may have been manually closed)
                    position.status = PositionStatus.CLOSED
                    position.exit_date = datetime.utcnow()
                    position.notes = "Closed (not found in Alpaca)"

            db.commit()

            logger.info(
                "positions_synced",
                alpaca_count=len(alpaca_positions),
                db_count=len(db_positions)
            )

        except Exception as e:
            logger.error("failed_to_sync_positions", error=str(e))


# Global order executor instance
order_executor = OrderExecutor()
