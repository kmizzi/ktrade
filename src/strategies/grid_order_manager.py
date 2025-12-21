"""
Grid Order Manager for multi-order grid trading.
Handles order lifecycle and state persistence for grid strategies.
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path
import structlog

from src.api.alpaca_client import alpaca_client

logger = structlog.get_logger(__name__)


class GridLevel:
    """Represents a single grid level with its order state."""

    def __init__(
        self,
        level: int,
        price: float,
        order_type: str,  # 'buy' or 'sell'
        order_id: Optional[str] = None,
        status: str = "pending",
        filled_qty: float = 0,
        filled_price: Optional[float] = None
    ):
        self.level = level  # Negative for buy levels, positive for sell levels
        self.price = price
        self.order_type = order_type
        self.order_id = order_id
        self.status = status  # pending, open, filled, cancelled
        self.filled_qty = filled_qty
        self.filled_price = filled_price

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "price": self.price,
            "order_type": self.order_type,
            "order_id": self.order_id,
            "status": self.status,
            "filled_qty": self.filled_qty,
            "filled_price": self.filled_price
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GridLevel":
        return cls(
            level=data["level"],
            price=data["price"],
            order_type=data["order_type"],
            order_id=data.get("order_id"),
            status=data.get("status", "pending"),
            filled_qty=data.get("filled_qty", 0),
            filled_price=data.get("filled_price")
        )


class GridState:
    """State for a single symbol's grid."""

    def __init__(
        self,
        symbol: str,
        center_price: float,
        qty_per_level: float,
        levels: Optional[List[GridLevel]] = None,
        total_invested: float = 0,
        realized_profit: float = 0,
        status: str = "active",  # active, stopped, paused
        last_updated: Optional[datetime] = None
    ):
        self.symbol = symbol
        self.center_price = center_price
        self.qty_per_level = qty_per_level
        self.levels = levels or []
        self.total_invested = total_invested
        self.realized_profit = realized_profit
        self.status = status
        self.last_updated = last_updated or datetime.utcnow()

    def get_level(self, level_num: int) -> Optional[GridLevel]:
        """Get a specific grid level by number."""
        for level in self.levels:
            if level.level == level_num:
                return level
        return None

    def get_open_orders(self) -> List[GridLevel]:
        """Get all levels with open orders."""
        return [l for l in self.levels if l.status == "open"]

    def get_filled_buys(self) -> List[GridLevel]:
        """Get all filled buy orders (positions we hold)."""
        return [l for l in self.levels if l.order_type == "buy" and l.status == "filled"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "center_price": self.center_price,
            "qty_per_level": self.qty_per_level,
            "levels": [l.to_dict() for l in self.levels],
            "total_invested": self.total_invested,
            "realized_profit": self.realized_profit,
            "status": self.status,
            "last_updated": self.last_updated.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GridState":
        levels = [GridLevel.from_dict(l) for l in data.get("levels", [])]
        last_updated = None
        if data.get("last_updated"):
            last_updated = datetime.fromisoformat(data["last_updated"])
        return cls(
            symbol=data["symbol"],
            center_price=data["center_price"],
            qty_per_level=data.get("qty_per_level", 0),
            levels=levels,
            total_invested=data.get("total_invested", 0),
            realized_profit=data.get("realized_profit", 0),
            status=data.get("status", "active"),
            last_updated=last_updated
        )


class GridOrderManager:
    """
    Manages grid order lifecycle and state persistence.

    Handles:
    - Placing limit orders at grid levels
    - Tracking order fills
    - Replacing filled orders (buy filled -> place sell, sell filled -> place buy)
    - Persisting state to JSON file
    """

    STATE_FILE = "data/grid_state.json"

    def __init__(self):
        self.grids: Dict[str, GridState] = {}
        self._ensure_data_dir()
        self.load_state()

    def _ensure_data_dir(self):
        """Ensure data directory exists."""
        Path("data").mkdir(exist_ok=True)

    def save_state(self) -> None:
        """Save all grid states to file."""
        try:
            state = {
                symbol: grid.to_dict()
                for symbol, grid in self.grids.items()
            }
            with open(self.STATE_FILE, 'w') as f:
                json.dump(state, f, indent=2)
            logger.debug("grid_state_saved", symbols=list(self.grids.keys()))
        except Exception as e:
            logger.error("failed_to_save_grid_state", error=str(e))

    def load_state(self) -> None:
        """Load grid states from file."""
        try:
            if os.path.exists(self.STATE_FILE):
                with open(self.STATE_FILE, 'r') as f:
                    state = json.load(f)
                self.grids = {
                    symbol: GridState.from_dict(data)
                    for symbol, data in state.items()
                }
                logger.info(
                    "grid_state_loaded",
                    symbols=list(self.grids.keys()),
                    grids_count=len(self.grids)
                )
            else:
                logger.info("no_existing_grid_state")
        except Exception as e:
            logger.error("failed_to_load_grid_state", error=str(e))
            self.grids = {}

    def initialize_grid(
        self,
        symbol: str,
        center_price: float,
        spacing_pct: float,
        num_levels: int,
        qty_per_level: float
    ) -> GridState:
        """
        Initialize a new grid for a symbol.

        Args:
            symbol: Trading symbol (e.g., 'BTC/USD')
            center_price: Grid center price
            spacing_pct: Spacing between levels as percentage
            num_levels: Number of levels above and below center
            qty_per_level: Quantity to trade at each level

        Returns:
            Initialized GridState
        """
        levels = []

        # Create buy levels (below center)
        for i in range(1, num_levels + 1):
            price = center_price * (1 - (spacing_pct / 100) * i)
            levels.append(GridLevel(
                level=-i,
                price=round(price, 2),
                order_type="buy",
                status="pending"
            ))

        # Create sell levels (above center)
        for i in range(1, num_levels + 1):
            price = center_price * (1 + (spacing_pct / 100) * i)
            levels.append(GridLevel(
                level=i,
                price=round(price, 2),
                order_type="sell",
                status="pending"
            ))

        grid = GridState(
            symbol=symbol,
            center_price=center_price,
            qty_per_level=qty_per_level,
            levels=levels,
            status="active"
        )

        self.grids[symbol] = grid
        self.save_state()

        logger.info(
            "grid_initialized",
            symbol=symbol,
            center_price=center_price,
            num_levels=num_levels,
            spacing_pct=spacing_pct,
            qty_per_level=qty_per_level
        )

        return grid

    def place_grid_orders(self, symbol: str) -> int:
        """
        Place limit orders for all pending buy levels.

        Only places buy orders initially - sell orders are placed
        when corresponding buy orders fill.

        Args:
            symbol: Symbol to place orders for

        Returns:
            Number of orders placed
        """
        grid = self.grids.get(symbol)
        if not grid or grid.status != "active":
            return 0

        orders_placed = 0

        for level in grid.levels:
            # Only place pending buy orders initially
            if level.status == "pending" and level.order_type == "buy":
                try:
                    order = alpaca_client.place_limit_order(
                        symbol=symbol,
                        qty=grid.qty_per_level,
                        limit_price=level.price,
                        side="buy",
                        time_in_force="gtc",
                        client_order_id=f"grid_{symbol}_{level.level}"
                    )

                    level.order_id = str(order['id'])
                    level.status = "open"
                    orders_placed += 1

                    logger.info(
                        "grid_buy_order_placed",
                        symbol=symbol,
                        level=level.level,
                        price=level.price,
                        qty=grid.qty_per_level,
                        order_id=level.order_id
                    )

                except Exception as e:
                    logger.error(
                        "failed_to_place_grid_order",
                        symbol=symbol,
                        level=level.level,
                        error=str(e)
                    )

        grid.last_updated = datetime.utcnow()
        self.save_state()

        return orders_placed

    def check_and_update_orders(self, symbol: str) -> Dict[str, int]:
        """
        Check all open orders for fills and update accordingly.

        For filled buy orders: Place corresponding sell order
        For filled sell orders: Place new buy order at that level

        Args:
            symbol: Symbol to check

        Returns:
            Dict with counts of fills and new orders placed
        """
        grid = self.grids.get(symbol)
        if not grid or grid.status != "active":
            return {"buys_filled": 0, "sells_filled": 0, "orders_placed": 0}

        results = {"buys_filled": 0, "sells_filled": 0, "orders_placed": 0}

        # Get all open orders from Alpaca
        try:
            open_orders = alpaca_client.get_open_orders(symbol)
            open_order_ids = {str(o['id']) for o in open_orders}
        except Exception as e:
            logger.error("failed_to_get_open_orders", symbol=symbol, error=str(e))
            return results

        for level in grid.levels:
            if level.status != "open" or not level.order_id:
                continue

            # Check if order is still open
            if level.order_id not in open_order_ids:
                # Order is no longer open - check if filled
                try:
                    order = alpaca_client.get_order(level.order_id)
                    if order['status'] == 'filled':
                        level.status = "filled"
                        level.filled_qty = order['filled_qty']
                        level.filled_price = order['filled_avg_price']

                        if level.order_type == "buy":
                            results["buys_filled"] += 1
                            grid.total_invested += level.filled_price * level.filled_qty

                            # Place corresponding sell order at next level up
                            sell_level = level.level + 1
                            sell_price = grid.center_price * (1 + (2.0 / 100) * sell_level)

                            try:
                                sell_order = alpaca_client.place_limit_order(
                                    symbol=symbol,
                                    qty=level.filled_qty,
                                    limit_price=round(sell_price, 2),
                                    side="sell",
                                    time_in_force="gtc",
                                    client_order_id=f"grid_{symbol}_sell_{level.level}"
                                )

                                # Add or update sell level
                                existing_sell = grid.get_level(sell_level)
                                if existing_sell:
                                    existing_sell.order_id = str(sell_order['id'])
                                    existing_sell.status = "open"
                                else:
                                    grid.levels.append(GridLevel(
                                        level=sell_level,
                                        price=round(sell_price, 2),
                                        order_type="sell",
                                        order_id=str(sell_order['id']),
                                        status="open"
                                    ))

                                results["orders_placed"] += 1
                                logger.info(
                                    "grid_sell_order_placed_after_buy_fill",
                                    symbol=symbol,
                                    buy_level=level.level,
                                    sell_level=sell_level,
                                    sell_price=round(sell_price, 2)
                                )

                            except Exception as e:
                                logger.error(
                                    "failed_to_place_sell_after_buy",
                                    symbol=symbol,
                                    level=level.level,
                                    error=str(e)
                                )

                        elif level.order_type == "sell":
                            results["sells_filled"] += 1
                            # Calculate profit
                            profit = (level.filled_price - grid.center_price) * level.filled_qty
                            grid.realized_profit += profit
                            grid.total_invested -= level.filled_price * level.filled_qty

                            # Place new buy order at original buy level
                            buy_level = level.level - 1
                            buy_price = grid.center_price * (1 - (2.0 / 100) * abs(buy_level))

                            try:
                                buy_order = alpaca_client.place_limit_order(
                                    symbol=symbol,
                                    qty=grid.qty_per_level,
                                    limit_price=round(buy_price, 2),
                                    side="buy",
                                    time_in_force="gtc",
                                    client_order_id=f"grid_{symbol}_rebuy_{buy_level}"
                                )

                                # Update original buy level to reopen
                                original_buy = grid.get_level(buy_level)
                                if original_buy:
                                    original_buy.order_id = str(buy_order['id'])
                                    original_buy.status = "open"
                                    original_buy.filled_qty = 0
                                    original_buy.filled_price = None

                                results["orders_placed"] += 1
                                logger.info(
                                    "grid_buy_order_placed_after_sell_fill",
                                    symbol=symbol,
                                    sell_level=level.level,
                                    buy_level=buy_level,
                                    buy_price=round(buy_price, 2),
                                    profit=profit
                                )

                            except Exception as e:
                                logger.error(
                                    "failed_to_place_buy_after_sell",
                                    symbol=symbol,
                                    level=level.level,
                                    error=str(e)
                                )

                    elif order['status'] in ['canceled', 'cancelled', 'expired']:
                        level.status = "cancelled"
                        logger.info(
                            "grid_order_cancelled",
                            symbol=symbol,
                            level=level.level,
                            order_id=level.order_id
                        )

                except Exception as e:
                    logger.error(
                        "failed_to_check_order_status",
                        symbol=symbol,
                        order_id=level.order_id,
                        error=str(e)
                    )

        grid.last_updated = datetime.utcnow()
        self.save_state()

        if results["buys_filled"] > 0 or results["sells_filled"] > 0:
            logger.info(
                "grid_orders_updated",
                symbol=symbol,
                **results,
                realized_profit=grid.realized_profit
            )

        return results

    def cancel_all_orders(self, symbol: str) -> int:
        """
        Cancel all open grid orders for a symbol.

        Args:
            symbol: Symbol to cancel orders for

        Returns:
            Number of orders cancelled
        """
        grid = self.grids.get(symbol)
        if not grid:
            return 0

        cancelled = 0

        for level in grid.levels:
            if level.status == "open" and level.order_id:
                try:
                    alpaca_client.cancel_order(level.order_id)
                    level.status = "cancelled"
                    cancelled += 1
                    logger.info(
                        "grid_order_cancelled",
                        symbol=symbol,
                        level=level.level,
                        order_id=level.order_id
                    )
                except Exception as e:
                    logger.error(
                        "failed_to_cancel_grid_order",
                        symbol=symbol,
                        order_id=level.order_id,
                        error=str(e)
                    )

        grid.status = "stopped"
        grid.last_updated = datetime.utcnow()
        self.save_state()

        return cancelled

    def stop_grid(self, symbol: str) -> Dict[str, Any]:
        """
        Stop a grid by cancelling all orders and closing positions.

        Args:
            symbol: Symbol to stop grid for

        Returns:
            Summary of actions taken
        """
        grid = self.grids.get(symbol)
        if not grid:
            return {"error": "Grid not found"}

        # Cancel all open orders
        cancelled = self.cancel_all_orders(symbol)

        # Close any positions from filled buys
        filled_buys = grid.get_filled_buys()
        positions_closed = 0

        if filled_buys:
            try:
                # Check if we have a position in Alpaca
                positions = alpaca_client.get_positions()
                for pos in positions:
                    if pos['symbol'] == symbol:
                        alpaca_client.close_position(symbol)
                        positions_closed = 1
                        logger.info("grid_position_closed", symbol=symbol)
                        break
            except Exception as e:
                logger.error("failed_to_close_grid_position", symbol=symbol, error=str(e))

        grid.status = "stopped"
        self.save_state()

        return {
            "orders_cancelled": cancelled,
            "positions_closed": positions_closed,
            "realized_profit": grid.realized_profit
        }

    def get_grid_status(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get current status of a grid."""
        grid = self.grids.get(symbol)
        if not grid:
            return None

        open_buys = len([l for l in grid.levels if l.order_type == "buy" and l.status == "open"])
        open_sells = len([l for l in grid.levels if l.order_type == "sell" and l.status == "open"])
        filled_buys = len([l for l in grid.levels if l.order_type == "buy" and l.status == "filled"])

        return {
            "symbol": symbol,
            "status": grid.status,
            "center_price": grid.center_price,
            "open_buy_orders": open_buys,
            "open_sell_orders": open_sells,
            "filled_positions": filled_buys,
            "total_invested": grid.total_invested,
            "realized_profit": grid.realized_profit,
            "last_updated": grid.last_updated.isoformat() if grid.last_updated else None
        }

    def recenter_grid(
        self,
        symbol: str,
        new_center: float,
        spacing_pct: float,
        num_levels: int
    ) -> bool:
        """
        Recenter a grid around a new price.

        Cancels existing orders and creates new grid levels.

        Args:
            symbol: Symbol to recenter
            new_center: New center price
            spacing_pct: Grid spacing percentage
            num_levels: Number of levels

        Returns:
            True if successful
        """
        grid = self.grids.get(symbol)
        if not grid:
            return False

        logger.info(
            "recentering_grid",
            symbol=symbol,
            old_center=grid.center_price,
            new_center=new_center
        )

        # Cancel all existing orders
        self.cancel_all_orders(symbol)

        # Reinitialize grid with new center
        self.initialize_grid(
            symbol=symbol,
            center_price=new_center,
            spacing_pct=spacing_pct,
            num_levels=num_levels,
            qty_per_level=grid.qty_per_level
        )

        # Place new orders
        self.place_grid_orders(symbol)

        return True


# Global grid order manager instance
grid_order_manager = GridOrderManager()
