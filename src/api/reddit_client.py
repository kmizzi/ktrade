"""
Reddit API client for sentiment analysis and stock discovery.
Focuses on r/wallstreetbets and other trading subreddits.
"""

import re
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timedelta
from collections import defaultdict
import structlog
import praw
from praw.models import Submission, Comment

from config.settings import settings

logger = structlog.get_logger(__name__)


# Common stock ticker pattern (1-5 uppercase letters, possibly with $)
TICKER_PATTERN = re.compile(r'\$?([A-Z]{1,5})\b')

# Words that look like tickers but aren't
TICKER_BLACKLIST = {
    # Common words
    'I', 'A', 'AN', 'THE', 'TO', 'FOR', 'OF', 'IN', 'ON', 'AT', 'BY', 'OR',
    'AND', 'IS', 'IT', 'BE', 'AS', 'ARE', 'WAS', 'SO', 'IF', 'MY', 'PM', 'AM',
    'CEO', 'CFO', 'IPO', 'ATH', 'ATL', 'DD', 'TA', 'EPS', 'PE', 'IV', 'OI',
    'ITM', 'OTM', 'ATM', 'YOLO', 'FOMO', 'FUD', 'HODL', 'LOL', 'IMO', 'IMHO',
    'TL', 'DR', 'TLDR', 'WSB', 'SEC', 'FDA', 'NYC', 'USA', 'UK', 'EU', 'US',
    'ETF', 'IRA', 'USD', 'GDP', 'CPI', 'FED', 'FOMC', 'JPM', 'BTC', 'ETH',
    # WSB specific jargon
    'MOON', 'PUTS', 'CALL', 'CALLS', 'PUT', 'BEAR', 'BULL', 'DIP', 'BUY',
    'SELL', 'HOLD', 'LONG', 'SHORT', 'GAIN', 'LOSS', 'ROPE', 'RIP', 'GUH',
    'APE', 'APES', 'WIFE', 'BF', 'GF', 'EDIT', 'UPDATE', 'NEWS', 'HELP',
    'NEED', 'WANT', 'LIKE', 'THINK', 'KNOW', 'MAKE', 'TAKE', 'JUST', 'NOW',
    'NEW', 'OLD', 'BIG', 'HIGH', 'LOW', 'ALL', 'ANY', 'GET', 'GOT', 'HAS',
    'HAD', 'HAVE', 'WILL', 'CAN', 'MAY', 'MUST', 'SHOULD', 'WOULD', 'COULD',
    'NEXT', 'LAST', 'WEEK', 'DAY', 'DAYS', 'TODAY', 'MONEY', 'CASH', 'FREE',
    'SURE', 'GOOD', 'BAD', 'BEST', 'WORST', 'MORE', 'LESS', 'MOST', 'ONLY',
    'VERY', 'MUCH', 'MANY', 'SOME', 'SHIT', 'FUCK', 'WTF', 'OMG', 'LMAO',
    'WHEN', 'WHY', 'HOW', 'WHAT', 'WHO', 'WHICH', 'WHERE', 'EVER', 'EVEN',
    'STILL', 'ALSO', 'JUST', 'BEEN', 'BEING', 'GOING', 'COME', 'CAME', 'WENT',
    'DONE', 'MADE', 'SAID', 'SAY', 'TELL', 'TOLD', 'ASK', 'ASKED', 'LOOK',
    'BECAUSE', 'AFTER', 'BEFORE', 'THEN', 'THAN', 'OVER', 'UNDER', 'ABOVE',
    'WITH', 'FROM', 'INTO', 'BACK', 'DOWN', 'OUT', 'OFF', 'OVER', 'THEY',
    'THEM', 'THEIR', 'THERE', 'HERE', 'THIS', 'THAT', 'THESE', 'THOSE',
    'EVERY', 'EACH', 'BOTH', 'FEW', 'SAME', 'OTHER', 'ANOTHER', 'SUCH',
    'DONT', 'CANT', 'WONT', 'ISNT', 'ARENT', 'WASNT', 'WERENT', 'HAVENT',
    'HASNT', 'HADNT', 'DIDNT', 'DOESNT', 'WOULDNT', 'COULDNT', 'SHOULDNT',
}

