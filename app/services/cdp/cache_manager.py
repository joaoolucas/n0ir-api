"""Intelligent caching for CDP queries."""

from typing import Optional, Dict, Any
from app.core.cache import cache
import hashlib
import json
from loguru import logger


class CDPCacheManager:
    """Intelligent caching for CDP queries."""
    
    # Cache TTLs for different query types (in seconds)
    TTL_WALLET_HISTORY = 60        # 1 minute for recent transactions
    TTL_POSITION_EVENTS = 300       # 5 minutes for position events
    TTL_SUMMARY_METRICS = 30        # 30 seconds for real-time metrics
    TTL_HISTORICAL_DATA = 3600      # 1 hour for historical data
    TTL_USDC_TRANSFERS = 120        # 2 minutes for USDC transfers
    
    @staticmethod
    def generate_cache_key(query_type: str, params: Dict[str, Any]) -> str:
        """Generate deterministic cache key from query parameters.
        
        Args:
            query_type: Type of query (e.g., 'wallet_history', 'position_events')
            params: Query parameters
            
        Returns:
            Cache key string
        """
        # Sort params for consistency
        sorted_params = json.dumps(params, sort_keys=True, default=str)
        param_hash = hashlib.md5(sorted_params.encode()).hexdigest()[:8]
        return f"cdp:{query_type}:{param_hash}"
    
    @staticmethod
    def get_ttl_for_query_type(query_type: str) -> int:
        """Get appropriate TTL based on query type.
        
        Args:
            query_type: Type of query
            
        Returns:
            TTL in seconds
        """
        ttl_map = {
            'wallet_history': CDPCacheManager.TTL_WALLET_HISTORY,
            'position_events': CDPCacheManager.TTL_POSITION_EVENTS,
            'summary_metrics': CDPCacheManager.TTL_SUMMARY_METRICS,
            'historical_data': CDPCacheManager.TTL_HISTORICAL_DATA,
            'usdc_transfers': CDPCacheManager.TTL_USDC_TRANSFERS,
            'wallet_summary': CDPCacheManager.TTL_SUMMARY_METRICS,
            'combined_wallet': CDPCacheManager.TTL_WALLET_HISTORY,
        }
        return ttl_map.get(query_type, 60)  # Default to 1 minute
    
    @staticmethod
    async def get_cached_result(
        query_type: str, 
        params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Get cached result if available.
        
        Args:
            query_type: Type of query
            params: Query parameters
            
        Returns:
            Cached result or None
        """
        cache_key = CDPCacheManager.generate_cache_key(query_type, params)
        
        try:
            cached = await cache.get(cache_key)
            if cached:
                logger.debug(f"Cache hit for {query_type}: {cache_key}")
                return cached
        except Exception as e:
            logger.warning(f"Cache get error for {cache_key}: {e}")
        
        return None
    
    @staticmethod
    async def set_cached_result(
        query_type: str,
        params: Dict[str, Any],
        result: Dict[str, Any],
        custom_ttl: Optional[int] = None
    ) -> bool:
        """Cache query result.
        
        Args:
            query_type: Type of query
            params: Query parameters
            result: Query result to cache
            custom_ttl: Optional custom TTL (overrides default)
            
        Returns:
            True if cached successfully
        """
        cache_key = CDPCacheManager.generate_cache_key(query_type, params)
        ttl = custom_ttl or CDPCacheManager.get_ttl_for_query_type(query_type)
        
        try:
            await cache.set(cache_key, result, ttl=ttl)
            logger.debug(f"Cached {query_type} result: {cache_key} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.warning(f"Cache set error for {cache_key}: {e}")
            return False
    
    @staticmethod
    async def invalidate_cache(query_type: str, params: Dict[str, Any]) -> bool:
        """Invalidate specific cache entry.
        
        Args:
            query_type: Type of query
            params: Query parameters
            
        Returns:
            True if invalidated successfully
        """
        cache_key = CDPCacheManager.generate_cache_key(query_type, params)
        
        try:
            await cache.delete(cache_key)
            logger.debug(f"Invalidated cache for {query_type}: {cache_key}")
            return True
        except Exception as e:
            logger.warning(f"Cache delete error for {cache_key}: {e}")
            return False
    
    @staticmethod
    async def invalidate_wallet_cache(wallet_address: str):
        """Invalidate all cache entries for a specific wallet.
        
        Args:
            wallet_address: Wallet address to invalidate cache for
        """
        # This would typically require a more sophisticated cache backend
        # that supports pattern-based deletion or tagging
        # For now, we log the intention
        logger.info(f"Would invalidate all cache for wallet: {wallet_address}")
    
    @staticmethod
    async def get_stale_cache(
        query_type: str,
        params: Dict[str, Any],
        max_stale_seconds: int = 3600
    ) -> Optional[Dict[str, Any]]:
        """Get potentially stale cache data as fallback.
        
        This method attempts to retrieve cached data even if it might be expired,
        useful for fallback scenarios during API failures.
        
        Args:
            query_type: Type of query
            params: Query parameters
            max_stale_seconds: Maximum staleness acceptable (default: 1 hour)
            
        Returns:
            Cached result or None
        """
        # Generate multiple cache keys with different time windows
        # This is a simplified approach - in production you'd want
        # a cache backend that supports TTL inspection
        cache_key = CDPCacheManager.generate_cache_key(query_type, params)
        
        try:
            # Try to get from cache (might be stale but still in memory)
            cached = await cache.get(cache_key)
            if cached:
                logger.info(f"Found stale cache for {query_type}: {cache_key}")
                # Mark as stale in the response
                if isinstance(cached, dict):
                    cached['_stale_cache'] = True
                return cached
        except Exception as e:
            logger.warning(f"Error retrieving stale cache for {cache_key}: {e}")
        
        return None
    
    @staticmethod
    def should_cache_result(result: Dict[str, Any]) -> bool:
        """Determine if a result should be cached.
        
        Args:
            result: Query result
            
        Returns:
            True if result should be cached
        """
        # Don't cache empty results
        if not result or not result.get('result'):
            return False
        
        # Don't cache error responses
        if result.get('error'):
            return False
        
        # Don't cache very large results (>1MB estimated)
        result_size = len(json.dumps(result, default=str))
        if result_size > 1_000_000:
            logger.warning(f"Result too large to cache: {result_size} bytes")
            return False
        
        return True