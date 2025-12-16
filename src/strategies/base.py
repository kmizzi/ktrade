"""
Abstract base class for trading strategies.
All strategies must implement this interface for consistency.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


class Signal:
    """Trading signal with metadata"""

    def __init__(
        self,
        symbol: str,
        signal_type: str,
        confidence: float,
        strategy_name: str,
        data_snapshot: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None
    ):
        self.symbol = symbol
        self.signal_type = signal_type  # 'buy', 'sell', 'hold'
        self.confidence = confidence  # 0.0 to 1.0
        self.strategy_name = strategy_name
        self.data_snapshot = data_snapshot or {}
        self.notes = notes
        self.timestamp = datetime.utcnow()

    def __repr__(self) -> str:
        return (
            f"<Signal({self.symbol}, {self.signal_type}, "
            f"confidence={self.confidence:.2f}, strategy={self.strategy_name})>"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert signal to dictionary"""
        return {
            "symbol": self.symbol,
            "signal_type": self.signal_type,
            "confidence": self.confidence,
            "strategy_name": self.strategy_name,
            "data_snapshot": self.data_snapshot,
            "notes": self.notes,
            "timestamp": self.timestamp.isoformat(),
        }


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.

    Subclasses must implement:
    - generate_signals(): Generate buy/sell signals for symbols
    - should_exit_position(): Determine if position should be closed
    """

    def __init__(self, name: str, enabled: bool = True):
        """
        Initialize strategy.

        Args:
            name: Strategy name
            enabled: Whether strategy is enabled
        """
        self.name = name
        self.enabled = enabled
        self.logger = structlog.get_logger(f"strategy.{name}")

    @abstractmethod
    def generate_signals(
        self,
        symbols: List[str],
        owned_symbols: Optional[List[str]] = None
    ) -> List[Signal]:
        """
        Generate trading signals for given symbols.

        Args:
            symbols: List of symbols to analyze
            owned_symbols: List of symbols currently owned (for SELL signal filtering)

        Returns:
            List of Signal objects
        """
        pass

    @abstractmethod
    def should_exit_position(
        self,
        symbol: str,
        entry_price: float,
        current_price: float,
        position_data: Optional[Dict[str, Any]] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Determine if position should be exited.

        Args:
            symbol: Position symbol
            entry_price: Entry price
            current_price: Current market price
            position_data: Additional position data

        Returns:
            Tuple of (should_exit: bool, reason: str)
        """
        pass

    def is_enabled(self) -> bool:
        """Check if strategy is enabled"""
        return self.enabled

    def enable(self) -> None:
        """Enable strategy"""
        self.enabled = True
        self.logger.info("strategy_enabled", strategy=self.name)

    def disable(self) -> None:
        """Disable strategy"""
        self.enabled = False
        self.logger.info("strategy_disabled", strategy=self.name)

    def log_signal(self, signal: Signal) -> None:
        """Log a generated signal"""
        self.logger.info(
            "signal_generated",
            symbol=signal.symbol,
            signal_type=signal.signal_type,
            confidence=signal.confidence,
            strategy=self.name
        )

    def _calculate_confidence(
        self,
        score: float,
        max_score: float = 100.0,
        min_confidence: float = 0.0,
        max_confidence: float = 1.0
    ) -> float:
        """
        Calculate confidence score normalized between min and max.

        Args:
            score: Raw score
            max_score: Maximum possible score
            min_confidence: Minimum confidence value
            max_confidence: Maximum confidence value

        Returns:
            Normalized confidence between min and max
        """
        normalized = score / max_score
        confidence = min_confidence + (normalized * (max_confidence - min_confidence))
        return max(min_confidence, min(max_confidence, confidence))

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name}, enabled={self.enabled})>"
