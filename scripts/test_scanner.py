"""
Test the stock scanner to see what it finds.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.logger import setup_logging
from src.data.stock_scanner import stock_scanner
from config.settings import settings

# Setup logging
logger = setup_logging()


def main():
    """Test stock scanner"""
    logger.info("testing_stock_scanner")

    print("\n" + "="*60)
    print("STOCK SCANNER TEST")
    print("="*60)

    # Test top gainers
    print("\n📈 TOP GAINERS:")
    gainers = stock_scanner.get_top_gainers(count=5)
    for i, symbol in enumerate(gainers, 1):
        print(f"  {i}. {symbol}")

    # Test high volume
    print("\n📊 HIGH VOLUME STOCKS:")
    high_vol = stock_scanner.get_high_volume_stocks(count=5)
    for i, symbol in enumerate(high_vol, 1):
        print(f"  {i}. {symbol}")

    # Test breakouts
    print("\n🚀 BREAKOUT STOCKS:")
    breakouts = stock_scanner.get_breakout_stocks(count=5)
    for i, symbol in enumerate(breakouts, 1):
        print(f"  {i}. {symbol}")

    # Test full watchlist
    print("\n🎯 DYNAMIC WATCHLIST (What the bot will trade):")
    watchlist = stock_scanner.get_dynamic_watchlist()
    print(f"  Total stocks: {len(watchlist)}")
    for i, symbol in enumerate(watchlist, 1):
        print(f"  {i}. {symbol}")

    print("\n" + "="*60)
    print(f"Dynamic Discovery Enabled: {settings.enable_dynamic_discovery}")
    print(f"Max Watchlist Size: {settings.max_watchlist_size}")
    print(f"Min Stock Price: ${settings.min_stock_price}")
    print(f"Min Daily Volume: {settings.min_daily_volume:,}")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
