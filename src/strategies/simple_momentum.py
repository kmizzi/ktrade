"""
Simple Momentum Strategy.

Buy Signal:
- Price > 20-day SMA
- RSI between 40 and 70 (not overbought/oversold)
- (Optional) Bullish Reddit/WSB sentiment boosts confidence

Sell Signal:
- RSI > 75 (overbought)
- Price < 20-day SMA (trend reversal)

Stop Loss: -5% from entry
"""

from typing import List, Dict, Any, Optional, Tuple
from src.strategies.base import BaseStrategy, Signal
from src.api.alpaca_client import alpaca_client
from src.data.indicators import calculate_all_indicators, get_latest_indicators
from config.settings import settings
import structlog

logger = structlog.get_logger(__name__)

# Lazy import for sentiment to avoid circular dependencies
_sentiment_analyzer = None


def _get_sentiment_analyzer():
    """Lazy load sentiment analyzer."""
    global _sentiment_analyzer
    if _sentiment_analyzer is None:
        try:
            from src.data.sentiment import sentiment_analyzer
            _sentiment_analyzer = sentiment_analyzer
        except ImportError:
            logger.debug("sentiment_analyzer_import_failed")
            _sentiment_analyzer = False
    return _sentiment_analyzer if _sentiment_analyzer else None


