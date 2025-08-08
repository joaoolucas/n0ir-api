import sys
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any
from web3 import Web3

# Add SDK path to system path
sdk_path = Path("/home/mortiee/projects/n0ir/sdk")
if str(sdk_path) not in sys.path:
    sys.path.insert(0, str(sdk_path))

from n0ir_sdk.pools import PoolsClient, PoolFilters, PoolAPRData, TokenInfo
from n0ir_sdk.pools.utils import fetch_token_prices

from app.core.config import settings
from app.core.cache import cache_manager


class PoolsService:
    def __init__(self):
        self._client: Optional[PoolsClient] = None
        self._w3: Optional[Web3] = None
        
    async def _get_client(self) -> PoolsClient:
        """Get or create PoolsClient instance"""
        if self._client is None:
            self._client = PoolsClient(rpc_url=settings.rpc_url)
            self._w3 = self._client.w3
        return self._client
    
    def _get_filters_hash(self, filters: PoolFilters) -> str:
        """Generate a hash for the filters to use as cache key"""
        filter_str = f"{filters.pool_type}:{filters.min_tvl_usd}:{filters.min_volume_24h}:{filters.min_apr}:{','.join(filters.blacklisted_tokens)}:{filters.limit}"
        return hashlib.md5(filter_str.encode()).hexdigest()
    
    async def get_pools(
        self,
        pool_type: str = "all",
        min_tvl: float = 1000,
        min_volume_24h: float = 10000,
        min_apr: float = 0,
        blacklist: Optional[List[str]] = None,
        limit: Optional[int] = 100,
        offset: Optional[int] = None,
        sort_by: str = "apr",
        sort_order: str = "desc"
    ) -> Dict:
        """Get pools with filters - optimized version"""
        # Check cache first
        cache_key = f"{pool_type}:{min_tvl}:{min_volume_24h}:{min_apr}:{','.join(blacklist or [])}:{limit}:{offset}:{sort_by}:{sort_order}"
        filters_hash = hashlib.md5(cache_key.encode()).hexdigest()
        cached_result = await cache_manager.get_pools_list(filters_hash)
        
        if cached_result is not None:
            return cached_result
        
        # For fast initial loading, skip expensive operations
        # We'll fetch basic pool data without individual price lookups
        client = await self._get_client()
        
        # Directly fetch from Sugar contract
        pools_raw = await self._fetch_pools_fast(client, pool_type, blacklist)
        
        # Quick filtering without price fetches
        filtered_pools = []
        for pool_data in pools_raw:
            # Basic TVL check (use reserves as proxy if no prices)
            if min_tvl > 1000:  # Only apply if significant TVL filter
                reserve0 = int(pool_data[8])  # RESERVE0 field (index 8)
                reserve1 = int(pool_data[11])  # RESERVE1 field (index 11)
                # Skip pools with very low reserves
                if reserve0 < 1e15 and reserve1 < 1e15:  # Rough filter
                    continue
            
            filtered_pools.append(pool_data)
        
        # Convert to response format with minimal processing
        pools = await self._process_pools_minimal(filtered_pools[:limit or 100])
        
        result = {
            "pools": pools,
            "pagination": {
                "total": len(filtered_pools),
                "limit": limit or 100,
                "offset": offset or 0,
                "has_more": (offset or 0) + (limit or 100) < len(filtered_pools)
            }
        }
        
        # Cache with shorter TTL for quick responses
        await cache_manager.set_pools_list(filters_hash, result)
        return result
    
    async def _fetch_pools_fast(self, client, pool_type: str, blacklist: Optional[List[str]]) -> List:
        """Fast pool fetching without price data"""
        sugar = client.sugar
        pools = []
        offset = 8100
        limit = 500
        
        # Sugar field indices based on the actual ABI structure
        LP = 0
        TYPE = 4  # tick_spacing for CL pools
        TICK = 5
        SQRT_RATIO = 6
        TOKEN0 = 7
        RESERVE0 = 8
        STAKED0 = 9
        TOKEN1 = 10
        RESERVE1 = 11
        STAKED1 = 12
        GAUGE = 13
        GAUGE_ALIVE = 15
        EMISSIONS = 19
        
        while True:
            try:
                result = sugar.functions.all(limit, offset).call()
                
                if not result:
                    break
                
                # Filter CL pools with active gauges
                for pool in result:
                    # Check if it's a CL pool (TYPE > 0) and has active gauge
                    if int(pool[TYPE]) > 0 and pool[GAUGE_ALIVE]:
                        # Apply type filter
                        tick_spacing = int(pool[TYPE])
                        is_stable = tick_spacing in settings.stable_tick_spacings
                        
                        if pool_type == "all":
                            pools.append(pool)
                        elif pool_type == "stable" and is_stable:
                            pools.append(pool)
                        elif pool_type == "volatile" and not is_stable:
                            pools.append(pool)
                
                offset += limit
                
                # Stop after reasonable amount
                if len(pools) > 500 or offset > 10000:
                    break
                    
            except Exception as e:
                import traceback
                traceback.print_exc()
                break
        
        return pools
    
    async def _process_pools_minimal(self, pools_raw: List) -> List[Dict]:
        """Minimal processing for fast response"""
        pools = []
        
        # Field indices matching the Sugar ABI
        LP = 0
        SYMBOL = 1
        TYPE = 4
        TICK = 5
        SQRT_RATIO = 6
        TOKEN0 = 7
        RESERVE0 = 8
        TOKEN1 = 10
        RESERVE1 = 11
        GAUGE = 13
        
        for pool in pools_raw[:100]:  # Limit processing
            try:
                # Basic pool info without external API calls
                pool_address = Web3.to_checksum_address(pool[LP])
                token0_addr = Web3.to_checksum_address(pool[TOKEN0])
                token1_addr = Web3.to_checksum_address(pool[TOKEN1])
                
                # Extract symbol parts (format: "sAMM-TOKEN0/TOKEN1")
                symbol = pool[SYMBOL] if pool[SYMBOL] else ""
                token_symbols = symbol.split("-")[-1].split("/") if "-" in symbol else ["???", "???"]
                token0_symbol = token_symbols[0] if len(token_symbols) > 0 else "???"
                token1_symbol = token_symbols[1] if len(token_symbols) > 1 else "???"
                
                # Use cached token info if available, otherwise create minimal
                token0 = await cache_manager.get_token_info(token0_addr) or {
                    "address": token0_addr,
                    "symbol": token0_symbol,
                    "decimals": 18,  # Default, will be updated when fetched
                    "name": "",
                    "price_usd": 0
                }
                
                token1 = await cache_manager.get_token_info(token1_addr) or {
                    "address": token1_addr,
                    "symbol": token1_symbol,
                    "decimals": 18,  # Default, will be updated when fetched
                    "name": "",
                    "price_usd": 0
                }
                
                tick_spacing = int(pool[TYPE])
                fee_tier = self._calculate_fee_tier(tick_spacing)
                
                pools.append({
                    "address": pool_address,
                    "symbol": f"{token0.get('symbol', '???')}/{token1.get('symbol', '???')}-{fee_tier/100}%",
                    "token0": self._serialize_token_minimal(token0),
                    "token1": self._serialize_token_minimal(token1),
                    "tvl_usd": 0,  # Will be updated async
                    "volume_24h": 0,
                    "tick_spacing": tick_spacing,
                    "fee_tier": fee_tier,
                    "apr": 0,  # Will be calculated async
                    "current_tick": int(pool[TICK]) if pool[TICK] else 0,
                    "liquidity": str(pool[3]) if pool[3] else "0",  # LIQUIDITY field
                    "sqrt_price_x96": str(pool[SQRT_RATIO]) if pool[SQRT_RATIO] else "0",
                    "gauge_address": Web3.to_checksum_address(pool[GAUGE]) if pool[GAUGE] != "0x0000000000000000000000000000000000000000" else None,
                    "is_stable": tick_spacing in settings.stable_tick_spacings
                })
            except Exception as e:
                continue
        
        return pools
    
    def _calculate_fee_tier(self, tick_spacing: int) -> int:
        """Calculate fee tier from tick spacing"""
        fee_map = {1: 100, 10: 100, 50: 500, 100: 500, 200: 3000, 2000: 10000}
        return fee_map.get(tick_spacing, 500)
    
    def _serialize_token_minimal(self, token: dict) -> Dict:
        """Minimal token serialization"""
        return {
            "address": token.get("address", ""),
            "symbol": token.get("symbol", "???"),
            "decimals": token.get("decimals", 18),
            "name": token.get("name", ""),
            "price_usd": token.get("price_usd", 0),
            "logo_uri": None
        }
    
    async def get_pools_full(
        self,
        pool_type: str = "all",
        min_tvl: float = 1000,
        min_volume_24h: float = 10000,
        min_apr: float = 0,
        blacklist: Optional[List[str]] = None,
        limit: Optional[int] = 100,
        offset: Optional[int] = None,
        sort_by: str = "apr",
        sort_order: str = "desc"
    ) -> Dict:
        """Get pools with full data (slower but complete)"""
        # Create filters
        filters = PoolFilters(
            pool_type=pool_type,
            min_tvl_usd=min_tvl,
            min_volume_24h=min_volume_24h,
            min_apr=min_apr,
            blacklisted_tokens=blacklist or [],
            limit=None  # We'll handle limit and offset manually
        )
        
        # Check cache
        filters_hash = self._get_filters_hash(filters)
        cached_pools = await cache_manager.get_pools_list(filters_hash)
        
        if cached_pools is None:
            # Fetch from SDK with full data
            client = await self._get_client()
            pools = await client.get_pools(filters)
            
            # Cache the full list
            await cache_manager.set_pools_list(filters_hash, pools)
            cached_pools = pools
        
        # Apply sorting
        if sort_by == "tvl":
            cached_pools.sort(key=lambda p: p.tvl_usd, reverse=(sort_order == "desc"))
        elif sort_by == "volume":
            cached_pools.sort(key=lambda p: p.volume_24h, reverse=(sort_order == "desc"))
        else:  # Default to APR
            cached_pools.sort(key=lambda p: p.apr, reverse=(sort_order == "desc"))
        
        # Apply pagination
        total = len(cached_pools)
        start = offset or 0
        end = start + (limit or 100)
        paginated_pools = cached_pools[start:end]
        
        return {
            "pools": [self._serialize_pool(p) for p in paginated_pools],
            "pagination": {
                "total": total,
                "limit": limit or 100,
                "offset": offset or 0,
                "has_more": end < total
            }
        }
    
    async def get_pool(self, address: str) -> Dict:
        """Get single pool by address"""
        # Check cache
        cached_pool = await cache_manager.get_pool(address)
        
        if cached_pool is None:
            # Fetch from SDK
            client = await self._get_client()
            pool = await client.get_pool(address)
            
            # Cache the pool
            await cache_manager.set_pool(address, pool)
            cached_pool = pool
        
        return self._serialize_pool(cached_pool)
    
    async def get_pools_batch(self, addresses: List[str]) -> List[Dict]:
        """Get multiple pools by addresses"""
        pools = []
        
        # Check cache first
        for address in addresses:
            cached_pool = await cache_manager.get_pool(address)
            if cached_pool:
                pools.append(cached_pool)
            else:
                # Fetch from SDK
                client = await self._get_client()
                try:
                    pool = await client.get_pool(address)
                    await cache_manager.set_pool(address, pool)
                    pools.append(pool)
                except Exception:
                    continue
        
        return [self._serialize_pool(p) for p in pools]
    
    async def get_token_info(self, address: str) -> Dict:
        """Get token information"""
        # Check cache
        cached_info = await cache_manager.get_token_info(address)
        
        if cached_info is None:
            # Fetch from SDK
            client = await self._get_client()
            info = await client.get_token_info(address)
            
            # Get price
            prices = await fetch_token_prices([address])
            info.price_usd = prices.get(address.lower(), 0)
            
            # Cache the info
            await cache_manager.set_token_info(address, info)
            cached_info = info
        
        return self._serialize_token(cached_info)
    
    async def get_token_prices(self, addresses: List[str]) -> Dict[str, float]:
        """Get token prices"""
        prices = {}
        addresses_to_fetch = []
        
        # Check cache first
        for address in addresses:
            cached_price = await cache_manager.get_token_price(address)
            if cached_price is not None:
                prices[address.lower()] = cached_price
            else:
                addresses_to_fetch.append(address)
        
        # Fetch missing prices
        if addresses_to_fetch:
            fetched_prices = await fetch_token_prices(addresses_to_fetch)
            prices.update(fetched_prices)
            
            # Cache the fetched prices
            await cache_manager.set_token_prices(fetched_prices)
        
        return {"prices": prices}
    
    async def get_pool_stats(self, address: str, period: str = "24h") -> Dict:
        """Get pool statistics"""
        # For now, return basic stats from the pool data
        pool = await self.get_pool(address)
        
        # In a real implementation, you would fetch historical data
        # For now, return current stats
        return {
            "volume": pool["volume_24h"],
            "fees_collected": pool["volume_24h"] * pool["fee_tier"] / 10000,
            "tvl_change": 0,  # Would need historical data
            "apr_history": [
                {"timestamp": int(Web3().eth.get_block("latest")["timestamp"]), "apr": pool["apr"]}
            ]
        }
    
    async def get_health(self) -> Dict:
        """Get service health status"""
        try:
            client = await self._get_client()
            block = client.w3.eth.get_block("latest")
            
            return {
                "status": "healthy",
                "network": "base",
                "block_number": block["number"],
                "sugar_contract": settings.sugar_contract_address,
                "last_update": block["timestamp"]
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "network": "base",
                "sugar_contract": settings.sugar_contract_address
            }
    
    def _serialize_pool(self, pool: PoolAPRData) -> Dict:
        """Convert PoolAPRData to dict for API response"""
        return {
            "address": pool.address,
            "symbol": pool.symbol,
            "token0": self._serialize_token(pool.token0),
            "token1": self._serialize_token(pool.token1),
            "tvl_usd": pool.tvl_usd,
            "volume_24h": pool.volume_24h,
            "tick_spacing": pool.tick_spacing,
            "fee_tier": pool.fee_tier,
            "apr": pool.apr,
            "current_tick": pool.current_tick,
            "liquidity": str(pool.liquidity),
            "sqrt_price_x96": str(pool.sqrt_price_x96),
            "gauge_address": pool.gauge_address,
            "is_stable": pool.is_stable
        }
    
    def _serialize_token(self, token: TokenInfo) -> Dict:
        """Convert TokenInfo to dict for API response"""
        return {
            "address": token.address,
            "symbol": token.symbol,
            "decimals": token.decimals,
            "name": token.name,
            "price_usd": token.price_usd or 0,
            "logo_uri": token.logo_uri
        }


# Create singleton instance
pools_service = PoolsService()