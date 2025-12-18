#!/usr/bin/env python3
"""
Test script for Reddit/WSB sentiment analysis integration.
Run this to verify Reddit API connection and sentiment analysis.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import settings


def test_reddit_client():
    """Test Reddit client connection."""
    print("\n=== Testing Reddit Client ===")

    from src.api.reddit_client import reddit_client

    if not reddit_client.is_available():
        print("Reddit client NOT available.")
        print("Please set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in .env")
        print("Get credentials at: https://www.reddit.com/prefs/apps")
        return False

    print("Reddit client initialized successfully!")

    # Test fetching WSB posts
    print("\nFetching WSB hot posts...")
    posts = reddit_client.get_wsb_hot_posts(limit=10)
    print(f"Fetched {len(posts)} posts")

    if posts:
        print("\nSample post:")
        post = posts[0]
        print(f"  Title: {post['title'][:60]}...")
        print(f"  Score: {post['score']}")
        print(f"  Tickers: {post['tickers']}")

    # Test ticker extraction
    print("\nTesting ticker extraction...")
    test_texts = [
        "AAPL to the moon! 🚀",
        "Bought $GME and $AMC calls",
        "What do you think about NVDA?",
        "I YOLO'd my life savings into TSLA puts"
    ]
    for text in test_texts:
        tickers = reddit_client.extract_tickers(text)
        print(f"  '{text}' -> {tickers}")

    return True


def test_sentiment_analyzer():
    """Test sentiment analysis."""
    print("\n=== Testing Sentiment Analyzer ===")

    from src.data.sentiment import sentiment_analyzer

    if not sentiment_analyzer.is_available():
        print("Sentiment analyzer NOT available.")
        print("Install with: pip install vaderSentiment")
        return False

    print("Sentiment analyzer initialized successfully!")

    # Test sentiment scoring
    print("\nTesting sentiment scoring...")
    test_texts = [
        "AAPL is going to the moon! This is the best investment ever!",
        "I lost everything on GME. Worst decision of my life.",
        "The stock market opened today.",
        "Diamond hands! We like the stock! 🚀🚀🚀",
        "This stock is trash, complete garbage, sell everything"
    ]

    for text in test_texts:
        scores = sentiment_analyzer.analyze_text(text)
        compound = scores['compound']
        label = "Bullish" if compound > 0.05 else "Bearish" if compound < -0.05 else "Neutral"
        print(f"  '{text[:50]}...' -> {compound:.3f} ({label})")

    return True


def test_wsb_trending():
    """Test WSB trending stocks."""
    print("\n=== Testing WSB Trending ===")

    from src.api.reddit_client import reddit_client

    if not reddit_client.is_available():
        print("Reddit client not available, skipping...")
        return False

    print("Fetching WSB trending stocks...")
    trending = reddit_client.get_wsb_trending(min_mentions=3)

    print(f"\nFound {len(trending)} trending stocks:")
    for stock in trending[:10]:
        print(f"  {stock['symbol']}: {stock['mentions']} mentions, avg score: {stock.get('avg_score', 0):.0f}")

    return True


def test_sentiment_integration():
    """Test full sentiment integration."""
    print("\n=== Testing Full Sentiment Integration ===")

    from src.data.sentiment import sentiment_analyzer, get_trending_with_sentiment

    if not settings.enable_reddit_sentiment:
        print("Reddit sentiment is disabled in settings")
        return False

    from src.api.reddit_client import reddit_client
    if not reddit_client.is_available():
        print("Reddit client not available")
        return False

    if not sentiment_analyzer.is_available():
        print("Sentiment analyzer not available")
        return False

    print("Getting trending stocks with sentiment...")
    trending = get_trending_with_sentiment(min_mentions=3)

    print(f"\nFound {len(trending)} stocks with sentiment data:")
    for stock in trending[:10]:
        sentiment = stock['sentiment_score']
        label = "Bullish" if sentiment > 0.05 else "Bearish" if sentiment < -0.05 else "Neutral"
        print(f"  {stock['symbol']}: {stock['mentions']} mentions, sentiment: {sentiment:.3f} ({label})")

    # Test WSB summary
    print("\nWSB Sentiment Summary:")
    summary = sentiment_analyzer.get_wsb_sentiment_summary()

    if summary.get('available'):
        print(f"  Total tickers: {summary['total_tickers']}")
        print(f"  Most mentioned: {[s['symbol'] for s in summary.get('most_mentioned', [])[:5]]}")
        print(f"  Most bullish: {[s['symbol'] for s in summary.get('most_bullish', [])[:3]]}")
        print(f"  Most bearish: {[s['symbol'] for s in summary.get('most_bearish', [])[:3]]}")

    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("Reddit/WSB Sentiment Analysis Test")
    print("=" * 60)

    print(f"\nSettings:")
    print(f"  Reddit enabled: {settings.enable_reddit_sentiment}")
    print(f"  Reddit client ID configured: {bool(settings.reddit_client_id)}")
    print(f"  Subreddits: {settings.get_reddit_subreddits()}")
    print(f"  WSB mention threshold: {settings.wsb_mention_threshold}")
    print(f"  Sentiment weight: {settings.sentiment_weight}")

    results = {
        "Reddit Client": test_reddit_client(),
        "Sentiment Analyzer": test_sentiment_analyzer(),
        "WSB Trending": test_wsb_trending(),
        "Full Integration": test_sentiment_integration()
    }

    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    for test_name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {test_name}: {status}")

    all_passed = all(results.values())
    print(f"\nOverall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