class SimpleMomentumStrategy(BaseStrategy):
    """
    Simple momentum-based trading strategy using RSI and SMA.
    """

    def __init__(self, enabled: bool = True):
        super().__init__(name="simple_momentum", enabled=enabled)

        # Strategy parameters
        self.rsi_buy_min = 40
        self.rsi_buy_max = 70
        self.rsi_sell_threshold = 75
        self.sma_period = 20
        self.min_confidence = 0.6
        self.stop_loss_pct = settings.default_stop_loss_pct

    def generate_signals(
        self,
        symbols: List[str],
        owned_symbols: Optional[List[str]] = None
    ) -> List[Signal]:
        """
        Generate buy/sell signals for given symbols.

        Args:
            symbols: List of symbols to analyze
            owned_symbols: List of symbols currently owned (SELL signals only for these)

        Returns:
            List of Signal objects
        """
        signals = []
        owned_set = set(owned_symbols or [])

        for symbol in symbols:
            try:
                # Get historical data
                bars = alpaca_client.get_bars(symbol, timeframe="1Day", limit=100)

                if not bars or len(bars) < 50:
                    self.logger.warning(
                        "insufficient_data",
                        symbol=symbol,
                        bars_count=len(bars) if bars else 0
                    )
                    continue

                # Calculate indicators
                df = calculate_all_indicators(bars)
                indicators = get_latest_indicators(df)

                # Check if we have required indicators
                if not all(key in indicators and indicators[key] is not None
                          for key in ['close', 'rsi', 'sma_20']):
                    self.logger.warning(
                        "missing_indicators",
                        symbol=symbol,
                        indicators=indicators
                    )
                    continue

                current_price = indicators['close']
                rsi = indicators['rsi']
                sma_20 = indicators['sma_20']

                # Generate signal
                signal = self._evaluate_symbol(
                    symbol, current_price, rsi, sma_20, indicators,
                    is_owned=(symbol in owned_set)
                )

                if signal and signal.signal_type != 'hold':
                    signals.append(signal)
                    self.log_signal(signal)

            except Exception as e:
                self.logger.error(
                    "failed_to_generate_signal",
                    symbol=symbol,
                    error=str(e)
                )

        return signals

    def _evaluate_symbol(
        self,
        symbol: str,
        current_price: float,
        rsi: float,
        sma_20: float,
        indicators: Dict[str, Any],
        is_owned: bool = False
    ) -> Optional[Signal]:
        """
        Evaluate a symbol and generate signal if conditions met.

        Args:
            symbol: Symbol to evaluate
            current_price: Current price
            rsi: RSI value
            sma_20: 20-day SMA value
            indicators: All calculated indicators
            is_owned: Whether we currently own this symbol

        Returns:
            Signal object or None
        """
        # Buy conditions (only for symbols we don't own)
        if not is_owned:
            price_above_sma = current_price > sma_20
            rsi_in_range = self.rsi_buy_min <= rsi <= self.rsi_buy_max

            if price_above_sma and rsi_in_range:
                # Calculate confidence based on how strong the signals are
                price_distance_pct = ((current_price - sma_20) / sma_20) * 100
                rsi_strength = self._calculate_rsi_strength(rsi)

                confidence = self._calculate_buy_confidence(
                    price_distance_pct, rsi_strength
                )

                if confidence >= self.min_confidence:
                    # Apply sentiment adjustment if available
                    sentiment_note = None
                    sentiment_analyzer = _get_sentiment_analyzer()
                    if sentiment_analyzer and settings.enable_reddit_sentiment:
                        adjusted_conf, sentiment_note = sentiment_analyzer.adjust_signal_confidence(
                            symbol, confidence, 'buy'
                        )
                        if adjusted_conf != confidence:
                            self.logger.debug(
                                "sentiment_adjusted_confidence",
                                symbol=symbol,
                                original=confidence,
                                adjusted=adjusted_conf
                            )
                            confidence = adjusted_conf

                    notes = f"Price above SMA ({price_distance_pct:.2f}%), RSI in buy range ({rsi:.1f})"
                    if sentiment_note:
                        notes = f"{notes} | {sentiment_note}"

                    return Signal(
                        symbol=symbol,
                        signal_type='buy',
                        confidence=confidence,
                        strategy_name=self.name,
                        data_snapshot={
                            'price': current_price,
                            'rsi': rsi,
                            'sma_20': sma_20,
                            'price_distance_pct': price_distance_pct,
                            'indicators': indicators,
                            'sentiment_adjusted': sentiment_note is not None
                        },
                        notes=notes
                    )

        # Sell conditions - ONLY for symbols we own
        if is_owned:
            rsi_overbought = rsi > self.rsi_sell_threshold
            price_below_sma = current_price < sma_20

            if rsi_overbought or price_below_sma:
                # Calculate sell confidence based on signal strength
                confidence = 0.85 if rsi_overbought else 0.75
                if rsi_overbought and price_below_sma:
                    confidence = 0.95  # Both conditions = very strong sell signal

                reason = []
                if rsi_overbought:
                    reason.append(f"RSI overbought ({rsi:.1f})")
                if price_below_sma:
                    reason.append(f"Price below SMA (${current_price:.2f} < ${sma_20:.2f})")

                return Signal(
                    symbol=symbol,
                    signal_type='sell',
                    confidence=confidence,
                    strategy_name=self.name,
                    data_snapshot={
                        'price': current_price,
                        'rsi': rsi,
                        'sma_20': sma_20,
                        'indicators': indicators
                    },
                    notes=", ".join(reason)
                )

        return None

    def _calculate_rsi_strength(self, rsi: float) -> float:
        """
        Calculate RSI strength score (0-100).
        Optimal RSI for buying is around 50 (neutral but not oversold).

        Args:
            rsi: RSI value

        Returns:
            Strength score
        """
        # Ideal RSI for momentum buying is 50-60 range
        if 50 <= rsi <= 60:
            return 100
        elif 45 <= rsi < 50:
            return 90
        elif 60 < rsi <= 65:
            return 80
        elif 40 <= rsi < 45:
            return 70
        elif 65 < rsi <= 70:
            return 60
        else:
            return 40

    def _calculate_buy_confidence(
        self,
        price_distance_pct: float,
        rsi_strength: float
    ) -> float:
        """
        Calculate overall buy confidence.

        Args:
            price_distance_pct: Distance of price from SMA (%)
            rsi_strength: RSI strength score (0-100)

        Returns:
            Confidence score (0.0 to 1.0)
        """
        # Price strength: better if price is moderately above SMA (2-5%)
        if 2 <= price_distance_pct <= 5:
            price_strength = 100
        elif 1 <= price_distance_pct < 2:
            price_strength = 80
        elif 5 < price_distance_pct <= 8:
            price_strength = 70
        elif 0 < price_distance_pct < 1:
            price_strength = 60
        else:
            price_strength = 40

        # Weighted average: 60% RSI, 40% price position
        combined_score = (rsi_strength * 0.6) + (price_strength * 0.4)

        # Normalize to 0.0-1.0 range
        return self._calculate_confidence(combined_score, max_score=100.0)

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
        try:
            # Calculate P&L percentage
            pnl_pct = ((current_price - entry_price) / entry_price) * 100

            # Stop loss check
            if pnl_pct <= -self.stop_loss_pct:
                return True, f"Stop loss triggered ({pnl_pct:.2f}%)"

            # Get current indicators
            bars = alpaca_client.get_bars(symbol, timeframe="1Day", limit=100)
            if not bars or len(bars) < 20:
                return False, None

            df = calculate_all_indicators(bars)
            indicators = get_latest_indicators(df)

            if not all(key in indicators and indicators[key] is not None
                      for key in ['rsi', 'sma_20']):
                return False, None

            rsi = indicators['rsi']
            sma_20 = indicators['sma_20']

            # Exit conditions
            rsi_overbought = rsi > self.rsi_sell_threshold
            price_below_sma = current_price < sma_20

            if rsi_overbought:
                return True, f"RSI overbought ({rsi:.1f})"

            if price_below_sma:
                return True, f"Price below SMA (${current_price:.2f} < ${sma_20:.2f})"

            return False, None

        except Exception as e:
            self.logger.error(
                "error_checking_exit",
                symbol=symbol,
                error=str(e)
            )
            return False, None
