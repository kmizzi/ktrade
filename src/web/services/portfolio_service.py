"""
Portfolio service for fetching account and position data.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc

from src.database.models import Position, Trade, PortfolioSnapshot, PositionStatus
from src.api.alpaca_client import alpaca_client
from config.settings import settings


class PortfolioService:
    """Service for portfolio data operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_summary(self) -> Dict[str, Any]:
        """Get portfolio summary with live data from Alpaca."""
        try:
            account = alpaca_client.get_account()
            positions = alpaca_client.get_positions()

            # Calculate position values
            positions_value = sum(float(p.get("market_value", 0)) for p in positions)
            daily_pnl = sum(float(p.get("unrealized_intraday_pl", 0)) for p in positions)

            return {
                "portfolio_value": float(account.get("equity", 0)),
                "cash": float(account.get("cash", 0)),
                "positions_value": positions_value,
                "daily_pnl": daily_pnl,
                "daily_pnl_pct": (daily_pnl / float(account.get("last_equity", 1))) * 100 if account.get("last_equity") else 0,
                "open_positions": len(positions),
                "buying_power": float(account.get("buying_power", 0)),
            }
        except Exception as e:
            return {
                "portfolio_value": 0,
                "cash": 0,
                "positions_value": 0,
                "daily_pnl": 0,
                "daily_pnl_pct": 0,
                "open_positions": 0,
                "buying_power": 0,
                "error": str(e),
            }

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Calculate performance metrics from portfolio snapshots."""
        try:
            # Get snapshots from last 30 days
            cutoff = datetime.utcnow() - timedelta(days=30)
            snapshots = (
                self.db.query(PortfolioSnapshot)
                .filter(PortfolioSnapshot.timestamp >= cutoff)
                .order_by(desc(PortfolioSnapshot.timestamp))
                .all()
            )

            if not snapshots:
                return {"error": "No performance data available"}

            # Calculate metrics
            first = snapshots[-1] if snapshots else None
            last = snapshots[0] if snapshots else None

            total_return = 0
            if first and last and first.total_value > 0:
                total_return = ((last.total_value - first.total_value) / first.total_value) * 100

            # Get closed positions for win rate
            closed_positions = (
                self.db.query(Position)
                .filter(Position.status == PositionStatus.CLOSED)
                .filter(Position.exit_date >= cutoff)
                .all()
            )

            wins = sum(1 for p in closed_positions if p.pnl and p.pnl > 0)
            total = len(closed_positions)
            win_rate = (wins / total * 100) if total > 0 else 0

            return {
                "total_return": round(total_return, 2),
                "win_rate": round(win_rate, 1),
                "total_trades": total,
                "winning_trades": wins,
                "losing_trades": total - wins,
            }
        except Exception as e:
            return {"error": str(e)}

    def get_equity_curve(self) -> Dict[str, Any]:
        """Get equity curve data for charting."""
        try:
            snapshots = (
                self.db.query(PortfolioSnapshot)
                .order_by(PortfolioSnapshot.timestamp)
                .limit(365)
                .all()
            )

            labels = [s.timestamp.strftime("%m/%d") for s in snapshots]
            values = [float(s.total_value) if s.total_value else 0 for s in snapshots]

            return {
                "labels": labels,
                "values": values,
            }
        except Exception as e:
            return {"labels": [], "values": [], "error": str(e)}

    def get_snapshots(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Get historical portfolio snapshots."""
        snapshots = (
            self.db.query(PortfolioSnapshot)
            .order_by(desc(PortfolioSnapshot.timestamp))
            .limit(limit)
            .all()
        )

        return [
            {
                "timestamp": s.timestamp.isoformat(),
                "total_value": float(s.total_value) if s.total_value else 0,
                "cash": float(s.cash) if s.cash else 0,
                "positions_value": float(s.positions_value) if s.positions_value else 0,
                "daily_return_pct": float(s.daily_return_pct) if s.daily_return_pct else 0,
                "position_count": s.position_count or 0,
            }
            for s in snapshots
        ]

    def get_exposure(self) -> Dict[str, Any]:
        """Get current portfolio exposure breakdown."""
        try:
            account = alpaca_client.get_account()
            positions = alpaca_client.get_positions()

            portfolio_value = float(account.get("equity", 0))
            positions_value = sum(float(p.get("market_value", 0)) for p in positions)

            exposure_pct = (positions_value / portfolio_value * 100) if portfolio_value > 0 else 0

            # Breakdown by symbol
            breakdown = [
                {
                    "symbol": p.get("symbol"),
                    "value": float(p.get("market_value", 0)),
                    "pct": (float(p.get("market_value", 0)) / portfolio_value * 100) if portfolio_value > 0 else 0,
                }
                for p in positions
            ]

            return {
                "total_exposure_pct": round(exposure_pct, 1),
                "max_allowed_pct": settings.max_portfolio_exposure_pct,
                "breakdown": sorted(breakdown, key=lambda x: x["pct"], reverse=True),
            }
        except Exception as e:
            return {"error": str(e)}

    def get_open_positions(self) -> List[Dict[str, Any]]:
        """Get current open positions with live prices."""
        try:
            positions = alpaca_client.get_positions()

            return [
                {
                    "symbol": p.get("symbol"),
                    "quantity": float(p.get("qty", 0)),
                    "entry_price": float(p.get("avg_entry_price", 0)),
                    "current_price": float(p.get("current_price", 0)),
                    "market_value": float(p.get("market_value", 0)),
                    "pnl": float(p.get("unrealized_pl", 0)),
                    "pnl_pct": float(p.get("unrealized_plpc", 0)) * 100,
                }
                for p in positions
            ]
        except Exception as e:
            return []

    def get_positions(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get positions from database with filters."""
        query = self.db.query(Position)

        if status:
            if status.lower() == "open":
                query = query.filter(Position.status == PositionStatus.OPEN)
            elif status.lower() == "closed":
                query = query.filter(Position.status == PositionStatus.CLOSED)

        positions = (
            query
            .order_by(desc(Position.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

        return [
            {
                "id": p.id,
                "symbol": p.symbol,
                "quantity": float(p.quantity) if p.quantity else 0,
                "entry_price": float(p.entry_price) if p.entry_price else 0,
                "exit_price": float(p.exit_price) if p.exit_price else None,
                "entry_date": p.entry_date.isoformat() if p.entry_date else None,
                "exit_date": p.exit_date.isoformat() if p.exit_date else None,
                "strategy": p.strategy,
                "status": p.status.value if p.status else None,
                "pnl": float(p.pnl) if p.pnl else None,
                "pnl_pct": float(p.pnl_pct) if p.pnl_pct else None,
            }
            for p in positions
        ]

    def get_position(self, position_id: int) -> Optional[Dict[str, Any]]:
        """Get single position detail."""
        position = self.db.query(Position).filter(Position.id == position_id).first()
        if not position:
            return None

        return {
            "id": position.id,
            "symbol": position.symbol,
            "quantity": float(position.quantity) if position.quantity else 0,
            "entry_price": float(position.entry_price) if position.entry_price else 0,
            "exit_price": float(position.exit_price) if position.exit_price else None,
            "entry_date": position.entry_date.isoformat() if position.entry_date else None,
            "exit_date": position.exit_date.isoformat() if position.exit_date else None,
            "strategy": position.strategy,
            "confidence_score": float(position.confidence_score) if position.confidence_score else None,
            "stop_loss": float(position.stop_loss) if position.stop_loss else None,
            "status": position.status.value if position.status else None,
            "notes": position.notes,
        }

    def get_position_trades(self, position_id: int) -> List[Dict[str, Any]]:
        """Get trades for a specific position."""
        trades = (
            self.db.query(Trade)
            .filter(Trade.position_id == position_id)
            .order_by(Trade.filled_at)
            .all()
        )

        return [
            {
                "id": t.id,
                "side": t.side.value if t.side else None,
                "quantity": float(t.quantity) if t.quantity else 0,
                "price": float(t.price) if t.price else 0,
                "filled_at": t.filled_at.isoformat() if t.filled_at else None,
            }
            for t in trades
        ]
