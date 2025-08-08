from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from app.schemas.common import PaginationInfo


class TokenInfo(BaseModel):
    address: str = Field(..., description="Token contract address")
    symbol: str = Field(..., description="Token symbol")
    decimals: int = Field(..., description="Token decimals")
    name: str = Field(..., description="Token name")
    price_usd: float = Field(0, description="Token price in USD")
    logo_uri: Optional[str] = Field(None, description="Token logo URI")


class PoolData(BaseModel):
    address: str = Field(..., description="Pool contract address")
    symbol: str = Field(..., description="Pool symbol")
    token0: TokenInfo = Field(..., description="First token in pair")
    token1: TokenInfo = Field(..., description="Second token in pair")
    tvl_usd: float = Field(..., description="Total value locked in USD")
    volume_24h: float = Field(..., description="24-hour trading volume in USD")
    tick_spacing: int = Field(..., description="Pool tick spacing")
    fee_tier: int = Field(..., description="Fee tier in basis points")
    apr: float = Field(..., description="Annual percentage rate")
    current_tick: int = Field(..., description="Current tick")
    liquidity: str = Field(..., description="Pool liquidity")
    sqrt_price_x96: str = Field(..., description="Square root price X96")
    gauge_address: Optional[str] = Field(None, description="Gauge contract address")
    is_stable: bool = Field(..., description="Whether this is a stable pool")


class PoolsListResponse(BaseModel):
    pools: List[PoolData] = Field(..., description="List of pools")
    pagination: PaginationInfo = Field(..., description="Pagination information")


class PoolBatchRequest(BaseModel):
    addresses: List[str] = Field(..., description="List of pool addresses", min_items=1, max_items=100)
    
    @field_validator("addresses")
    def validate_addresses(cls, v):
        # Validate that all addresses are valid Ethereum addresses
        for addr in v:
            if not addr.startswith("0x") or len(addr) != 42:
                raise ValueError(f"Invalid address format: {addr}")
        return v


class PoolStatsResponse(BaseModel):
    volume: float = Field(..., description="Trading volume for the period")
    fees_collected: float = Field(..., description="Fees collected for the period")
    tvl_change: float = Field(..., description="TVL change percentage")
    apr_history: List[dict] = Field(..., description="Historical APR data")


class PoolType(BaseModel):
    value: str = Field(..., pattern="^(stable|volatile|all)$")