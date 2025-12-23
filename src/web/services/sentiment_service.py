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
        """Get overall market sentiment from Reddit analysis."""
        try:
            from src.data.sentiment import sentiment_analyzer

            # Get Reddit sentiment summary
            summary = sentiment_analyzer.get_wsb_sentiment_summary()

            if not summary.get("available", False):
                return {
                    "sentiment": "neutral",
                    "score": 0,
                    "articles_count": 0,
                    "message": summary.get("message", "Sentiment data not available"),
                }

            # Calculate overall sentiment from trending stocks
            most_mentioned = summary.get("most_mentioned", [])
            if most_mentioned:
                avg_sentiment = sum(s.get("sentiment", 0) for s in most_mentioned) / len(most_mentioned)
                total_mentions = sum(s.get("mentions", 0) for s in most_mentioned)

                # Convert score to sentiment label
                if avg_sentiment > 0.1:
                    sentiment_label = "bullish"
                elif avg_sentiment < -0.1:
                    sentiment_label = "bearish"
                else:
                    sentiment_label = "neutral"

                return {
                    "sentiment": sentiment_label,
                    "score": round(avg_sentiment, 2),
                    "articles_count": total_mentions,  # Using mentions as article count
                    "top_stocks": most_mentioned[:5],
                }

            return {
                "sentiment": "neutral",
                "score": 0,
                "articles_count": 0,
            }
        except Exception as e:
            return {
                "sentiment": "unknown",
                "score": 0,
                "error": str(e),
            }

    def get_symbol_sentiment(self, symbol: str) -> Dict[str, Any]:
        """Get sentiment for a specific symbol from Reddit."""
        try:
            from src.data.sentiment import sentiment_analyzer

            signal_strength, description = sentiment_analyzer.get_sentiment_signal(symbol)

            if signal_strength == 0:
                return {
                    "symbol": symbol,
                    "sentiment": "neutral",
                    "score": 0,
                    "description": description,
                }

            sentiment_label = "bullish" if signal_strength > 0 else "bearish"
            return {
                "symbol": symbol,
                "sentiment": sentiment_label,
                "score": round(signal_strength, 2),
                "description": description,
            }
        except Exception as e:
            return {
                "symbol": symbol,
                "sentiment": "unknown",
                "error": str(e),
            }

    def get_news(self) -> List[Dict[str, Any]]:
        """Get recent news headlines."""
        # News provider not implemented - return empty
        return []

    def get_wsb_trending(self) -> List[Dict[str, Any]]:
        """Get WSB trending stocks from Reddit."""
        try:
            from src.data.sentiment import get_trending_with_sentiment

            trending = get_trending_with_sentiment(min_mentions=3)
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
