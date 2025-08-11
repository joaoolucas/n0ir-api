"""Client for interacting with Aerodrome CL pools."""

import asyncio
import os
import pickle
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
from web3 import Web3
from web3.contract import Contract

from .exceptions import PoolNotFoundError, RPCError
from .models import SwapRoute
from .constants import (
    DEFAULT_BASE_RPC,
    STABLE_TICK_SPACINGS,
    SUGAR_ABI,
    SUGAR_ADDRESS,
    TOKEN_ABI,
    SugarFields,
)
from .models import PoolAPRData, PoolFilters, TokenInfo
from typing import Tuple
from .route_finder import RouteFinder
from .utils import (
    calculate_apr,
    calculate_fee_tier,
    fetch_pool_volume,
    fetch_token_prices,
    format_pool_symbol,
    get_aero_price,
    is_valid_address,
    normalize_address,
)


class PoolsClient:
    """Client for fetching and analyzing Aerodrome CL pools."""
    
    def __init__(self, rpc_url: Optional[str] = None, cache_dir: Optional[Path] = None):
        """
        Initialize the PoolsClient.
        
        Args:
            rpc_url: Ethereum RPC URL. If not provided, uses environment variable or default.
            cache_dir: Directory for caching token data. Defaults to ~/.n0ir_api/cache
        """
        # Set up RPC connection
        if not rpc_url:
            rpc_url = os.environ.get("RPC_URL", DEFAULT_BASE_RPC)
        
        try:
            self.w3 = Web3(Web3.HTTPProvider(rpc_url))
            if not self.w3.is_connected():
                raise RPCError(f"Failed to connect to RPC endpoint: {rpc_url}")
        except Exception as e:
            raise RPCError(f"Error connecting to RPC: {e}")
        
        # Initialize Sugar contract
        self.sugar = self.w3.eth.contract(
            address=normalize_address(SUGAR_ADDRESS),
            abi=SUGAR_ABI
        )
        
        # Set up cache
        self.token_cache: Dict[str, TokenInfo] = {}
        if cache_dir is None:
            cache_dir = Path.home() / ".n0ir_api" / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = cache_dir / "token_cache.pkl"
        self._load_cache()
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - save cache."""
        self._save_cache()
    
    def _load_cache(self):
        """Load token cache from disk."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'rb') as f:
                    cached_data = pickle.load(f)
                    # Check if cache is less than 24 hours old
                    if time.time() - cached_data.get('timestamp', 0) < 86400:
                        self.token_cache = cached_data.get('tokens', {})
            except Exception:
                pass
    
    def _save_cache(self):
        """Save token cache to disk."""
        try:
            cache_data = {
                'timestamp': time.time(),
                'tokens': self.token_cache
            }
            with open(self.cache_file, 'wb') as f:
                pickle.dump(cache_data, f)
        except Exception:
            pass
    
    async def get_token_info(self, address: str) -> TokenInfo:
        """
        Fetch token metadata.
        
        Args:
            address: Token contract address
            
        Returns:
            TokenInfo object with token details
        """
        address_lower = address.lower()
        if address_lower in self.token_cache:
            return self.token_cache[address_lower]
        
        checksum_addr = normalize_address(address)
        token_contract = self.w3.eth.contract(address=checksum_addr, abi=TOKEN_ABI)
        
        try:
            symbol = token_contract.functions.symbol().call()
            decimals = token_contract.functions.decimals().call()
            name = token_contract.functions.name().call()
            
            info = TokenInfo(
                address=checksum_addr,
                symbol=symbol,
                decimals=decimals,
                name=name
            )
            self.token_cache[address_lower] = info
            return info
        except Exception as e:
            # Return default info if token metadata fetch fails
            return TokenInfo(
                address=checksum_addr,
                symbol="???",
                decimals=18,
                name="Unknown"
            )
    
    async def get_pools(self, filters: Optional[PoolFilters] = None) -> List[PoolAPRData]:
        """
        Fetch all CL pools matching specified criteria.
        
        Args:
            filters: PoolFilters object with filtering criteria
            
        Returns:
            List of PoolAPRData objects sorted by APR (highest first)
        """
        if filters is None:
            filters = PoolFilters()
        
        # Fetch all CL pools from Sugar
        cl_pools_raw = await self._fetch_all_pools()
        
        # Filter for active gauges and pool type
        active_pools = self._filter_active_pools(cl_pools_raw, filters)
        
        # Get AERO price once
        aero_price = await get_aero_price()
        
        # Process pools in batches
        all_pools = []
        batch_size = 50
        total_batches = (len(active_pools) + batch_size - 1) // batch_size
        
        for i in range(0, len(active_pools), batch_size):
            batch = active_pools[i:i + batch_size]
            current_batch = i // batch_size + 1
            
            
            await self._process_pool_batch(batch, filters, aero_price, all_pools)
            
            # Small delay between batches
            await asyncio.sleep(0.1)
        
        
        # Sort by APR
        all_pools.sort(key=lambda p: p.apr, reverse=True)
        
        # Apply limit if specified
        if filters.limit:
            all_pools = all_pools[:filters.limit]
        
        # Save cache
        self._save_cache()
        
        return all_pools
    
    async def get_pool(self, address: str) -> PoolAPRData:
        """
        Fetch detailed information for a specific pool.
        
        Args:
            address: Pool contract address
            
        Returns:
            PoolAPRData object with pool details
            
        Raises:
            PoolNotFoundError: If pool not found or not a CL pool
        """
        try:
            pool_address = normalize_address(address)
            
            # Fetch pool data from Sugar
            pool_data = self.sugar.functions.byAddress(pool_address).call()
            
            # Check if it's a CL pool
            if int(pool_data[SugarFields.TYPE]) <= 0:
                raise PoolNotFoundError(f"Pool {address} is not a concentrated liquidity pool")
            
            # Process pool data
            return await self._process_single_pool(pool_data)
            
        except PoolNotFoundError:
            raise
        except Exception as e:
            raise PoolNotFoundError(f"Error fetching pool {address}: {e}")
    
    async def get_pools_batch(self, addresses: List[str]) -> List[PoolAPRData]:
        """
        Fetch information for multiple pools efficiently.
        
        Args:
            addresses: List of pool addresses
            
        Returns:
            List of PoolAPRData objects
        """
        pools = []
        for address in addresses:
            try:
                pool = await self.get_pool(address)
                pools.append(pool)
            except PoolNotFoundError:
                continue
        
        return pools
    
    async def _fetch_all_pools(self) -> List[Any]:
        """Fetch all CL pools from Sugar contract."""
        cl_pools_raw = []
        offset = 8100  # Starting offset for CL pools
        limit = 500
        
        while True:
            try:
                result = self.sugar.functions.all(limit, offset).call()
                
                if not result:
                    break
                
                # Add only CL pools (type > 0)
                cl_batch = [p for p in result if int(p[SugarFields.TYPE]) > 0]
                cl_pools_raw.extend(cl_batch)
                
                
                offset += limit
                
            except Exception as e:
                break
        
        return cl_pools_raw
    
    def _filter_active_pools(self, pools: List[Any], filters: PoolFilters) -> List[Any]:
        """Filter pools by active gauge and pool type."""
        # Filter for active gauges
        active_pools = [p for p in pools if p[SugarFields.GAUGE_ALIVE]]
        
        # Apply pool type filter
        if filters.pool_type != "all":
            filtered_pools = []
            for pool in active_pools:
                tick_spacing = int(pool[SugarFields.TYPE])
                is_stable = tick_spacing in STABLE_TICK_SPACINGS
                
                if filters.pool_type == "stable" and is_stable:
                    filtered_pools.append(pool)
                elif filters.pool_type == "volatile" and not is_stable:
                    filtered_pools.append(pool)
            
            active_pools = filtered_pools
        
        return active_pools
    
    async def _process_single_pool(self, pool_data: Any) -> PoolAPRData:
        """Process a single pool data tuple into PoolAPRData."""
        # Get token info
        token0_addr = normalize_address(pool_data[SugarFields.TOKEN0])
        token1_addr = normalize_address(pool_data[SugarFields.TOKEN1])
        
        token0 = await self.get_token_info(token0_addr)
        token1 = await self.get_token_info(token1_addr)
        
        # Get prices
        print("Fetching token prices...")
        prices = await fetch_token_prices([token0_addr, token1_addr])
        token0_price = prices.get(token0_addr.lower(), 0)
        token1_price = prices.get(token1_addr.lower(), 0)
        
        # Get AERO price
        aero_price = await get_aero_price()
        
        # Calculate TVL
        reserve0 = int(pool_data[SugarFields.RESERVE0]) / (10 ** token0.decimals)
        reserve1 = int(pool_data[SugarFields.RESERVE1]) / (10 ** token1.decimals)
        tvl_usd = (reserve0 * token0_price) + (reserve1 * token1_price)
        
        # Get tick spacing
        tick_spacing = int(pool_data[SugarFields.TYPE])
        
        # Calculate APR
        emissions_per_second = int(pool_data[SugarFields.EMISSIONS]) / 1e18
        staked0 = int(pool_data[SugarFields.STAKED0]) / (10 ** token0.decimals)
        staked1 = int(pool_data[SugarFields.STAKED1]) / (10 ** token1.decimals)
        staked_tvl = (staked0 * token0_price) + (staked1 * token1_price)
        
        apr = calculate_apr(emissions_per_second, staked_tvl, aero_price, tick_spacing)
        
        # Get volume
        pool_address = normalize_address(pool_data[SugarFields.LP])
        volume_24h = await fetch_pool_volume(pool_address)
        
        # Calculate fee tier
        fee_tier = calculate_fee_tier(tick_spacing)
        
        # Get gauge address
        gauge_address = normalize_address(pool_data[SugarFields.GAUGE]) if pool_data[SugarFields.GAUGE] != "0x0000000000000000000000000000000000000000" else None
        
        return PoolAPRData(
            address=pool_address,
            symbol=format_pool_symbol(token0.symbol, token1.symbol, fee_tier),
            token0=token0,
            token1=token1,
            tvl_usd=tvl_usd,
            volume_24h=volume_24h,
            tick_spacing=tick_spacing,
            fee_tier=fee_tier,
            apr=apr,
            current_tick=int(pool_data[SugarFields.TICK]) if pool_data[SugarFields.TICK] else 0,
            liquidity=int(pool_data[SugarFields.LIQUIDITY]) if pool_data[SugarFields.LIQUIDITY] else 0,
            sqrt_price_x96=int(pool_data[SugarFields.SQRT_RATIO]) if pool_data[SugarFields.SQRT_RATIO] else 0,
            gauge_address=gauge_address
        )
    
    async def _process_pool_batch(self, batch: List[Any], filters: PoolFilters, aero_price: float, all_pools: List[PoolAPRData]):
        """Process a batch of pools."""
        # Get unique token addresses from this batch
        token_addresses = set()
        for pool in batch:
            try:
                token0 = pool[SugarFields.TOKEN0]
                token1 = pool[SugarFields.TOKEN1]
                
                if is_valid_address(token0):
                    token_addresses.add(token0)
                if is_valid_address(token1):
                    token_addresses.add(token1)
            except Exception:
                continue
        
        # Fetch token info concurrently
        token_infos = {}
        token_tasks = []
        for addr in token_addresses:
            task = self.get_token_info(addr)
            token_tasks.append((addr, task))
        
        # Execute all token info fetches concurrently
        for addr, task in token_tasks:
            try:
                info = await task
                token_infos[addr.lower()] = info
            except Exception:
                pass
        
        # Fetch prices concurrently
        prices = await fetch_token_prices(list(token_addresses))
        
        # Process each pool
        for pool in batch:
            try:
                # Skip if token addresses are invalid
                if not is_valid_address(pool[SugarFields.TOKEN0]) or not is_valid_address(pool[SugarFields.TOKEN1]):
                    continue
                
                token0_addr = normalize_address(pool[SugarFields.TOKEN0])
                token1_addr = normalize_address(pool[SugarFields.TOKEN1])
                
                # Skip blacklisted tokens
                if filters.blacklisted_tokens:
                    if token0_addr.lower() in filters.blacklisted_tokens or token1_addr.lower() in filters.blacklisted_tokens:
                        continue
                
                # Get token info
                token0 = token_infos.get(token0_addr.lower())
                token1 = token_infos.get(token1_addr.lower())
                
                if not token0 or not token1:
                    continue
                
                # Get prices
                token0_price = prices.get(token0_addr.lower(), 0)
                token1_price = prices.get(token1_addr.lower(), 0)
                
                # Skip if we don't have prices for either token
                if token0_price == 0 or token1_price == 0:
                    continue
                
                # Calculate TVL
                reserve0 = int(pool[SugarFields.RESERVE0]) / (10 ** token0.decimals)
                reserve1 = int(pool[SugarFields.RESERVE1]) / (10 ** token1.decimals)
                tvl_usd = (reserve0 * token0_price) + (reserve1 * token1_price)
                
                # Skip if below TVL threshold
                if tvl_usd < filters.min_tvl_usd:
                    continue
                
                # Get tick spacing
                tick_spacing = int(pool[SugarFields.TYPE])
                
                # Calculate APR
                emissions_per_second = int(pool[SugarFields.EMISSIONS]) / 1e18
                staked0 = int(pool[SugarFields.STAKED0]) / (10 ** token0.decimals)
                staked1 = int(pool[SugarFields.STAKED1]) / (10 ** token1.decimals)
                staked_tvl = (staked0 * token0_price) + (staked1 * token1_price)
                
                apr = calculate_apr(emissions_per_second, staked_tvl, aero_price, tick_spacing)
                
                # Skip if below APR threshold
                if apr < filters.min_apr:
                    continue
                
                # Calculate fee tier
                fee_tier = calculate_fee_tier(tick_spacing)
                
                # Get pool address
                pool_address = normalize_address(pool[SugarFields.LP])
                
                # Fetch volume if we have a volume filter
                volume_24h = 0
                if filters.min_volume_24h > 0:
                    volume_24h = await fetch_pool_volume(pool_address)
                    if volume_24h < filters.min_volume_24h:
                        continue
                
                # Create pool data
                pool_data = PoolAPRData(
                    address=pool_address,
                    symbol=format_pool_symbol(token0.symbol, token1.symbol, fee_tier),
                    token0=token0,
                    token1=token1,
                    tvl_usd=tvl_usd,
                    volume_24h=volume_24h,
                    tick_spacing=tick_spacing,
                    fee_tier=fee_tier,
                    apr=apr,
                    current_tick=int(pool[SugarFields.TICK]) if pool[SugarFields.TICK] else 0,
                    liquidity=int(pool[SugarFields.LIQUIDITY]) if pool[SugarFields.LIQUIDITY] else 0,
                    sqrt_price_x96=int(pool[SugarFields.SQRT_RATIO]) if pool[SugarFields.SQRT_RATIO] else 0
                )
                
                all_pools.append(pool_data)
                
            except Exception as e:
                continue
    
    async def find_routes_for_position_open(
        self,
        pool_address: str
    ) -> Tuple[Optional[SwapRoute], Optional[SwapRoute]]:
        """
        Find optimal routes from USDC to pool tokens for opening a position.
        
        Args:
            pool_address: Address of the target pool
            
        Returns:
            Tuple of (token0_route, token1_route) where None means no swap needed
        """
        # Get pool information
        pool = await self.get_pool(pool_address)
        
        # Initialize route finder with Web3 connection
        finder = RouteFinder(self.w3)
        
        # Find routes for position opening
        # Pass the target pool info so it can be used in routing
        return finder.find_routes_for_position_open(
            pool.token0.address,
            pool.token1.address,
            target_pool_address=pool_address,
            target_pool_tick_spacing=pool.tick_spacing
        )
    
    async def find_routes_for_position_close(
        self,
        pool_address: str
    ) -> Tuple[Optional[SwapRoute], Optional[SwapRoute]]:
        """
        Find optimal routes from pool tokens to USDC for closing a position.
        
        Args:
            pool_address: Address of the pool being closed
            
        Returns:
            Tuple of (token0_route, token1_route) where None means no swap needed
        """
        # Get pool information
        pool = await self.get_pool(pool_address)
        
        # Initialize route finder with Web3 connection
        finder = RouteFinder(self.w3)
        
        # Find routes for position closing
        return finder.find_routes_for_position_close(
            pool.token0.address,
            pool.token1.address
        )