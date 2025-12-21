"""
StockTwits provider for retail trader sentiment.
Free API - no authentication required for basic access.

API docs: https://api.stocktwits.com/developers/docs
"""

import requests
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)

STOCKTWITS_BASE_URL = "https://api.stocktwits.com/api/2"


@dataclass
class StockTwitsSentiment:
    """StockTwits sentiment data for a symbol."""
    symbol: str
    bullish: int
    bearish: int
    total_messages: int
    sentiment_score: float  # -1 to 1
    timestamp: datetime


class StockTwitsProvider:
    """
    Provider for StockTwits sentiment data.
    No API key required for basic access.
    """

    def __init__(self):
        """Initialize provider."""
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_times: Dict[str, datetime] = {}
        self._cache_ttl = timedelta(minutes=10)
        self._trending_cache: List[Dict[str, Any]] = []
        self._trending_cache_time: Optional[datetime] = None

    def _is_cache_valid(self, symbol: str) -> bool:
        """Check if cache for symbol is still valid."""
        if symbol not in self._cache_times:
            return False
        return datetime.utcnow() - self._cache_times[symbol] < self._cache_ttl

    def _is_trending_cache_valid(self) -> bool:
        """Check if trending cache is still valid."""
        if not self._trending_cache_time:
            return False
        return datetime.utcnow() - self._trending_cache_time < self._cache_ttl

    def get_symbol_sentiment(
        self,
        symbol: str,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Get sentiment data for a specific symbol.

        Args:
            symbol: Stock ticker symbol
            force_refresh: Force refresh even if cached

        Returns:
            Sentiment data including bullish/bearish counts
        """
        symbol = symbol.upper()

        if not force_refresh and self._is_cache_valid(symbol):
            return self._cache[symbol]

        try:
            response = requests.get(
                f"{STOCKTWITS_BASE_URL}/streams/symbol/{symbol}.json",
                params={"filter": "all"},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()

                # Extract sentiment from messages
                messages = data.get('messages', [])
                bullish = 0
                bearish = 0

                for msg in messages:
                    sentiment = msg.get('entities', {}).get('sentiment', {})
                    if sentiment:
                        if sentiment.get('basic') == 'Bullish':
                            bullish += 1
                        elif sentiment.get('basic') == 'Bearish':
                            bearish += 1

                total = bullish + bearish
                if total > 0:
                    # Score from -1 (all bearish) to +1 (all bullish)
                    sentiment_score = (bullish - bearish) / total
                else:
                    sentiment_score = 0

                # Get symbol info
                symbol_info = data.get('symbol', {})

                result = {
                    'symbol': symbol,
                    'bullish': bullish,
                    'bearish': bearish,
                    'total_messages': len(messages),
                    'sentiment_score': sentiment_score,
                    'bullish_pct': (bullish / total * 100) if total > 0 else 50,
                    'bearish_pct': (bearish / total * 100) if total > 0 else 50,
                    'watchlist_count': symbol_info.get('watchlist_count', 0),
                    'timestamp': datetime.utcnow().isoformat(),
                }

                # Cache
                self._cache[symbol] = result
                self._cache_times[symbol] = datetime.utcnow()

                logger.debug(
                    "stocktwits_sentiment_fetched",
                    symbol=symbol,
                    bullish=bullish,
                    bearish=bearish,
                    score=sentiment_score
                )

                return result

            elif response.status_code == 404:
                logger.debug("stocktwits_symbol_not_found", symbol=symbol)
                return {
                    'symbol': symbol,
                    'bullish': 0,
                    'bearish': 0,
                    'total_messages': 0,
                    'sentiment_score': 0,
                    'error': 'Symbol not found'
                }

            elif response.status_code == 429:
                logger.warning("stocktwits_rate_limited")
                return self._cache.get(symbol, {
                    'symbol': symbol,
                    'error': 'Rate limited'
                })

            else:
                logger.error(
                    "stocktwits_api_error",
                    symbol=symbol,
                    status_code=response.status_code
                )
                return self._cache.get(symbol, {
                    'symbol': symbol,
                    'error': f'API error: {response.status_code}'
                })

        except requests.exceptions.RequestException as e:
            logger.error("stocktwits_request_failed", symbol=symbol, error=str(e))
            return self._cache.get(symbol, {
                'symbol': symbol,
                'error': str(e)
            })

    def get_trending(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Get trending stocks on StockTwits.

        Returns:
            List of trending symbols with activity data
        """
        if not force_refresh and self._is_trending_cache_valid():
            return self._trending_cache

        try:
            response = requests.get(
                f"{STOCKTWITS_BASE_URL}/trending/symbols.json",
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                symbols = data.get('symbols', [])

                trending = []
                for sym in symbols:
                    trending.append({
                        'symbol': sym.get('symbol', ''),
                        'title': sym.get('title', ''),
                        'watchlist_count': sym.get('watchlist_count', 0),
                    })

                self._trending_cache = trending
                self._trending_cache_time = datetime.utcnow()

                logger.info(
                    "stocktwits_trending_fetched",
                    count=len(trending)
                )

                return trending

            return self._trending_cache

        except Exception as e:
            logger.error("stocktwits_trending_failed", error=str(e))
            return self._trending_cache

    def get_sentiment_score(self, symbol: str) -> float:
        """
        Get sentiment score for a symbol.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Sentiment score (-1 to 1), 0 if not available
        """
        data = self.get_symbol_sentiment(symbol)
        return data.get('sentiment_score', 0.0)

    def is_bullish(self, symbol: str, threshold: float = 0.2) -> bool:
        """
        Check if sentiment for symbol is bullish.

        Args:
            symbol: Stock ticker symbol
            threshold: Minimum score to be considered bullish

        Returns:
            True if bullish
        """
        return self.get_sentiment_score(symbol) >= threshold

    def is_bearish(self, symbol: str, threshold: float = -0.2) -> bool:
        """
        Check if sentiment for symbol is bearish.

        Args:
            symbol: Stock ticker symbol
            threshold: Maximum score to be considered bearish

        Returns:
            True if bearish
        """
        return self.get_sentiment_score(symbol) <= threshold

    def get_bulk_sentiment(
        self,
        symbols: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get sentiment for multiple symbols.

        Args:
            symbols: List of stock ticker symbols

        Returns:
            Dict mapping symbol to sentiment data
        """
        results = {}
        for symbol in symbols:
            results[symbol] = self.get_symbol_sentiment(symbol)
        return results

    def is_trending(self, symbol: str) -> bool:
        """
        Check if symbol is currently trending on StockTwits.

        Args:
            symbol: Stock ticker symbol

        Returns:
            True if trending
        """
        trending = self.get_trending()
        trending_symbols = [t['symbol'].upper() for t in trending]
        return symbol.upper() in trending_symbols


# Global provider instance
stocktwits_provider = StockTwitsProvider()
