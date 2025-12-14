"""
Portfolio tracking and management.
Maintains portfolio snapshots and calculates performance metrics.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import structlog
from sqlalchemy.orm import Session

from src.api.alpaca_client import alpaca_client
from src.database.models import Position, PortfolioSnapshot, PositionStatus
from config.settings import settings

logger = structlog.get_logger(__name__)


class PortfolioTracker:
    """
    Tracks portfolio state and performance.
    """

    def __init__(self):
        self.last_snapshot_value = None

    def get_current_state(self) -> Dict[str, Any]:
        """
        Get current portfolio state from Alpaca.

        Returns:
            Dict with portfolio information
        """
        try:
            account = alpaca_client.get_account()
            positions = alpaca_client.get_positions()

            positions_value = sum(pos['market_value'] for pos in positions)

            return {
                "total_value": account['portfolio_value'],
                "cash": account['cash'],
                "positions_value": positions_value,
                "equity": account['equity'],
                "buying_power": account['buying_power'],
                "position_count": len(positions),
                "positions": positions
            }

        except Exception as e:
            logger.error("failed_to_get_portfolio_state", error=str(e))
            return {}

    def save_snapshot(self, db: Session) -> Optional[PortfolioSnapshot]:
        """
        Save current portfolio snapshot to database.

        Args:
            db: Database session

        Returns:
            PortfolioSnapshot object or None
        """
        try:
            state = self.get_current_state()

            if not state:
                logger.error("no_state_to_snapshot")
                return None

            # Get previous snapshot for daily return calculation
            prev_snapshot = db.query(PortfolioSnapshot).order_by(
                PortfolioSnapshot.timestamp.desc()
            ).first()

            daily_return_pct = None
            total_return_pct = None

            if prev_snapshot:
                daily_return_pct = (
                    (state['total_value'] - prev_snapshot.total_value) /
                    prev_snapshot.total_value
                ) * 100

                # Get first snapshot for total return
                first_snapshot = db.query(PortfolioSnapshot).order_by(
                    PortfolioSnapshot.timestamp.asc()
                ).first()

                if first_snapshot:
                    total_return_pct = (
                        (state['total_value'] - first_snapshot.total_value) /
                        first_snapshot.total_value
                    ) * 100

            # Count open positions
            open_positions = db.query(Position).filter(
                Position.status == PositionStatus.OPEN
            ).count()

            # Calculate exposure
            exposure_pct = 0.0
            if state['total_value'] > 0:
                exposure_pct = (state['positions_value'] / state['total_value']) * 100

            # Create snapshot
            snapshot = PortfolioSnapshot(
                timestamp=datetime.utcnow(),
                total_value=state['total_value'],
                cash=state['cash'],
                positions_value=state['positions_value'],
                daily_return_pct=daily_return_pct,
                total_return_pct=total_return_pct,
                position_count=state['position_count'],
                open_positions_count=open_positions,
                portfolio_exposure_pct=exposure_pct,
                positions_snapshot=state.get('positions', [])
            )

            db.add(snapshot)
            db.commit()

            self.last_snapshot_value = state['total_value']

            logger.info(
                "portfolio_snapshot_saved",
                total_value=state['total_value'],
                cash=state['cash'],
                positions_value=state['positions_value'],
                daily_return_pct=daily_return_pct,
                position_count=state['position_count']
            )

            return snapshot

        except Exception as e:
            logger.error("failed_to_save_snapshot", error=str(e))
            db.rollback()
            return None

    def get_performance_summary(self, db: Session, days: int = 7) -> Dict[str, Any]:
        """
        Get performance summary for the last N days.

        Args:
            db: Database session
            days: Number of days to look back

        Returns:
            Performance summary dict
        """
        try:
            # Get recent snapshots
            snapshots = db.query(PortfolioSnapshot).order_by(
                PortfolioSnapshot.timestamp.desc()
            ).limit(days).all()

            if not snapshots:
                return {}

            snapshots.reverse()  # Oldest first

            # Calculate metrics
            start_value = snapshots[0].total_value
            end_value = snapshots[-1].total_value
            period_return_pct = ((end_value - start_value) / start_value) * 100

            # Average daily return
            daily_returns = [
                s.daily_return_pct for s in snapshots
                if s.daily_return_pct is not None
            ]
            avg_daily_return = sum(daily_returns) / len(daily_returns) if daily_returns else 0

            # Count trades
            total_positions = db.query(Position).count()
            open_positions = db.query(Position).filter(
                Position.status == PositionStatus.OPEN
            ).count()
            closed_positions = db.query(Position).filter(
                Position.status == PositionStatus.CLOSED
            ).count()

            # Calculate win rate
            winning_positions = db.query(Position).filter(
                Position.status == PositionStatus.CLOSED,
                Position.exit_price > Position.entry_price
            ).count()

            win_rate = (winning_positions / closed_positions * 100) if closed_positions > 0 else 0

            return {
                "period_days": days,
                "start_value": start_value,
                "end_value": end_value,
                "period_return_pct": period_return_pct,
                "avg_daily_return_pct": avg_daily_return,
                "total_positions": total_positions,
                "open_positions": open_positions,
                "closed_positions": closed_positions,
                "winning_positions": winning_positions,
                "win_rate_pct": win_rate,
            }

        except Exception as e:
            logger.error("failed_to_get_performance_summary", error=str(e))
            return {}


# Global portfolio tracker instance
portfolio_tracker = PortfolioTracker()
