import time
from typing import Any, Dict, Optional
from dataclasses import dataclass
import asyncio
from app.core.config import settings


@dataclass
class CacheEntry:
    value: Any
    timestamp: float
    ttl: int


class InMemoryCache:
    def __init__(self):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()
        
    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key not in self._cache:
                return None
            
            entry = self._cache[key]
            current_time = time.time()
            
            # Check if entry has expired
            if current_time - entry.timestamp > entry.ttl:
                del self._cache[key]
                return None
            
            return entry.value
    
    async def set(self, key: str, value: Any, ttl: int) -> None:
        async with self._lock:
            self._cache[key] = CacheEntry(
                value=value,
                timestamp=time.time(),
                ttl=ttl
            )
    
    async def delete(self, key: str) -> None:
        async with self._lock:
            self._cache.pop(key, None)
    
    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()
    
    async def cleanup_expired(self) -> None:
        """Remove expired entries from cache"""
        async with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, entry in self._cache.items()
                if current_time - entry.timestamp > entry.ttl
            ]
            for key in expired_keys:
                del self._cache[key]


class CacheManager:
    def __init__(self):
        self.cache = InMemoryCache()
        # User-specific cache TTLs
        self.USER_CONTEXT_TTL = 10  # 10 seconds for user context
        self.USER_ANALYSIS_TTL = 5   # 5 seconds for analysis results
        
    async def get_pool(self, address: str) -> Optional[Any]:
        key = f"pool:{address.lower()}"
        return await self.cache.get(key)
    
    async def set_pool(self, address: str, data: Any) -> None:
        key = f"pool:{address.lower()}"
        await self.cache.set(key, data, settings.cache_ttl_pool_data)
    
    async def get_pools_list(self, filters_hash: str) -> Optional[Any]:
        key = f"pools_list:{filters_hash}"
        return await self.cache.get(key)
    
    async def set_pools_list(self, filters_hash: str, data: Any) -> None:
        key = f"pools_list:{filters_hash}"
        await self.cache.set(key, data, settings.cache_ttl_pool_list)
    
    async def get_token_info(self, address: str) -> Optional[Any]:
        key = f"token:{address.lower()}"
        return await self.cache.get(key)
    
    async def set_token_info(self, address: str, data: Any) -> None:
        key = f"token:{address.lower()}"
        await self.cache.set(key, data, settings.cache_ttl_token_info)
    
    async def get_token_price(self, address: str) -> Optional[float]:
        key = f"price:{address.lower()}"
        return await self.cache.get(key)
    
    async def set_token_price(self, address: str, price: float) -> None:
        key = f"price:{address.lower()}"
        await self.cache.set(key, price, settings.cache_ttl_token_prices)
    
    async def get_token_prices(self, addresses: list[str]) -> Dict[str, Optional[float]]:
        prices = {}
        for address in addresses:
            prices[address.lower()] = await self.get_token_price(address)
        return prices
    
    async def set_token_prices(self, prices: Dict[str, float]) -> None:
        for address, price in prices.items():
            await self.set_token_price(address, price)
    
    # User-specific cache methods
    async def get_user_context(self, user_address: str) -> Optional[Any]:
        """Get cached user context (positions, etc)."""
        key = f"user:context:{user_address.lower()}"
        return await self.cache.get(key)
    
    async def set_user_context(self, user_address: str, data: Any) -> None:
        """Cache user context with short TTL."""
        key = f"user:context:{user_address.lower()}"
        await self.cache.set(key, data, self.USER_CONTEXT_TTL)
    
    async def get_user_analysis(self, user_address: str, capital: float) -> Optional[Any]:
        """Get cached comprehensive analysis for user."""
        key = f"user:analysis:{user_address.lower()}:{capital}"
        return await self.cache.get(key)
    
    async def set_user_analysis(self, user_address: str, capital: float, data: Any) -> None:
        """Cache comprehensive analysis with very short TTL."""
        key = f"user:analysis:{user_address.lower()}:{capital}"
        await self.cache.set(key, data, self.USER_ANALYSIS_TTL)
    
    def build_user_cache_key(self, user_address: str, capital: float, prefix: str = "screen") -> str:
        """Build standardized cache key for user-specific data."""
        return f"{prefix}:{user_address.lower()}:{capital}"
    
    async def invalidate_user_cache(self, user_address: str) -> None:
        """Invalidate all cache entries for a specific user."""
        # This would need to track user keys or use pattern matching
        # For now, we'll just clear specific known keys
        context_key = f"user:context:{user_address.lower()}"
        await self.cache.delete(context_key)
    
    async def clear_all(self) -> None:
        await self.cache.clear()
    
    async def get_custom(self, key: str, ttl: Optional[int] = None) -> Optional[Any]:
        """Get a custom cache entry."""
        return await self.cache.get(key)
    
    async def set_custom(self, key: str, data: Any, ttl: int = 300) -> None:
        """Set a custom cache entry with specified TTL."""
        await self.cache.set(key, data, ttl)


# Create singleton instance
cache_manager = CacheManager()