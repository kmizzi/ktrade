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

            # Check if we already have a position in this symbol
            existing_positions = alpaca_client.get_positions()
            for pos in existing_positions:
                if pos['symbol'] == symbol:
                    logger.info(
                        "skipping_buy_already_have_position",
                        symbol=symbol,
                        existing_qty=pos['qty']
                    )
                    return None

            # Check if we already have a pending buy order for this symbol
            open_orders = alpaca_client.get_open_orders()
            for order in open_orders:
                if order['symbol'] == symbol and order['side'] == 'buy':
                    logger.info(
                        "skipping_buy_pending_order_exists",
                        symbol=symbol,
                        order_id=order['id']
                    )
                    return None

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

            # Place market order for entry
            order = alpaca_client.place_market_order(
                symbol=symbol,
                qty=quantity,
                side="buy"
            )

            logger.info(
                "entry_order_placed",
                symbol=symbol,
                quantity=quantity,
                price=current_price,
                order_id=order['id']
            )

            # Wait briefly for fill (in production, use webhooks)
            import time
            time.sleep(2)

            # Get order status
            order_status = alpaca_client.get_order(str(order['id']))

            filled_price = order_status.get('filled_avg_price') or current_price
            filled_qty = order_status.get('filled_qty', quantity)

            # Calculate stop loss for tracking (trailing stop will handle exit)
            stop_loss = filled_price * (1 - settings.trailing_stop_pct / 100)

            # Place exit protection order
            # Note: Alpaca doesn't support trailing stops for fractional shares
            trailing_stop_order = None
            is_fractional = filled_qty != int(filled_qty)

            if settings.use_trailing_stops and not is_fractional:
                # Use trailing stop for whole shares
                try:
                    trailing_stop_order = alpaca_client.place_trailing_stop_order(
                        symbol=symbol,
                        qty=filled_qty,
                        trail_percent=settings.trailing_stop_pct,
                        side="sell"
                    )
                    logger.info(
                        "trailing_stop_placed",
                        symbol=symbol,
                        qty=filled_qty,
                        trail_percent=settings.trailing_stop_pct,
                        order_id=trailing_stop_order['id']
                    )
                except Exception as e:
                    logger.error("failed_to_place_trailing_stop", symbol=symbol, error=str(e))

            # Fall back to regular stop order for fractional shares or if trailing stop failed
            if not trailing_stop_order:
                try:
                    trailing_stop_order = alpaca_client.place_stop_order(
                        symbol=symbol,
                        qty=filled_qty,
                        stop_price=round(stop_loss, 2),
                        side="sell"
                    )
                    logger.info(
                        "stop_order_placed",
                        symbol=symbol,
                        stop_price=round(stop_loss, 2),
                        reason="fractional_shares" if is_fractional else "trailing_stop_failed"
                    )
                except Exception as e2:
                    logger.error("failed_to_place_stop_order", error=str(e2))

            # Create position record
            position = Position(
                symbol=symbol,
                platform="alpaca",
                quantity=filled_qty,
                entry_price=filled_price,
                entry_date=datetime.utcnow(),
                strategy=signal.strategy,
                confidence_score=confidence,
                stop_loss=stop_loss,
                take_profit=None,  # No fixed take-profit with trailing stops
                status=PositionStatus.OPEN,
                alpaca_order_id=str(order['id']),
                alpaca_stop_order_id=str(trailing_stop_order['id']) if trailing_stop_order else None
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
                alpaca_order_id=str(order['id'])
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
                trailing_stop=True if trailing_stop_order else False
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

            # Cancel any existing orders for this symbol first (e.g., stop orders)
            open_orders = alpaca_client.get_open_orders()
            for existing_order in open_orders:
                if existing_order['symbol'] == symbol:
                    try:
                        alpaca_client.cancel_order(existing_order['id'])
                        logger.info(
                            "cancelled_existing_order_for_close",
                            symbol=symbol,
                            order_id=existing_order['id'],
                            order_type=existing_order['type']
                        )
                        import time
                        time.sleep(0.5)  # Brief pause after cancel
                    except Exception as e:
                        logger.warning(
                            "failed_to_cancel_order",
                            symbol=symbol,
                            order_id=existing_order['id'],
                            error=str(e)
                        )

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
                alpaca_order_id=str(order['id']),
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

    def add_trailing_stop_to_position(
        self,
        position: Position,
        db: Session,
        trail_percent: float = None
    ) -> bool:
        """
        Add a trailing stop order to an existing position on Alpaca.

        This is useful for positions that were opened without a trailing stop,
        or to refresh DAY orders for fractional shares.

        Args:
            position: Position to add trailing stop to
            db: Database session
            trail_percent: Optional custom trail percentage (uses settings.trailing_stop_pct if not provided)

        Returns:
            True if successful
        """
        try:
            symbol = position.symbol

            # Check if there's already an active stop order
            existing_orders = alpaca_client.get_open_orders(symbol)
            stop_orders = [o for o in existing_orders if o['type'] in ['stop', 'trailing_stop']]

            if stop_orders:
                logger.info(
                    "stop_order_already_exists",
                    symbol=symbol,
                    order_id=stop_orders[0]['id'],
                    order_type=stop_orders[0]['type']
                )
                return True

            # Use settings trail percent if not provided
            if trail_percent is None:
                trail_percent = settings.trailing_stop_pct

            # Check if fractional shares (Alpaca doesn't support trailing stops for fractional)
            is_fractional = position.quantity != int(position.quantity)

            # Place trailing stop order (only for whole shares)
            if settings.use_trailing_stops and not is_fractional:
                order = alpaca_client.place_trailing_stop_order(
                    symbol=symbol,
                    qty=position.quantity,
                    trail_percent=trail_percent,
                    side="sell"
                )
                order_type = "trailing_stop"
            else:
                # Use regular stop for fractional shares or if trailing stops disabled
                stop_price = position.entry_price * (1 - trail_percent / 100)
                order = alpaca_client.place_stop_order(
                    symbol=symbol,
                    qty=position.quantity,
                    stop_price=round(stop_price, 2),
                    side="sell"
                )
                order_type = "stop"
                if is_fractional:
                    logger.info(
                        "using_stop_order_for_fractional",
                        symbol=symbol,
                        reason="alpaca_doesnt_support_trailing_stops_for_fractional_shares"
                    )

            # Update position with stop order ID
            position.alpaca_stop_order_id = str(order['id'])
            db.commit()

            logger.info(
                "trailing_stop_added_to_position",
                position_id=position.id,
                symbol=symbol,
                trail_percent=trail_percent,
                order_type=order_type,
                order_id=order['id']
            )

            return True

        except Exception as e:
            logger.error(
                "failed_to_add_trailing_stop",
                position_id=position.id,
                symbol=position.symbol,
                error=str(e)
            )
            return False

    def tighten_trailing_stop(
        self,
        position: Position,
        db: Session,
        new_trail_percent: float,
        current_price: float
    ) -> bool:
        """
        Tighten the trailing stop for a position.

        Cancels the existing stop order and places a new one with a tighter trail.
        Only tightens if the position is profitable.

        Args:
            position: Position to tighten stop for
            db: Database session
            new_trail_percent: New tighter trail percentage
            current_price: Current market price

        Returns:
            True if successful
        """
        try:
            symbol = position.symbol

            # Check if position is profitable
            pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100
            if pnl_pct <= 0:
                logger.info(
                    "skip_tighten_not_profitable",
                    symbol=symbol,
                    pnl_pct=pnl_pct
                )
                return False

            # Cancel existing stop order
            existing_orders = alpaca_client.get_open_orders(symbol)
            stop_orders = [o for o in existing_orders if o['type'] in ['stop', 'trailing_stop']]

            for stop_order in stop_orders:
                try:
                    alpaca_client.cancel_order(stop_order['id'])
                    logger.info(
                        "cancelled_stop_for_tightening",
                        symbol=symbol,
                        order_id=stop_order['id'],
                        old_type=stop_order['type']
                    )
                    import time
                    time.sleep(0.5)  # Brief pause after cancel
                except Exception as e:
                    logger.warning(
                        "failed_to_cancel_stop_for_tightening",
                        symbol=symbol,
                        error=str(e)
                    )

            # Place new tighter stop
            is_fractional = position.quantity != int(position.quantity)

            if settings.use_trailing_stops and not is_fractional:
                order = alpaca_client.place_trailing_stop_order(
                    symbol=symbol,
                    qty=position.quantity,
                    trail_percent=new_trail_percent,
                    side="sell"
                )
                order_type = "trailing_stop"
            else:
                # Use regular stop for fractional shares
                # Calculate stop price based on current price (not entry)
                stop_price = current_price * (1 - new_trail_percent / 100)
                order = alpaca_client.place_stop_order(
                    symbol=symbol,
                    qty=position.quantity,
                    stop_price=round(stop_price, 2),
                    side="sell"
                )
                order_type = "stop"

            # Update position
            position.alpaca_stop_order_id = str(order['id'])
            position.stop_loss = current_price * (1 - new_trail_percent / 100)
            db.commit()

            logger.info(
                "trailing_stop_tightened",
                symbol=symbol,
                position_id=position.id,
                old_trail_pct=settings.trailing_stop_pct,
                new_trail_pct=new_trail_percent,
                current_price=current_price,
                pnl_pct=pnl_pct,
                order_type=order_type
            )

            return True

        except Exception as e:
            logger.error(
                "failed_to_tighten_trailing_stop",
                symbol=position.symbol,
                error=str(e)
            )
            return False

    def refresh_trailing_stops_for_fractional_shares(self, db: Session) -> int:
        """
        Refresh trailing stop orders for positions with fractional shares.

        Fractional share orders must be DAY orders, so they need to be
        re-placed each day at market open.

        Args:
            db: Database session

        Returns:
            Number of trailing stops refreshed
        """
        count = 0
        try:
            # Get all open positions
            positions = db.query(Position).filter(
                Position.status == PositionStatus.OPEN
            ).all()

            for position in positions:
                # Check if fractional shares
                is_fractional = position.quantity != int(position.quantity)
                if not is_fractional:
                    continue

                # Cancel existing stop order if any
                if position.alpaca_stop_order_id:
                    try:
                        alpaca_client.cancel_order(position.alpaca_stop_order_id)
                        logger.info(
                            "cancelled_expired_stop_order",
                            symbol=position.symbol,
                            order_id=position.alpaca_stop_order_id
                        )
                    except Exception:
                        pass  # Order may have already expired or filled
                    position.alpaca_stop_order_id = None

                # Place new trailing stop
                if self.add_trailing_stop_to_position(position, db):
                    count += 1

            logger.info(
                "fractional_trailing_stops_refreshed",
                positions_checked=len(positions),
                stops_refreshed=count
            )
            return count

        except Exception as e:
            logger.error("failed_to_refresh_trailing_stops", error=str(e))
            return count

    def ensure_all_positions_have_trailing_stops(self, db: Session) -> int:
        """
        Ensure all open positions have trailing stop orders on Alpaca.

        Returns:
            Number of trailing stop orders placed
        """
        count = 0
        try:
            # Get all open positions
            positions = db.query(Position).filter(
                Position.status == PositionStatus.OPEN
            ).all()

            for position in positions:
                # Check if position already has a stop order on Alpaca
                existing_orders = alpaca_client.get_open_orders(position.symbol)
                stop_orders = [o for o in existing_orders if o['type'] in ['stop', 'trailing_stop']]

                if stop_orders:
                    # Update position with order ID if not set
                    if not position.alpaca_stop_order_id:
                        position.alpaca_stop_order_id = str(stop_orders[0]['id'])
                        db.commit()
                    continue

                # Try to add trailing stop
                if self.add_trailing_stop_to_position(position, db):
                    count += 1

            logger.info("trailing_stops_ensured", positions_checked=len(positions), stops_added=count)
            return count

        except Exception as e:
            logger.error("failed_to_ensure_trailing_stops", error=str(e))
            return count


# Global order executor instance
order_executor = OrderExecutor()
