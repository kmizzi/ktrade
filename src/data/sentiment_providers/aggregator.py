"""
Unified sentiment aggregator.
Combines sentiment from multiple sources: WSB (Quiver), StockTwits, and News.
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
import structlog

from src.data.sentiment_providers.quiver import quiver_provider, QuiverQuantProvider
from src.data.sentiment_providers.stocktwits import stocktwits_provider, StockTwitsProvider
from src.data.sentiment_providers.news import news_provider, NewsProvider

logger = structlog.get_logger(__name__)


@dataclass
class AggregatedSentiment:
    """Combined sentiment from all sources."""
    symbol: str
    overall_score: float  # -1 to 1
    overall_label: str  # "Bullish", "Bearish", "Neutral"
    confidence: float  # 0 to 1

    # Individual source scores
    wsb_score: float
    wsb_mentions: int
    wsb_trending: bool

    stocktwits_score: float
    stocktwits_bullish_pct: float
    stocktwits_volume: int

    news_score: float
    news_articles: int

    timestamp: datetime


class SentimentAggregator:
    """
    Aggregates sentiment from multiple providers.
    Provides weighted combination of WSB, StockTwits, and News sentiment.
    """

    def __init__(
        self,
        wsb_weight: float = 0.4,
        stocktwits_weight: float = 0.35,
        news_weight: float = 0.25,
        alpha_vantage_key: Optional[str] = None
    ):
        """
        Initialize aggregator.

        Args:
            wsb_weight: Weight for WSB sentiment (0-1)
            stocktwits_weight: Weight for StockTwits sentiment (0-1)
            news_weight: Weight for news sentiment (0-1)
            alpha_vantage_key: API key for news provider
        """
        self.wsb_weight = wsb_weight
        self.stocktwits_weight = stocktwits_weight
        self.news_weight = news_weight

        # Providers
        self.wsb = quiver_provider
        self.stocktwits = stocktwits_provider
        self.news = news_provider

        if alpha_vantage_key:
            self.news.set_api_key(alpha_vantage_key)

        # Cache
        self._cache: Dict[str, AggregatedSentiment] = {}

    def set_alpha_vantage_key(self, api_key: str):
        """Set Alpha Vantage API key for news sentiment."""
        self.news.set_api_key(api_key)

    def get_sentiment(
        self,
        symbol: str,
        include_news: bool = True
    ) -> AggregatedSentiment:
        """
        Get aggregated sentiment for a symbol.

        Args:
            symbol: Stock ticker symbol
            include_news: Whether to include news sentiment (uses API quota)

        Returns:
            Aggregated sentiment data
        """
        symbol = symbol.upper()

        # Get WSB data
        wsb_data = self.wsb.get_symbol_mentions(symbol)
        wsb_score = wsb_data.get('sentiment', 0) if wsb_data else 0
        wsb_mentions = wsb_data.get('mentions', 0) if wsb_data else 0
        wsb_trending = wsb_mentions >= 10

        # Get StockTwits data
        st_data = self.stocktwits.get_symbol_sentiment(symbol)
        st_score = st_data.get('sentiment_score', 0)
        st_bullish_pct = st_data.get('bullish_pct', 50)
        st_volume = st_data.get('total_messages', 0)

        # Get news data (optional)
        if include_news and self.news.api_key:
            news_data = self.news.get_news_sentiment(symbol)
            news_score = news_data.get('sentiment_score', 0)
            news_articles = news_data.get('article_count', 0)
        else:
            news_score = 0
            news_articles = 0

        # Calculate weighted score
        weights_used = []
        scores_used = []

        if wsb_mentions > 0:
            weights_used.append(self.wsb_weight)
            scores_used.append(wsb_score)

        if st_volume > 0:
            weights_used.append(self.stocktwits_weight)
            scores_used.append(st_score)

        if news_articles > 0:
            weights_used.append(self.news_weight)
            scores_used.append(news_score)

        # Normalize weights
        if weights_used:
            total_weight = sum(weights_used)
            normalized_weights = [w / total_weight for w in weights_used]
            overall_score = sum(s * w for s, w in zip(scores_used, normalized_weights))
        else:
            overall_score = 0

        # Determine label
        if overall_score >= 0.25:
            overall_label = "Very Bullish"
        elif overall_score >= 0.1:
            overall_label = "Bullish"
        elif overall_score <= -0.25:
            overall_label = "Very Bearish"
        elif overall_score <= -0.1:
            overall_label = "Bearish"
        else:
            overall_label = "Neutral"

        # Calculate confidence based on data availability
        data_sources = sum([
            1 if wsb_mentions > 0 else 0,
            1 if st_volume > 0 else 0,
            1 if news_articles > 0 else 0
        ])
        confidence = data_sources / 3.0

        # Boost confidence for high-volume data
        if wsb_mentions >= 50:
            confidence = min(1.0, confidence + 0.1)
        if st_volume >= 20:
            confidence = min(1.0, confidence + 0.1)

        result = AggregatedSentiment(
            symbol=symbol,
            overall_score=overall_score,
            overall_label=overall_label,
            confidence=confidence,
            wsb_score=wsb_score,
            wsb_mentions=wsb_mentions,
            wsb_trending=wsb_trending,
            stocktwits_score=st_score,
            stocktwits_bullish_pct=st_bullish_pct,
            stocktwits_volume=st_volume,
            news_score=news_score,
            news_articles=news_articles,
            timestamp=datetime.utcnow()
        )

        self._cache[symbol] = result

        logger.info(
            "sentiment_aggregated",
            symbol=symbol,
            overall_score=overall_score,
            overall_label=overall_label,
            confidence=confidence,
            wsb_mentions=wsb_mentions,
            stocktwits_messages=st_volume,
            news_articles=news_articles
        )

        return result

    def get_signal_adjustment(
        self,
        symbol: str,
        signal_type: str,
        base_confidence: float
    ) -> Tuple[float, str]:
        """
        Get adjusted confidence based on sentiment.

        Args:
            symbol: Stock ticker symbol
            signal_type: "buy" or "sell"
            base_confidence: Original strategy confidence

        Returns:
            Tuple of (adjusted_confidence, explanation)
        """
        sentiment = self.get_sentiment(symbol, include_news=False)  # Skip news to save API

        if sentiment.confidence < 0.3:
            return base_confidence, "Insufficient sentiment data"

        score = sentiment.overall_score

        # Adjust based on signal type
        if signal_type.lower() == 'buy':
            # Bullish sentiment boosts buy confidence
            adjustment = score * 0.15 * sentiment.confidence
        else:
            # Bearish sentiment boosts sell confidence
            adjustment = -score * 0.15 * sentiment.confidence

        adjusted = max(0.0, min(1.0, base_confidence + adjustment))

        # Build explanation
        parts = []
        if sentiment.wsb_mentions > 0:
            parts.append(f"WSB: {sentiment.wsb_mentions} mentions")
        if sentiment.stocktwits_volume > 0:
            parts.append(f"ST: {sentiment.stocktwits_bullish_pct:.0f}% bullish")

        explanation = f"{sentiment.overall_label} ({', '.join(parts)})" if parts else "No sentiment data"

        return adjusted, explanation

    def get_wsb_trending(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get WSB trending stocks with full sentiment data.

        Args:
            limit: Max stocks to return

        Returns:
            List of trending stocks with sentiment
        """
        trending = self.wsb.get_top_mentioned(limit=limit)

        results = []
        for stock in trending:
            symbol = stock['symbol']
            st_data = self.stocktwits.get_symbol_sentiment(symbol)

            results.append({
                'symbol': symbol,
                'wsb_mentions': stock['mentions'],
                'wsb_sentiment': stock['sentiment'],
                'wsb_rank': stock.get('rank', 0),
                'stocktwits_score': st_data.get('sentiment_score', 0),
                'stocktwits_bullish_pct': st_data.get('bullish_pct', 50),
            })

        return results

    def get_market_mood(self) -> Dict[str, Any]:
        """
        Get overall market mood from all sources.

        Returns:
            Market mood summary
        """
        # Get WSB top stocks
        wsb_trending = self.wsb.get_wsb_trending()
        wsb_sentiments = [s.get('sentiment', 0) for s in wsb_trending[:20]]
        wsb_avg = sum(wsb_sentiments) / len(wsb_sentiments) if wsb_sentiments else 0

        # Get StockTwits trending
        st_trending = self.stocktwits.get_trending()

        # Calculate overall mood
        if wsb_avg >= 0.2:
            mood = "Bullish"
            emoji = "🟢"
        elif wsb_avg <= -0.2:
            mood = "Bearish"
            emoji = "🔴"
        else:
            mood = "Neutral"
            emoji = "🟡"

        return {
            'mood': mood,
            'emoji': emoji,
            'wsb_sentiment': wsb_avg,
            'wsb_trending_count': len(wsb_trending),
            'stocktwits_trending': [s['symbol'] for s in st_trending[:10]],
            'timestamp': datetime.utcnow().isoformat()
        }

    def should_boost_signal(
        self,
        symbol: str,
        signal_type: str,
        threshold: float = 0.2
    ) -> Tuple[bool, str]:
        """
        Check if sentiment suggests boosting a trading signal.

        Args:
            symbol: Stock ticker symbol
            signal_type: "buy" or "sell"
            threshold: Sentiment threshold for boosting

        Returns:
            Tuple of (should_boost, reason)
        """
        sentiment = self.get_sentiment(symbol, include_news=False)

        if signal_type.lower() == 'buy':
            if sentiment.overall_score >= threshold:
                return True, f"Bullish sentiment ({sentiment.overall_label})"
            if sentiment.wsb_trending and sentiment.wsb_score > 0:
                return True, f"WSB trending with {sentiment.wsb_mentions} mentions"
        else:
            if sentiment.overall_score <= -threshold:
                return True, f"Bearish sentiment ({sentiment.overall_label})"

        return False, "Sentiment neutral or contrary"


# Global aggregator instance
sentiment_aggregator = SentimentAggregator()
