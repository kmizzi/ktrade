"""
News sentiment provider using Alpha Vantage News API.
Provides news sentiment analysis for stocks.

Requires Alpha Vantage API key (free tier: 25 requests/day).
Get key at: https://www.alphavantage.co/support/#api-key
"""

import requests
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger(__name__)

ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"


class NewsProvider:
    """
    Provider for news sentiment data using Alpha Vantage.
    Free tier: 25 requests/day, 5 requests/minute.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize provider.

        Args:
            api_key: Alpha Vantage API key
        """
        self.api_key = api_key
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_times: Dict[str, datetime] = {}
        self._cache_ttl = timedelta(hours=1)  # News doesn't change as frequently
        self._market_cache: Dict[str, Any] = {}
        self._market_cache_time: Optional[datetime] = None

    def set_api_key(self, api_key: str):
        """Set API key."""
        self.api_key = api_key

    def _is_cache_valid(self, symbol: str) -> bool:
        """Check if cache for symbol is still valid."""
        if symbol not in self._cache_times:
            return False
        return datetime.utcnow() - self._cache_times[symbol] < self._cache_ttl

    def _is_market_cache_valid(self) -> bool:
        """Check if market sentiment cache is valid."""
        if not self._market_cache_time:
            return False
        return datetime.utcnow() - self._market_cache_time < self._cache_ttl

    def get_news_sentiment(
        self,
        symbol: str,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Get news sentiment for a specific symbol.

        Args:
            symbol: Stock ticker symbol
            force_refresh: Force refresh even if cached

        Returns:
            News sentiment data
        """
        if not self.api_key:
            logger.warning("alpha_vantage_no_api_key")
            return {
                'symbol': symbol,
                'error': 'No API key configured',
                'sentiment_score': 0,
                'articles': []
            }

        symbol = symbol.upper()

        if not force_refresh and self._is_cache_valid(symbol):
            return self._cache[symbol]

        try:
            response = requests.get(
                ALPHA_VANTAGE_BASE,
                params={
                    "function": "NEWS_SENTIMENT",
                    "tickers": symbol,
                    "apikey": self.api_key,
                    "limit": 50,
                    "sort": "LATEST"
                },
                timeout=15
            )

            if response.status_code == 200:
                data = response.json()

                # Check for API errors
                if 'Error Message' in data or 'Note' in data:
                    error_msg = data.get('Error Message') or data.get('Note', 'API limit reached')
                    logger.warning("alpha_vantage_api_error", error=error_msg)
                    return self._cache.get(symbol, {
                        'symbol': symbol,
                        'error': error_msg,
                        'sentiment_score': 0
                    })

                # Parse news articles
                articles = data.get('feed', [])
                sentiment_scores = []
                relevance_scores = []
                bullish_count = 0
                bearish_count = 0
                neutral_count = 0

                processed_articles = []

                for article in articles:
                    # Find sentiment for our specific ticker
                    ticker_sentiment = None
                    for ts in article.get('ticker_sentiment', []):
                        if ts.get('ticker', '').upper() == symbol:
                            ticker_sentiment = ts
                            break

                    if ticker_sentiment:
                        score = float(ticker_sentiment.get('ticker_sentiment_score', 0))
                        relevance = float(ticker_sentiment.get('relevance_score', 0))
                        label = ticker_sentiment.get('ticker_sentiment_label', 'Neutral')

                        sentiment_scores.append(score)
                        relevance_scores.append(relevance)

                        if label in ['Bullish', 'Somewhat-Bullish']:
                            bullish_count += 1
                        elif label in ['Bearish', 'Somewhat-Bearish']:
                            bearish_count += 1
                        else:
                            neutral_count += 1

                        processed_articles.append({
                            'title': article.get('title', ''),
                            'url': article.get('url', ''),
                            'source': article.get('source', ''),
                            'time_published': article.get('time_published', ''),
                            'sentiment_score': score,
                            'sentiment_label': label,
                            'relevance': relevance
                        })

                # Calculate aggregate sentiment
                if sentiment_scores:
                    # Weighted by relevance
                    total_relevance = sum(relevance_scores)
                    if total_relevance > 0:
                        weighted_sentiment = sum(
                            s * r for s, r in zip(sentiment_scores, relevance_scores)
                        ) / total_relevance
                    else:
                        weighted_sentiment = sum(sentiment_scores) / len(sentiment_scores)
                else:
                    weighted_sentiment = 0

                total_labeled = bullish_count + bearish_count + neutral_count

                result = {
                    'symbol': symbol,
                    'sentiment_score': weighted_sentiment,
                    'article_count': len(processed_articles),
                    'bullish_count': bullish_count,
                    'bearish_count': bearish_count,
                    'neutral_count': neutral_count,
                    'bullish_pct': (bullish_count / total_labeled * 100) if total_labeled > 0 else 0,
                    'bearish_pct': (bearish_count / total_labeled * 100) if total_labeled > 0 else 0,
                    'articles': processed_articles[:10],  # Keep top 10
                    'timestamp': datetime.utcnow().isoformat()
                }

                # Cache
                self._cache[symbol] = result
                self._cache_times[symbol] = datetime.utcnow()

                logger.info(
                    "news_sentiment_fetched",
                    symbol=symbol,
                    articles=len(processed_articles),
                    sentiment=weighted_sentiment
                )

                return result

            else:
                logger.error(
                    "alpha_vantage_http_error",
                    status_code=response.status_code
                )
                return self._cache.get(symbol, {
                    'symbol': symbol,
                    'error': f'HTTP {response.status_code}'
                })

        except requests.exceptions.RequestException as e:
            logger.error("news_request_failed", symbol=symbol, error=str(e))
            return self._cache.get(symbol, {
                'symbol': symbol,
                'error': str(e)
            })

    def get_market_sentiment(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Get overall market news sentiment.

        Returns:
            Market-wide sentiment data
        """
        if not self.api_key:
            return {'error': 'No API key configured'}

        if not force_refresh and self._is_market_cache_valid():
            return self._market_cache

        try:
            response = requests.get(
                ALPHA_VANTAGE_BASE,
                params={
                    "function": "NEWS_SENTIMENT",
                    "topics": "financial_markets",
                    "apikey": self.api_key,
                    "limit": 50,
                    "sort": "LATEST"
                },
                timeout=15
            )

            if response.status_code == 200:
                data = response.json()

                if 'Error Message' in data or 'Note' in data:
                    return self._market_cache or {'error': 'API limit'}

                articles = data.get('feed', [])
                sentiment_scores = []

                for article in articles:
                    score = float(article.get('overall_sentiment_score', 0))
                    sentiment_scores.append(score)

                avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0

                result = {
                    'market_sentiment': avg_sentiment,
                    'article_count': len(articles),
                    'timestamp': datetime.utcnow().isoformat()
                }

                self._market_cache = result
                self._market_cache_time = datetime.utcnow()

                return result

            return self._market_cache or {}

        except Exception as e:
            logger.error("market_sentiment_failed", error=str(e))
            return self._market_cache or {}

    def get_sentiment_score(self, symbol: str) -> float:
        """
        Get news sentiment score for a symbol.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Sentiment score (-1 to 1), 0 if not available
        """
        data = self.get_news_sentiment(symbol)
        return data.get('sentiment_score', 0.0)

    def get_latest_headlines(self, symbol: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get latest news headlines for a symbol.

        Args:
            symbol: Stock ticker symbol
            limit: Max headlines to return

        Returns:
            List of headline data
        """
        data = self.get_news_sentiment(symbol)
        return data.get('articles', [])[:limit]

    def is_news_bullish(self, symbol: str, threshold: float = 0.15) -> bool:
        """
        Check if news sentiment is bullish.

        Args:
            symbol: Stock ticker symbol
            threshold: Minimum score for bullish

        Returns:
            True if bullish
        """
        return self.get_sentiment_score(symbol) >= threshold

    def is_news_bearish(self, symbol: str, threshold: float = -0.15) -> bool:
        """
        Check if news sentiment is bearish.

        Args:
            symbol: Stock ticker symbol
            threshold: Maximum score for bearish

        Returns:
            True if bearish
        """
        return self.get_sentiment_score(symbol) <= threshold

    def get_bulk_sentiment(
        self,
        symbols: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get news sentiment for multiple symbols.
        Note: Each symbol uses one API call, be mindful of rate limits.

        Args:
            symbols: List of stock ticker symbols

        Returns:
            Dict mapping symbol to sentiment data
        """
        results = {}
        for symbol in symbols:
            results[symbol] = self.get_news_sentiment(symbol)
        return results


# Global provider instance
news_provider = NewsProvider()
