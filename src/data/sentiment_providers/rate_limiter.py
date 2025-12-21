"""
Rate limiter for Alpha Vantage API.
Free tier: 25 requests/day, 5 requests/minute.

Strategy:
- Track daily requests with persistent storage
- Spread requests across trading hours (9:30 AM - 4:00 PM ET)
- Prioritize market sentiment over individual symbols
- Cache aggressively to minimize API calls
"""

import json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, Tuple
import pytz
import structlog

logger = structlog.get_logger(__name__)

# Constants
DAILY_LIMIT = 25
REQUESTS_PER_MINUTE = 5
TRADING_START_HOUR = 9
TRADING_START_MINUTE = 30
TRADING_END_HOUR = 16
TRADING_END_MINUTE = 0
ET_TIMEZONE = pytz.timezone('US/Eastern')

# Storage file for tracking requests
RATE_LIMIT_FILE = Path("data/rate_limit_state.json")


class AlphaVantageRateLimiter:
    """
    Smart rate limiter for Alpha Vantage API.
    Spreads requests across trading hours to stay within free tier limits.
    """

    def __init__(self, daily_limit: int = DAILY_LIMIT):
        self.daily_limit = daily_limit
        self._state = self._load_state()

    def _load_state(self) -> dict:
        """Load rate limit state from file."""
        try:
            if RATE_LIMIT_FILE.exists():
                with open(RATE_LIMIT_FILE, 'r') as f:
                    state = json.load(f)
                    # Reset if it's a new day
                    if state.get('date') != str(date.today()):
                        return self._new_state()
                    return state
        except Exception as e:
            logger.warning("rate_limit_state_load_failed", error=str(e))

        return self._new_state()

    def _new_state(self) -> dict:
        """Create new state for today."""
        return {
            'date': str(date.today()),
            'requests_made': 0,
            'last_request_time': None,
            'request_log': []
        }

    def _save_state(self):
        """Save rate limit state to file."""
        try:
            RATE_LIMIT_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(RATE_LIMIT_FILE, 'w') as f:
                json.dump(self._state, f, indent=2)
        except Exception as e:
            logger.warning("rate_limit_state_save_failed", error=str(e))

    def _get_et_now(self) -> datetime:
        """Get current time in Eastern timezone."""
        return datetime.now(ET_TIMEZONE)

    def is_market_hours(self) -> bool:
        """Check if currently within market hours."""
        now = self._get_et_now()

        # Weekday check (0=Monday, 6=Sunday)
        if now.weekday() >= 5:
            return False

        market_open = now.replace(
            hour=TRADING_START_HOUR,
            minute=TRADING_START_MINUTE,
            second=0,
            microsecond=0
        )
        market_close = now.replace(
            hour=TRADING_END_HOUR,
            minute=TRADING_END_MINUTE,
            second=0,
            microsecond=0
        )

        return market_open <= now <= market_close

    def get_remaining_requests(self) -> int:
        """Get number of requests remaining today."""
        # Reset if new day
        if self._state.get('date') != str(date.today()):
            self._state = self._new_state()
            self._save_state()

        return max(0, self.daily_limit - self._state['requests_made'])

    def get_requests_made_today(self) -> int:
        """Get number of requests made today."""
        if self._state.get('date') != str(date.today()):
            return 0
        return self._state['requests_made']

    def can_make_request(self, priority: str = "normal") -> Tuple[bool, str]:
        """
        Check if a request can be made now.

        Args:
            priority: "high" (market sentiment), "normal" (symbol lookup), "low" (bulk)

        Returns:
            Tuple of (can_request, reason)
        """
        remaining = self.get_remaining_requests()

        # No requests left
        if remaining <= 0:
            return False, "Daily limit reached (25 requests)"

        # Reserve some requests for high priority
        if priority == "low" and remaining <= 5:
            return False, "Reserving remaining requests for priority calls"

        if priority == "normal" and remaining <= 2:
            return False, "Reserving remaining requests for market sentiment"

        # Check per-minute rate limit
        if self._state.get('last_request_time'):
            last_time = datetime.fromisoformat(self._state['last_request_time'])
            elapsed = (datetime.now() - last_time).total_seconds()
            if elapsed < 12:  # Conservative: 5 per minute = 1 per 12 seconds
                wait_time = 12 - elapsed
                return False, f"Rate limit: wait {wait_time:.0f}s"

        return True, "OK"

    def record_request(self, endpoint: str = "unknown"):
        """Record that a request was made."""
        if self._state.get('date') != str(date.today()):
            self._state = self._new_state()

        self._state['requests_made'] += 1
        self._state['last_request_time'] = datetime.now().isoformat()
        self._state['request_log'].append({
            'time': datetime.now().isoformat(),
            'endpoint': endpoint
        })

        # Keep only last 50 entries in log
        self._state['request_log'] = self._state['request_log'][-50:]

        self._save_state()

        logger.info(
            "alpha_vantage_request_recorded",
            requests_today=self._state['requests_made'],
            remaining=self.get_remaining_requests(),
            endpoint=endpoint
        )

    def get_optimal_refresh_interval(self) -> int:
        """
        Calculate optimal refresh interval in minutes based on remaining requests.

        Returns:
            Recommended minutes between requests
        """
        remaining = self.get_remaining_requests()

        if remaining <= 0:
            return 999999  # Don't refresh

        now = self._get_et_now()

        # Calculate remaining trading minutes today
        if self.is_market_hours():
            market_close = now.replace(
                hour=TRADING_END_HOUR,
                minute=TRADING_END_MINUTE,
                second=0,
                microsecond=0
            )
            remaining_minutes = (market_close - now).total_seconds() / 60
        else:
            # Outside market hours, use 24 hours
            remaining_minutes = 24 * 60

        if remaining_minutes <= 0:
            remaining_minutes = 60  # Default fallback

        # Calculate interval (spread remaining requests over remaining time)
        # Reserve 5 requests for manual lookups
        available_for_auto = max(1, remaining - 5)
        interval = remaining_minutes / available_for_auto

        # Minimum 15 minutes, maximum 120 minutes
        return max(15, min(120, int(interval)))

    def get_status(self) -> dict:
        """Get current rate limit status."""
        return {
            'date': str(date.today()),
            'requests_made': self.get_requests_made_today(),
            'requests_remaining': self.get_remaining_requests(),
            'daily_limit': self.daily_limit,
            'is_market_hours': self.is_market_hours(),
            'recommended_interval_minutes': self.get_optimal_refresh_interval(),
            'last_request': self._state.get('last_request_time')
        }


# Global instance
rate_limiter = AlphaVantageRateLimiter()
