"""
Grid Trading Strategy for crypto markets.

Multi-order grid trading with limit orders at predefined price levels.
Optimized for 24/7 crypto markets (BTC/USD, ETH/USD).

Key features:
- Dynamic grid center based on 24h SMA
- Automatic order replacement when levels fill
- Boundary protection when price breaks range
- State persistence across restarts
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import structlog

from src.strategies.base import BaseStrategy, Signal
from src.strategies.grid_order_manager import grid_order_manager, GridState
from src.api.alpaca_client import alpaca_client
from src.data.indicators import calculate_sma
from config.settings import settings
import pandas as pd

logger = structlog.get_logger(__name__)


class GridTradingStrategy(BaseStrategy):
    """
    Multi-order grid trading strategy for crypto.

    Places limit orders at predetermined price levels:
    - BUY orders below the grid center
    - SELL orders above the grid center

    When a buy fills, a sell is placed at the next level up.
    When a sell fills, a new buy is placed at that level.
    This creates a "grid" that profits from price oscillation.
    """

    def __init__(self):
        super().__init__(name="grid_trading", enabled=settings.enable_grid_trading)

        # Configuration from settings
        self.spacing_pct = settings.grid_spacing_pct
        self.num_levels = settings.grid_levels
        self.grid_symbols = [s.strip() for s in settings.grid_symbols.split(",")]
        self.allocation_pct = settings.grid_allocation_pct
        self.boundary_stop_pct = settings.grid_boundary_stop_pct
        self.recenter_threshold_pct = settings.grid_recenter_threshold_pct

        self.logger.info(
            "grid_strategy_initialized",
            symbols=self.grid_symbols,
            spacing_pct=self.spacing_pct,
            num_levels=self.num_levels,
            allocation_pct=self.allocation_pct
        )

    def generate_signals(
        self,
        symbols: List[str],
        owned_symbols: Optional[List[str]] = None
    ) -> List[Signal]:
        """
        Grid strategy doesn't generate signals like other strategies.
        It manages orders directly through the GridOrderManager.

        This method is called for compatibility but returns empty list.
        Use run_grid_cycle() for actual grid management.
        """
        return []

    def should_exit_position(
        self,
        symbol: str,
        entry_price: float,
        current_price: float,
        position_data: Optional[Dict[str, Any]] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Grid positions are managed by sell orders, not exit signals.
        This is here for interface compatibility.
        """
        return False, None

    def run_grid_cycle(self) -> Dict[str, Any]:
        """
        Run a complete grid management cycle.

        This should be called periodically (e.g., every 5 minutes) to:
        1. Initialize grids for new symbols
        2. Check for filled orders and place replacements
        3. Check for boundary breaks and stop if needed
        4. Recenter grids if price moved too far

        Returns:
            Summary of actions taken
        """
        if not self.enabled:
            return {"status": "disabled"}

        results = {
            "timestamp": datetime.utcnow().isoformat(),
            "symbols": {},
            "errors": []
        }

        for symbol in self.grid_symbols:
            try:
                symbol_result = self._manage_symbol_grid(symbol)
                results["symbols"][symbol] = symbol_result
            except Exception as e:
                self.logger.error(
                    "grid_cycle_error",
                    symbol=symbol,
                    error=str(e)
                )
                results["errors"].append({"symbol": symbol, "error": str(e)})

        return results

    def _manage_symbol_grid(self, symbol: str) -> Dict[str, Any]:
        """
        Manage grid for a single symbol.

        Args:
            symbol: Trading symbol (e.g., 'BTC/USD')

        Returns:
            Summary of actions for this symbol
        """
        result = {"action": None, "details": {}}

        # Get current price
        current_price = self._get_current_price(symbol)
        if not current_price:
            result["action"] = "error"
            result["details"]["error"] = "Could not get current price"
            return result

        # Check if grid exists
        grid_status = grid_order_manager.get_grid_status(symbol)

        if not grid_status or grid_status["status"] == "stopped":
            # Initialize new grid
            result = self._initialize_new_grid(symbol, current_price)
        else:
            # Check boundary break
            if self._check_boundary_break(symbol, current_price):
                result["action"] = "boundary_stop"
                stop_result = grid_order_manager.stop_grid(symbol)
                result["details"] = stop_result
                self.logger.warning(
                    "grid_boundary_break",
                    symbol=symbol,
                    current_price=current_price,
                    center_price=grid_status["center_price"]
                )
                return result

            # Check if recenter needed
            if self._check_recenter_needed(symbol, current_price):
                result["action"] = "recenter"
                new_center = self._calculate_grid_center(symbol)
                if new_center:
                    grid_order_manager.recenter_grid(
                        symbol=symbol,
                        new_center=new_center,
                        spacing_pct=self.spacing_pct,
                        num_levels=self.num_levels
                    )
                    result["details"]["new_center"] = new_center
                return result

            # Normal cycle - check and update orders
            result["action"] = "update"
            update_result = grid_order_manager.check_and_update_orders(symbol)
            result["details"] = update_result

        return result

    def _initialize_new_grid(self, symbol: str, current_price: float) -> Dict[str, Any]:
        """
        Initialize a new grid for a symbol.

        Args:
            symbol: Trading symbol
            current_price: Current market price

        Returns:
            Result summary
        """
        result = {"action": "initialize", "details": {}}

        # Calculate grid center (24h SMA or current price if not enough data)
        center_price = self._calculate_grid_center(symbol)
        if not center_price:
            center_price = current_price

        # Calculate quantity per level based on allocation
        qty_per_level = self._calculate_qty_per_level(symbol, center_price)

        if qty_per_level <= 0:
            result["details"]["error"] = "Insufficient allocation for grid"
            return result

        # Initialize grid
        grid_order_manager.initialize_grid(
            symbol=symbol,
            center_price=center_price,
            spacing_pct=self.spacing_pct,
            num_levels=self.num_levels,
            qty_per_level=qty_per_level
        )

        # Place initial buy orders
        orders_placed = grid_order_manager.place_grid_orders(symbol)

        result["details"] = {
            "center_price": center_price,
            "qty_per_level": qty_per_level,
            "orders_placed": orders_placed
        }

        self.logger.info(
            "grid_initialized",
            symbol=symbol,
            center_price=center_price,
            qty_per_level=qty_per_level,
            orders_placed=orders_placed
        )

        return result

    def _calculate_grid_center(self, symbol: str) -> Optional[float]:
        """
        Calculate grid center using 24h SMA.

        Args:
            symbol: Trading symbol

        Returns:
            Center price or None
        """
        try:
            # Get 24 hours of hourly bars - must specify time range for crypto
            end = datetime.utcnow()
            start = end - timedelta(hours=24)
            bars = alpaca_client.get_bars(
                symbol=symbol,
                timeframe="1Hour",
                start=start,
                end=end,
                limit=24
            )

            if not bars or len(bars) < 12:  # Need at least 12 hours
                return None

            # Calculate SMA
            prices = pd.Series([bar['close'] for bar in bars])
            sma = prices.mean()

            return round(sma, 2)

        except Exception as e:
            self.logger.error(
                "failed_to_calculate_grid_center",
                symbol=symbol,
                error=str(e)
            )
            return None

    def _calculate_qty_per_level(self, symbol: str, center_price: float) -> float:
        """
        Calculate quantity to trade at each grid level.

        Args:
            symbol: Trading symbol
            center_price: Grid center price

        Returns:
            Quantity per level
        """
        try:
            # Get account info
            account = alpaca_client.get_account()
            portfolio_value = account['portfolio_value']

            # Total allocation for grid
            grid_allocation = portfolio_value * (self.allocation_pct / 100)

            # Divide by number of levels (only buy side)
            allocation_per_level = grid_allocation / self.num_levels

            # Calculate quantity
            qty = allocation_per_level / center_price

            # Round appropriately for crypto
            if 'BTC' in symbol:
                qty = round(qty, 4)  # BTC to 4 decimals
            elif 'ETH' in symbol:
                qty = round(qty, 3)  # ETH to 3 decimals
            else:
                qty = round(qty, 2)

            return qty

        except Exception as e:
            self.logger.error(
                "failed_to_calculate_qty",
                symbol=symbol,
                error=str(e)
            )
            return 0

    def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol."""
        try:
            # Must specify time range for crypto to get recent data
            end = datetime.utcnow()
            start = end - timedelta(hours=1)
            bars = alpaca_client.get_bars(symbol, timeframe="1Min", start=start, end=end, limit=10)
            if bars:
                return bars[-1]['close']
            return None
        except Exception as e:
            self.logger.error("failed_to_get_price", symbol=symbol, error=str(e))
            return None

    def _check_boundary_break(self, symbol: str, current_price: float) -> bool:
        """
        Check if price has broken grid boundaries.

        Args:
            symbol: Trading symbol
            current_price: Current price

        Returns:
            True if boundary is broken
        """
        grid_status = grid_order_manager.get_grid_status(symbol)
        if not grid_status:
            return False

        center_price = grid_status["center_price"]
        boundary_pct = self.boundary_stop_pct / 100

        # Calculate boundary prices
        upper_boundary = center_price * (1 + boundary_pct)
        lower_boundary = center_price * (1 - boundary_pct)

        return current_price > upper_boundary or current_price < lower_boundary

    def _check_recenter_needed(self, symbol: str, current_price: float) -> bool:
        """
        Check if grid should be recentered.

        Args:
            symbol: Trading symbol
            current_price: Current price

        Returns:
            True if recenter is needed
        """
        grid_status = grid_order_manager.get_grid_status(symbol)
        if not grid_status:
            return False

        center_price = grid_status["center_price"]
        threshold_pct = self.recenter_threshold_pct / 100

        deviation = abs(current_price - center_price) / center_price

        return deviation > threshold_pct

    def get_grid_summary(self) -> Dict[str, Any]:
        """
        Get summary of all grids.

        Returns:
            Dict with status of all managed grids
        """
        summary = {
            "enabled": self.enabled,
            "symbols": self.grid_symbols,
            "grids": {}
        }

        for symbol in self.grid_symbols:
            status = grid_order_manager.get_grid_status(symbol)
            if status:
                summary["grids"][symbol] = status

        return summary


# Global grid trading strategy instance
grid_trading_strategy = GridTradingStrategy()
