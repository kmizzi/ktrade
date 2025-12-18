#!/usr/bin/env python3
"""
Strategy Parameter Optimization.
Tests different parameter combinations to find optimal settings.

Usage:
    python scripts/optimize_strategy.py
    python scripts/optimize_strategy.py --days 180 --quick
"""

import sys
import os
import argparse
from datetime import datetime, timedelta
from itertools import product
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple
import pandas as pd

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backtest.engine import Backtester
from src.backtest.metrics import PerformanceMetrics
from src.strategies.simple_momentum import SimpleMomentumStrategy


@dataclass
class OptimizationResult:
    """Result of a single parameter combination test."""
    params: Dict[str, Any]
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate_pct: float
    total_trades: int
    profit_factor: float


# Parameter grid to test
PARAM_GRID = {
    'rsi_buy_min': [30, 35, 40, 45],
    'rsi_buy_max': [60, 65, 70, 75],
    'rsi_sell_threshold': [70, 75, 80],
    'trailing_stop_pct': [5.0, 7.0, 10.0, 15.0],
}

# Quick mode uses fewer parameters
QUICK_PARAM_GRID = {
    'rsi_buy_min': [35, 40],
    'rsi_buy_max': [65, 70],
    'rsi_sell_threshold': [70, 75],
    'trailing_stop_pct': [5.0, 10.0],
}

# Test symbols (smaller set for faster optimization)
TEST_SYMBOLS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
    "JPM", "UNH", "XOM"
]


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Optimize strategy parameters using backtesting"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=180,
        help="Number of days to backtest (default: 180)"
    )
    parser.add_argument(
        "--cash",
        type=float,
        default=100000.0,
        help="Initial cash amount (default: 100000)"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Use reduced parameter grid for faster results"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of top results to show (default: 10)"
    )
    return parser.parse_args()


def count_combinations(param_grid: Dict) -> int:
    """Count total parameter combinations."""
    total = 1
    for values in param_grid.values():
        total *= len(values)
    return total


def generate_param_combinations(param_grid: Dict) -> List[Dict]:
    """Generate all parameter combinations."""
    keys = list(param_grid.keys())
    values = list(param_grid.values())

    combinations = []
    for combo in product(*values):
        combinations.append(dict(zip(keys, combo)))

    return combinations


def run_backtest_with_params(
    params: Dict[str, Any],
    symbols: List[str],
    start_date: datetime,
    end_date: datetime,
    initial_cash: float
) -> Tuple[PerformanceMetrics, Dict]:
    """Run a single backtest with given parameters."""

    # Create strategy with custom parameters
    strategy = SimpleMomentumStrategy(enabled=True)
    strategy.rsi_buy_min = params['rsi_buy_min']
    strategy.rsi_buy_max = params['rsi_buy_max']
    strategy.rsi_sell_threshold = params['rsi_sell_threshold']

    # Create backtester
    backtester = Backtester(
        strategy=strategy,
        initial_cash=initial_cash,
        trailing_stop_pct=params['trailing_stop_pct'],
        use_trailing_stops=True
    )

    # Override the check methods to use custom parameters
    original_check_buy = backtester._check_buy_signal
    original_check_sell = backtester._check_sell_signal

    def custom_check_buy(symbol, indicators, price):
        rsi = indicators.get('rsi')
        sma_20 = indicators.get('sma_20')
        if rsi is None or sma_20 is None:
            return False
        price_above_sma = price > sma_20
        rsi_in_range = params['rsi_buy_min'] <= rsi <= params['rsi_buy_max']
        return price_above_sma and rsi_in_range

    def custom_check_sell(symbol, indicators, price):
        rsi = indicators.get('rsi')
        sma_20 = indicators.get('sma_20')
        if rsi is None or sma_20 is None:
            return False
        rsi_overbought = rsi > params['rsi_sell_threshold']
        price_below_sma = price < sma_20
        return rsi_overbought or price_below_sma

    backtester._check_buy_signal = custom_check_buy
    backtester._check_sell_signal = custom_check_sell

    # Run backtest
    results = backtester.run(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date
    )

    return results, params


def optimize(
    param_grid: Dict,
    symbols: List[str],
    start_date: datetime,
    end_date: datetime,
    initial_cash: float
) -> List[OptimizationResult]:
    """Run optimization over all parameter combinations."""

    combinations = generate_param_combinations(param_grid)
    total = len(combinations)
    results = []

    print(f"\nTesting {total} parameter combinations...")
    print("-" * 60)

    for i, params in enumerate(combinations):
        # Progress update
        pct = (i + 1) / total * 100
        print(f"\r[{i+1}/{total}] ({pct:.1f}%) Testing: RSI {params['rsi_buy_min']}-{params['rsi_buy_max']}, "
              f"Sell>{params['rsi_sell_threshold']}, Stop={params['trailing_stop_pct']}%",
              end="", flush=True)

        try:
            metrics, tested_params = run_backtest_with_params(
                params, symbols, start_date, end_date, initial_cash
            )

            result = OptimizationResult(
                params=tested_params,
                total_return_pct=metrics.total_return_pct,
                sharpe_ratio=metrics.sharpe_ratio,
                max_drawdown_pct=metrics.max_drawdown_pct,
                win_rate_pct=metrics.win_rate_pct,
                total_trades=metrics.total_trades,
                profit_factor=metrics.profit_factor
            )
            results.append(result)

        except Exception as e:
            print(f"\n  Error with params {params}: {e}")
            continue

    print("\n")
    return results


