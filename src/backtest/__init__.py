"""
Backtesting framework for strategy validation.
Test strategies against historical data before live trading.
"""

from src.backtest.engine import Backtester
from src.backtest.metrics import PerformanceMetrics

__all__ = ['Backtester', 'PerformanceMetrics']
