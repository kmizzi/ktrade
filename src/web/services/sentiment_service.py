"""
Sentiment service for fetching news and social sentiment.
"""

from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session

from config.settings import settings


class SentimentService:
    """Service for sentiment data operations."""

    def __init__(self, db: Optional[Session]):
        self.db = db

    def get_market_sentiment(self) -> Dict[str, Any]:
        """Get overall market sentiment."""
        try:
            from src.data.sentiment_providers import news_provider

            sentiment = news_provider.get_market_sentiment()
            return {
                "sentiment": sentiment.get("sentiment", "neutral"),
                "score": sentiment.get("score", 0),
                "articles_count": sentiment.get("articles_count", 0),
                "api_quota_remaining": sentiment.get("api_quota_remaining", 0),
            }
        except Exception as e:
            return {
                "sentiment": "unknown",
                "score": 0,
                "error": str(e),
            }

    def get_symbol_sentiment(self, symbol: str) -> Dict[str, Any]:
        """Get sentiment for a specific symbol."""
        try:
            from src.data.sentiment_providers import news_provider

            sentiment = news_provider.get_news_sentiment(symbol)
            return {
                "symbol": symbol,
                "sentiment": sentiment.get("sentiment", "neutral"),
                "score": sentiment.get("score", 0),
                "articles": sentiment.get("articles", []),
            }
        except Exception as e:
            return {
                "symbol": symbol,
                "sentiment": "unknown",
                "error": str(e),
            }

    def get_news(self) -> List[Dict[str, Any]]:
        """Get recent news headlines."""
        try:
            from src.data.sentiment_providers import news_provider

            news = news_provider.get_latest_headlines()
            return news[:20] if news else []
        except Exception as e:
            return []

    def get_wsb_trending(self) -> List[Dict[str, Any]]:
        """Get WSB trending stocks."""
        try:
            from src.data.sentiment_providers import quiver_provider

            trending = quiver_provider.get_wsb_trending()
            return trending[:10]  # Top 10
        except Exception as e:
            return []

    def get_watchlist_sentiment(self) -> List[Dict[str, Any]]:
        """Get sentiment for all watchlist symbols."""
        symbols = []
        if settings.watchlist_stocks:
            symbols.extend(settings.watchlist_stocks)

        results = []
        for symbol in symbols[:10]:  # Limit to avoid rate limits
            sentiment = self.get_symbol_sentiment(symbol)
            results.append(sentiment)

        return results
