"""Position schemas for API responses."""

from typing import Optional, List
from pydantic import BaseModel, Field


class PositionInfo(BaseModel):
    """Position information model."""
    
    id: int = Field(..., description="NFT token ID of the position")
    owner: str = Field(..., description="Owner address of the position")
    pool_address: str = Field(..., description="Pool address")
    tick_lower: int = Field(..., description="Lower tick boundary")
    tick_upper: int = Field(..., description="Upper tick boundary")
    current_tick: int = Field(..., description="Current tick of the pool")
    liquidity: str = Field(..., description="Position liquidity")
    in_range: bool = Field(..., description="Whether position is in range")
    staked: bool = Field(..., description="Whether position is staked in gauge")
    current_value_usd: Optional[float] = Field(None, description="Current staked position value in USD")
    unclaimed_fees_usd: Optional[float] = Field(None, description="Unclaimed emissions (AERO rewards) in USD")
    unclaimed_rewards_aero: Optional[float] = Field(None, description="Unclaimed emissions in AERO tokens")
    gauge_address: Optional[str] = Field(None, description="Gauge address if staked")
    
    # Additional fields from position manager
    token0: Optional[str] = Field(None, description="Token0 address")
    token1: Optional[str] = Field(None, description="Token1 address")
    tick_spacing: Optional[int] = Field(None, description="Pool tick spacing")
    
    # User tracking field (from database)
    user_id: Optional[str] = Field(None, description="User ID if position is tracked in database")

    class Config:
        json_schema_extra = {
            "example": {
                "id": 12345,
                "owner": "0x742d35Cc6634C0532925a3b844Bc9e7595f0fA27",
                "pool_address": "0x123...",
                "tick_lower": -887220,
                "tick_upper": 887220,
                "current_tick": -100,
                "liquidity": "1000000000000000000",
                "in_range": True,
                "staked": True,
                "current_value_usd": 1500.50,
                "gauge_address": "0x456..."
            }
        }


class PositionListResponse(BaseModel):
    """Response model for position list."""
    
    positions: List[PositionInfo] = Field(..., description="List of positions")
    total: int = Field(..., description="Total number of positions")
    
    class Config:
        json_schema_extra = {
            "example": {
                "positions": [],
                "total": 0
            }
        }


class PositionDetailResponse(BaseModel):
    """Response model for single position details."""
    
    position: PositionInfo = Field(..., description="Position details")
    
    class Config:
        json_schema_extra = {
            "example": {
                "position": {
                    "id": 12345,
                    "owner": "0x742d35Cc6634C0532925a3b844Bc9e7595f0fA27",
                    "pool_address": "0x123...",
                    "tick_lower": -887220,
                    "tick_upper": 887220,
                    "current_tick": -100,
                    "liquidity": "1000000000000000000",
                    "in_range": True,
                    "staked": True,
                    "current_value_usd": 1500.50,
                    "gauge_address": "0x456..."
                }
            }
        }