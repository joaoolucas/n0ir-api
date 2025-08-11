"""Data models for the pools module."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TokenInfo:
    """Token information."""
    
    address: str
    symbol: str
    decimals: int
    name: str = ""
    price_usd: Optional[float] = None
    logo_uri: Optional[str] = None
    
    def __post_init__(self):
        """Validate and normalize token address."""
        if self.address:
            # Ensure address is lowercase for consistency
            self.address = self.address.lower()


@dataclass
class PoolFilters:
    """Filters for pool queries."""
    
    pool_type: str = "all"  # "stable" | "volatile" | "all"
    min_tvl_usd: float = 1000
    min_volume_24h: float = 10000
    min_apr: float = 0
    blacklisted_tokens: List[str] = field(default_factory=list)
    limit: Optional[int] = None
    
    def __post_init__(self):
        """Validate filter parameters."""
        if self.pool_type not in ["stable", "volatile", "all"]:
            raise ValueError(f"Invalid pool_type: {self.pool_type}. Must be 'stable', 'volatile', or 'all'")
        
        if self.min_tvl_usd < 0:
            raise ValueError("min_tvl_usd must be non-negative")
            
        if self.min_volume_24h < 0:
            raise ValueError("min_volume_24h must be non-negative")
            
        if self.min_apr < 0:
            raise ValueError("min_apr must be non-negative")
            
        if self.limit is not None and self.limit <= 0:
            raise ValueError("limit must be positive")
        
        # Normalize blacklisted token addresses
        self.blacklisted_tokens = [addr.lower() for addr in self.blacklisted_tokens]


@dataclass
class PoolAPRData:
    """Concentrated liquidity pool data with APR information."""
    
    address: str
    symbol: str
    token0: TokenInfo
    token1: TokenInfo
    tvl_usd: float
    volume_24h: float
    tick_spacing: int
    fee_tier: int  # Fee in basis points (e.g., 500 = 0.05%)
    apr: float  # Total APR percentage
    current_tick: int
    liquidity: int
    sqrt_price_x96: int
    gauge_address: Optional[str] = None
    
    def __post_init__(self):
        """Validate and normalize pool address."""
        if self.address:
            self.address = self.address.lower()
    
    @property
    def fee_percentage(self) -> float:
        """Get fee as percentage (e.g., 0.05 for 0.05%)."""
        return self.fee_tier / 10000
    
    @property
    def is_stable(self) -> bool:
        """Check if this is a stable pool based on tick spacing."""
        from .constants import STABLE_TICK_SPACINGS
        return self.tick_spacing in STABLE_TICK_SPACINGS
    
    @property
    def is_volatile(self) -> bool:
        """Check if this is a volatile pool based on tick spacing."""
        from .constants import VOLATILE_TICK_SPACINGS
        return self.tick_spacing in VOLATILE_TICK_SPACINGS


@dataclass
class SwapRoute:
    """Swap route configuration for token conversion.
    
    Used for defining token swap paths through pools.
    """
    pools: List[str]
    tokens: List[str]
    tick_spacings: List[int]