#!/usr/bin/env python3
"""
Backtest runner script.
Tests trading strategies against historical data.

Usage:
    python scripts/run_backtest.py
    python scripts/run_backtest.py --days 180 --cash 50000
    python scripts/run_backtest.py --symbols AAPL,MSFT,GOOGL
"""

import sys
import os
import argparse
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backtest.engine import Backtester
from src.strategies.simple_momentum import SimpleMomentumStrategy


# Default symbols to test
DEFAULT_SYMBOLS = [
    # Tech
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
    # Finance
    "JPM", "BAC", "GS",
    # Healthcare
    "UNH", "JNJ", "PFE", "MRK",
    # Consumer
    "WMT", "HD", "DIS",
    # Energy
    "XOM", "CVX",
    # Meme/High Volume
    "PLTR", "SOFI"
]


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run backtest on trading strategy"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Number of days to backtest (default: 365)"
    )
    parser.add_argument(
        "--cash",
        type=float,
        default=100000.0,
        help="Initial cash amount (default: 100000)"
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated list of symbols (default: built-in list)"
    )
    parser.add_argument(
        "--trailing-stop",
        type=float,
        default=7.0,
        help="Trailing stop percentage (default: 7.0)"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Don't use cached data"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file for report (default: print to console)"
    )
    return parser.parse_args()


def progress_bar(current: int, total: int, width: int = 50):
    """Print a progress bar."""
    pct = current / total
    filled = int(width * pct)
    bar = "=" * filled + "-" * (width - filled)
    print(f"\rProgress: [{bar}] {pct*100:.1f}%", end="", flush=True)


def main():
    """Run the backtest."""
    args = parse_args()

    # Parse symbols
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = DEFAULT_SYMBOLS

    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)

    print("=" * 60)
    print("         KTRADE BACKTESTER")
    print("=" * 60)
    print(f"\nStrategy:     Simple Momentum")
    print(f"Period:       {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"Days:         {args.days}")
    print(f"Initial Cash: ${args.cash:,.2f}")
    print(f"Symbols:      {len(symbols)} stocks")
    print(f"Trailing Stop: {args.trailing_stop}%")
    print(f"\nSymbols: {', '.join(symbols[:10])}{'...' if len(symbols) > 10 else ''}")
    print("\n" + "=" * 60)

    # Initialize strategy and backtester
    strategy = SimpleMomentumStrategy(enabled=True)

    backtester = Backtester(
        strategy=strategy,
        initial_cash=args.cash,
        trailing_stop_pct=args.trailing_stop,
        use_trailing_stops=True
    )

    # Load data
    print("\nLoading historical data...")
    backtester.load_data(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        timeframe="1Day"
    )

    # Run backtest
    print("\nRunning backtest...")
    results = backtester.run(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        progress_callback=progress_bar
    )

    print("\n")  # New line after progress bar

    # Generate report
    report = backtester.get_report()

    # Output report
    if args.output:
        with open(args.output, 'w') as f:
            f.write(report)
        print(f"\nReport saved to: {args.output}")
    else:
        print(report)

    # Save equity curve
    equity_df = backtester.get_equity_curve()
    if not equity_df.empty:
        equity_file = f"data/backtest_equity_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        os.makedirs("data", exist_ok=True)
        equity_df.to_csv(equity_file, index=False)
        print(f"\nEquity curve saved to: {equity_file}")

    # Save trades
    trades_df = backtester.get_trades_df()
    if not trades_df.empty:
        trades_file = f"data/backtest_trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        trades_df.to_csv(trades_file, index=False)
        print(f"Trades saved to: {trades_file}")

    # Summary
    print("\n" + "=" * 60)
    print("QUICK SUMMARY")
    print("=" * 60)

    if results.total_return_pct >= 0:
        print(f"  Return:      +{results.total_return_pct:.2f}% (${results.net_profit:,.2f})")
    else:
        print(f"  Return:      {results.total_return_pct:.2f}% (${results.net_profit:,.2f})")

    print(f"  Sharpe:      {results.sharpe_ratio:.2f}")
    print(f"  Max DD:      {results.max_drawdown_pct:.2f}%")
    print(f"  Win Rate:    {results.win_rate_pct:.1f}%")
    print(f"  Trades:      {results.total_trades}")

    # Verdict
    print("\nVERDICT: ", end="")
    if results.sharpe_ratio > 1.0 and results.total_return_pct > 0:
        print("STRATEGY LOOKS PROMISING")
    elif results.sharpe_ratio > 0.5 and results.total_return_pct > 0:
        print("STRATEGY HAS POTENTIAL (needs optimization)")
    elif results.total_return_pct > 0:
        print("MARGINAL - high risk for returns")
    else:
        print("STRATEGY NEEDS WORK")

    return 0 if results.total_return_pct > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
