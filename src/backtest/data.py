"""
Historical data fetcher for backtesting.
Fetches and caches OHLCV data from Alpaca.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import structlog
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from config.settings import settings

logger = structlog.get_logger(__name__)

# Cache directory for historical data
CACHE_DIR = Path("data/backtest_cache")


class HistoricalDataFetcher:
    """
    Fetches and caches historical OHLCV data for backtesting.
    """

    def __init__(self):
        self.client = StockHistoricalDataClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key
        )
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def get_historical_bars(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = "1Day",
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        Get historical bar data for a symbol.

        Args:
            symbol: Stock symbol
            start_date: Start date for data
            end_date: End date for data
            timeframe: Bar timeframe (1Day, 1Hour, etc.)
            use_cache: Whether to use cached data

        Returns:
            DataFrame with OHLCV data
        """
        # Check cache first
        cache_file = self._get_cache_path(symbol, start_date, end_date, timeframe)

        if use_cache and cache_file.exists():
            logger.debug("loading_cached_data", symbol=symbol, cache_file=str(cache_file))
            return pd.read_parquet(cache_file)

        # Fetch from Alpaca
        logger.info(
            "fetching_historical_data",
            symbol=symbol,
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            timeframe=timeframe
        )

        try:
            # Map timeframe string to Alpaca TimeFrame
            tf_map = {
                "1Min": TimeFrame.Minute,
                "5Min": TimeFrame(5, "Min"),
                "15Min": TimeFrame(15, "Min"),
                "1Hour": TimeFrame.Hour,
                "1Day": TimeFrame.Day,
                "1Week": TimeFrame.Week,
            }
            tf = tf_map.get(timeframe, TimeFrame.Day)

            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                start=start_date,
                end=end_date,
                timeframe=tf
            )

            bars = self.client.get_stock_bars(request)

            if bars is None:
                logger.warning("no_data_returned", symbol=symbol)
                return pd.DataFrame()

            # Convert to DataFrame
            try:
                if hasattr(bars, 'df'):
                    df = bars.df.reset_index()
                else:
                    logger.warning("unexpected_response_format", symbol=symbol)
                    return pd.DataFrame()

                if df.empty:
                    logger.warning("empty_dataframe", symbol=symbol)
                    return pd.DataFrame()

                # Rename columns to lowercase
                df.columns = [c.lower() for c in df.columns]

                # Filter to just this symbol if multi-symbol response
                if 'symbol' in df.columns:
                    df = df[df['symbol'] == symbol].copy()

                # Ensure we have required columns
                required = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
                for col in required:
                    if col not in df.columns:
                        logger.warning("missing_column", symbol=symbol, column=col, available=list(df.columns))
                        return pd.DataFrame()

                # Add symbol column if not present
                if 'symbol' not in df.columns:
                    df['symbol'] = symbol

                logger.debug("data_fetched", symbol=symbol, rows=len(df))

            except Exception as e:
                logger.error("data_conversion_error", symbol=symbol, error=str(e))
                return pd.DataFrame()

            # Cache the data
            if use_cache:
                df.to_parquet(cache_file)
                logger.debug("data_cached", symbol=symbol, rows=len(df))

            return df

        except Exception as e:
            logger.error("failed_to_fetch_historical_data", symbol=symbol, error=str(e))
            return pd.DataFrame()

    def get_multiple_symbols(
        self,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime,
        timeframe: str = "1Day",
        use_cache: bool = True
    ) -> Dict[str, pd.DataFrame]:
        """
        Get historical data for multiple symbols.

        Args:
            symbols: List of stock symbols
            start_date: Start date
            end_date: End date
            timeframe: Bar timeframe
            use_cache: Whether to use cache

        Returns:
            Dict mapping symbol to DataFrame
        """
        data = {}
        for symbol in symbols:
            df = self.get_historical_bars(
                symbol, start_date, end_date, timeframe, use_cache
            )
            if not df.empty:
                data[symbol] = df

        logger.info(
            "historical_data_loaded",
            symbols_requested=len(symbols),
            symbols_loaded=len(data)
        )
        return data

    def _get_cache_path(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str
    ) -> Path:
        """Generate cache file path."""
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")
        filename = f"{symbol}_{start_str}_{end_str}_{timeframe}.parquet"
        return CACHE_DIR / filename

    def clear_cache(self, symbol: Optional[str] = None):
        """
        Clear cached data.

        Args:
            symbol: Specific symbol to clear, or None for all
        """
        if symbol:
            for f in CACHE_DIR.glob(f"{symbol}_*.parquet"):
                f.unlink()
                logger.debug("cache_cleared", file=str(f))
        else:
            for f in CACHE_DIR.glob("*.parquet"):
                f.unlink()
            logger.info("all_cache_cleared")


# Global instance
historical_data = HistoricalDataFetcher()
