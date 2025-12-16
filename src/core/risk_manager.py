"""
Risk management module.
Validates trades against risk limits and portfolio constraints.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import structlog
from sqlalchemy.orm import Session

from config.settings import settings
from src.database.models import Position, PortfolioSnapshot, PositionStatus
from src.api.alpaca_client import alpaca_client

logger = structlog.get_logger(__name__)


class RiskManager:
    """
    Manages risk controls for the trading bot.

    Risk Controls:
    - Position size limits
    - Portfolio exposure limits
    - Daily loss limits
    - Stop loss enforcement
    """

    def __init__(self):
        self.max_position_size_pct = settings.max_position_size_pct
        self.max_portfolio_exposure_pct = settings.max_portfolio_exposure_pct
        self.daily_loss_limit_pct = settings.daily_loss_limit_pct
        self.default_stop_loss_pct = settings.default_stop_loss_pct
        self.take_profit_pct = settings.take_profit_pct

        # Track daily performance
        self._daily_start_value = None
        self._daily_trades_halted = False

    def can_open_position(
        self,
        symbol: str,
        quantity: float,
        price: float,
        db: Session
    ) -> tuple[bool, Optional[str]]:
        """
        Check if a position can be opened.

        Args:
            symbol: Symbol to trade
            quantity: Quantity to buy
            price: Current price
            db: Database session

        Returns:
            Tuple of (can_trade: bool, reason: str)
        """
        try:
            # Get account info
            account = alpaca_client.get_account()
            portfolio_value = account['portfolio_value']
            cash = account['cash']

            # Calculate position value
            position_value = quantity * price

            # Check 1: Sufficient cash
            if position_value > cash:
                return False, f"Insufficient cash (need ${position_value:.2f}, have ${cash:.2f})"

            # Check 2: Position size limit
            position_size_pct = (position_value / portfolio_value) * 100
            if position_size_pct > self.max_position_size_pct:
                return False, (
                    f"Position size too large ({position_size_pct:.1f}% > "
                    f"{self.max_position_size_pct:.1f}%)"
                )

            # Check 3: Portfolio exposure limit
            current_exposure = self._calculate_portfolio_exposure(portfolio_value)
            new_exposure = current_exposure + position_size_pct

            if new_exposure > self.max_portfolio_exposure_pct:
                return False, (
                    f"Portfolio exposure too high ({new_exposure:.1f}% > "
                    f"{self.max_portfolio_exposure_pct:.1f}%)"
                )

            # Check 4: Daily loss limit
            if self._is_daily_limit_exceeded(portfolio_value):
                return False, "Daily loss limit exceeded"

            # Check 5: Trading not halted
            if self._daily_trades_halted:
                return False, "Trading halted due to daily loss limit"

            return True, None

        except Exception as e:
            logger.error("error_checking_position_limit", symbol=symbol, error=str(e))
            return False, f"Error checking limits: {str(e)}"

    def calculate_position_size(
        self,
        symbol: str,
        price: float,
        confidence: float
    ) -> float:
        """
        Calculate optimal position size based on confidence and portfolio value.

        Args:
            symbol: Symbol to trade
            price: Current price
            confidence: Signal confidence (0.0 to 1.0)

        Returns:
            Position size in shares
        """
        try:
            account = alpaca_client.get_account()
            portfolio_value = account['portfolio_value']

            # Base position size from confidence
            # Higher confidence = larger position (up to max)
            target_pct = self.max_position_size_pct * confidence

            # Calculate target dollar amount
            target_value = (portfolio_value * target_pct) / 100

            # Calculate quantity
            quantity = target_value / price

            # Round down to whole shares if preferred (enables trailing stops on Alpaca)
            if settings.prefer_whole_shares:
                quantity = int(quantity)  # Floor to whole shares
            else:
                quantity = round(quantity, 2)  # Allow fractional shares

            logger.debug(
                "position_size_calculated",
                symbol=symbol,
                price=price,
                confidence=confidence,
                target_pct=target_pct,
                quantity=quantity
            )

            return quantity

        except Exception as e:
            logger.error("error_calculating_position_size", symbol=symbol, error=str(e))
            return 0.0

    def _calculate_portfolio_exposure(self, portfolio_value: float) -> float:
        """
        Calculate current portfolio exposure percentage.

        Args:
            portfolio_value: Total portfolio value

        Returns:
            Exposure percentage
        """
        try:
            positions = alpaca_client.get_positions()
            total_positions_value = sum(pos['market_value'] for pos in positions)

            exposure_pct = (total_positions_value / portfolio_value) * 100
            return exposure_pct

        except Exception as e:
            logger.error("error_calculating_exposure", error=str(e))
            return 0.0

    def _is_daily_limit_exceeded(self, current_portfolio_value: float) -> bool:
        """
        Check if daily loss limit has been exceeded.

        Args:
            current_portfolio_value: Current portfolio value

        Returns:
            True if limit exceeded
        """
        try:
            # Initialize daily start value if not set
            if self._daily_start_value is None:
                self._daily_start_value = current_portfolio_value
                logger.info(
                    "daily_start_value_set",
                    value=self._daily_start_value
                )
                return False

            # Calculate daily return
            daily_return_pct = (
                (current_portfolio_value - self._daily_start_value) /
                self._daily_start_value
            ) * 100

            if daily_return_pct <= -self.daily_loss_limit_pct:
                if not self._daily_trades_halted:
                    self._daily_trades_halted = True
                    logger.warning(
                        "daily_loss_limit_exceeded",
                        daily_return_pct=daily_return_pct,
                        limit_pct=self.daily_loss_limit_pct,
                        start_value=self._daily_start_value,
                        current_value=current_portfolio_value
                    )
                return True

            return False

        except Exception as e:
            logger.error("error_checking_daily_limit", error=str(e))
            return False

    def reset_daily_tracking(self) -> None:
        """Reset daily tracking (call at market open)"""
        try:
            account = alpaca_client.get_account()
            self._daily_start_value = account['portfolio_value']
            self._daily_trades_halted = False

            logger.info(
                "daily_tracking_reset",
                start_value=self._daily_start_value
            )

        except Exception as e:
            logger.error("error_resetting_daily_tracking", error=str(e))

    def should_close_position(
        self,
        position: Position,
        current_price: float
    ) -> tuple[bool, Optional[str]]:
        """
        Check if a position should be closed for risk management.

        Args:
            position: Position object
            current_price: Current market price

        Returns:
            Tuple of (should_close: bool, reason: str)
        """
        # Calculate P&L percentage
        pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100

        # Check stop loss
        if position.stop_loss and current_price <= position.stop_loss:
            return True, f"Stop loss hit (${current_price:.2f} <= ${position.stop_loss:.2f})"

        # Check default stop loss if none set
        if not position.stop_loss and pnl_pct <= -self.default_stop_loss_pct:
            return True, f"Default stop loss triggered ({pnl_pct:.2f}%)"

        # Check take profit (if explicitly set on position)
        if position.take_profit and current_price >= position.take_profit:
            return True, f"Take profit hit (${current_price:.2f} >= ${position.take_profit:.2f})"

        # Check take profit for fractional positions (can't use OCO orders on Alpaca)
        # Whole share positions use trailing stops on Alpaca, so skip them here
        is_fractional = position.quantity != int(position.quantity)
        if is_fractional and pnl_pct >= self.take_profit_pct:
            return True, f"Fractional position take profit ({pnl_pct:.1f}% >= {self.take_profit_pct}%)"

        return False, None

    def get_risk_metrics(self, db: Session) -> Dict[str, Any]:
        """
        Get current risk metrics.

        Args:
            db: Database session

        Returns:
            Dict of risk metrics
        """
        try:
            account = alpaca_client.get_account()
            portfolio_value = account['portfolio_value']

            # Get open positions count
            open_positions = db.query(Position).filter(
                Position.status == PositionStatus.OPEN
            ).count()

            # Calculate exposure
            exposure_pct = self._calculate_portfolio_exposure(portfolio_value)

            # Calculate daily return
            daily_return_pct = 0.0
            if self._daily_start_value:
                daily_return_pct = (
                    (portfolio_value - self._daily_start_value) /
                    self._daily_start_value
                ) * 100

            return {
                "portfolio_value": portfolio_value,
                "cash": account['cash'],
                "open_positions": open_positions,
                "exposure_pct": exposure_pct,
                "daily_return_pct": daily_return_pct,
                "daily_start_value": self._daily_start_value,
                "trades_halted": self._daily_trades_halted,
                "max_position_size_pct": self.max_position_size_pct,
                "max_exposure_pct": self.max_portfolio_exposure_pct,
                "daily_loss_limit_pct": self.daily_loss_limit_pct,
            }

        except Exception as e:
            logger.error("error_getting_risk_metrics", error=str(e))
            return {}


# Global risk manager instance
risk_manager = RiskManager()
