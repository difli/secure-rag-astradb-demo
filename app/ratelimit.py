"""Simple in-memory rate limiter per user."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from fastapi import HTTPException
from app.config import config


class RateLimiter:
    """In-memory rate limiter using per-minute buckets."""
    
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.buckets: Dict[str, List[datetime]] = defaultdict(list)
    
    def _cleanup_old_entries(self, user_id: str, now: datetime):
        """Remove entries older than 1 minute."""
        cutoff = now - timedelta(minutes=1)
        self.buckets[user_id] = [
            timestamp for timestamp in self.buckets[user_id]
            if timestamp > cutoff
        ]
    
    def check_rate_limit(self, user_id: str) -> None:
        """Check if user has exceeded rate limit. Raises HTTPException if exceeded."""
        now = datetime.now(timezone.utc)
        self._cleanup_old_entries(user_id, now)
        
        if len(self.buckets[user_id]) >= self.requests_per_minute:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {self.requests_per_minute} requests per minute"
            )
        
        self.buckets[user_id].append(now)


# Global rate limiter instance (lazy initialization)
_rate_limiter_instance = None

def get_rate_limiter():
    """Get or create the global rate limiter instance."""
    global _rate_limiter_instance
    if _rate_limiter_instance is None:
        from app.config import get_config
        _rate_limiter_instance = RateLimiter(requests_per_minute=get_config().RATE_LIMIT_PER_MINUTE)
    return _rate_limiter_instance

# For backward compatibility
rate_limiter = property(lambda self: get_rate_limiter())
class _RateLimiterProxy:
    """Proxy to lazy-loaded rate limiter."""
    def __getattr__(self, name):
        return getattr(get_rate_limiter(), name)
rate_limiter = _RateLimiterProxy()

