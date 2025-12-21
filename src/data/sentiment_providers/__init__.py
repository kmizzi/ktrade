"""
Sentiment data providers.
Multiple sources for market sentiment analysis.
"""

from src.data.sentiment_providers.quiver import QuiverQuantProvider, quiver_provider
from src.data.sentiment_providers.stocktwits import StockTwitsProvider, stocktwits_provider
from src.data.sentiment_providers.news import NewsProvider, news_provider
from src.data.sentiment_providers.aggregator import SentimentAggregator, sentiment_aggregator

__all__ = [
    'QuiverQuantProvider',
    'StockTwitsProvider',
    'NewsProvider',
    'SentimentAggregator',
    'quiver_provider',
    'stocktwits_provider',
    'news_provider',
    'sentiment_aggregator',
]
