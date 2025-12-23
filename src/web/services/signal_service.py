"""
Signal service for fetching signal history and generating new signals.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from src.database.models import Signal as DBSignal, SignalType
from src.api.alpaca_client import alpaca_client
from config.settings import settings


class SignalService:
    """Service for signal data operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_signals(
        self,
        limit: int = 50,
        offset: int = 0,
        strategy: Optional[str] = None,
        executed: Optional[bool] = None,
        signal_type: Optional[str] = None,
        status: Optional[str] = None,
        symbol: Optional[str] = None,
        sort: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get signals with optional filters and sorting."""
        from sqlalchemy import asc

        query = self.db.query(DBSignal)

        # Apply filters
        if strategy:
            query = query.filter(DBSignal.strategy == strategy)
        if executed is not None:
            query = query.filter(DBSignal.executed == executed)
        if signal_type:
            query = query.filter(DBSignal.signal_type == SignalType(signal_type))
        if status == "executed":
            query = query.filter(DBSignal.executed == True)
        elif status == "rejected":
            query = query.filter(DBSignal.executed == False, DBSignal.execution_notes.isnot(None))
        elif status == "pending":
            query = query.filter(DBSignal.executed == False, DBSignal.execution_notes.is_(None))
        if symbol:
            query = query.filter(DBSignal.symbol == symbol)
        if search:
            query = query.filter(DBSignal.symbol.ilike(f"%{search}%"))

        # Apply sorting
        sort_map = {
            "time_desc": desc(DBSignal.timestamp),
            "time_asc": asc(DBSignal.timestamp),
            "symbol_asc": asc(DBSignal.symbol),
            "symbol_desc": desc(DBSignal.symbol),
            "confidence_desc": desc(DBSignal.confidence),
            "confidence_asc": asc(DBSignal.confidence),
        }
        order_by = sort_map.get(sort, desc(DBSignal.timestamp))

        signals = (
            query
            .order_by(order_by)
            .offset(offset)
            .limit(limit)
            .all()
        )

        return [self._signal_to_dict(s) for s in signals]

    def get_unique_symbols(self) -> List[str]:
        """Get list of unique signaled symbols."""
        symbols = (
            self.db.query(DBSignal.symbol)
            .distinct()
            .filter(DBSignal.symbol.isnot(None))
            .order_by(DBSignal.symbol)
            .all()
        )
        return [s[0] for s in symbols]

    def get_unique_strategies(self) -> List[str]:
        """Get list of unique strategies."""
        strategies = (
            self.db.query(DBSignal.strategy)
            .distinct()
            .filter(DBSignal.strategy.isnot(None))
            .order_by(DBSignal.strategy)
            .all()
        )
        return [s[0] for s in strategies]

    def get_recent_signals(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most recent signals."""
        # Get signals from the last 24 hours
        cutoff = datetime.utcnow() - timedelta(hours=24)
        signals = (
            self.db.query(DBSignal)
            .filter(DBSignal.timestamp >= cutoff)
            .order_by(desc(DBSignal.timestamp))
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

            # Get symbols to analyze from watchlist
            symbols = settings.get_full_watchlist()
            if not symbols:
                return []

            # Get currently owned symbols from Alpaca
            try:
                positions = alpaca_client.get_positions()
                owned_symbols = [p.get("symbol") for p in positions if p.get("symbol")]
            except Exception:
                owned_symbols = []

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
                    strategy_signals = strategy.generate_signals(
                        symbols=symbols,
                        owned_symbols=owned_symbols
                    )
                    for signal in strategy_signals:
                        # Convert string signal_type to SignalType enum
                        signal_type_enum = SignalType(signal.signal_type)

                        # Save to database
                        db_signal = DBSignal(
                            symbol=signal.symbol,
                            timestamp=signal.timestamp,
                            strategy=signal.strategy_name,  # Note: strategy_name not strategy
                            signal_type=signal_type_enum,
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
            self.db.query(DBSignal)
            .filter(DBSignal.executed == False)
            .filter(DBSignal.execution_notes.isnot(None))
            .order_by(desc(DBSignal.timestamp))
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
            self.db.query(DBSignal)
            .filter(DBSignal.executed == False)
            .filter(DBSignal.execution_notes.isnot(None))
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

    def _signal_to_dict(self, signal: DBSignal) -> Dict[str, Any]:
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
