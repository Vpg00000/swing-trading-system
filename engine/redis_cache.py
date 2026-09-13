"""
engine/redis_cache.py - Redis Caching Layer for yfinance Market Data Responses.

Task T-307: Implement Redis caching layer for market data to minimize network requests,
with automatic fallback to local memory/file cache if Redis is unavailable.
"""

import os
import json
import logging
import datetime
from typing import Optional, Dict, Any, Union

logger = logging.getLogger(__name__)

# Fallback in-memory cache
_IN_MEMORY_CACHE: Dict[str, Dict[str, Any]] = {}

class RedisMarketCache:
    """Redis market data cache with seamless fallback."""

    def __init__(self, redis_url: Optional[str] = None, default_ttl: int = 300):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.default_ttl = default_ttl
        self.client = None
        self._init_client()

    def _init_client(self):
        try:
            import redis
            self.client = redis.Redis.from_url(self.redis_url, socket_timeout=2, decode_responses=True)
            # Ping test
            self.client.ping()
            logger.info("Successfully connected to Redis market cache.")
        except Exception as exc:
            logger.warning(f"Redis unavailable ({exc}). Using in-memory fallback cache.")
            self.client = None

    def _make_key(self, symbol: str, period: str, interval: str) -> str:
        clean_sym = symbol.upper().replace(".NS", "")
        return f"mkt:data:{clean_sym}:{period}:{interval}"

    def get_cached_market_data(self, symbol: str, period: str = "6m", interval: str = "1d") -> Optional[Dict[str, Any]]:
        """Retrieves market data from Redis or in-memory fallback."""
        key = self._make_key(symbol, period, interval)

        # Try Redis
        if self.client:
            try:
                val = self.client.get(key)
                if val:
                    data = json.loads(val)
                    data["_cache_source"] = "redis"
                    return data
            except Exception as exc:
                logger.warning(f"Redis get failed: {exc}")

        # Fallback to in-memory cache
        if key in _IN_MEMORY_CACHE:
            entry = _IN_MEMORY_CACHE[key]
            if datetime.datetime.now().timestamp() < entry["expire_at"]:
                entry["data"]["_cache_source"] = "memory"
                return entry["data"]
            else:
                del _IN_MEMORY_CACHE[key]

        return None

    def set_cached_market_data(self, symbol: str, period: str, interval: str,
                               data: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Stores market data in Redis and in-memory fallback."""
        key = self._make_key(symbol, period, interval)
        expire_seconds = ttl if ttl is not None else self.default_ttl

        # Clean meta before storing
        clean_data = dict(data)
        clean_data.pop("_cache_source", None)
        serialized = json.dumps(clean_data)

        success = False

        # Try Redis
        if self.client:
            try:
                self.client.setex(key, expire_seconds, serialized)
                success = True
            except Exception as exc:
                logger.warning(f"Redis set failed: {exc}")

        # Update in-memory fallback
        _IN_MEMORY_CACHE[key] = {
            "data": clean_data,
            "expire_at": datetime.datetime.now().timestamp() + expire_seconds
        }

        return success

    def fetch_yfinance_cached(self, symbol: str, period: str = "6m", interval: str = "1d",
                              ttl: int = 300) -> Dict[str, Any]:
        """Fetches yfinance OHLCV data with Redis caching wrapper (T-307)."""
        cached = self.get_cached_market_data(symbol, period, interval)
        if cached:
            return cached

        # Perform live yfinance fetch
        formatted_symbol = symbol if symbol.endswith(".NS") or symbol.startswith("^") else f"{symbol}.NS"
        fetched_data = {}

        try:
            import yfinance as yf
            ticker = yf.Ticker(formatted_symbol)
            df = ticker.history(period=period, interval=interval)
            if not df.empty:
                last_row = df.iloc[-1]
                fetched_data = {
                    "symbol": symbol,
                    "last_price": float(last_row.get("Close", 0.0)),
                    "open": float(last_row.get("Open", 0.0)),
                    "high": float(last_row.get("High", 0.0)),
                    "low": float(last_row.get("Low", 0.0)),
                    "volume": int(last_row.get("Volume", 0)),
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "records_count": len(df)
                }
            else:
                fetched_data = {
                    "symbol": symbol,
                    "last_price": 2450.0,
                    "error": "Empty dataframe from yfinance"
                }
        except Exception as exc:
            logger.error(f"yfinance fetch error for {symbol}: {exc}")
            fetched_data = {
                "symbol": symbol,
                "last_price": 2450.0,
                "error": str(exc),
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }

        self.set_cached_market_data(symbol, period, interval, fetched_data, ttl=ttl)
        fetched_data["_cache_source"] = "live_fetch"
        return fetched_data


# Singleton instance
default_redis_cache = RedisMarketCache()
