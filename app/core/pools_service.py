import hashlib
from typing import Dict, List, Optional, Any
from web3 import Web3

# Import local modules
from app.core.pool_models import PoolFilters, PoolAPRData, TokenInfoInternal
from app.core.pool_constants import (
    SUGAR_ABI,
    TOKEN_ABI,
    SugarFields,
    TICK_SPACING_TO_FEE_TIER,
    DEXSCREENER_API_BASE,
    API_BATCH_SIZE,
    API_RATE_LIMIT_DELAY
)
from app.core.config import settings
from app.core.cache import cache_manager
from app.core.logger import logger
from app.core.effective_apr_calculator import EffectiveAPRCalculator
from app.schemas.pools import EffectiveAPRInfo


class PoolsService:
    def __init__(self):
        # Initialize Web3 and Sugar contract directly
        self.w3 = Web3(Web3.HTTPProvider(settings.rpc_url))
        if not self.w3.is_connected():
            logger.error(f"Failed to connect to RPC endpoint: {settings.rpc_url}")
            raise Exception(f"Failed to connect to RPC endpoint")
        
        # Initialize Sugar contract
        self.sugar = self.w3.eth.contract(
            address=Web3.to_checksum_address(settings.sugar_contract_address),
            abi=SUGAR_ABI
        )
        
        self.effective_apr_calc = EffectiveAPRCalculator()
        logger.debug("PoolsService initialized with direct Web3 connection")
    
    def _get_filters_hash(self, filters: PoolFilters) -> str:
        """Generate a hash for the filters to use as cache key"""
        filter_str = f"{filters.pool_type}:{filters.min_tvl_usd}:{filters.min_volume_24h}:{filters.min_apr}:{','.join(filters.blacklisted_tokens)}:{filters.limit}"
        return hashlib.md5(filter_str.encode()).hexdigest()
    
    async def get_pools(
        self,
        pool_type: str = "all",
        min_tvl: float = 1000,
        min_volume_24h: float = 1000,
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
            logger.debug(f"Cache hit for pools list with hash {filters_hash}")
            return cached_result
        
        logger.debug(f"Cache miss for pools list, fetching from blockchain")
        
        # For fast initial loading, skip expensive operations
        # We'll fetch basic pool data without individual price lookups
        
        # Directly fetch from Sugar contract
        logger.info(f"Fetching pools: type={pool_type}, filters applied")
        pools_raw = await self._fetch_pools_fast(pool_type, blacklist)
        logger.debug(f"Fetched {len(pools_raw)} raw pools from Sugar contract")
        
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
        
        # Apply pagination on filtered pools
        start = offset or 0
        end = start + (limit or 100)
        paginated_pools = filtered_pools[start:end]
        
        # Convert to response format with minimal processing
        pools = await self._process_pools_minimal(paginated_pools)
        logger.info(f"Processed {len(pools)} pools for response")
        
        result = {
            "pools": pools,
            "pagination": {
                "total": len(filtered_pools),
                "limit": limit or 100,
                "offset": offset or 0,
                "has_more": end < len(filtered_pools)
            }
        }
        
        # Cache with shorter TTL for quick responses
        await cache_manager.set_pools_list(filters_hash, result)
        logger.debug(f"Cached pools list with hash {filters_hash}")
        return result
    
    async def _fetch_pools_fast(self, pool_type: str, blacklist: Optional[List[str]]) -> List:
        """Fast pool fetching without price data"""
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
                result = self.sugar.functions.all(limit, offset).call()
                
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
                logger.error(f"Error fetching pools from Sugar: {str(e)}", exc_info=True)
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
        
        for pool in pools_raw:  # Process all pools passed in
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
        return TICK_SPACING_TO_FEE_TIER.get(tick_spacing, 500)
    
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
        min_volume_24h: float = 1000,
        min_apr: float = 0,
        blacklist: Optional[List[str]] = None,
        limit: Optional[int] = 100,
        offset: Optional[int] = None,
        sort_by: str = "apr",
        sort_order: str = "desc",
        include_effective_apr: bool = False
    ) -> Dict:
        """Get pools with full data - optimized version"""
        # Check cache first
        cache_key = f"full:{pool_type}:{min_tvl}:{min_volume_24h}:{min_apr}:{','.join(blacklist or [])}:{limit}:{offset}:{sort_by}:{sort_order}"
        filters_hash = hashlib.md5(cache_key.encode()).hexdigest()
        cached_result = await cache_manager.get_pools_list(filters_hash)
        
        if cached_result is not None:
            return cached_result
        
        # Fetch pools using fast method first
        pools_raw = await self._fetch_pools_fast(pool_type, blacklist)
        
        # Collect all unique token addresses
        token_addresses = set()
        for pool in pools_raw:
            token_addresses.add(pool[7].lower())  # TOKEN0
            token_addresses.add(pool[10].lower())  # TOKEN1
        
        # Batch fetch all token prices at once
        prices = {}
        if token_addresses:
            # Use get_token_prices which checks cache first, then fetches missing prices
            prices = await self.get_token_prices(list(token_addresses))
        
        # Get AERO price for APR calculation
        aero_price = prices.get(settings.aero_token_address.lower(), 0)
        if aero_price == 0:
            # Fetch AERO price separately if not in batch
            aero_prices = await self.get_token_prices([settings.aero_token_address])
            aero_price = aero_prices.get(settings.aero_token_address.lower(), 50)  # Default to $50 if failed
        
        # Batch fetch volume data for all pools
        pool_volumes = {}
        pool_addresses = [Web3.to_checksum_address(pool[0]) for pool in pools_raw]
        if pool_addresses:
            pool_volumes = await self._batch_fetch_pool_volumes(pool_addresses)
        
        # Process pools with full data
        pools_with_data = []
        
        for pool in pools_raw:
            try:
                pool_address = Web3.to_checksum_address(pool[0])
                volume_24h = pool_volumes.get(pool_address.lower(), 0)
                pool_data = await self._process_pool_full(pool, prices, aero_price, volume_24h, include_effective_apr)
                
                # Apply filters
                if pool_data["tvl_usd"] < min_tvl:
                    continue
                if pool_data["apr"] < min_apr:
                    continue
                if min_volume_24h > 0 and pool_data["volume_24h"] < min_volume_24h:
                    continue
                
                # Check blacklist
                if blacklist:
                    token0_addr = pool_data["token0"]["address"].lower()
                    token1_addr = pool_data["token1"]["address"].lower()
                    if token0_addr in [b.lower() for b in blacklist] or token1_addr in [b.lower() for b in blacklist]:
                        continue
                
                pools_with_data.append(pool_data)
                
            except Exception:
                continue
        
        # Apply sorting
        if sort_by == "tvl":
            pools_with_data.sort(key=lambda p: p["tvl_usd"], reverse=(sort_order == "desc"))
        elif sort_by == "volume":
            pools_with_data.sort(key=lambda p: p["volume_24h"], reverse=(sort_order == "desc"))
        else:  # Default to APR
            pools_with_data.sort(key=lambda p: p["apr"], reverse=(sort_order == "desc"))
        
        # Apply pagination
        total = len(pools_with_data)
        start = offset or 0
        end = start + (limit or 100)
        paginated_pools = pools_with_data[start:end]
        
        result = {
            "pools": paginated_pools,
            "pagination": {
                "total": total,
                "limit": limit or 100,
                "offset": offset or 0,
                "has_more": end < total
            }
        }
        
        # Cache with longer TTL for full data
        await cache_manager.set_pools_list(filters_hash, result)
        return result
    
    async def _process_pool_full(self, pool: List, prices: Dict[str, float], aero_price: float, volume_24h: float = 0, include_effective_apr: bool = False) -> Dict:
        """Process a single pool with full data including prices, APR, and volume"""
        # Field indices
        LP = 0
        SYMBOL = 1
        TYPE = 4
        TICK = 5
        SQRT_RATIO = 6
        TOKEN0 = 7
        RESERVE0 = 8
        STAKED0 = 9
        TOKEN1 = 10
        RESERVE1 = 11
        STAKED1 = 12
        GAUGE = 13
        EMISSIONS = 19
        
        pool_address = Web3.to_checksum_address(pool[LP])
        token0_addr = Web3.to_checksum_address(pool[TOKEN0])
        token1_addr = Web3.to_checksum_address(pool[TOKEN1])
        
        # Get token info (from cache or fetch)
        token0 = await self._get_or_fetch_token_info(token0_addr, pool[SYMBOL])
        token1 = await self._get_or_fetch_token_info(token1_addr, pool[SYMBOL])
        
        # Get prices
        token0_price = prices.get(token0_addr.lower(), 0)
        token1_price = prices.get(token1_addr.lower(), 0)
        
        # Calculate TVL
        reserve0 = int(pool[RESERVE0]) / (10 ** token0["decimals"])
        reserve1 = int(pool[RESERVE1]) / (10 ** token1["decimals"])
        tvl_usd = (reserve0 * token0_price) + (reserve1 * token1_price)
        
        # Calculate APR
        emissions_per_second = int(pool[EMISSIONS]) / 1e18
        staked0 = int(pool[STAKED0]) / (10 ** token0["decimals"])
        staked1 = int(pool[STAKED1]) / (10 ** token1["decimals"])
        staked_tvl = (staked0 * token0_price) + (staked1 * token1_price)
        
        tick_spacing = int(pool[TYPE])
        apr = self._calculate_apr(emissions_per_second, staked_tvl, aero_price, tick_spacing)
        
        fee_tier = self._calculate_fee_tier(tick_spacing)
        
        pool_data = {
            "address": pool_address,
            "symbol": f"{token0['symbol']}/{token1['symbol']}-{fee_tier/100}%",
            "token0": {
                "address": token0_addr,
                "symbol": token0["symbol"],
                "decimals": token0["decimals"],
                "name": token0.get("name", ""),
                "price_usd": token0_price,
                "logo_uri": None
            },
            "token1": {
                "address": token1_addr,
                "symbol": token1["symbol"],
                "decimals": token1["decimals"],
                "name": token1.get("name", ""),
                "price_usd": token1_price,
                "logo_uri": None
            },
            "tvl_usd": tvl_usd,
            "volume_24h": volume_24h,
            "tick_spacing": tick_spacing,
            "fee_tier": fee_tier,
            "apr": apr,
            "current_tick": int(pool[TICK]) if pool[TICK] else 0,
            "liquidity": str(pool[3]),
            "sqrt_price_x96": str(pool[SQRT_RATIO]),
            "gauge_address": Web3.to_checksum_address(pool[GAUGE]) if pool[GAUGE] != "0x0000000000000000000000000000000000000000" else None,
            "is_stable": tick_spacing in settings.stable_tick_spacings
        }
        
        # Add effective APR if requested
        if include_effective_apr and apr > 0:
            effective_apr_ranges = self.effective_apr_calc.calculate_multiple_ranges(apr, tick_spacing)
            pool_data["effective_apr"] = effective_apr_ranges.get("standard", 0)
            pool_data["effective_apr_range"] = EffectiveAPRInfo(
                narrow=effective_apr_ranges.get("narrow", 0),
                standard=effective_apr_ranges.get("standard", 0),
                wide=effective_apr_ranges.get("wide", 0)
            )
        
        return pool_data
    
    async def _get_or_fetch_token_info(self, address: str, pool_symbol: str) -> Dict:
        """Get token info from cache or fetch from chain"""
        # Check cache first
        cached = await cache_manager.get_token_info(address)
        if cached:
            logger.debug(f"Cache hit for token info: {address}")
            return cached
        
        # Try to get from chain
        try:
            logger.debug(f"Fetching token info from chain: {address}")
            # Create token contract instance
            token_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(address),
                abi=TOKEN_ABI
            )
            
            # Fetch token info from chain
            symbol = token_contract.functions.symbol().call()
            decimals = token_contract.functions.decimals().call()
            name = token_contract.functions.name().call()
            
            token_dict = {
                "address": address,
                "symbol": symbol,
                "decimals": decimals,
                "name": name
            }
            await cache_manager.set_token_info(address, token_dict)
            logger.debug(f"Cached token info for {address}")
            return token_dict
        except Exception as e:
            logger.warning(f"Failed to fetch token info for {address}: {e}")
            # Fallback: extract from pool symbol
            symbol_parts = pool_symbol.split("-")[-1].split("/") if "-" in pool_symbol else ["???", "???"]
            return {
                "address": address,
                "symbol": symbol_parts[0] if address == address else symbol_parts[1],
                "decimals": 18,
                "name": ""
            }
    
    async def _batch_fetch_pool_volumes(self, pool_addresses: List[str]) -> Dict[str, float]:
        """Batch fetch 24h volume data for multiple pools from DexScreener"""
        import aiohttp
        import asyncio
        
        volumes = {}
        batch_size = API_BATCH_SIZE  # Use constant from pool_constants
        
        async def fetch_pool_volume(session: aiohttp.ClientSession, pool_address: str) -> tuple[str, float]:
            """Fetch volume for a single pool"""
            try:
                url = f"{DEXSCREENER_API_BASE}/pairs/base/{pool_address}"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("pairs") and len(data["pairs"]) > 0:
                            pair = data["pairs"][0]
                            volume = float(pair.get("volume", {}).get("h24", 0))
                            return pool_address.lower(), volume
            except Exception:
                pass
            return pool_address.lower(), 0
        
        async with aiohttp.ClientSession() as session:
            # Process in batches to avoid rate limits
            for i in range(0, len(pool_addresses), batch_size):
                batch = pool_addresses[i:i + batch_size]
                tasks = [fetch_pool_volume(session, addr) for addr in batch]
                results = await asyncio.gather(*tasks)
                
                for addr, volume in results:
                    volumes[addr] = volume
                
                # Small delay between batches to respect rate limits
                if i + batch_size < len(pool_addresses):
                    await asyncio.sleep(API_RATE_LIMIT_DELAY)
        
        return volumes
    
    def _calculate_apr(self, emissions_per_second: float, staked_tvl: float, aero_price: float, tick_spacing: int) -> float:
        """Calculate APR based on emissions and TVL"""
        if staked_tvl <= 0:
            return 0
        
        # Calculate annual emissions value
        annual_emissions = emissions_per_second * 365 * 24 * 60 * 60
        annual_emissions_value = annual_emissions * aero_price
        
        # Calculate APR directly without efficiency rate
        apr = (annual_emissions_value / staked_tvl) * 100
        
        return apr  # Return actual APR without cap for accurate agent decision-making
    
    async def get_pool(self, address: str, include_effective_apr: bool = True) -> Dict:
        """Get single pool by address"""
        # Don't use cache for single pool fetches to ensure fresh data
        try:
            pool_data = self.sugar.functions.byAddress(
                Web3.to_checksum_address(address)
            ).call()
            
            # Convert to dict with effective APR
            result = await self._convert_sugar_to_pool_data(pool_data, include_effective_apr=include_effective_apr)
            
            return result
        except Exception as e:
            logger.error(f"Failed to fetch pool {address}: {e}")
            raise
    
    async def get_pools_batch(self, addresses: List[str]) -> List[Dict]:
        """Get multiple pools by addresses"""
        pools = []
        
        # Check cache first
        for address in addresses:
            cached_pool = await cache_manager.get_pool(address)
            if cached_pool:
                pools.append(cached_pool)
            else:
                # Fetch from Sugar contract
                try:
                    pool_data = self.sugar.functions.byAddress(
                        Web3.to_checksum_address(address)
                    ).call()
                    
                    # Convert to dict
                    pool = await self._convert_sugar_to_pool_data(pool_data, include_effective_apr=False)  # No effective APR for batch
                    
                    await cache_manager.set_pool(address, pool)
                    pools.append(pool)
                except Exception as e:
                    logger.warning(f"Failed to fetch pool {address}: {e}")
                    continue
        
        # Return dicts directly
        return pools
    
    async def get_token_info(self, address: str) -> Dict:
        """Get token information"""
        # Check cache
        cached_info = await cache_manager.get_token_info(address)
        
        if cached_info is None:
            # Fetch from chain
            try:
                token_contract = self.w3.eth.contract(
                    address=Web3.to_checksum_address(address),
                    abi=TOKEN_ABI
                )
                
                symbol = token_contract.functions.symbol().call()
                decimals = token_contract.functions.decimals().call()
                name = token_contract.functions.name().call()
                
                cached_info = {
                    "address": address,
                    "symbol": symbol,
                    "decimals": decimals,
                    "name": name,
                    "price_usd": 0  # Will be updated separately
                }
                
                # Cache the info
                await cache_manager.set_token_info(address, cached_info)
            except Exception as e:
                logger.error(f"Failed to fetch token info for {address}: {e}")
                raise
        
        # Always fetch fresh price (cache is short TTL)
        prices = await self._fetch_token_prices_from_dexscreener([address])
        price_usd = prices.get(address.lower(), 0)
        
        # Update cached info with price
        result = dict(cached_info)
        result["price_usd"] = price_usd
        
        return self._serialize_token(result)
    
    async def _fetch_token_prices_from_dexscreener(self, addresses: List[str]) -> Dict[str, float]:
        """Fetch token prices from DexScreener API"""
        import aiohttp
        import asyncio
        
        prices = {}
        
        # Known stablecoins (lowercase addresses)
        stablecoins = {
            "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913".lower(): 1.0,  # USDC on Base
            "0x50c5725949a6f0c72e6c4a641f24049a917db0cb".lower(): 1.0,  # DAI on Base
            "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca".lower(): 1.0,  # USDbC on Base
        }
        
        async def fetch_single_token_price(session: aiohttp.ClientSession, address: str) -> tuple[str, float]:
            """Fetch price for a single token"""
            # Check if it's a stablecoin
            if address.lower() in stablecoins:
                return (address.lower(), stablecoins[address.lower()])
            
            try:
                url = f"{DEXSCREENER_API_BASE}/tokens/{address}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data and 'pairs' in data and data['pairs'] and len(data['pairs']) > 0:
                            # Get price from the most liquid Base network pair
                            base_pairs = [p for p in data['pairs'] if p.get('chainId') == 'base']
                            if base_pairs:
                                # Sort by liquidity and get the highest
                                base_pairs.sort(key=lambda x: float(x.get('liquidity', {}).get('usd', 0)), reverse=True)
                                price = float(base_pairs[0].get('priceUsd', 0))
                                return (address.lower(), price)
            except Exception as e:
                logger.warning(f"Failed to fetch price for {address}: {str(e)}")
            
            return (address.lower(), 0.0)
        
        # Fetch prices concurrently
        async with aiohttp.ClientSession() as session:
            tasks = [fetch_single_token_price(session, addr) for addr in addresses]
            results = await asyncio.gather(*tasks)
            
            for addr, price in results:
                prices[addr] = price
        
        return prices
    
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
            fetched_prices = await self._fetch_token_prices_from_dexscreener(addresses_to_fetch)
            prices.update(fetched_prices)
            
            # Cache the fetched prices
            await cache_manager.set_token_prices(fetched_prices)
        
        return prices
    
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
            logger.debug("Checking service health")
            block = self.w3.eth.get_block("latest")
            
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
    
    def _serialize_pool(self, pool) -> Dict:
        """Convert pool data to dict for API response"""
        # Handle both PoolAPRData objects and dicts
        if isinstance(pool, PoolAPRData):
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
        else:
            # It's already a dict, just return it
            return pool
    
    def _serialize_token(self, token) -> Dict:
        """Convert token info to dict for API response"""
        # Handle both TokenInfoInternal objects and dicts
        if isinstance(token, TokenInfoInternal):
            return {
                "address": token.address,
                "symbol": token.symbol,
                "decimals": token.decimals,
                "name": token.name,
                "price_usd": token.price_usd or 0,
                "logo_uri": token.logo_uri
            }
        elif isinstance(token, dict):
            # It's already a dict, ensure all fields are present
            return {
                "address": token.get("address", ""),
                "symbol": token.get("symbol", "???"),
                "decimals": token.get("decimals", 18),
                "name": token.get("name", ""),
                "price_usd": token.get("price_usd", 0),
                "logo_uri": token.get("logo_uri")
            }
        else:
            # Fallback
            return {
                "address": "",
                "symbol": "???",
                "decimals": 18,
                "name": "",
                "price_usd": 0,
                "logo_uri": None
            }


    async def _convert_sugar_to_pool_data(self, pool_data: tuple, include_effective_apr: bool = True) -> Dict:
        """Convert Sugar contract response to pool data dict."""
        # Extract basic data using SugarFields indices
        pool_address = Web3.to_checksum_address(pool_data[SugarFields.LP])
        token0_addr = Web3.to_checksum_address(pool_data[SugarFields.TOKEN0])
        token1_addr = Web3.to_checksum_address(pool_data[SugarFields.TOKEN1])
        
        # Get token info
        token0_info = await self._get_or_fetch_token_info(token0_addr, pool_data[SugarFields.SYMBOL])
        token1_info = await self._get_or_fetch_token_info(token1_addr, pool_data[SugarFields.SYMBOL])
        
        # Fetch token prices
        prices = await self._fetch_token_prices_from_dexscreener([token0_addr, token1_addr, settings.aero_token_address])
        token0_price = prices.get(token0_addr.lower(), 0)
        token1_price = prices.get(token1_addr.lower(), 0)
        aero_price = prices.get(settings.aero_token_address.lower(), 50)  # Default to $50 if not found
        
        # Calculate TVL
        token0_decimals = token0_info.get("decimals", 18)
        token1_decimals = token1_info.get("decimals", 18)
        reserve0 = int(pool_data[SugarFields.RESERVE0]) / (10 ** token0_decimals)
        reserve1 = int(pool_data[SugarFields.RESERVE1]) / (10 ** token1_decimals)
        tvl_usd = (reserve0 * token0_price) + (reserve1 * token1_price)
        
        # Get tick spacing and fee tier
        tick_spacing = int(pool_data[SugarFields.TYPE])
        fee_tier = self._calculate_fee_tier(tick_spacing)
        
        # Calculate APR
        emissions_per_second = int(pool_data[SugarFields.EMISSIONS]) / 1e18
        staked0 = int(pool_data[SugarFields.STAKED0]) / (10 ** token0_decimals)
        staked1 = int(pool_data[SugarFields.STAKED1]) / (10 ** token1_decimals)
        staked_tvl = (staked0 * token0_price) + (staked1 * token1_price)
        
        apr = self._calculate_apr(emissions_per_second, staked_tvl, aero_price, tick_spacing)
        
        # Get volume
        volumes = await self._batch_fetch_pool_volumes([pool_address])
        volume_24h = volumes.get(pool_address.lower(), 0)
        
        # Build response dict
        result = {
            "address": pool_address,
            "symbol": f"{token0_info.get('symbol', '???')}/{token1_info.get('symbol', '???')}-{fee_tier/100}%",
            "token0": {
                "address": token0_addr,
                "symbol": token0_info.get("symbol", "???"),
                "decimals": token0_decimals,
                "name": token0_info.get("name", ""),
                "price_usd": token0_price,
                "logo_uri": None
            },
            "token1": {
                "address": token1_addr,
                "symbol": token1_info.get("symbol", "???"),
                "decimals": token1_decimals,
                "name": token1_info.get("name", ""),
                "price_usd": token1_price,
                "logo_uri": None
            },
            "tvl_usd": tvl_usd,
            "volume_24h": volume_24h,
            "tick_spacing": tick_spacing,
            "fee_tier": fee_tier,
            "apr": apr,
            "current_tick": int(pool_data[SugarFields.TICK]) if pool_data[SugarFields.TICK] else 0,
            "liquidity": str(pool_data[SugarFields.LIQUIDITY]),
            "sqrt_price_x96": str(pool_data[SugarFields.SQRT_RATIO]),
            "gauge_address": Web3.to_checksum_address(pool_data[SugarFields.GAUGE]) if pool_data[SugarFields.GAUGE] != "0x0000000000000000000000000000000000000000" else None,
            "is_stable": tick_spacing in settings.stable_tick_spacings
        }
        
        # Add effective APR if requested and APR > 0
        if include_effective_apr and apr > 0:
            effective_apr_ranges = self.effective_apr_calc.calculate_multiple_ranges(apr, tick_spacing)
            result["effective_apr"] = effective_apr_ranges.get("standard", 0)
            result["effective_apr_range"] = {
                "narrow": effective_apr_ranges.get("narrow", 0),
                "standard": effective_apr_ranges.get("standard", 0),
                "wide": effective_apr_ranges.get("wide", 0)
            }
        else:
            result["effective_apr"] = None
            result["effective_apr_range"] = None
        
        return result


# Create singleton instance
pools_service = PoolsService()