"""
Grid trading service for fetching grid status and history.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc

from src.strategies.grid_order_manager import grid_order_manager, GridState
from src.database.models import GridOrderExecution, GridOrderType, GridOrderStatus
from config.settings import settings


class GridService:
    """Service for grid trading data operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_all_grids(self) -> List[Dict[str, Any]]:
        """Get status of all active grids."""
        grids = []
        for symbol, grid in grid_order_manager.grids.items():
            status = grid_order_manager.get_grid_status(symbol)
            if status:
                # Add level details
                status["levels"] = self._get_levels_summary(grid)
                status["qty_per_level"] = grid.qty_per_level
                grids.append(status)
        return grids

    def get_grid_status(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get detailed status for a specific grid."""
        grid = grid_order_manager.grids.get(symbol)
        if not grid:
            return None

        status = grid_order_manager.get_grid_status(symbol)
        if status:
            status["levels"] = self._get_levels_detail(grid)
            status["qty_per_level"] = grid.qty_per_level
            status["config"] = self._get_grid_config()
        return status

    def _get_levels_summary(self, grid: GridState) -> Dict[str, Any]:
        """Get summary of grid levels."""
        buy_levels = [l for l in grid.levels if l.order_type == "buy"]
        sell_levels = [l for l in grid.levels if l.order_type == "sell"]

        return {
            "buy_levels": len(buy_levels),
            "sell_levels": len(sell_levels),
            "lowest_buy": min((l.price for l in buy_levels), default=0),
            "highest_sell": max((l.price for l in sell_levels), default=0),
        }

    def _get_levels_detail(self, grid: GridState) -> List[Dict[str, Any]]:
        """Get detailed level information."""
        levels = []
        for level in sorted(grid.levels, key=lambda l: l.level):
            levels.append({
                "level": level.level,
                "price": level.price,
                "order_type": level.order_type,
                "status": level.status,
                "order_id": level.order_id,
                "filled_qty": level.filled_qty,
                "filled_price": level.filled_price,
            })
        return levels

    def _get_grid_config(self) -> Dict[str, Any]:
        """Get current grid configuration from settings."""
        return {
            "enabled": settings.enable_grid_trading,
            "spacing_pct": settings.grid_spacing_pct,
            "num_levels": settings.grid_levels,
            "symbols": settings.grid_symbols.split(","),
            "allocation_pct": settings.grid_allocation_pct,
            "boundary_stop_pct": settings.grid_boundary_stop_pct,
            "recenter_threshold_pct": settings.grid_recenter_threshold_pct,
            "check_interval_minutes": settings.grid_check_interval_minutes,
        }

    def get_grid_config(self) -> Dict[str, Any]:
        """Get grid trading configuration."""
        return self._get_grid_config()

    def get_grid_summary(self) -> Dict[str, Any]:
        """Get overall grid trading summary."""
        grids = self.get_all_grids()

        total_invested = sum(g.get("total_invested", 0) for g in grids)
        total_profit = sum(g.get("realized_profit", 0) for g in grids)
        active_grids = len([g for g in grids if g.get("status") == "active"])
        total_open_orders = sum(
            g.get("open_buy_orders", 0) + g.get("open_sell_orders", 0)
            for g in grids
        )

        return {
            "active_grids": active_grids,
            "total_grids": len(grids),
            "total_invested": total_invested,
            "realized_profit": total_profit,
            "total_open_orders": total_open_orders,
            "config": self._get_grid_config(),
        }

    def get_order_history(
        self,
        symbol: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get grid order execution history from database."""
        query = self.db.query(GridOrderExecution)

        if symbol:
            query = query.filter(GridOrderExecution.symbol == symbol)

        orders = (
            query
            .order_by(desc(GridOrderExecution.timestamp))
            .limit(limit)
            .all()
        )

        return [
            {
                "id": o.id,
                "symbol": o.symbol,
                "timestamp": o.timestamp.isoformat() if o.timestamp else None,
                "grid_level": o.grid_level,
                "order_type": o.order_type.value if o.order_type else None,
                "order_status": o.order_status.value if o.order_status else None,
                "limit_price": float(o.limit_price) if o.limit_price else None,
                "quantity": float(o.quantity) if o.quantity else None,
                "filled_price": float(o.filled_price) if o.filled_price else None,
                "filled_quantity": float(o.filled_quantity) if o.filled_quantity else None,
                "filled_at": o.filled_at.isoformat() if o.filled_at else None,
                "realized_profit": float(o.realized_profit) if o.realized_profit else None,
                "cumulative_profit": float(o.cumulative_profit) if o.cumulative_profit else None,
            }
            for o in orders
        ]

    def get_profit_history(
        self,
        symbol: Optional[str] = None,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get profit history for grid trading."""
        cutoff = datetime.utcnow() - timedelta(days=days)

        query = (
            self.db.query(GridOrderExecution)
            .filter(GridOrderExecution.timestamp >= cutoff)
            .filter(GridOrderExecution.order_status == GridOrderStatus.FILLED)
            .filter(GridOrderExecution.realized_profit.isnot(None))
        )

        if symbol:
            query = query.filter(GridOrderExecution.symbol == symbol)

        orders = query.order_by(GridOrderExecution.timestamp).all()

        # Aggregate by day
        daily_profit: Dict[str, float] = {}
        for order in orders:
            if order.timestamp:
                day = order.timestamp.strftime("%Y-%m-%d")
                daily_profit[day] = daily_profit.get(day, 0) + float(order.realized_profit or 0)

        return [
            {"date": date, "profit": profit}
            for date, profit in sorted(daily_profit.items())
        ]

    def get_current_prices(self) -> Dict[str, float]:
        """Get current prices for grid symbols."""
        from src.api.alpaca_client import alpaca_client

        prices = {}
        config = self._get_grid_config()

        for symbol in config["symbols"]:
            symbol = symbol.strip()
            if not symbol:
                continue
            try:
                quote = alpaca_client.get_latest_quote(symbol)
                if quote:
                    prices[symbol] = float(quote.get("ask_price") or quote.get("price", 0))
            except Exception:
                prices[symbol] = 0

        return prices
