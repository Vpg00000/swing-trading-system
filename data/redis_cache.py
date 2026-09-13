"""
Redis In-Memory Data & Order Book Cache Layer (TASK-052 / Phase 2 Task D).

Provides sub-5ms quote retrievals and microsecond Level-2 order book caching.
Dual-mode implementation: uses Redis client if Redis is available, or falls back to a fast
in-memory Python dictionary cache with TTL expiration if Redis is unavailable.
"""

import time
import json
import logging
from typing import Dict, Any, Optional

log = logging.getLogger(__name__)

class RedisCacheManager:
    """
    Dual-mode Cache Manager supporting Redis backend with automatic in-memory fallback.
    """
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        ttl_seconds: int = 300
    ):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.ttl_seconds = ttl_seconds
        
        self.memory_store: Dict[str, Dict[str, Any]] = {}
        self.hits = 0
        self.misses = 0
        
        self.redis_client = None
        self.is_redis_available = False
        
        # Try initializing Redis connection
        self._init_redis()

    def _init_redis(self):
        """Attempts to connect to Redis server and test availability."""
        try:
            import redis
            client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
                socket_timeout=1.0,
                decode_responses=True
            )
            if client.ping():
                self.redis_client = client
                self.is_redis_available = True
                log.info(f"RedisCacheManager: Connected to Redis at {self.host}:{self.port}")
        except Exception as err:
            self.is_redis_available = False
            self.redis_client = None
            log.info(f"RedisCacheManager: Redis server unavailable ({err}). Operating in in-memory fallback mode.")

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Stores key-value pair with expiration timestamp in Redis or memory store."""
        effective_ttl = ttl if ttl is not None else self.ttl_seconds
        
        if self.is_redis_available and self.redis_client is not None:
            try:
                val_str = json.dumps(value) if not isinstance(value, str) else value
                self.redis_client.set(key, val_str, ex=effective_ttl)
                return True
            except Exception as err:
                log.warning(f"Redis set failed ({err}), falling back to memory store for key '{key}'")
                self.is_redis_available = False
                
        # In-memory fallback
        expire_at = time.time() + effective_ttl
        self.memory_store[key] = {
            "value": value,
            "expire_at": expire_at
        }
        return True

    def get(self, key: str) -> Optional[Any]:
        """Retrieves item from cache if not expired."""
        if self.is_redis_available and self.redis_client is not None:
            try:
                val = self.redis_client.get(key)
                if val is not None:
                    self.hits += 1
                    try:
                        return json.loads(val)
                    except Exception:
                        return val
                else:
                    self.misses += 1
                    return None
            except Exception as err:
                log.warning(f"Redis get failed ({err}), falling back to memory store for key '{key}'")
                self.is_redis_available = False

        # In-memory fallback lookup
        item = self.memory_store.get(key)
        if not item:
            self.misses += 1
            return None
            
        if time.time() > item["expire_at"]:
            del self.memory_store[key]
            self.misses += 1
            return None
            
        self.hits += 1
        return item["value"]

    def delete(self, key: str) -> bool:
        """Deletes item from cache."""
        deleted = False
        if self.is_redis_available and self.redis_client is not None:
            try:
                result = self.redis_client.delete(key)
                deleted = bool(result > 0)
            except Exception as err:
                log.warning(f"Redis delete failed ({err})")
                self.is_redis_available = False

        if key in self.memory_store:
            del self.memory_store[key]
            deleted = True
            
        return deleted

    def clear(self) -> bool:
        """Clears all cached items."""
        self.memory_store.clear()
        if self.is_redis_available and self.redis_client is not None:
            try:
                self.redis_client.flushdb()
            except Exception as err:
                log.warning(f"Redis flushdb failed ({err})")
        return True

    def cleanup_expired(self) -> int:
        """Cleans up expired keys from in-memory store and returns count removed."""
        now = time.time()
        expired_keys = [k for k, v in self.memory_store.items() if now > v["expire_at"]]
        for k in expired_keys:
            del self.memory_store[k]
        return len(expired_keys)

    def get_stats(self) -> Dict[str, Any]:
        """Returns cache hit ratio and status statistics."""
        self.cleanup_expired()
        total = self.hits + self.misses
        hit_ratio = (self.hits / total * 100.0) if total > 0 else 100.0
        mode = "REDIS" if self.is_redis_available else "IN_MEMORY"
        
        total_keys = len(self.memory_store)
        if self.is_redis_available and self.redis_client is not None:
            try:
                total_keys = self.redis_client.dbsize()
            except Exception:
                pass
                
        return {
            "mode": mode,
            "is_redis_available": self.is_redis_available,
            "total_keys": total_keys,
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio_pct": round(hit_ratio, 2),
            "status": "HEALTHY"
        }

default_cache = RedisCacheManager()
