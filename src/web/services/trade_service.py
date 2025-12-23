"""
Trade service for fetching trade history and strategy performance.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from collections import defaultdict

from src.database.models import Trade, Position, Signal, TradeSide, PositionStatus


class TradeService:
    """Service for trade data operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_trades(
        self,
        limit: int = 50,
        offset: int = 0,
        strategy: Optional[str] = None,
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get trades with optional filters."""
        query = self.db.query(Trade).join(Position, Trade.position_id == Position.id, isouter=True)

        if strategy:
            query = query.filter(Position.strategy == strategy)
        if symbol:
            query = query.filter(Trade.symbol == symbol)

        trades = (
            query
            .order_by(desc(Trade.filled_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

        return [self._trade_to_dict(t) for t in trades]

    def get_recent_trades(self, limit: int = 10, group_fills: bool = True) -> List[Dict[str, Any]]:
        """Get most recent trades, optionally grouping fills from same order."""
        # Fetch more trades to allow for grouping
        trades = (
            self.db.query(Trade)
            .order_by(desc(Trade.filled_at))
            .limit(limit * 3 if group_fills else limit)
            .all()
        )

        if not group_fills:
            return [self._trade_to_dict(t) for t in trades[:limit]]

        # Group trades by symbol, side, price, and time window (same minute)
        grouped = []
        seen_keys = set()

        for trade in trades:
            # Create grouping key: symbol + side + price + minute
            time_key = trade.filled_at.strftime("%Y-%m-%d %H:%M") if trade.filled_at else ""
            group_key = f"{trade.symbol}|{trade.side.value if trade.side else ''}|{float(trade.price):.2f}|{time_key}"

            if group_key in seen_keys:
                # Find existing group and add to it
                for g in grouped:
                    if g.get("_group_key") == group_key:
                        g["quantity"] += float(trade.quantity) if trade.quantity else 0
                        g["total_value"] += float(trade.quantity * trade.price) if trade.quantity and trade.price else 0
                        g["fill_count"] += 1
                        break
            else:
                seen_keys.add(group_key)
                trade_dict = self._trade_to_dict(trade)
                trade_dict["_group_key"] = group_key
                trade_dict["fill_count"] = 1
                grouped.append(trade_dict)

            if len(grouped) >= limit:
                break

        # Remove internal group key
        for g in grouped:
            g.pop("_group_key", None)

        return grouped[:limit]

    def get_trades_by_strategy(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get trades grouped by strategy."""
        trades = (
            self.db.query(Trade, Position.strategy)
            .join(Position, Trade.position_id == Position.id)
            .order_by(desc(Trade.filled_at))
            .limit(500)
            .all()
        )

        result = defaultdict(list)
        for trade, strategy in trades:
            result[strategy or "unknown"].append(self._trade_to_dict(trade))

        return dict(result)

    def get_trades_by_symbol(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get trades grouped by symbol."""
        trades = (
            self.db.query(Trade)
            .order_by(desc(Trade.filled_at))
            .limit(500)
            .all()
        )

        result = defaultdict(list)
        for trade in trades:
            result[trade.symbol or "unknown"].append(self._trade_to_dict(trade))

        return dict(result)

    def get_strategies(self) -> List[str]:
        """List all unique strategies."""
        strategies = (
            self.db.query(Position.strategy)
            .distinct()
            .filter(Position.strategy.isnot(None))
            .all()
        )
        return [s[0] for s in strategies]

    def get_strategy_performance(self) -> List[Dict[str, Any]]:
        """Get performance metrics for all strategies."""
        strategies = self.get_strategies()

        # Map confusing strategy names to clearer labels
        name_map = {
            "synced": "Imported",
            "unknown": "Manual Trades",
            "": "Uncategorized",
            None: "Uncategorized",
        }

        results = []
        for s in strategies:
            metrics = self.get_strategy_metrics(s)
            # Skip strategies with 0 trades (nothing useful to show)
            if metrics["total_trades"] == 0:
                continue
            # Rename confusing strategy names
            if metrics["strategy"] in name_map:
                metrics["strategy"] = name_map[metrics["strategy"]]
            results.append(metrics)

        # Sort by total trades (most active first)
        results.sort(key=lambda x: x["total_trades"], reverse=True)
        return results

    def get_strategy_metrics(self, strategy_name: str) -> Dict[str, Any]:
        """Get performance metrics for a single strategy."""
        # Get closed positions for this strategy
        positions = (
            self.db.query(Position)
            .filter(Position.strategy == strategy_name)
            .filter(Position.status == PositionStatus.CLOSED)
            .all()
        )

        total_trades = len(positions)
        if total_trades == 0:
            return {
                "strategy": strategy_name,
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0,
                "total_pnl": 0,
                "avg_pnl": 0,
                "signals_generated": 0,
                "signals_executed": 0,
                "execution_rate": 0,
            }

        wins = sum(1 for p in positions if p.pnl and p.pnl > 0)
        total_pnl = sum(float(p.pnl or 0) for p in positions)

        # Get signals for execution rate
        signals = (
            self.db.query(Signal)
            .filter(Signal.strategy == strategy_name)
            .all()
        )
        total_signals = len(signals)
        executed_signals = sum(1 for s in signals if s.executed)
        execution_rate = (executed_signals / total_signals * 100) if total_signals > 0 else 0

        return {
            "strategy": strategy_name,
            "total_trades": total_trades,
            "wins": wins,
            "losses": total_trades - wins,
            "win_rate": round(wins / total_trades * 100, 1),
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(total_pnl / total_trades, 2),
            "signals_generated": total_signals,
            "signals_executed": executed_signals,
            "execution_rate": round(execution_rate, 1),
        }

    def get_strategy_comparison(self) -> Dict[str, Any]:
        """Get strategy comparison data for charts."""
        strategies = self.get_strategies()
        metrics = [self.get_strategy_metrics(s) for s in strategies]

        return {
            "labels": [m["strategy"] for m in metrics],
            "win_rates": [m["win_rate"] for m in metrics],
            "total_pnl": [m["total_pnl"] for m in metrics],
            "trade_counts": [m["total_trades"] for m in metrics],
        }

    def _trade_to_dict(self, trade: Trade) -> Dict[str, Any]:
        """Convert Trade model to dictionary."""
        return {
            "id": trade.id,
            "symbol": trade.symbol,
            "side": trade.side.value if trade.side else None,
            "quantity": float(trade.quantity) if trade.quantity else 0,
            "price": float(trade.price) if trade.price else 0,
            "total_value": float(trade.quantity * trade.price) if trade.quantity and trade.price else 0,
            "filled_at": trade.filled_at.isoformat() if trade.filled_at else None,
            "position_id": trade.position_id,
            "notes": trade.notes,
        }
