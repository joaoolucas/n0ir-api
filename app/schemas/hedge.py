"""Schemas for hedge-related API endpoints."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime


class HedgedPositionCreate(BaseModel):
    """Request model for creating a hedged position."""
    
    pool_address: str = Field(..., description="Address of the Uniswap V3 pool")
    usdc_amount: int = Field(..., description="Amount of USDC to invest", ge=10000000)  # Min 10 USDC
    range_percentage: int = Field(500, description="Range percentage from current price (500 = 5%)", ge=100, le=10000)
    enable_hedge: bool = Field(True, description="Whether to enable delta-neutral hedge")
    slippage_bps: int = Field(30, description="Slippage tolerance in basis points", ge=0, le=1000)
    
    class Config:
        json_schema_extra = {
            "example": {
                "pool_address": "0x123...",
                "usdc_amount": 100000000,  # 100 USDC
                "range_percentage": 500,    # 5% range
                "enable_hedge": True,
                "slippage_bps": 30
            }
        }


class HedgedPositionResponse(BaseModel):
    """Response model for hedged position creation."""
    
    token_id: int = Field(..., description="NFT token ID of the LP position")
    hedge_id: int = Field(..., description="Hedge position ID (0 if no hedge)")
    pool_address: str = Field(..., description="Pool address")
    usdc_invested: int = Field(..., description="Total USDC invested")
    hedge_enabled: bool = Field(..., description="Whether hedge is enabled")
    hedge_size_usdc: Optional[int] = Field(None, description="Hedge position size in USDC")
    collateral_usdc: Optional[int] = Field(None, description="Hedge collateral in USDC")
    leverage: Optional[int] = Field(None, description="Hedge leverage")
    status: str = Field(..., description="Position status")
    tx_hash: Optional[str] = Field(None, description="Transaction hash")
    
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
                "status": "active",
                "tx_hash": "0xabc..."
            }
        }


class HedgeStatusResponse(BaseModel):
    """Response model for hedge status query."""
    
    nft_token_id: int = Field(..., description="NFT token ID")
    hedge_id: int = Field(..., description="Hedge position ID")
    hedge_enabled: bool = Field(..., description="Whether hedge is enabled")
    market: str = Field(..., description="Trading market (e.g., ETH-USD)")
    size_usdc: Decimal = Field(..., description="Hedge size in USDC")
    collateral_usdc: Decimal = Field(..., description="Collateral amount in USDC")
    leverage: int = Field(..., description="Position leverage")
    entry_price: Decimal = Field(..., description="Entry price")
    current_price: Decimal = Field(..., description="Current market price")
    pnl_usdc: Decimal = Field(..., description="Current P&L in USDC")
    funding_paid_usdc: Decimal = Field(..., description="Total funding paid in USDC")
    status: str = Field(..., description="Position status (active, closed, liquidated)")
    health_ratio: float = Field(..., description="Position health ratio (< 0.2 = liquidation risk)")
    created_at: datetime = Field(..., description="Position creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
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
                "health_ratio": 0.85,
                "created_at": "2025-01-12T10:00:00Z",
                "updated_at": "2025-01-12T11:00:00Z"
            }
        }


class HedgeCloseRequest(BaseModel):
    """Request model for closing a hedge position."""
    
    min_usdc_out: int = Field(0, description="Minimum USDC to receive", ge=0)
    slippage_bps: int = Field(30, description="Slippage tolerance in basis points", ge=0, le=1000)
    
    class Config:
        json_schema_extra = {
            "example": {
                "min_usdc_out": 95000000,  # 95 USDC minimum
                "slippage_bps": 30
            }
        }


class HedgeCloseResponse(BaseModel):
    """Response model for hedge closure."""
    
    token_id: int = Field(..., description="NFT token ID")
    hedge_id: int = Field(..., description="Hedge position ID")
    usdc_received: int = Field(..., description="Total USDC received")
    final_pnl: Decimal = Field(..., description="Final P&L in USDC")
    funding_paid: Decimal = Field(..., description="Total funding paid")
    tx_hash: str = Field(..., description="Transaction hash")
    
    class Config:
        json_schema_extra = {
            "example": {
                "token_id": 12345,
                "hedge_id": 67890,
                "usdc_received": 102500000,
                "final_pnl": "2.500000",
                "funding_paid": "0.150000",
                "tx_hash": "0xdef..."
            }
        }


class HedgeSummaryResponse(BaseModel):
    """Response model for hedge summary statistics."""
    
    total_hedged_positions: int = Field(..., description="Total number of hedged positions")
    active_hedges: int = Field(..., description="Number of active hedges")
    total_hedge_value_usdc: float = Field(..., description="Total value locked in hedges")
    total_pnl_usdc: float = Field(..., description="Total P&L across all hedges")
    average_leverage: float = Field(..., description="Average leverage across hedges")
    total_funding_paid: float = Field(..., description="Total funding paid")
    at_risk_positions: int = Field(..., description="Number of positions at liquidation risk")
    markets: Dict[str, int] = Field(..., description="Breakdown by market")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_hedged_positions": 150,
                "active_hedges": 125,
                "total_hedge_value_usdc": 1500000.50,
                "total_pnl_usdc": 25000.75,
                "average_leverage": 3.2,
                "total_funding_paid": 1500.25,
                "at_risk_positions": 3,
                "markets": {
                    "ETH-USD": 80,
                    "BTC-USD": 45
                }
            }
        }


class HedgePerformanceResponse(BaseModel):
    """Response model for hedge performance metrics."""
    
    timeframe: str = Field(..., description="Analysis timeframe")
    hedged_positions: Dict[str, Any] = Field(..., description="Hedged position metrics")
    unhedged_positions: Dict[str, Any] = Field(..., description="Unhedged position metrics")
    hedge_effectiveness: float = Field(..., description="Hedge effectiveness ratio")
    volatility_reduction: float = Field(..., description="Volatility reduction percentage")
    
    class Config:
        json_schema_extra = {
            "example": {
                "timeframe": "24h",
                "hedged_positions": {
                    "count": 125,
                    "avg_return": 2.5,
                    "total_pnl": 25000.0
                },
                "unhedged_positions": {
                    "count": 200,
                    "avg_return": 1.8,
                    "total_pnl": 36000.0
                },
                "hedge_effectiveness": 0.85,
                "volatility_reduction": 42.5
            }
        }


class HedgeAlert(BaseModel):
    """Model for hedge monitoring alerts."""
    
    type: str = Field(..., description="Alert type")
    severity: str = Field(..., description="Alert severity (info, warning, critical)")
    token_id: int = Field(..., description="NFT token ID")
    hedge_id: int = Field(..., description="Hedge position ID")
    message: str = Field(..., description="Alert message")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional alert details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Alert timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "liquidation_risk",
                "severity": "critical",
                "token_id": 12345,
                "hedge_id": 67890,
                "message": "Position 12345 at liquidation risk (health: 0.15)",
                "details": {
                    "health_ratio": 0.15,
                    "pnl": -15000.0
                },
                "timestamp": "2025-01-12T12:00:00Z"
            }
        }


class HedgeEventResponse(BaseModel):
    """Response model for hedge events."""
    
    id: int = Field(..., description="Event ID")
    nft_token_id: int = Field(..., description="NFT token ID")
    hedge_id: int = Field(..., description="Hedge position ID")
    event_type: str = Field(..., description="Event type")
    tx_hash: Optional[str] = Field(None, description="Transaction hash")
    block_number: Optional[int] = Field(None, description="Block number")
    block_timestamp: Optional[datetime] = Field(None, description="Block timestamp")
    data: Dict[str, Any] = Field(default_factory=dict, description="Event data")
    created_at: datetime = Field(..., description="Event creation timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "nft_token_id": 12345,
                "hedge_id": 67890,
                "event_type": "opened",
                "tx_hash": "0xabc...",
                "block_number": 12345678,
                "block_timestamp": "2025-01-12T10:00:00Z",
                "data": {
                    "size_usdc": "50000000",
                    "leverage": 3,
                    "entry_price": "3500.00"
                },
                "created_at": "2025-01-12T10:00:05Z"
            }
        }