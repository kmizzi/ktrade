"""
Risk service for fetching risk metrics and monitoring.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc

from src.database.models import PortfolioSnapshot
from src.api.alpaca_client import alpaca_client
from config.settings import settings


class RiskService:
    """Service for risk data operations."""

    def __init__(self, db: Optional[Session]):
        self.db = db

    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current risk metrics with live data."""
        try:
            account = alpaca_client.get_account()
            positions = alpaca_client.get_positions()

            portfolio_value = float(account.get("equity", 0))
            last_equity = float(account.get("last_equity", portfolio_value))
            cash = float(account.get("cash", 0))

            # Calculate exposure
            positions_value = sum(float(p.get("market_value", 0)) for p in positions)
            exposure_pct = (positions_value / portfolio_value * 100) if portfolio_value > 0 else 0

            # Calculate daily P&L
            daily_pnl = portfolio_value - last_equity
            daily_pnl_pct = (daily_pnl / last_equity * 100) if last_equity > 0 else 0

            # Check position concentration
            max_position_pct = 0
            max_position_symbol = None
            max_position_value = 0
            for p in positions:
                pos_value = float(p.get("market_value", 0))
                pos_pct = (pos_value / portfolio_value * 100) if portfolio_value > 0 else 0
                if pos_pct > max_position_pct:
                    max_position_pct = pos_pct
                    max_position_symbol = p.get("symbol")
                    max_position_value = pos_value

            return {
                "portfolio_value": portfolio_value,
                "cash": cash,
                "positions_value": positions_value,
                "daily_pnl": daily_pnl,
                "daily_pnl_pct": round(daily_pnl_pct, 2),
                "daily_loss_limit_pct": settings.daily_loss_limit_pct,
                "daily_loss_ok": abs(daily_pnl_pct) < settings.daily_loss_limit_pct,
                "exposure_pct": round(exposure_pct, 1),
                "max_exposure_pct": settings.max_portfolio_exposure_pct,
                "exposure_ok": exposure_pct <= settings.max_portfolio_exposure_pct,
                "max_position_pct": round(max_position_pct, 1),
                "max_position_symbol": max_position_symbol,
                "max_position_value": max_position_value,
                "max_position_limit_pct": settings.max_position_size_pct,
                "position_concentration_ok": max_position_pct <= settings.max_position_size_pct,
                "position_count": len(positions),
            }
        except Exception as e:
            return {"error": str(e)}

    def get_limits(self) -> Dict[str, Any]:
        """Get current risk limits from settings."""
        return {
            "max_position_size_pct": settings.max_position_size_pct,
            "max_portfolio_exposure_pct": settings.max_portfolio_exposure_pct,
            "daily_loss_limit_pct": settings.daily_loss_limit_pct,
            "default_stop_loss_pct": settings.default_stop_loss_pct,
        }

    def get_check_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get risk check history from database."""
        # TODO: Implement with RiskCheckLog model
        return []

    def get_rejections(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get order rejections from database."""
        # TODO: Implement with OrderRejection model
        return []

    def get_daily_pnl(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get daily P&L history from portfolio snapshots."""
        if not self.db:
            return []

        cutoff = datetime.utcnow() - timedelta(days=days)
        snapshots = (
            self.db.query(PortfolioSnapshot)
            .filter(PortfolioSnapshot.timestamp >= cutoff)
            .order_by(PortfolioSnapshot.timestamp)
            .all()
        )

        return [
            {
                "date": s.timestamp.strftime("%Y-%m-%d"),
                "value": float(s.total_value) if s.total_value else 0,
                "return_pct": float(s.daily_return_pct) if s.daily_return_pct else 0,
            }
            for s in snapshots
        ]
