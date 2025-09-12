"""Position schemas for API responses."""

from typing import Optional, List
from pydantic import BaseModel, Field
from decimal import Decimal


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
    
    # Pool information
    pool_name: Optional[str] = Field(None, description="Pool name/symbol (e.g., WETH/USDC-0.3%)")
    
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


# Hedge-related schemas (imported from spec)
class HedgedPositionCreate(BaseModel):
    """Request model for creating a hedged position via positions endpoint."""
    
    pool_address: str = Field(..., description="Pool address for the position")
    usdc_amount: int = Field(..., description="Amount of USDC to invest")
    range_percentage: int = Field(500, description="Range percentage (500 = 5%)")
    enable_hedge: bool = Field(True, description="Whether to enable hedge")
    slippage_bps: int = Field(30, description="Slippage tolerance in basis points")
    
    class Config:
        json_schema_extra = {
            "example": {
                "pool_address": "0x123...",
                "usdc_amount": 100000000,
                "range_percentage": 500,
                "enable_hedge": True,
                "slippage_bps": 30
            }
        }


class HedgedPositionResponse(BaseModel):
    """Response model for hedged position creation."""
    
    token_id: int = Field(..., description="NFT token ID")
    hedge_id: int = Field(..., description="Hedge ID (0 if no hedge)")
    pool_address: str = Field(..., description="Pool address")
    usdc_invested: int = Field(..., description="USDC invested")
    hedge_enabled: bool = Field(..., description="Hedge enabled status")
    hedge_size_usdc: Optional[int] = Field(None, description="Hedge size in USDC")
    collateral_usdc: Optional[int] = Field(None, description="Hedge collateral")
    leverage: Optional[int] = Field(None, description="Hedge leverage")
    status: str = Field(..., description="Position status")
    
    class Config:
        json_schema_extra = {
            "example": {
                "token_id": 12345,
                "hedge_id": 67890,
                "pool_address": "0x123...",
                "usdc_invested": 100000000,
                "hedge_enabled": True,
                "hedge_size_usdc": 50000000,
                "collateral_usdc": 16666667,
                "leverage": 3,
                "status": "active"
            }
        }


class HedgeStatusResponse(BaseModel):
    """Response model for hedge status query."""
    
    nft_token_id: int = Field(..., description="NFT token ID")
    hedge_id: int = Field(..., description="Hedge ID")
    hedge_enabled: bool = Field(..., description="Hedge enabled")
    market: str = Field(..., description="Market (ETH-USD, BTC-USD)")
    size_usdc: Decimal = Field(..., description="Hedge size")
    collateral_usdc: Decimal = Field(..., description="Collateral")
    leverage: int = Field(..., description="Leverage")
    entry_price: Decimal = Field(..., description="Entry price")
    current_price: Decimal = Field(..., description="Current price")
    pnl_usdc: Decimal = Field(..., description="P&L in USDC")
    funding_paid_usdc: Decimal = Field(..., description="Funding paid")
    status: str = Field(..., description="Status")
    health_ratio: float = Field(..., description="Health ratio")
    
    class Config:
        json_schema_extra = {
            "example": {
                "nft_token_id": 12345,
                "hedge_id": 67890,
                "hedge_enabled": True,
                "market": "ETH-USD",
                "size_usdc": "50.000000",
                "collateral_usdc": "16.666667",
                "leverage": 3,
                "entry_price": "3500.00000000",
                "current_price": "3550.00000000",
                "pnl_usdc": "2.500000",
                "funding_paid_usdc": "0.150000",
                "status": "active",
                "health_ratio": 0.85
            }
        }