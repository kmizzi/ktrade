"""
Stock scanner for discovering trading opportunities.
Finds hot stocks using technical criteria, volume, and price action.
"""

from typing import List, Dict, Any, Set, Optional
from datetime import datetime, timedelta
import structlog
from alpaca.data.requests import StockSnapshotRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from config.settings import settings
from src.api.alpaca_client import alpaca_client

logger = structlog.get_logger(__name__)


class StockScanner:
    """
    Scans the market for trading opportunities using technical criteria.
    Provides dynamic stock discovery to replace static watchlists.
    """

    def __init__(self):
        self.min_price = settings.min_stock_price
        self.min_volume = settings.min_daily_volume
        self.max_watchlist_size = settings.max_watchlist_size

        # Common stock universe (top liquid stocks by sector)
        # This is a curated list to scan from - real movers will be selected
        self.stock_universe = [
            # Tech
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "NFLX",
            "AMD", "INTC", "CRM", "ADBE", "ORCL", "CSCO", "AVGO",
            # Finance
            "JPM", "BAC", "WFC", "GS", "MS", "C", "V", "MA", "AXP",
            # Healthcare
            "UNH", "JNJ", "PFE", "ABBV", "TMO", "MRK", "LLY", "ABT",
            # Consumer
            "WMT", "HD", "DIS", "NKE", "SBUX", "MCD", "TGT", "COST",
            # Energy
            "XOM", "CVX", "COP", "SLB", "EOG",
            # Communications
            "T", "VZ", "CMCSA",
            # Industrial
            "BA", "CAT", "GE", "UPS", "HON",
            # Meme/High Volume
            "GME", "AMC", "PLTR", "COIN", "RIVN", "LCID", "SOFI", "HOOD"
        ]

    def get_top_gainers(self, count: int = 10) -> List[str]:
        """
        Find top gaining stocks from universe.

        Args:
            count: Number of top gainers to return

        Returns:
            List of stock symbols
        """
        try:
            gainers = []

            # Get snapshots for all stocks in universe
            for symbol in self.stock_universe:
                try:
                    bars = alpaca_client.get_bars(
                        symbol,
                        timeframe="1Day",
                        limit=2
                    )

                    if len(bars) < 2:
                        continue

                    # Calculate daily change
                    current_close = bars[-1]['close']
                    prev_close = bars[-2]['close']
                    volume = bars[-1]['volume']

                    pct_change = ((current_close - prev_close) / prev_close) * 100

                    # Filter by price and volume
                    if current_close >= self.min_price and volume >= self.min_volume:
                        gainers.append({
                            'symbol': symbol,
                            'pct_change': pct_change,
                            'price': current_close,
                            'volume': volume
                        })

                except Exception as e:
                    logger.debug("failed_to_get_data", symbol=symbol, error=str(e))
                    continue

            # Sort by percent change descending
            gainers.sort(key=lambda x: x['pct_change'], reverse=True)

            # Return top gainers
            top_gainers = [g['symbol'] for g in gainers[:count]]

            logger.info(
                "top_gainers_found",
                count=len(top_gainers),
                symbols=top_gainers,
                top_gainer=gainers[0] if gainers else None
            )

            return top_gainers

        except Exception as e:
            logger.error("failed_to_get_top_gainers", error=str(e))
            return []

    def get_high_volume_stocks(self, count: int = 10) -> List[str]:
        """
        Find stocks with unusually high volume.

        Args:
            count: Number of stocks to return

        Returns:
            List of stock symbols
        """
        try:
            high_volume = []

            for symbol in self.stock_universe:
                try:
                    # Get last 20 days for average volume
                    bars = alpaca_client.get_bars(
                        symbol,
                        timeframe="1Day",
                        limit=20
                    )

                    if len(bars) < 10:
                        continue

                    # Calculate average volume
                    volumes = [bar['volume'] for bar in bars[:-1]]  # Exclude today
                    avg_volume = sum(volumes) / len(volumes)

                    current_volume = bars[-1]['volume']
                    current_price = bars[-1]['close']

                    # Check if volume is unusual (2x+ average)
                    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

                    if (volume_ratio >= 2.0 and
                        current_price >= self.min_price and
                        current_volume >= self.min_volume):

                        high_volume.append({
                            'symbol': symbol,
                            'volume_ratio': volume_ratio,
                            'current_volume': current_volume,
                            'avg_volume': avg_volume,
                            'price': current_price
                        })

                except Exception as e:
                    logger.debug("failed_to_check_volume", symbol=symbol, error=str(e))
                    continue

            # Sort by volume ratio descending
            high_volume.sort(key=lambda x: x['volume_ratio'], reverse=True)

            # Return top high volume stocks
            top_volume = [s['symbol'] for s in high_volume[:count]]

            logger.info(
                "high_volume_stocks_found",
                count=len(top_volume),
                symbols=top_volume,
                top_volume=high_volume[0] if high_volume else None
            )

            return top_volume

        except Exception as e:
            logger.error("failed_to_get_high_volume_stocks", error=str(e))
            return []

    def get_breakout_stocks(self, count: int = 10) -> List[str]:
        """
        Find stocks breaking out to new highs.

        Args:
            count: Number of stocks to return

        Returns:
            List of stock symbols
        """
        try:
            breakouts = []

            for symbol in self.stock_universe:
                try:
                    # Get 50 days of data
                    bars = alpaca_client.get_bars(
                        symbol,
                        timeframe="1Day",
                        limit=50
                    )

                    if len(bars) < 50:
                        continue

                    current_price = bars[-1]['close']
                    current_volume = bars[-1]['volume']

                    # Get 50-day high (excluding today)
                    highs = [bar['high'] for bar in bars[:-1]]
                    fifty_day_high = max(highs)

                    # Check if breaking out
                    is_breakout = current_price > fifty_day_high

                    if (is_breakout and
                        current_price >= self.min_price and
                        current_volume >= self.min_volume):

                        pct_above_high = ((current_price - fifty_day_high) / fifty_day_high) * 100

                        breakouts.append({
                            'symbol': symbol,
                            'current_price': current_price,
                            'fifty_day_high': fifty_day_high,
                            'pct_above_high': pct_above_high,
                            'volume': current_volume
                        })

                except Exception as e:
                    logger.debug("failed_to_check_breakout", symbol=symbol, error=str(e))
                    continue

            # Sort by percent above 50-day high
            breakouts.sort(key=lambda x: x['pct_above_high'], reverse=True)

            # Return top breakouts
            top_breakouts = [b['symbol'] for b in breakouts[:count]]

            logger.info(
                "breakout_stocks_found",
                count=len(top_breakouts),
                symbols=top_breakouts,
                top_breakout=breakouts[0] if breakouts else None
            )

            return top_breakouts

        except Exception as e:
            logger.error("failed_to_get_breakout_stocks", error=str(e))
            return []

    def get_dynamic_watchlist(self) -> List[str]:
        """
        Generate dynamic watchlist by combining multiple discovery methods.

        Returns:
            List of stock symbols (up to max_watchlist_size)
        """
        try:
            logger.info("generating_dynamic_watchlist")

            # Collect stocks from various sources
            all_candidates: Set[str] = set()

            # Get top gainers
            gainers = self.get_top_gainers(count=settings.top_gainers_count)
            all_candidates.update(gainers)

            # Get high volume stocks
            high_vol = self.get_high_volume_stocks(count=settings.top_volume_count)
            all_candidates.update(high_vol)

            # Get breakouts
            breakouts = self.get_breakout_stocks(count=5)
            all_candidates.update(breakouts)

            # Add crypto (always include for diversification)
            crypto_symbols = settings.get_watchlist_crypto()
            all_candidates.update(crypto_symbols)

            # Convert to list and limit size
            watchlist = list(all_candidates)[:self.max_watchlist_size]

            logger.info(
                "dynamic_watchlist_generated",
                total_candidates=len(all_candidates),
                final_watchlist_size=len(watchlist),
                symbols=watchlist,
                sources={
                    "gainers": len(gainers),
                    "high_volume": len(high_vol),
                    "breakouts": len(breakouts),
                    "crypto": len(crypto_symbols)
                }
            )

            return watchlist

        except Exception as e:
            logger.error("failed_to_generate_dynamic_watchlist", error=str(e))
            # Fallback to static watchlist
            logger.warning("falling_back_to_static_watchlist")
            return settings.get_full_watchlist()

    def get_watchlist(self) -> List[str]:
        """
        Get watchlist (dynamic or static based on settings).

        Returns:
            List of stock symbols to monitor
        """
        if settings.enable_dynamic_discovery:
            return self.get_dynamic_watchlist()
        else:
            logger.info("using_static_watchlist")
            return settings.get_full_watchlist()


# Global stock scanner instance
stock_scanner = StockScanner()