# Known valid stock tickers to always include
KNOWN_TICKERS = {
    'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'META', 'NVDA', 'TSLA', 'NFLX',
    'AMD', 'INTC', 'CRM', 'ADBE', 'ORCL', 'CSCO', 'AVGO', 'QCOM', 'TXN',
    'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'V', 'MA', 'AXP', 'PYPL', 'SQ',
    'UNH', 'JNJ', 'PFE', 'ABBV', 'TMO', 'MRK', 'LLY', 'ABT', 'BMY', 'GILD',
    'WMT', 'HD', 'DIS', 'NKE', 'SBUX', 'MCD', 'TGT', 'COST', 'LOW', 'TJX',
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY', 'PSX', 'VLO', 'MPC', 'HAL',
    'T', 'VZ', 'CMCSA', 'TMUS', 'CHTR',
    'BA', 'CAT', 'GE', 'UPS', 'HON', 'RTX', 'LMT', 'NOC', 'GD',
    # Meme stocks
    'GME', 'AMC', 'BBBY', 'BB', 'NOK', 'PLTR', 'COIN', 'RIVN', 'LCID',
    'SOFI', 'HOOD', 'WISH', 'CLOV', 'SPCE', 'TLRY', 'SNDL',
    # Popular ETFs that might be discussed
    'SPY', 'QQQ', 'IWM', 'DIA', 'VTI', 'VOO', 'ARKK', 'XLF', 'XLE', 'XLK',
}


