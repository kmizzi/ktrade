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

    def get_recent_trades(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most recent trades."""
        trades = (
            self.db.query(Trade)
            .order_by(desc(Trade.filled_at))
            .limit(limit)
            .all()
        )
        return [self._trade_to_dict(t) for t in trades]

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
        return [self.get_strategy_metrics(s) for s in strategies]

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
                "win_rate": 0,
                "total_pnl": 0,
                "avg_pnl": 0,
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
