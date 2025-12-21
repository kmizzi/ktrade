"""
Technical Breakout Strategy.

Identifies and trades breakouts above resistance levels with volume confirmation.
Follows PRD Strategy 5: Technical Breakout.

Entry Conditions (ALL required):
- Price breaks above 50-day high (resistance)
- Volume >= 1.5x 20-day average
- MACD line > Signal line with positive histogram

Exit Conditions (ANY triggers exit):
- Price breaks below 20-day low (support)
- Profit target reached (+8%)
- Failed breakout (price falls back below resistance)
- MACD bearish crossover
"""

from typing import List, Dict, Any, Optional
import pandas as pd
import structlog

from src.strategies.base import BaseStrategy, Signal
from src.api.alpaca_client import alpaca_client
from src.data.indicators import calculate_all_indicators, get_latest_indicators
from config.settings import settings

logger = structlog.get_logger(__name__)


class TechnicalBreakoutStrategy(BaseStrategy):
    """
    Technical breakout strategy that enters positions when price breaks
    above resistance with volume confirmation and MACD support.
    """

    def __init__(self, enabled: bool = None):
        if enabled is None:
            enabled = settings.enable_technical_breakout
        super().__init__(name="technical_breakout", enabled=enabled)

        # Breakout parameters
        self.resistance_period = settings.breakout_resistance_period
        self.support_period = settings.breakout_support_period
        self.volume_multiplier = settings.breakout_volume_multiplier
        self.volume_avg_period = 20

        # Exit parameters
        self.profit_target_pct = settings.breakout_profit_target_pct
        self.stop_loss_buffer_pct = 1.0  # Stop 1% below support

        # Confidence thresholds
        self.min_confidence = 0.65

        self.logger.info(
            "technical_breakout_strategy_initialized",
            resistance_period=self.resistance_period,
            support_period=self.support_period,
            volume_multiplier=self.volume_multiplier,
            profit_target_pct=self.profit_target_pct
        )

    def generate_signals(
        self,
        symbols: List[str],
        owned_symbols: Optional[List[str]] = None
    ) -> List[Signal]:
        """
        Generate breakout signals for given symbols.

        Args:
            symbols: List of symbols to analyze
            owned_symbols: Symbols already owned (for filtering)

        Returns:
            List of Signal objects
        """
        if not self.enabled:
            return []

        owned_symbols = owned_symbols or []
        signals = []

        for symbol in symbols:
            try:
                signal = self._evaluate_symbol(symbol, owned_symbols)
                if signal and signal.signal_type != 'hold':
                    self.log_signal(signal)
                    signals.append(signal)

            except Exception as e:
                self.logger.error(
                    "breakout_evaluation_failed",
                    symbol=symbol,
                    error=str(e)
                )

        return signals

    def _evaluate_symbol(
        self,
        symbol: str,
        owned_symbols: List[str]
    ) -> Optional[Signal]:
        """
        Evaluate a single symbol for breakout conditions.

        Args:
            symbol: Symbol to evaluate
            owned_symbols: List of currently owned symbols

        Returns:
            Signal object or None
        """
        # Skip crypto for this strategy (better suited for stocks)
        if "/" in symbol:
            return None

        # Get historical data
        bars = alpaca_client.get_bars(symbol, timeframe="1Day", limit=100)
        if not bars or len(bars) < self.resistance_period:
            self.logger.debug(
                "insufficient_data_for_breakout",
                symbol=symbol,
                bars=len(bars) if bars else 0
            )
            return None

        # Calculate indicators
        df = calculate_all_indicators(bars)
        indicators = get_latest_indicators(df)

        # Validate required indicators
        required = ['close', 'volume', 'macd', 'macd_signal', 'macd_hist']
        for ind in required:
            if indicators.get(ind) is None:
                self.logger.debug(
                    "missing_indicator",
                    symbol=symbol,
                    indicator=ind
                )
                return None

        # Check if we already own this symbol
        if symbol in owned_symbols:
            return self._evaluate_sell(symbol, df, indicators)
        else:
            return self._evaluate_buy(symbol, df, indicators)

    def _evaluate_buy(
        self,
        symbol: str,
        df: pd.DataFrame,
        indicators: Dict[str, Any]
    ) -> Optional[Signal]:
        """
        Evaluate buy conditions for breakout entry.

        Args:
            symbol: Symbol to evaluate
            df: DataFrame with price data
            indicators: Latest indicator values

        Returns:
            BUY signal if conditions met, None otherwise
        """
        current_price = indicators['close']
        current_volume = indicators['volume']

        # Calculate resistance and support levels
        resistance = df['close'].tail(self.resistance_period).max()
        support = df['close'].tail(self.support_period).min()
        volume_avg = df['volume'].tail(self.volume_avg_period).mean()

        # Check breakout conditions
        is_breakout = current_price > resistance
        volume_ratio = current_volume / volume_avg if volume_avg > 0 else 0
        volume_confirmed = volume_ratio >= self.volume_multiplier

        macd = indicators['macd']
        macd_signal = indicators['macd_signal']
        macd_hist = indicators['macd_hist']
        macd_bullish = macd > macd_signal and macd_hist > 0

        # Calculate confidence score (max 100 points)
        score = 0
        score_breakdown = []

        if is_breakout:
            score += 35
            score_breakdown.append("breakout:35")

        if volume_confirmed:
            score += 30
            score_breakdown.append(f"volume({volume_ratio:.1f}x):30")

        if macd_bullish:
            score += 25
            score_breakdown.append("macd:25")

        # Bonus for strength of breakout
        if is_breakout:
            breakout_pct = ((current_price - resistance) / resistance) * 100
            if breakout_pct > 1.0:
                score += 10
                score_breakdown.append(f"strong_breakout({breakout_pct:.1f}%):10")

        confidence = score / 100.0

        # All conditions must be met
        if is_breakout and volume_confirmed and macd_bullish and confidence >= self.min_confidence:
            return Signal(
                symbol=symbol,
                signal_type='buy',
                confidence=confidence,
                strategy_name=self.name,
                data_snapshot={
                    'price': current_price,
                    'resistance': resistance,
                    'support': support,
                    'volume_ratio': volume_ratio,
                    'macd': macd,
                    'macd_signal': macd_signal,
                    'macd_hist': macd_hist,
                    'score_breakdown': score_breakdown,
                },
                notes=f"Breakout above ${resistance:.2f}, volume {volume_ratio:.1f}x avg, MACD bullish"
            )

        return None

    def _evaluate_sell(
        self,
        symbol: str,
        df: pd.DataFrame,
        indicators: Dict[str, Any]
    ) -> Optional[Signal]:
        """
        Evaluate sell conditions for owned positions.

        Note: Primary exit logic is in should_exit_position().
        This generates SELL signals for momentum loss while still above support.

        Args:
            symbol: Symbol to evaluate
            df: DataFrame with price data
            indicators: Latest indicator values

        Returns:
            SELL signal if conditions warrant, None otherwise
        """
        current_price = indicators['close']
        resistance = df['close'].tail(self.resistance_period).max()

        macd = indicators['macd']
        macd_signal = indicators['macd_signal']

        # MACD bearish crossover while near resistance = weakening momentum
        if macd < macd_signal and current_price < resistance * 1.02:
            return Signal(
                symbol=symbol,
                signal_type='sell',
                confidence=0.7,
                strategy_name=self.name,
                data_snapshot={
                    'price': current_price,
                    'resistance': resistance,
                    'macd': macd,
                    'macd_signal': macd_signal,
                },
                notes=f"MACD bearish near resistance ${resistance:.2f}"
            )

        return None

    def should_exit_position(
        self,
        symbol: str,
        entry_price: float,
        current_price: float,
        position_data: Optional[Dict[str, Any]] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Determine if a breakout position should be exited.

        Exit conditions:
        1. Profit target reached (+8%)
        2. Price breaks below support
        3. Failed breakout (price back below resistance)
        4. MACD bearish crossover

        Args:
            symbol: Position symbol
            entry_price: Entry price
            current_price: Current price
            position_data: Additional position data

        Returns:
            Tuple of (should_exit, reason)
        """
        try:
            # Calculate P&L
            pnl_pct = ((current_price - entry_price) / entry_price) * 100

            # Check profit target
            if pnl_pct >= self.profit_target_pct:
                return True, f"Profit target reached ({pnl_pct:.2f}%)"

            # Get fresh data
            bars = alpaca_client.get_bars(symbol, timeframe="1Day", limit=100)
            if not bars or len(bars) < self.resistance_period:
                return False, None

            df = calculate_all_indicators(bars)
            indicators = get_latest_indicators(df)

            if not indicators:
                return False, None

            # Calculate dynamic support and resistance
            support = df['close'].tail(self.support_period).min()
            resistance = df['close'].tail(self.resistance_period).max()
            stop_price = support * (1 - self.stop_loss_buffer_pct / 100)

            # Check support breakdown
            if current_price < stop_price:
                return True, f"Support breakdown (below ${support:.2f})"

            # Check failed breakout - price falls back below resistance
            # Only check if we're in profit to avoid premature exit
            if pnl_pct < 0 and current_price < resistance * 0.99:
                return True, f"Failed breakout (below ${resistance:.2f})"

            # Check MACD reversal
            macd = indicators.get('macd')
            macd_signal = indicators.get('macd_signal')

            if macd is not None and macd_signal is not None:
                if macd < macd_signal and pnl_pct > 2:
                    # Only exit on MACD reversal if we have some profit
                    return True, f"MACD bearish crossover (locking {pnl_pct:.1f}% gain)"

            return False, None

        except Exception as e:
            self.logger.error(
                "breakout_exit_check_failed",
                symbol=symbol,
                error=str(e)
            )
            return False, None


# Global strategy instance
technical_breakout_strategy = TechnicalBreakoutStrategy()
