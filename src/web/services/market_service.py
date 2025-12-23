"""
Market service for fetching watchlist and market data.
"""

from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session

from src.api.alpaca_client import alpaca_client
from config.settings import settings


class MarketService:
    """Service for market data operations."""

    def __init__(self, db: Optional[Session]):
        self.db = db

    def get_symbols(self) -> List[str]:
        """Get watchlist symbols from settings."""
        symbols = []
        if settings.watchlist_stocks:
            # Handle both list and comma-separated string formats
            if isinstance(settings.watchlist_stocks, str):
                symbols.extend([s.strip() for s in settings.watchlist_stocks.split(",") if s.strip()])
            else:
                symbols.extend(settings.watchlist_stocks)
        if settings.watchlist_crypto:
            if isinstance(settings.watchlist_crypto, str):
                symbols.extend([s.strip() for s in settings.watchlist_crypto.split(",") if s.strip()])
            else:
                symbols.extend(settings.watchlist_crypto)
        return symbols

    def get_watchlist(self) -> List[Dict[str, Any]]:
        """Get watchlist with current prices."""
        symbols = self.get_symbols()
        watchlist = []

        for symbol in symbols:
            try:
                # Get latest bar
                bars = alpaca_client.get_bars(symbol, timeframe="1Day", limit=2)
                if bars and len(bars) >= 1:
                    latest = bars[-1]
                    prev = bars[-2] if len(bars) >= 2 else None

                    change = 0
                    change_pct = 0
                    if prev:
                        change = latest.get("close", 0) - prev.get("close", 0)
                        change_pct = (change / prev.get("close", 1)) * 100 if prev.get("close") else 0

                    watchlist.append({
                        "symbol": symbol,
                        "price": latest.get("close", 0),
                        "change": round(change, 2),
                        "change_pct": round(change_pct, 2),
                        "volume": latest.get("volume", 0),
                        "high": latest.get("high", 0),
                        "low": latest.get("low", 0),
                    })
            except Exception:
                watchlist.append({
                    "symbol": symbol,
                    "price": 0,
                    "change": 0,
                    "change_pct": 0,
                    "error": True,
                })

        return watchlist

    def refresh_watchlist(self) -> List[Dict[str, Any]]:
        """Refresh watchlist data (same as get_watchlist)."""
        return self.get_watchlist()

    def get_symbol_detail(self, symbol: str) -> Dict[str, Any]:
        """Get detailed data for a single symbol."""
        try:
            bars = alpaca_client.get_bars(symbol, timeframe="1Day", limit=50)
            if not bars:
                return {"symbol": symbol, "error": "No data"}

            latest = bars[-1]

            # Calculate simple indicators
            closes = [b.get("close", 0) for b in bars]
            sma_20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None

            return {
                "symbol": symbol,
                "price": latest.get("close", 0),
                "open": latest.get("open", 0),
                "high": latest.get("high", 0),
                "low": latest.get("low", 0),
                "volume": latest.get("volume", 0),
                "sma_20": round(sma_20, 2) if sma_20 else None,
                "above_sma": latest.get("close", 0) > sma_20 if sma_20 else None,
            }
        except Exception as e:
            return {"symbol": symbol, "error": str(e)}

    def get_bars(self, symbol: str, timeframe: str = "1Day", limit: int = 100) -> List[Dict[str, Any]]:
        """Get price bars for a symbol."""
        try:
            bars = alpaca_client.get_bars(symbol, timeframe=timeframe, limit=limit)
            return [
                {
                    "timestamp": b.get("timestamp"),
                    "open": b.get("open", 0),
                    "high": b.get("high", 0),
                    "low": b.get("low", 0),
                    "close": b.get("close", 0),
                    "volume": b.get("volume", 0),
                }
                for b in bars
            ]
        except Exception as e:
            return []
