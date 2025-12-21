"""
Trading strategies for KTrade.
"""

from src.strategies.base import BaseStrategy, Signal
from src.strategies.simple_momentum import SimpleMomentumStrategy
from src.strategies.news_momentum import NewsMomentumStrategy

__all__ = [
    'BaseStrategy',
    'Signal',
    'SimpleMomentumStrategy',
    'NewsMomentumStrategy',
]
