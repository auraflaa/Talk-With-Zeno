"""
Caching Service for LLM and TTS responses
Implements in-memory caching with TTL (Time To Live) for performance optimization
"""

import hashlib
import json
import time
from typing import Optional, Dict, Any
from datetime import datetime, timedelta


class CacheService:
    """In-memory cache service for LLM and TTS responses"""
    
    def __init__(self, default_ttl_seconds: int = 3600):
        """
        Initialize cache service
        
        Args:
            default_ttl_seconds: Default time-to-live for cache entries (1 hour)
        """
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.default_ttl = default_ttl_seconds
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0
        }
    
    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """
        Generate cache key from arguments
        
        Args:
            prefix: Cache key prefix (e.g., 'llm', 'tts')
            *args: Positional arguments to include in key
            **kwargs: Keyword arguments to include in key
        
        Returns:
            MD5 hash of the serialized arguments
        """
        # Create a deterministic string from arguments
        key_data = {
            'prefix': prefix,
            'args': args,
            'kwargs': sorted(kwargs.items()) if kwargs else {}
        }
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def get(self, prefix: str, *args, **kwargs) -> Optional[Any]:
        """
        Get cached value
        
        Args:
            prefix: Cache key prefix
            *args: Positional arguments for key generation
            **kwargs: Keyword arguments for key generation
        
        Returns:
            Cached value if found and not expired, None otherwise
        """
        key = self._generate_key(prefix, *args, **kwargs)
        
        if key in self.cache:
            entry = self.cache[key]
            # Check if entry is expired
            if time.time() < entry['expires_at']:
                self.stats['hits'] += 1
                return entry['value']
            else:
                # Entry expired, remove it
                del self.cache[key]
                self.stats['evictions'] += 1
        
        self.stats['misses'] += 1
        return None
    
    def set(self, prefix: str, value: Any, ttl_seconds: Optional[int] = None, *args, **kwargs) -> None:
        """
        Set cached value
        
        Args:
            prefix: Cache key prefix
            value: Value to cache
            ttl_seconds: Time-to-live in seconds (uses default if None)
            *args: Positional arguments for key generation
            **kwargs: Keyword arguments for key generation
        """
        key = self._generate_key(prefix, *args, **kwargs)
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        
        self.cache[key] = {
            'value': value,
            'expires_at': time.time() + ttl,
            'created_at': time.time()
        }
    
    def clear(self, prefix: Optional[str] = None) -> int:
        """
        Clear cache entries
        
        Args:
            prefix: If provided, only clear entries with this prefix, otherwise clear all
        
        Returns:
            Number of entries cleared
        """
        if prefix is None:
            count = len(self.cache)
            self.cache.clear()
            return count
        
        # Clear entries with specific prefix
        keys_to_remove = [
            key for key, entry in self.cache.items()
            if entry.get('prefix') == prefix
        ]
        for key in keys_to_remove:
            del self.cache[key]
        
        return len(keys_to_remove)
    
    def cleanup_expired(self) -> int:
        """
        Remove expired entries from cache
        
        Returns:
            Number of entries removed
        """
        current_time = time.time()
        keys_to_remove = [
            key for key, entry in self.cache.items()
            if entry['expires_at'] < current_time
        ]
        
        for key in keys_to_remove:
            del self.cache[key]
            self.stats['evictions'] += 1
        
        return len(keys_to_remove)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics
        
        Returns:
            Dictionary with cache statistics
        """
        self.cleanup_expired()
        total_requests = self.stats['hits'] + self.stats['misses']
        hit_rate = (self.stats['hits'] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'size': len(self.cache),
            'hits': self.stats['hits'],
            'misses': self.stats['misses'],
            'hit_rate': hit_rate,
            'evictions': self.stats['evictions']
        }


# Singleton instance
_cache_service: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    """Get cache service instance (singleton)"""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService(default_ttl_seconds=3600)  # 1 hour default TTL
    return _cache_service

