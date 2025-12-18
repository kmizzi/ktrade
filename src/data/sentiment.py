"""
Sentiment analysis module for social media and news text.
Uses VADER (Valence Aware Dictionary and sEntiment Reasoner) for sentiment scoring.
VADER is specifically attuned to social media sentiment.
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import structlog

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    VADER_AVAILABLE = True
except ImportError:
    VADER_AVAILABLE = False

from config.settings import settings
from src.api.reddit_client import reddit_client

logger = structlog.get_logger(__name__)


class SentimentAnalyzer:
    """
    Analyzes sentiment from text using VADER.
    Optimized for social media content like Reddit posts.
    """

    def __init__(self):
        self._analyzer = None
        self._initialized = False

        # Cache for sentiment data
        self._sentiment_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl_minutes = settings.sentiment_refresh_minutes

    def _initialize(self) -> bool:
        """Initialize VADER analyzer."""
        if self._initialized:
            return True

        if not VADER_AVAILABLE:
            logger.warning(
                "vader_not_available",
                message="vaderSentiment not installed. Run: pip install vaderSentiment"
            )
            return False

        try:
            self._analyzer = SentimentIntensityAnalyzer()
            self._initialized = True
            logger.info("sentiment_analyzer_initialized")
            return True

        except Exception as e:
            logger.error("sentiment_init_failed", error=str(e))
            return False

    def is_available(self) -> bool:
        """Check if sentiment analyzer is available."""
        return self._initialize()

    def analyze_text(self, text: str) -> Dict[str, float]:
        """
        Analyze sentiment of a single text.

        Args:
            text: Text to analyze

        Returns:
            Dict with sentiment scores:
            - neg: Negative sentiment (0-1)
            - neu: Neutral sentiment (0-1)
            - pos: Positive sentiment (0-1)
            - compound: Compound score (-1 to 1)
        """
        if not self._initialize():
            return {'neg': 0, 'neu': 1, 'pos': 0, 'compound': 0}

        if not text:
            return {'neg': 0, 'neu': 1, 'pos': 0, 'compound': 0}

        try:
            scores = self._analyzer.polarity_scores(text)
            return scores
        except Exception as e:
            logger.error("sentiment_analysis_failed", error=str(e))
            return {'neg': 0, 'neu': 1, 'pos': 0, 'compound': 0}

    def analyze_posts(self, posts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze sentiment across multiple posts.

        Args:
            posts: List of post dictionaries with 'title' and 'selftext'

        Returns:
            Aggregated sentiment data
        """
        if not self._initialize() or not posts:
            return {
                'count': 0,
                'avg_compound': 0,
                'positive_pct': 0,
                'negative_pct': 0,
                'neutral_pct': 0
            }

        compounds = []
        positive = 0
        negative = 0
        neutral = 0

        for post in posts:
            text = f"{post.get('title', '')} {post.get('selftext', '')}"
            scores = self.analyze_text(text)

            compounds.append(scores['compound'])

            # Classify based on compound score
            if scores['compound'] >= 0.05:
                positive += 1
            elif scores['compound'] <= -0.05:
                negative += 1
            else:
                neutral += 1

        count = len(posts)
        return {
            'count': count,
            'avg_compound': sum(compounds) / count if count > 0 else 0,
            'positive_pct': (positive / count * 100) if count > 0 else 0,
            'negative_pct': (negative / count * 100) if count > 0 else 0,
            'neutral_pct': (neutral / count * 100) if count > 0 else 0,
            'positive_count': positive,
            'negative_count': negative,
            'neutral_count': neutral
        }

    def get_ticker_sentiment(
        self,
        ticker: str,
        posts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Get sentiment for a specific ticker from posts mentioning it.

        Args:
            ticker: Stock ticker symbol
            posts: List of posts (with 'tickers' field)

        Returns:
            Sentiment data for the ticker
        """
        # Filter posts mentioning this ticker
        ticker_posts = [
            p for p in posts
            if ticker in p.get('tickers', [])
        ]

        if not ticker_posts:
            return {
                'symbol': ticker,
                'mentions': 0,
                'sentiment': None,
                'avg_compound': 0,
                'bullish_pct': 0
            }

        sentiment = self.analyze_posts(ticker_posts)

        return {
            'symbol': ticker,
            'mentions': len(ticker_posts),
            'sentiment': sentiment,
            'avg_compound': sentiment['avg_compound'],
            'bullish_pct': sentiment['positive_pct'],
            'bearish_pct': sentiment['negative_pct'],
            'total_score': sum(p.get('score', 0) for p in ticker_posts),
            'avg_upvote_ratio': sum(p.get('upvote_ratio', 0) for p in ticker_posts) / len(ticker_posts)
        }

    def _is_cache_valid(self) -> bool:
        """Check if sentiment cache is still valid."""
        if not self._cache_timestamp or not self._sentiment_cache:
            return False

        cache_age = datetime.utcnow() - self._cache_timestamp
        return cache_age < timedelta(minutes=self._cache_ttl_minutes)

    def get_reddit_sentiment(
        self,
        force_refresh: bool = False
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get sentiment data for all tickers mentioned on Reddit.
        Results are cached to avoid excessive API calls.

        Args:
            force_refresh: Force refresh even if cache is valid

        Returns:
            Dict mapping ticker to sentiment data
        """
        # Check cache
        if not force_refresh and self._is_cache_valid():
            logger.debug("using_cached_sentiment", cache_age_minutes=self._cache_ttl_minutes)
            return self._sentiment_cache

        if not settings.enable_reddit_sentiment:
            logger.debug("reddit_sentiment_disabled")
            return {}

        if not reddit_client.is_available():
            logger.warning("reddit_client_not_available")
            return {}

        if not self._initialize():
            return {}

        try:
            logger.info("refreshing_reddit_sentiment")

            # Get posts from all configured subreddits
            all_posts = []
            for subreddit in settings.get_reddit_subreddits():
                posts = reddit_client.get_subreddit_posts(
                    subreddit,
                    sort="hot",
                    limit=100
                )
                all_posts.extend(posts)

            # Extract all unique tickers
            all_tickers = set()
            for post in all_posts:
                all_tickers.update(post.get('tickers', []))

            # Calculate sentiment for each ticker
            sentiment_data = {}
            for ticker in all_tickers:
                ticker_sentiment = self.get_ticker_sentiment(ticker, all_posts)
                if ticker_sentiment['mentions'] > 0:
                    sentiment_data[ticker] = ticker_sentiment

            # Update cache
            self._sentiment_cache = sentiment_data
            self._cache_timestamp = datetime.utcnow()

            logger.info(
                "reddit_sentiment_refreshed",
                unique_tickers=len(sentiment_data),
                total_posts=len(all_posts),
                cache_ttl_minutes=self._cache_ttl_minutes
            )

            return sentiment_data

        except Exception as e:
            logger.error("failed_to_get_reddit_sentiment", error=str(e))
            return self._sentiment_cache if self._sentiment_cache else {}

    def get_wsb_sentiment_summary(self) -> Dict[str, Any]:
        """
        Get a summary of WSB sentiment including trending stocks.

        Returns:
            Summary with top bullish/bearish stocks
        """
        sentiment_data = self.get_reddit_sentiment()

        if not sentiment_data:
            return {
                'available': False,
                'message': 'Sentiment data not available'
            }

        # Filter for WSB mentions
        wsb_data = {
            ticker: data for ticker, data in sentiment_data.items()
            if 'wallstreetbets' in str(data.get('sentiment', {}).get('subreddits', {}))
            or data['mentions'] >= settings.wsb_mention_threshold
        }

        # Sort by various metrics
        by_mentions = sorted(
            wsb_data.items(),
            key=lambda x: x[1]['mentions'],
            reverse=True
        )

        by_bullish = sorted(
            wsb_data.items(),
            key=lambda x: x[1]['avg_compound'],
            reverse=True
        )

        by_bearish = sorted(
            wsb_data.items(),
            key=lambda x: x[1]['avg_compound']
        )

        return {
            'available': True,
            'timestamp': self._cache_timestamp.isoformat() if self._cache_timestamp else None,
            'total_tickers': len(wsb_data),
            'most_mentioned': [
                {'symbol': t, 'mentions': d['mentions'], 'sentiment': d['avg_compound']}
                for t, d in by_mentions[:10]
            ],
            'most_bullish': [
                {'symbol': t, 'sentiment': d['avg_compound'], 'mentions': d['mentions']}
                for t, d in by_bullish[:5]
                if d['avg_compound'] > 0.1 and d['mentions'] >= 3
            ],
            'most_bearish': [
                {'symbol': t, 'sentiment': d['avg_compound'], 'mentions': d['mentions']}
                for t, d in by_bearish[:5]
                if d['avg_compound'] < -0.1 and d['mentions'] >= 3
            ]
        }

    def get_sentiment_signal(
        self,
        symbol: str,
        min_mentions: int = 3
    ) -> Tuple[float, str]:
        """
        Get a sentiment-based signal for a symbol.

        Args:
            symbol: Stock symbol
            min_mentions: Minimum mentions required

        Returns:
            Tuple of (signal_strength, description)
            signal_strength: -1 (very bearish) to +1 (very bullish)
            description: Human-readable description
        """
        sentiment_data = self.get_reddit_sentiment()

        if symbol not in sentiment_data:
            return (0.0, "No Reddit mentions found")

        data = sentiment_data[symbol]
        mentions = data['mentions']
        compound = data['avg_compound']
        bullish_pct = data['bullish_pct']

        if mentions < min_mentions:
            return (0.0, f"Insufficient mentions ({mentions} < {min_mentions})")

        # Generate description
        if compound >= 0.5:
            desc = f"Very bullish sentiment ({bullish_pct:.0f}% positive, {mentions} mentions)"
        elif compound >= 0.2:
            desc = f"Bullish sentiment ({bullish_pct:.0f}% positive, {mentions} mentions)"
        elif compound >= 0.05:
            desc = f"Slightly bullish ({bullish_pct:.0f}% positive, {mentions} mentions)"
        elif compound <= -0.5:
            desc = f"Very bearish sentiment ({data['bearish_pct']:.0f}% negative, {mentions} mentions)"
        elif compound <= -0.2:
            desc = f"Bearish sentiment ({data['bearish_pct']:.0f}% negative, {mentions} mentions)"
        elif compound <= -0.05:
            desc = f"Slightly bearish ({data['bearish_pct']:.0f}% negative, {mentions} mentions)"
        else:
            desc = f"Neutral sentiment ({mentions} mentions)"

        return (compound, desc)

    def adjust_signal_confidence(
        self,
        symbol: str,
        base_confidence: float,
        signal_type: str
    ) -> Tuple[float, Optional[str]]:
        """
        Adjust signal confidence based on sentiment.

        Args:
            symbol: Stock symbol
            base_confidence: Original confidence from strategy
            signal_type: 'buy' or 'sell'

        Returns:
            Tuple of (adjusted_confidence, sentiment_note)
        """
        if not settings.enable_reddit_sentiment:
            return (base_confidence, None)

        sentiment_signal, description = self.get_sentiment_signal(symbol)

        if sentiment_signal == 0:
            return (base_confidence, None)

        # Weight from settings
        weight = settings.sentiment_weight

        # For BUY signals: positive sentiment boosts, negative sentiment reduces
        # For SELL signals: negative sentiment boosts, positive sentiment reduces
        if signal_type.lower() == 'buy':
            adjustment = sentiment_signal * weight
        else:  # sell
            adjustment = -sentiment_signal * weight

        # Calculate adjusted confidence
        adjusted = base_confidence + (adjustment * (1 - base_confidence))

        # Clamp to valid range
        adjusted = max(0.0, min(1.0, adjusted))

        note = f"Sentiment: {description}"

        logger.debug(
            "confidence_adjusted_by_sentiment",
            symbol=symbol,
            signal_type=signal_type,
            base_confidence=base_confidence,
            sentiment_signal=sentiment_signal,
            adjusted_confidence=adjusted
        )

        return (adjusted, note)


# Global sentiment analyzer instance
sentiment_analyzer = SentimentAnalyzer()


def get_trending_with_sentiment(min_mentions: int = 5) -> List[Dict[str, Any]]:
    """
    Convenience function to get WSB trending stocks with sentiment.

    Args:
        min_mentions: Minimum mentions required

    Returns:
        List of trending stocks with sentiment data
    """
    sentiment_data = sentiment_analyzer.get_reddit_sentiment()

    trending = []
    for symbol, data in sentiment_data.items():
        if data['mentions'] >= min_mentions:
            trending.append({
                'symbol': symbol,
                'mentions': data['mentions'],
                'sentiment_score': data['avg_compound'],
                'bullish_pct': data['bullish_pct'],
                'bearish_pct': data['bearish_pct'],
                'total_score': data['total_score']
            })

    # Sort by mentions
    trending.sort(key=lambda x: x['mentions'], reverse=True)

    return trending
