"""
Simulated portfolio for backtesting.
Tracks positions, cash, and trade history.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class SimulatedPosition:
    """A simulated trading position."""
    symbol: str
    quantity: float
    entry_price: float
    entry_date: datetime
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    @property
    def cost_basis(self) -> float:
        """Total cost of position."""
        return self.quantity * self.entry_price

    def current_value(self, current_price: float) -> float:
        """Current market value."""
        return self.quantity * current_price

    def unrealized_pnl(self, current_price: float) -> float:
        """Unrealized profit/loss."""
        return self.current_value(current_price) - self.cost_basis

    def unrealized_pnl_pct(self, current_price: float) -> float:
        """Unrealized P&L as percentage."""
        if self.entry_price == 0:
            return 0
        return ((current_price - self.entry_price) / self.entry_price) * 100


@dataclass
class SimulatedTrade:
    """Record of a simulated trade."""
    timestamp: datetime
    symbol: str
    side: str  # 'buy' or 'sell'
    quantity: float
    price: float
    commission: float = 0.0
    reason: str = ""

    @property
    def total_value(self) -> float:
        """Total trade value."""
        return self.quantity * self.price

    @property
    def total_cost(self) -> float:
        """Total cost including commission."""
        return self.total_value + self.commission


@dataclass
class PortfolioSnapshot:
    """Point-in-time portfolio snapshot."""
    timestamp: datetime
    total_value: float
    cash: float
    positions_value: float
    positions_count: int
    daily_return_pct: float = 0.0


class SimulatedPortfolio:
    """
    Simulates a trading portfolio for backtesting.
    Tracks cash, positions, and trade history.
    """

    def __init__(
        self,
        initial_cash: float = 100000.0,
        commission_per_trade: float = 0.0,
        max_position_pct: float = 10.0
    ):
        """
        Initialize simulated portfolio.

        Args:
            initial_cash: Starting cash amount
            commission_per_trade: Commission per trade (default: 0 for Alpaca)
            max_position_pct: Max position size as % of portfolio
        """
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.commission = commission_per_trade
        self.max_position_pct = max_position_pct

        self.positions: Dict[str, SimulatedPosition] = {}
        self.trades: List[SimulatedTrade] = []
        self.snapshots: List[PortfolioSnapshot] = []

        self._previous_value = initial_cash

    def get_position(self, symbol: str) -> Optional[SimulatedPosition]:
        """Get position for a symbol."""
        return self.positions.get(symbol)

    def has_position(self, symbol: str) -> bool:
        """Check if we have a position in symbol."""
        return symbol in self.positions

    def get_owned_symbols(self) -> List[str]:
        """Get list of symbols we own."""
        return list(self.positions.keys())

    def positions_value(self, current_prices: Dict[str, float]) -> float:
        """Calculate total value of all positions."""
        total = 0.0
        for symbol, pos in self.positions.items():
            price = current_prices.get(symbol, pos.entry_price)
            total += pos.current_value(price)
        return total

    def total_value(self, current_prices: Dict[str, float]) -> float:
        """Calculate total portfolio value."""
        return self.cash + self.positions_value(current_prices)

    def calculate_position_size(
        self,
        symbol: str,
        price: float,
        current_prices: Dict[str, float]
    ) -> int:
        """
        Calculate appropriate position size.

        Args:
            symbol: Symbol to buy
            price: Current price
            current_prices: All current prices

        Returns:
            Number of shares to buy (whole shares)
        """
        portfolio_value = self.total_value(current_prices)
        max_position_value = portfolio_value * (self.max_position_pct / 100)

        # Use available cash or max position, whichever is smaller
        available = min(self.cash, max_position_value)

        # Calculate whole shares
        shares = int(available / price)
        return shares

    def buy(
        self,
        symbol: str,
        quantity: float,
        price: float,
        timestamp: datetime,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        reason: str = ""
    ) -> bool:
        """
        Execute a buy order.

        Args:
            symbol: Symbol to buy
            quantity: Number of shares
            price: Price per share
            timestamp: Trade timestamp
            stop_loss: Optional stop loss price
            take_profit: Optional take profit price
            reason: Reason for trade

        Returns:
            True if trade executed, False otherwise
        """
        total_cost = quantity * price + self.commission

        if total_cost > self.cash:
            logger.debug(
                "insufficient_cash",
                symbol=symbol,
                required=total_cost,
                available=self.cash
            )
            return False

        if symbol in self.positions:
            # Add to existing position (average up/down)
            existing = self.positions[symbol]
            new_qty = existing.quantity + quantity
            new_avg_price = (
                (existing.quantity * existing.entry_price) + (quantity * price)
            ) / new_qty
            existing.quantity = new_qty
            existing.entry_price = new_avg_price
            if stop_loss:
                existing.stop_loss = stop_loss
            if take_profit:
                existing.take_profit = take_profit
        else:
            # New position
            self.positions[symbol] = SimulatedPosition(
                symbol=symbol,
                quantity=quantity,
                entry_price=price,
                entry_date=timestamp,
                stop_loss=stop_loss,
                take_profit=take_profit
            )

        self.cash -= total_cost

        # Record trade
        trade = SimulatedTrade(
            timestamp=timestamp,
            symbol=symbol,
            side='buy',
            quantity=quantity,
            price=price,
            commission=self.commission,
            reason=reason
        )
        self.trades.append(trade)

        logger.debug(
            "backtest_buy",
            symbol=symbol,
            quantity=quantity,
            price=price,
            total_cost=total_cost
        )
        return True

    def sell(
        self,
        symbol: str,
        quantity: Optional[float],
        price: float,
        timestamp: datetime,
        reason: str = ""
    ) -> bool:
        """
        Execute a sell order.

        Args:
            symbol: Symbol to sell
            quantity: Shares to sell (None = sell all)
            price: Price per share
            timestamp: Trade timestamp
            reason: Reason for sale

        Returns:
            True if trade executed, False otherwise
        """
        if symbol not in self.positions:
            logger.debug("no_position_to_sell", symbol=symbol)
            return False

        position = self.positions[symbol]

        # Sell all if quantity not specified
        if quantity is None:
            quantity = position.quantity

        if quantity > position.quantity:
            quantity = position.quantity

        proceeds = quantity * price - self.commission
        self.cash += proceeds

        # Record trade
        trade = SimulatedTrade(
            timestamp=timestamp,
            symbol=symbol,
            side='sell',
            quantity=quantity,
            price=price,
            commission=self.commission,
            reason=reason
        )
        self.trades.append(trade)

        # Update or remove position
        if quantity >= position.quantity:
            del self.positions[symbol]
        else:
            position.quantity -= quantity

        logger.debug(
            "backtest_sell",
            symbol=symbol,
            quantity=quantity,
            price=price,
            proceeds=proceeds,
            reason=reason
        )
        return True

    def check_stop_loss(
        self,
        symbol: str,
        current_price: float,
        timestamp: datetime
    ) -> bool:
        """
        Check and execute stop loss if triggered.

        Returns:
            True if stop loss was triggered
        """
        if symbol not in self.positions:
            return False

        position = self.positions[symbol]

        if position.stop_loss and current_price <= position.stop_loss:
            pnl_pct = position.unrealized_pnl_pct(current_price)
            self.sell(
                symbol=symbol,
                quantity=None,
                price=current_price,
                timestamp=timestamp,
                reason=f"Stop loss triggered ({pnl_pct:.1f}%)"
            )
            return True
        return False

    def check_take_profit(
        self,
        symbol: str,
        current_price: float,
        timestamp: datetime
    ) -> bool:
        """
        Check and execute take profit if triggered.

        Returns:
            True if take profit was triggered
        """
        if symbol not in self.positions:
            return False

        position = self.positions[symbol]

        if position.take_profit and current_price >= position.take_profit:
            pnl_pct = position.unrealized_pnl_pct(current_price)
            self.sell(
                symbol=symbol,
                quantity=None,
                price=current_price,
                timestamp=timestamp,
                reason=f"Take profit triggered ({pnl_pct:.1f}%)"
            )
            return True
        return False

    def update_trailing_stop(
        self,
        symbol: str,
        current_price: float,
        trail_pct: float = 7.0
    ):
        """
        Update trailing stop based on current price.

        Args:
            symbol: Symbol to update
            current_price: Current market price
            trail_pct: Trailing stop percentage
        """
        if symbol not in self.positions:
            return

        position = self.positions[symbol]
        new_stop = current_price * (1 - trail_pct / 100)

        # Only update if new stop is higher (trailing up)
        if position.stop_loss is None or new_stop > position.stop_loss:
            position.stop_loss = new_stop

    def take_snapshot(
        self,
        timestamp: datetime,
        current_prices: Dict[str, float]
    ):
        """Record a portfolio snapshot."""
        total = self.total_value(current_prices)
        pos_value = self.positions_value(current_prices)

        # Calculate daily return
        daily_return = 0.0
        if self._previous_value > 0:
            daily_return = ((total - self._previous_value) / self._previous_value) * 100

        snapshot = PortfolioSnapshot(
            timestamp=timestamp,
            total_value=total,
            cash=self.cash,
            positions_value=pos_value,
            positions_count=len(self.positions),
            daily_return_pct=daily_return
        )
        self.snapshots.append(snapshot)
        self._previous_value = total

    def get_trade_summary(self) -> Dict[str, Any]:
        """Get summary of all trades."""
        if not self.trades:
            return {'total_trades': 0}

        buys = [t for t in self.trades if t.side == 'buy']
        sells = [t for t in self.trades if t.side == 'sell']

        return {
            'total_trades': len(self.trades),
            'buys': len(buys),
            'sells': len(sells),
            'total_buy_value': sum(t.total_value for t in buys),
            'total_sell_value': sum(t.total_value for t in sells),
            'total_commission': sum(t.commission for t in self.trades)
        }

    def reset(self):
        """Reset portfolio to initial state."""
        self.cash = self.initial_cash
        self.positions = {}
        self.trades = []
        self.snapshots = []
        self._previous_value = self.initial_cash
