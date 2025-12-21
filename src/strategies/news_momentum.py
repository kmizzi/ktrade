"""
News-Driven Momentum Strategy.

Based on PRD Strategy 4: News-Driven Momentum
- Trigger: Positive news sentiment + volume spike + price momentum
- Action: Quick entry for short-term gains
- Exit: Within 4-24 hours or at profit target (+5%)
- Risk: Tight stop loss at -2%

This strategy is designed for catching moves on positive news catalysts.
It uses Alpha Vantage news sentiment combined with volume and price momentum.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from src.strategies.base import BaseStrategy, Signal
from src.api.alpaca_client import alpaca_client
from src.data.indicators import calculate_all_indicators, get_latest_indicators
from config.settings import settings
import structlog

logger = structlog.get_logger(__name__)

# Lazy import for sentiment to avoid circular dependencies
_news_provider = None


def _get_news_provider():
    """Lazy load news provider."""
    global _news_provider
    if _news_provider is None:
        try:
            from src.data.sentiment_providers.news import news_provider
            _news_provider = news_provider
        except ImportError:
            logger.warning("news_provider_import_failed")
            _news_provider = False
    return _news_provider if _news_provider else None


class NewsMomentumStrategy(BaseStrategy):
    """
    News-driven momentum strategy for catching short-term moves on news catalysts.

    Buy when:
    - News sentiment is bullish (score > 0.15)
    - Volume is above average (1.5x+ normal)
    - Price is up on the day (momentum confirmation)
    - RSI not overbought (< 70)

    Sell when:
    - Profit target hit (+5%)
    - Stop loss hit (-2%)
    - News sentiment turns bearish
    - RSI overbought (> 75)
    - Max holding period exceeded (24 hours)
    """

    def __init__(self, enabled: bool = True):
        super().__init__(name="news_momentum", enabled=enabled)

        # Strategy parameters
        self.min_sentiment_score = 0.15  # Minimum bullish sentiment
        self.min_bullish_pct = 50.0      # Minimum % of bullish articles
        self.min_article_count = 3       # Minimum articles for confidence
        self.volume_multiplier = 1.5     # Minimum volume vs average
        self.min_daily_gain_pct = 0.5    # Minimum price gain on day
        self.rsi_max = 70                # Don't buy if RSI above this

        # Exit parameters
        self.profit_target_pct = 5.0     # Take profit at +5%
        self.stop_loss_pct = 2.0         # Tight stop at -2%
        self.max_holding_hours = 24      # Max holding period
        self.rsi_exit_threshold = 75     # Exit if RSI exceeds this

        # Confidence parameters
        self.min_confidence = 0.65

    def generate_signals(
        self,
        symbols: List[str],
        owned_symbols: Optional[List[str]] = None
    ) -> List[Signal]:
        """
        Generate buy/sell signals based on news sentiment and momentum.

        Args:
            symbols: List of symbols to analyze
            owned_symbols: List of symbols currently owned

        Returns:
            List of Signal objects
        """
        signals = []
        owned_set = set(owned_symbols or [])
        news_provider = _get_news_provider()

        if not news_provider:
            self.logger.warning("news_provider_not_available")
            return signals

        for symbol in symbols:
            try:
                signal = self._evaluate_symbol(
                    symbol,
                    news_provider,
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
        news_provider,
        is_owned: bool = False
    ) -> Optional[Signal]:
        """
        Evaluate a symbol for news-driven momentum.

        Args:
            symbol: Symbol to evaluate
            news_provider: News sentiment provider
            is_owned: Whether we currently own this symbol

        Returns:
            Signal object or None
        """
        # Get news sentiment (uses cache to avoid rate limits)
        sentiment = news_provider.get_news_sentiment(symbol)

        if 'error' in sentiment:
            self.logger.debug(
                "sentiment_fetch_failed",
                symbol=symbol,
                error=sentiment.get('error')
            )
            return None

        sentiment_score = sentiment.get('sentiment_score', 0)
        article_count = sentiment.get('article_count', 0)
        bullish_pct = sentiment.get('bullish_pct', 0)

        # Get market data
        bars = alpaca_client.get_bars(symbol, timeframe="1Day", limit=50)

        if not bars or len(bars) < 20:
            self.logger.debug("insufficient_bars", symbol=symbol)
            return None

        # Calculate indicators
        df = calculate_all_indicators(bars)
        indicators = get_latest_indicators(df)

        if not all(key in indicators and indicators[key] is not None
                  for key in ['close', 'open', 'volume', 'rsi', 'volume_sma']):
            self.logger.debug("missing_indicators", symbol=symbol)
            return None

        current_price = indicators['close']
        open_price = indicators['open']
        volume = indicators['volume']
        volume_avg = indicators.get('volume_sma', volume)
        rsi = indicators['rsi']

        # Calculate daily gain
        daily_gain_pct = ((current_price - open_price) / open_price) * 100
        volume_ratio = volume / volume_avg if volume_avg > 0 else 1.0

        # Build data snapshot
        data_snapshot = {
            'price': current_price,
            'open': open_price,
            'daily_gain_pct': daily_gain_pct,
            'volume': volume,
            'volume_avg': volume_avg,
            'volume_ratio': volume_ratio,
            'rsi': rsi,
            'sentiment_score': sentiment_score,
            'article_count': article_count,
            'bullish_pct': bullish_pct,
        }

        # BUY signal logic (only for symbols we don't own)
        if not is_owned:
            buy_signal = self._check_buy_conditions(
                symbol, sentiment_score, article_count, bullish_pct,
                volume_ratio, daily_gain_pct, rsi, data_snapshot
            )
            if buy_signal:
                return buy_signal

        # SELL signal logic (only for symbols we own)
        if is_owned:
            sell_signal = self._check_sell_conditions(
                symbol, sentiment_score, rsi, data_snapshot
            )
            if sell_signal:
                return sell_signal

        return None

    def _check_buy_conditions(
        self,
        symbol: str,
        sentiment_score: float,
        article_count: int,
        bullish_pct: float,
        volume_ratio: float,
        daily_gain_pct: float,
        rsi: float,
        data_snapshot: Dict[str, Any]
    ) -> Optional[Signal]:
        """Check if buy conditions are met."""

        reasons = []
        score = 0
        max_score = 100

        # 1. News sentiment check (40 points max)
        if sentiment_score >= self.min_sentiment_score:
            sentiment_points = min(40, int(sentiment_score * 100))
            score += sentiment_points
            reasons.append(f"Bullish news ({sentiment_score:.2f})")
        else:
            return None  # Required condition

        # 2. Article count check (10 points max)
        if article_count >= self.min_article_count:
            article_points = min(10, article_count)
            score += article_points
            reasons.append(f"{article_count} articles")
        else:
            return None  # Need enough news coverage

        # 3. Bullish percentage check (15 points max)
        if bullish_pct >= self.min_bullish_pct:
            bullish_points = min(15, int(bullish_pct / 5))
            score += bullish_points
            reasons.append(f"{bullish_pct:.0f}% bullish")

        # 4. Volume spike check (20 points max)
        if volume_ratio >= self.volume_multiplier:
            volume_points = min(20, int(volume_ratio * 8))
            score += volume_points
            reasons.append(f"Volume {volume_ratio:.1f}x avg")
        else:
            # Volume not required but helpful
            pass

        # 5. Price momentum check (15 points max)
        if daily_gain_pct >= self.min_daily_gain_pct:
            momentum_points = min(15, int(daily_gain_pct * 5))
            score += momentum_points
            reasons.append(f"Up {daily_gain_pct:.1f}% today")
        else:
            # Momentum not required but helpful
            pass

        # 6. RSI check (required - don't buy overbought)
        if rsi > self.rsi_max:
            self.logger.debug(
                "rsi_too_high",
                symbol=symbol,
                rsi=rsi
            )
            return None

        # Calculate confidence
        confidence = score / max_score

        if confidence < self.min_confidence:
            return None

        return Signal(
            symbol=symbol,
            signal_type='buy',
            confidence=confidence,
            strategy_name=self.name,
            data_snapshot=data_snapshot,
            notes=" | ".join(reasons)
        )

    def _check_sell_conditions(
        self,
        symbol: str,
        sentiment_score: float,
        rsi: float,
        data_snapshot: Dict[str, Any]
    ) -> Optional[Signal]:
        """Check if sell conditions are met for owned position."""

        reasons = []
        confidence = 0.7

        # RSI overbought - strong sell signal
        if rsi > self.rsi_exit_threshold:
            reasons.append(f"RSI overbought ({rsi:.1f})")
            confidence = 0.85

        # Sentiment turned bearish - exit
        if sentiment_score < -0.1:
            reasons.append(f"News turned bearish ({sentiment_score:.2f})")
            confidence = max(confidence, 0.80)

        if not reasons:
            return None

        return Signal(
            symbol=symbol,
            signal_type='sell',
            confidence=confidence,
            strategy_name=self.name,
            data_snapshot=data_snapshot,
            notes=" | ".join(reasons)
        )

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
            position_data: Additional position data (including entry_time)

        Returns:
            Tuple of (should_exit: bool, reason: str)
        """
        try:
            # Calculate P&L percentage
            pnl_pct = ((current_price - entry_price) / entry_price) * 100

            # Profit target hit
            if pnl_pct >= self.profit_target_pct:
                return True, f"Profit target hit ({pnl_pct:.2f}%)"

            # Stop loss hit
            if pnl_pct <= -self.stop_loss_pct:
                return True, f"Stop loss triggered ({pnl_pct:.2f}%)"

            # Check holding period
            if position_data and 'entry_time' in position_data:
                entry_time = position_data['entry_time']
                if isinstance(entry_time, str):
                    entry_time = datetime.fromisoformat(entry_time)

                holding_hours = (datetime.utcnow() - entry_time).total_seconds() / 3600

                if holding_hours >= self.max_holding_hours:
                    return True, f"Max holding period exceeded ({holding_hours:.1f}h)"

            # Get current indicators for RSI check
            bars = alpaca_client.get_bars(symbol, timeframe="1Day", limit=30)
            if bars and len(bars) >= 14:
                df = calculate_all_indicators(bars)
                indicators = get_latest_indicators(df)

                rsi = indicators.get('rsi')
                if rsi and rsi > self.rsi_exit_threshold:
                    return True, f"RSI overbought ({rsi:.1f})"

            # Check if sentiment has turned negative
            news_provider = _get_news_provider()
            if news_provider:
                sentiment = news_provider.get_news_sentiment(symbol)
                if 'error' not in sentiment:
                    sentiment_score = sentiment.get('sentiment_score', 0)
                    if sentiment_score < -0.15:
                        return True, f"News sentiment turned bearish ({sentiment_score:.2f})"

            return False, None

        except Exception as e:
            self.logger.error(
                "error_checking_exit",
                symbol=symbol,
                error=str(e)
            )
            return False, None

    def get_strategy_params(self) -> Dict[str, Any]:
        """Return current strategy parameters for logging/display."""
        return {
            'min_sentiment_score': self.min_sentiment_score,
            'min_bullish_pct': self.min_bullish_pct,
            'min_article_count': self.min_article_count,
            'volume_multiplier': self.volume_multiplier,
            'min_daily_gain_pct': self.min_daily_gain_pct,
            'rsi_max': self.rsi_max,
            'profit_target_pct': self.profit_target_pct,
            'stop_loss_pct': self.stop_loss_pct,
            'max_holding_hours': self.max_holding_hours,
            'min_confidence': self.min_confidence,
        }
