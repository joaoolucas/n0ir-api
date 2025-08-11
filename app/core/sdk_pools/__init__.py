"""
Pools module for n0ir SDK.

This module provides functionality for discovering and analyzing Aerodrome Finance
Concentrated Liquidity (Slipstream) pools on Base network.
"""

from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from .client import PoolsClient
from .models import PoolAPRData, PoolFilters, TokenInfo, SwapRoute
from .route_finder import RouteFinder

# Module-level client instance
_default_client: Optional[PoolsClient] = None


def _get_default_client() -> PoolsClient:
    """Get or create the default client instance."""
    global _default_client
    if _default_client is None:
        _default_client = PoolsClient()
    return _default_client


async def get_pools(
    pool_type: str = "all",
    min_tvl_usd: float = 1000,
    min_volume_24h: float = 10000,
    min_apr: float = 0,
    blacklisted_tokens: Optional[List[str]] = None,
    limit: Optional[int] = None,
    rpc_url: Optional[str] = None
) -> List[PoolAPRData]:
    """
    Fetch all CL pools matching specified criteria.
    
    This is a convenience function that creates a client and fetches pools.
    For multiple operations, it's more efficient to create a PoolsClient instance.
    
    Args:
        pool_type: "stable" | "volatile" | "all" (default: "all")
        min_tvl_usd: Minimum TVL in USD (default: 1000)
        min_volume_24h: Minimum 24h volume in USD (default: 10000)
        min_apr: Minimum APR percentage (default: 0)
        blacklisted_tokens: List of token addresses to exclude
        limit: Maximum number of pools to return
        rpc_url: Custom RPC URL (uses default if not provided)
        
    Returns:
        List of PoolAPRData objects sorted by APR (highest first)
        
    Example:
        >>> pools = await get_pools(min_tvl_usd=50000, min_apr=10)
        >>> for pool in pools[:5]:
        ...     print(f"{pool.symbol}: ${pool.tvl_usd:,.0f} TVL, {pool.apr:.2f}% APR")
    """
    # Create filters
    filters = PoolFilters(
        pool_type=pool_type,
        min_tvl_usd=min_tvl_usd,
        min_volume_24h=min_volume_24h,
        min_apr=min_apr,
        blacklisted_tokens=blacklisted_tokens or [],
        limit=limit
    )
    
    # Use custom client if RPC URL provided
    if rpc_url:
        async with PoolsClient(rpc_url=rpc_url) as client:
            return await client.get_pools(filters)
    else:
        client = _get_default_client()
        return await client.get_pools(filters)


async def get_pool(address: str, rpc_url: Optional[str] = None) -> PoolAPRData:
    """
    Fetch detailed information for a specific pool.
    
    Args:
        address: Pool contract address
        rpc_url: Custom RPC URL (uses default if not provided)
        
    Returns:
        PoolAPRData object with pool details
        
    Raises:
        PoolNotFoundError: If pool not found or not a CL pool
        
    Example:
        >>> pool = await get_pool("0x...")
        >>> print(f"{pool.symbol}: ${pool.tvl_usd:,.0f} TVL, {pool.apr:.2f}% APR")
    """
    if rpc_url:
        async with PoolsClient(rpc_url=rpc_url) as client:
            return await client.get_pool(address)
    else:
        client = _get_default_client()
        return await client.get_pool(address)


async def get_pools_batch(addresses: List[str], rpc_url: Optional[str] = None) -> List[PoolAPRData]:
    """
    Fetch information for multiple pools efficiently.
    
    Args:
        addresses: List of pool addresses
        rpc_url: Custom RPC URL (uses default if not provided)
        
    Returns:
        List of PoolAPRData objects
        
    Example:
        >>> addresses = ["0x...", "0x...", "0x..."]
        >>> pools = await get_pools_batch(addresses)
        >>> for pool in pools:
        ...     print(f"{pool.symbol}: ${pool.tvl_usd:,.0f} TVL")
    """
    if rpc_url:
        async with PoolsClient(rpc_url=rpc_url) as client:
            return await client.get_pools_batch(addresses)
    else:
        client = _get_default_client()
        return await client.get_pools_batch(addresses)


async def find_routes_for_position_open(
    pool_address: str,
    rpc_url: Optional[str] = None
) -> Tuple[Optional[SwapRoute], Optional[SwapRoute]]:
    """
    Find optimal routes from USDC to pool tokens for opening a position.
    
    Uses the CL Factory to efficiently query for existing pools between tokens.
    
    Args:
        pool_address: Address of the target pool
        rpc_url: Custom RPC URL (uses default if not provided)
        
    Returns:
        Tuple of (token0_route, token1_route) where None means no swap needed
        
    Example:
        >>> pool_address = "0x70aCDF2Ad0bf2402C957154f944c19Ef4e1cbAE1"  # WETH/cbBTC
        >>> token0_route, token1_route = await find_routes_for_position_open(pool_address)
        >>> if token0_route:
        ...     print(f"Token0 route: {len(token0_route.pools)} hop(s)")
        >>> if token1_route:
        ...     print(f"Token1 route: {len(token1_route.pools)} hop(s)")
    """
    if rpc_url:
        async with PoolsClient(rpc_url=rpc_url) as client:
            return await client.find_routes_for_position_open(pool_address)
    else:
        client = _get_default_client()
        return await client.find_routes_for_position_open(pool_address)


async def find_routes_for_position_close(
    pool_address: str,
    rpc_url: Optional[str] = None
) -> Tuple[Optional[SwapRoute], Optional[SwapRoute]]:
    """
    Find optimal routes from pool tokens to USDC for closing a position.
    
    Uses the CL Factory to efficiently query for existing pools between tokens.
    
    Args:
        pool_address: Address of the pool being closed
        rpc_url: Custom RPC URL (uses default if not provided)
        
    Returns:
        Tuple of (token0_route, token1_route) where None means no swap needed
        
    Example:
        >>> pool_address = "0x70aCDF2Ad0bf2402C957154f944c19Ef4e1cbAE1"  # WETH/cbBTC
        >>> token0_route, token1_route = await find_routes_for_position_close(pool_address)
        >>> if token0_route:
        ...     print(f"Token0 route: {len(token0_route.pools)} hop(s)")
        >>> if token1_route:
        ...     print(f"Token1 route: {len(token1_route.pools)} hop(s)")
    """
    if rpc_url:
        async with PoolsClient(rpc_url=rpc_url) as client:
            return await client.find_routes_for_position_close(pool_address)
    else:
        client = _get_default_client()
        return await client.find_routes_for_position_close(pool_address)


# Public API exports
__all__ = [
    # Main client class
    "PoolsClient",
    
    # Data models
    "PoolAPRData",
    "PoolFilters",
    "TokenInfo",
    "SwapRoute",
    
    # Route finding
    "RouteFinder",
    
    # Convenience functions
    "get_pools",
    "get_pool",
    "get_pools_batch",
    "find_routes_for_position_open",
    "find_routes_for_position_close",
]