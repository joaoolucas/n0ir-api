"""Utility functions for the pools module."""

import asyncio
from typing import Dict, List, Optional, Tuple
import aiohttp
from web3 import Web3

from .constants import (
    AERO_TOKEN_ADDRESS,
    API_BATCH_SIZE,
    API_RATE_LIMIT_DELAY,
    DEXSCREENER_API_BASE,
    TICK_SPACING_TO_EFFICIENCY_RATE,
)


async def fetch_token_price(session: aiohttp.ClientSession, token_address: str) -> Tuple[str, float]:
    """
    Fetch a single token price from DexScreener.
    
    Args:
        session: aiohttp client session
        token_address: Token contract address
        
    Returns:
        Tuple of (token_address, price_usd)
    """
    try:
        url = f"{DEXSCREENER_API_BASE}/tokens/{token_address}"
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("pairs"):
                    # Prefer Base chain pairs
                    base_pairs = [p for p in data["pairs"] if p.get("chainId") == "base"]
                    if base_pairs:
                        # Sort by liquidity and get the highest
                        base_pairs.sort(key=lambda x: float(x.get("liquidity", {}).get("usd", 0)), reverse=True)
                        price = float(base_pairs[0].get("priceUsd", 0))
                        return token_address.lower(), price
                    # Fallback to first pair if no Base pairs
                    elif data["pairs"]:
                        pair = data["pairs"][0]
                        price = float(pair.get("priceUsd", 0))
                        return token_address.lower(), price
    except Exception:
        pass
    
    return token_address.lower(), 0


async def fetch_token_prices(token_addresses: List[str]) -> Dict[str, float]:
    """
    Fetch token prices from DexScreener with rate limiting.
    
    Args:
        token_addresses: List of token addresses
        
    Returns:
        Dict mapping token address to USD price
    """
    prices = {}
    
    async with aiohttp.ClientSession() as session:
        # Process in batches to avoid rate limits
        for i in range(0, len(token_addresses), API_BATCH_SIZE):
            batch = token_addresses[i:i + API_BATCH_SIZE]
            tasks = [fetch_token_price(session, addr) for addr in batch]
            results = await asyncio.gather(*tasks)
            
            for addr, price in results:
                if price > 0:
                    prices[addr] = price
            
            # Rate limit between batches
            if i + API_BATCH_SIZE < len(token_addresses):
                await asyncio.sleep(API_RATE_LIMIT_DELAY * 5)
                
    return prices


async def fetch_pool_volume(pool_address: str) -> float:
    """
    Fetch pool 24h volume from DexScreener.
    
    Args:
        pool_address: Pool contract address
        
    Returns:
        24h volume in USD
    """
    async with aiohttp.ClientSession() as session:
        try:
            url = f"{DEXSCREENER_API_BASE}/pairs/base/{pool_address}"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("pair"):
                        return float(data["pair"].get("volume", {}).get("h24", 0))
        except Exception:
            pass
    
    return 0


async def get_aero_price() -> float:
    """
    Fetch current AERO token price.
    
    Returns:
        AERO price in USD
    """
    prices = await fetch_token_prices([AERO_TOKEN_ADDRESS])
    return prices.get(AERO_TOKEN_ADDRESS.lower(), 0)


def calculate_apr(
    emissions_per_second: float,
    staked_tvl: float,
    aero_price: float,
    tick_spacing: int
) -> float:
    """
    Calculate APR based on emissions and efficiency rate.
    
    Args:
        emissions_per_second: Emissions in AERO per second
        staked_tvl: Total value locked in USD
        aero_price: Current AERO price in USD
        tick_spacing: Pool tick spacing
        
    Returns:
        APR as percentage
    """
    if staked_tvl == 0:
        return 0
    
    # Calculate emissions per year
    emissions_per_year = emissions_per_second * 365 * 24 * 60 * 60
    
    # Calculate emissions APR
    emissions_apr = (emissions_per_year * aero_price * 100) / staked_tvl
    
    # Get efficiency rate based on tick spacing
    efficiency_rate = TICK_SPACING_TO_EFFICIENCY_RATE.get(tick_spacing, 1)
    
    # Calculate real APR (divide by efficiency rate)
    real_apr = emissions_apr / efficiency_rate
    
    return real_apr


def calculate_fee_tier(tick_spacing: int) -> int:
    """
    Calculate fee tier in basis points from tick spacing.
    
    Args:
        tick_spacing: Pool tick spacing
        
    Returns:
        Fee tier in basis points (e.g., 500 = 0.05%)
    """
    # This is an approximation - actual fee calculation may vary
    return tick_spacing * 10


def normalize_address(address: str) -> str:
    """
    Normalize Ethereum address to checksummed format.
    
    Args:
        address: Ethereum address
        
    Returns:
        Checksummed address
    """
    try:
        return Web3.to_checksum_address(address)
    except Exception:
        return address


def is_valid_address(address: str) -> bool:
    """
    Check if an address is a valid Ethereum address.
    
    Args:
        address: Address to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not address or not isinstance(address, str):
        return False
    
    if not address.startswith("0x") or len(address) != 42:
        return False
    
    try:
        Web3.to_checksum_address(address)
        return True
    except Exception:
        return False


def format_pool_symbol(token0_symbol: str, token1_symbol: str, fee_tier: int) -> str:
    """
    Format pool symbol with fee tier.
    
    Args:
        token0_symbol: First token symbol
        token1_symbol: Second token symbol
        fee_tier: Fee tier in basis points
        
    Returns:
        Formatted pool symbol (e.g., "USDC/WETH-0.05%")
    """
    fee_percentage = fee_tier / 10000
    return f"{token0_symbol}/{token1_symbol}-{fee_percentage:.2%}"