"""
Signal service for fetching signal history and generating new signals.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from src.database.models import Signal, SignalType


class SignalService:
    """Service for signal data operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_signals(
        self,
        limit: int = 50,
        offset: int = 0,
        strategy: Optional[str] = None,
        executed: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """Get signals with optional filters."""
        query = self.db.query(Signal)

        if strategy:
            query = query.filter(Signal.strategy == strategy)
        if executed is not None:
            query = query.filter(Signal.executed == executed)

        signals = (
            query
            .order_by(desc(Signal.timestamp))
            .offset(offset)
            .limit(limit)
            .all()
        )

        return [self._signal_to_dict(s) for s in signals]

    def get_recent_signals(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most recent signals."""
        # Get signals from the last 24 hours
        cutoff = datetime.utcnow() - timedelta(hours=24)
        signals = (
            self.db.query(Signal)
            .filter(Signal.timestamp >= cutoff)
            .order_by(desc(Signal.timestamp))
            .limit(limit)
            .all()
        )
        return [self._signal_to_dict(s) for s in signals]

    def generate_current_signals(self) -> List[Dict[str, Any]]:
        """Generate current trading signals using strategies."""
        try:
            # Import strategy classes
            from src.strategies.simple_momentum import SimpleMomentumStrategy
            from src.strategies.technical_breakout import TechnicalBreakoutStrategy

            signals = []

            # Generate signals from each strategy
            strategies = [
                SimpleMomentumStrategy(),
                TechnicalBreakoutStrategy(),
            ]

            for strategy in strategies:
                if not strategy.enabled:
                    continue
                try:
                    strategy_signals = strategy.generate_signals()
                    for signal in strategy_signals:
                        # Save to database
                        db_signal = Signal(
                            symbol=signal.symbol,
                            timestamp=signal.timestamp,
                            strategy=signal.strategy,
                            signal_type=signal.signal_type,
                            confidence=signal.confidence,
                            data_snapshot=signal.data_snapshot,
                            executed=False,
                        )
                        self.db.add(db_signal)
                        signals.append(self._signal_to_dict(db_signal))
                except Exception as e:
                    continue

            self.db.commit()
            return signals

        except Exception as e:
            return [{"error": str(e)}]

    def get_rejections(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get rejected signals (signals that weren't executed)."""
        signals = (
            self.db.query(Signal)
            .filter(Signal.executed == False)
            .filter(Signal.execution_notes.isnot(None))
            .order_by(desc(Signal.timestamp))
            .limit(limit)
            .all()
        )

        return [
            {
                **self._signal_to_dict(s),
                "rejection_reason": s.execution_notes,
            }
            for s in signals
        ]

    def get_rejection_stats(self) -> Dict[str, Any]:
        """Get rejection reason breakdown."""
        # Get counts of rejection reasons
        signals = (
            self.db.query(Signal)
            .filter(Signal.executed == False)
            .filter(Signal.execution_notes.isnot(None))
            .all()
        )

        reason_counts = {}
        for signal in signals:
            reason = signal.execution_notes or "unknown"
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        total = len(signals)

        return {
            "total_rejections": total,
            "by_reason": [
                {"reason": k, "count": v, "pct": round(v / total * 100, 1) if total > 0 else 0}
                for k, v in sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)
            ],
        }

    def _signal_to_dict(self, signal: Signal) -> Dict[str, Any]:
        """Convert Signal model to dictionary."""
        # Determine execution status
        if signal.executed:
            exec_status = "executed"
        elif signal.execution_notes:
            exec_status = "rejected"
        else:
            exec_status = "pending"

        return {
            "id": signal.id,
            "symbol": signal.symbol,
            "timestamp": signal.timestamp.isoformat() if signal.timestamp else None,
            "strategy": signal.strategy,
            "signal_type": signal.signal_type.value if signal.signal_type else None,
            "confidence": round(float(signal.confidence), 2) if signal.confidence else 0,
            "executed": signal.executed,
            "execution_status": exec_status,
            "rejection_reason": signal.execution_notes if not signal.executed else None,
            "execution_time": signal.execution_time.isoformat() if signal.execution_time else None,
            "data_snapshot": signal.data_snapshot,
        }