def rank_results(results: List[OptimizationResult]) -> List[OptimizationResult]:
    """Rank results by composite score (Sharpe + Return - Drawdown)."""

    def score(r: OptimizationResult) -> float:
        # Composite score: prioritize Sharpe, then return, penalize drawdown
        # Only consider results with positive returns and trades
        if r.total_trades < 5:
            return -999
        if r.total_return_pct < 0:
            return -999 + r.total_return_pct

        sharpe_score = r.sharpe_ratio * 2  # Weight Sharpe heavily
        return_score = r.total_return_pct / 10  # Normalize return
        drawdown_penalty = r.max_drawdown_pct / 5  # Penalize drawdown
        win_rate_bonus = (r.win_rate_pct - 50) / 20  # Bonus for >50% win rate

        return sharpe_score + return_score - drawdown_penalty + win_rate_bonus

    return sorted(results, key=score, reverse=True)


def print_results(results: List[OptimizationResult], top_n: int = 10):
    """Print optimization results."""

    print("=" * 80)
    print("                    OPTIMIZATION RESULTS")
    print("=" * 80)

    if not results:
        print("No valid results found.")
        return

    ranked = rank_results(results)

    print(f"\nTop {min(top_n, len(ranked))} Parameter Combinations:")
    print("-" * 80)

    header = f"{'Rank':<5} {'RSI Buy':<10} {'RSI Sell':<10} {'Stop%':<8} {'Return%':<10} {'Sharpe':<8} {'MaxDD%':<8} {'WinRate':<8} {'Trades':<7}"
    print(header)
    print("-" * 80)

    for i, r in enumerate(ranked[:top_n], 1):
        rsi_range = f"{r.params['rsi_buy_min']}-{r.params['rsi_buy_max']}"
        print(f"{i:<5} {rsi_range:<10} >{r.params['rsi_sell_threshold']:<9} {r.params['trailing_stop_pct']:<8.1f} "
              f"{r.total_return_pct:<10.2f} {r.sharpe_ratio:<8.2f} {r.max_drawdown_pct:<8.2f} "
              f"{r.win_rate_pct:<8.1f} {r.total_trades:<7}")

    # Best result details
    best = ranked[0]
    print("\n" + "=" * 80)
    print("RECOMMENDED PARAMETERS")
    print("=" * 80)
    print(f"""
    RSI Buy Range:     {best.params['rsi_buy_min']} - {best.params['rsi_buy_max']}
    RSI Sell Threshold: > {best.params['rsi_sell_threshold']}
    Trailing Stop:      {best.params['trailing_stop_pct']}%

    Expected Performance:
    - Total Return:    {best.total_return_pct:.2f}%
    - Sharpe Ratio:    {best.sharpe_ratio:.2f}
    - Max Drawdown:    {best.max_drawdown_pct:.2f}%
    - Win Rate:        {best.win_rate_pct:.1f}%
    - Total Trades:    {best.total_trades}
    - Profit Factor:   {best.profit_factor:.2f}
""")

    # Show worst performers for contrast
    print("\nWorst Performers (avoid these settings):")
    print("-" * 80)
    worst = ranked[-3:] if len(ranked) >= 3 else ranked
    for r in reversed(worst):
        rsi_range = f"{r.params['rsi_buy_min']}-{r.params['rsi_buy_max']}"
        print(f"  RSI {rsi_range}, Sell>{r.params['rsi_sell_threshold']}, Stop={r.params['trailing_stop_pct']}% "
              f"-> Return: {r.total_return_pct:.2f}%, Sharpe: {r.sharpe_ratio:.2f}")


def save_results(results: List[OptimizationResult], filename: str):
    """Save results to CSV."""
    data = []
    for r in results:
        row = {
            'rsi_buy_min': r.params['rsi_buy_min'],
            'rsi_buy_max': r.params['rsi_buy_max'],
            'rsi_sell_threshold': r.params['rsi_sell_threshold'],
            'trailing_stop_pct': r.params['trailing_stop_pct'],
            'total_return_pct': r.total_return_pct,
            'sharpe_ratio': r.sharpe_ratio,
            'max_drawdown_pct': r.max_drawdown_pct,
            'win_rate_pct': r.win_rate_pct,
            'total_trades': r.total_trades,
            'profit_factor': r.profit_factor
        }
        data.append(row)

    df = pd.DataFrame(data)
    df = df.sort_values('sharpe_ratio', ascending=False)
    df.to_csv(filename, index=False)
    print(f"\nResults saved to: {filename}")


def main():
    """Run the optimization."""
    args = parse_args()

    # Select parameter grid
    param_grid = QUICK_PARAM_GRID if args.quick else PARAM_GRID

    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)

    print("=" * 60)
    print("         KTRADE STRATEGY OPTIMIZER")
    print("=" * 60)
    print(f"\nPeriod:       {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"Days:         {args.days}")
    print(f"Initial Cash: ${args.cash:,.2f}")
    print(f"Symbols:      {len(TEST_SYMBOLS)} stocks")
    print(f"Mode:         {'Quick' if args.quick else 'Full'}")
    print(f"Combinations: {count_combinations(param_grid)}")
    print(f"\nSymbols: {', '.join(TEST_SYMBOLS)}")

    # Run optimization
    results = optimize(
        param_grid=param_grid,
        symbols=TEST_SYMBOLS,
        start_date=start_date,
        end_date=end_date,
        initial_cash=args.cash
    )

    # Print results
    print_results(results, top_n=args.top)

    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    os.makedirs("data", exist_ok=True)
    save_results(results, f"data/optimization_results_{timestamp}.csv")

    return 0


if __name__ == "__main__":
    sys.exit(main())
