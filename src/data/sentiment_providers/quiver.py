"""
Quiver Quant provider for WallStreetBets sentiment data.
Tracks WSB mentions, trending stocks, and sentiment.

Free tier available at: https://www.quiverquant.com/
"""

import requests
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)

# Quiver Quant API endpoints
QUIVER_BASE_URL = "https://api.quiverquant.com/beta"
QUIVER_WSB_ENDPOINT = f"{QUIVER_BASE_URL}/live/wallstreetbets"
QUIVER_WSB_HISTORICAL = f"{QUIVER_BASE_URL}/historical/wallstreetbets"


@dataclass
class WSBMention:
    """WSB stock mention data."""
    symbol: str
    mentions: int
    rank: int
    sentiment: float  # -1 to 1
    timestamp: datetime


class QuiverQuantProvider:
    """
    Provider for Quiver Quant WSB data.
    Tracks WallStreetBets mentions and sentiment.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize provider.

        Args:
            api_key: Quiver Quant API key (optional for some endpoints)
        """
        self.api_key = api_key
        self._cache: Dict[str, Any] = {}
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=15)

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers."""
        headers = {
            "Accept": "application/json",
            "User-Agent": "KTrade/1.0"
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if not self._cache_time:
            return False
        return datetime.utcnow() - self._cache_time < self._cache_ttl

    def get_wsb_trending(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Get current WSB trending stocks.

        Returns:
            List of trending stocks with mention counts and sentiment
        """
        if not force_refresh and self._is_cache_valid() and 'trending' in self._cache:
            return self._cache['trending']

        try:
            response = requests.get(
                QUIVER_WSB_ENDPOINT,
                headers=self._get_headers(),
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()

                # Parse response
                trending = []
                for item in data:
                    trending.append({
                        'symbol': item.get('Ticker', ''),
                        'mentions': item.get('Mentions', 0),
                        'rank': item.get('Rank', 0),
                        'sentiment': item.get('Sentiment', 0),
                        'date': item.get('Date', ''),
                    })

                # Cache results
                self._cache['trending'] = trending
                self._cache_time = datetime.utcnow()

                logger.info(
                    "quiver_wsb_data_fetched",
                    stocks_count=len(trending),
                    top_stock=trending[0]['symbol'] if trending else None
                )

                return trending

            elif response.status_code == 401:
                # Quiver Quant now requires paid API subscription
                logger.warning(
                    "quiver_auth_required",
                    message="Quiver Quant API requires subscription. WSB data disabled."
                )
                return []

            elif response.status_code == 429:
                logger.warning("quiver_rate_limited")
                return self._cache.get('trending', [])

            else:
                logger.error(
                    "quiver_api_error",
                    status_code=response.status_code,
                    response=response.text[:200]
                )
                return self._cache.get('trending', [])

        except requests.exceptions.RequestException as e:
            logger.error("quiver_request_failed", error=str(e))
            return self._cache.get('trending', [])

    def get_symbol_mentions(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get WSB mention data for a specific symbol.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Mention data or None if not found
        """
        trending = self.get_wsb_trending()

        for stock in trending:
            if stock['symbol'].upper() == symbol.upper():
                return stock

        return None

    def get_sentiment_score(self, symbol: str) -> float:
        """
        Get WSB sentiment score for a symbol.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Sentiment score (-1 to 1), 0 if not found
        """
        data = self.get_symbol_mentions(symbol)
        if data:
            return data.get('sentiment', 0)
        return 0.0

    def get_mention_count(self, symbol: str) -> int:
        """
        Get WSB mention count for a symbol.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Mention count, 0 if not found
        """
        data = self.get_symbol_mentions(symbol)
        if data:
            return data.get('mentions', 0)
        return 0

    def is_wsb_trending(self, symbol: str, min_mentions: int = 10) -> bool:
        """
        Check if a symbol is currently trending on WSB.

        Args:
            symbol: Stock ticker symbol
            min_mentions: Minimum mentions to be considered trending

        Returns:
            True if trending
        """
        data = self.get_symbol_mentions(symbol)
        if data:
            return data.get('mentions', 0) >= min_mentions
        return False

    def get_top_bullish(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get top bullish stocks on WSB.

        Args:
            limit: Max stocks to return

        Returns:
            List of bullish stocks sorted by sentiment
        """
        trending = self.get_wsb_trending()
        bullish = [s for s in trending if s.get('sentiment', 0) > 0.1]
        bullish.sort(key=lambda x: x.get('sentiment', 0), reverse=True)
        return bullish[:limit]

    def get_top_mentioned(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get most mentioned stocks on WSB.

        Args:
            limit: Max stocks to return

        Returns:
            List of stocks sorted by mention count
        """
        trending = self.get_wsb_trending()
        trending.sort(key=lambda x: x.get('mentions', 0), reverse=True)
        return trending[:limit]

    def get_historical_mentions(
        self,
        symbol: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get historical WSB mention data for a symbol.

        Args:
            symbol: Stock ticker symbol
            days: Number of days of history

        Returns:
            List of historical mention data
        """
        try:
            response = requests.get(
                f"{QUIVER_WSB_HISTORICAL}/{symbol}",
                headers=self._get_headers(),
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()

                # Filter to requested days
                cutoff = datetime.utcnow() - timedelta(days=days)
                historical = []

                for item in data:
                    try:
                        date = datetime.strptime(item.get('Date', ''), '%Y-%m-%d')
                        if date >= cutoff:
                            historical.append({
                                'date': date,
                                'mentions': item.get('Mentions', 0),
                                'rank': item.get('Rank', 0),
                                'sentiment': item.get('Sentiment', 0),
                            })
                    except ValueError:
                        continue

                return historical

            return []

        except Exception as e:
            logger.error("quiver_historical_failed", symbol=symbol, error=str(e))
            return []


# Global provider instance
quiver_provider = QuiverQuantProvider()