class RedditClient:
    """
    Reddit API client for extracting stock mentions and sentiment from trading subreddits.
    """

    def __init__(self):
        self._reddit: Optional[praw.Reddit] = None
        self._initialized = False
        self._last_error: Optional[str] = None

    def _initialize(self) -> bool:
        """
        Initialize Reddit API connection.
        Returns True if successful, False otherwise.
        """
        if self._initialized and self._reddit:
            return True

        if not settings.reddit_client_id or not settings.reddit_client_secret:
            logger.warning(
                "reddit_credentials_missing",
                message="Reddit API credentials not configured. Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in .env"
            )
            return False

        try:
            self._reddit = praw.Reddit(
                client_id=settings.reddit_client_id,
                client_secret=settings.reddit_client_secret,
                user_agent=settings.reddit_user_agent,
                check_for_async=False
            )
            # Test the connection by fetching read-only status
            _ = self._reddit.read_only
            self._initialized = True
            logger.info("reddit_client_initialized", read_only=True)
            return True

        except Exception as e:
            self._last_error = str(e)
            logger.error("reddit_init_failed", error=str(e))
            return False

    def is_available(self) -> bool:
        """Check if Reddit client is available and configured."""
        return self._initialize()

    def extract_tickers(self, text: str) -> Set[str]:
        """
        Extract stock tickers from text.

        Args:
            text: Text to extract tickers from

        Returns:
            Set of valid ticker symbols
        """
        if not text:
            return set()

        # Find all potential tickers
        matches = TICKER_PATTERN.findall(text.upper())

        # Filter to valid tickers
        tickers = set()
        for match in matches:
            # Skip blacklisted words
            if match in TICKER_BLACKLIST:
                continue
            # Include known tickers or tickers that are 2-5 characters
            if match in KNOWN_TICKERS or (2 <= len(match) <= 5):
                tickers.add(match)

        return tickers

    def get_wsb_hot_posts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get hot posts from r/wallstreetbets.

        Args:
            limit: Number of posts to fetch

        Returns:
            List of post data dictionaries
        """
        if not self._initialize():
            return []

        try:
            posts = []
            subreddit = self._reddit.subreddit("wallstreetbets")

            for submission in subreddit.hot(limit=limit):
                tickers = self.extract_tickers(f"{submission.title} {submission.selftext}")

                posts.append({
                    'id': submission.id,
                    'title': submission.title,
                    'selftext': submission.selftext[:500] if submission.selftext else '',
                    'score': submission.score,
                    'upvote_ratio': submission.upvote_ratio,
                    'num_comments': submission.num_comments,
                    'created_utc': datetime.utcfromtimestamp(submission.created_utc),
                    'tickers': list(tickers),
                    'flair': submission.link_flair_text,
                    'url': f"https://reddit.com{submission.permalink}"
                })

            logger.info(
                "wsb_hot_posts_fetched",
                count=len(posts),
                total_tickers=sum(len(p['tickers']) for p in posts)
            )
            return posts

        except Exception as e:
            logger.error("failed_to_fetch_wsb_posts", error=str(e))
            return []

    def get_subreddit_posts(
        self,
        subreddit_name: str,
        sort: str = "hot",
        limit: int = 50,
        time_filter: str = "day"
    ) -> List[Dict[str, Any]]:
        """
        Get posts from a subreddit.

        Args:
            subreddit_name: Name of subreddit
            sort: Sort method (hot, new, top, rising)
            limit: Number of posts to fetch
            time_filter: Time filter for top posts (hour, day, week, month, year, all)

        Returns:
            List of post data dictionaries
        """
        if not self._initialize():
            return []

        try:
            posts = []
            subreddit = self._reddit.subreddit(subreddit_name)

            if sort == "hot":
                submissions = subreddit.hot(limit=limit)
            elif sort == "new":
                submissions = subreddit.new(limit=limit)
            elif sort == "top":
                submissions = subreddit.top(time_filter=time_filter, limit=limit)
            elif sort == "rising":
                submissions = subreddit.rising(limit=limit)
            else:
                submissions = subreddit.hot(limit=limit)

            for submission in submissions:
                tickers = self.extract_tickers(f"{submission.title} {submission.selftext}")

                posts.append({
                    'id': submission.id,
                    'subreddit': subreddit_name,
                    'title': submission.title,
                    'selftext': submission.selftext[:500] if submission.selftext else '',
                    'score': submission.score,
                    'upvote_ratio': submission.upvote_ratio,
                    'num_comments': submission.num_comments,
                    'created_utc': datetime.utcfromtimestamp(submission.created_utc),
                    'tickers': list(tickers),
                    'flair': submission.link_flair_text,
                    'url': f"https://reddit.com{submission.permalink}"
                })

            logger.debug(
                "subreddit_posts_fetched",
                subreddit=subreddit_name,
                count=len(posts)
            )
            return posts

        except Exception as e:
            logger.error(
                "failed_to_fetch_subreddit_posts",
                subreddit=subreddit_name,
                error=str(e)
            )
            return []

    def get_ticker_mentions(
        self,
        subreddits: Optional[List[str]] = None,
        hours_back: int = 24,
        limit_per_sub: int = 100
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get ticker mention counts and sentiment data across subreddits.

        Args:
            subreddits: List of subreddits to search (default: from settings)
            hours_back: How far back to look for posts
            limit_per_sub: Posts to fetch per subreddit

        Returns:
            Dict mapping ticker to mention data:
            {
                'AAPL': {
                    'mentions': 15,
                    'total_score': 5000,
                    'avg_upvote_ratio': 0.85,
                    'posts': [post_ids...],
                    'subreddits': {'wallstreetbets': 10, 'stocks': 5}
                }
            }
        """
        if not self._initialize():
            return {}

        if subreddits is None:
            subreddits = settings.get_reddit_subreddits()

        cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
        ticker_data: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            'mentions': 0,
            'total_score': 0,
            'upvote_ratios': [],
            'posts': [],
            'subreddits': defaultdict(int),
            'sample_titles': []
        })

        for subreddit_name in subreddits:
            try:
                posts = self.get_subreddit_posts(
                    subreddit_name,
                    sort="hot",
                    limit=limit_per_sub
                )

                for post in posts:
                    # Filter by time
                    if post['created_utc'] < cutoff_time:
                        continue

                    for ticker in post['tickers']:
                        data = ticker_data[ticker]
                        data['mentions'] += 1
                        data['total_score'] += post['score']
                        data['upvote_ratios'].append(post['upvote_ratio'])
                        data['posts'].append(post['id'])
                        data['subreddits'][subreddit_name] += 1
                        if len(data['sample_titles']) < 3:
                            data['sample_titles'].append(post['title'][:100])

            except Exception as e:
                logger.error(
                    "failed_to_process_subreddit",
                    subreddit=subreddit_name,
                    error=str(e)
                )
                continue

        # Calculate averages and clean up
        result = {}
        for ticker, data in ticker_data.items():
            if data['mentions'] > 0:
                result[ticker] = {
                    'mentions': data['mentions'],
                    'total_score': data['total_score'],
                    'avg_score': data['total_score'] / data['mentions'],
                    'avg_upvote_ratio': sum(data['upvote_ratios']) / len(data['upvote_ratios']),
                    'posts': data['posts'][:10],  # Limit stored posts
                    'subreddits': dict(data['subreddits']),
                    'sample_titles': data['sample_titles']
                }

        logger.info(
            "ticker_mentions_compiled",
            unique_tickers=len(result),
            subreddits_searched=len(subreddits),
            top_mentioned=sorted(
                result.items(),
                key=lambda x: x[1]['mentions'],
                reverse=True
            )[:5] if result else []
        )

        return result

    def get_wsb_trending(self, min_mentions: int = 5) -> List[Dict[str, Any]]:
        """
        Get trending stocks on r/wallstreetbets.

        Args:
            min_mentions: Minimum mentions to be considered trending

        Returns:
            List of trending stocks with mention data, sorted by mentions
        """
        if not self._initialize():
            return []

        # Focus on WSB only for this method
        mentions = self.get_ticker_mentions(
            subreddits=['wallstreetbets'],
            hours_back=24,
            limit_per_sub=200
        )

        trending = []
        for ticker, data in mentions.items():
            if data['mentions'] >= min_mentions:
                trending.append({
                    'symbol': ticker,
                    'mentions': data['mentions'],
                    'total_score': data['total_score'],
                    'avg_score': data['avg_score'],
                    'avg_upvote_ratio': data['avg_upvote_ratio'],
                    'sample_titles': data['sample_titles']
                })

        # Sort by mentions
        trending.sort(key=lambda x: x['mentions'], reverse=True)

        logger.info(
            "wsb_trending_stocks",
            count=len(trending),
            stocks=[t['symbol'] for t in trending[:10]]
        )

        return trending

    def get_daily_discussion_tickers(self) -> List[str]:
        """
        Extract tickers from today's WSB Daily Discussion thread.

        Returns:
            List of mentioned tickers sorted by frequency
        """
        if not self._initialize():
            return []

        try:
            subreddit = self._reddit.subreddit("wallstreetbets")

            # Find daily discussion thread
            daily_thread = None
            for submission in subreddit.hot(limit=10):
                title_lower = submission.title.lower()
                if 'daily discussion' in title_lower or 'what are your moves' in title_lower:
                    daily_thread = submission
                    break

            if not daily_thread:
                logger.debug("wsb_daily_thread_not_found")
                return []

            # Get top-level comments
            daily_thread.comments.replace_more(limit=0)
            ticker_counts: Dict[str, int] = defaultdict(int)

            for comment in daily_thread.comments[:200]:  # Limit comments processed
                tickers = self.extract_tickers(comment.body)
                for ticker in tickers:
                    ticker_counts[ticker] += 1

            # Sort by frequency
            sorted_tickers = sorted(
                ticker_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )

            result = [ticker for ticker, count in sorted_tickers if count >= 2]

            logger.info(
                "wsb_daily_discussion_tickers",
                total_unique=len(ticker_counts),
                filtered_count=len(result),
                top_tickers=result[:10]
            )

            return result[:20]  # Return top 20

        except Exception as e:
            logger.error("failed_to_get_daily_discussion", error=str(e))
            return []


# Global Reddit client instance
reddit_client = RedditClient()
