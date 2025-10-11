"""Pydantic schemas for capital allocation tracking."""

from decimal import Decimal
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


class CapitalInfo(BaseModel):
    """Capital allocation breakdown for a strategy."""
    total_usd: Decimal = Field(..., description="Amount available to deploy now (min of available_to_deploy and wallet_balance)")
    allocated_for_strategy: Decimal = Field(..., description="Total capital allocated to this strategy")
    already_deployed: Decimal = Field(..., description="Capital currently active in positions")
    available_to_deploy: Decimal = Field(..., description="Remaining allocation (allocated - deployed)")
    wallet_balance: Decimal = Field(..., description="Actual USDC balance in wallet")
    reason: Optional[str] = Field(None, description="Reason if action is limited/blocked (e.g., 'allocation_exhausted')")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_usd": "70.0",
                "allocated_for_strategy": "100.0",
                "already_deployed": "30.0",
                "available_to_deploy": "70.0",
                "wallet_balance": "150.0",
                "reason": None
            }
        }
    )


class PositionEventRequest(BaseModel):
    """Request body for reporting position lifecycle events."""
    type: Literal["opened", "closed", "rebalanced"] = Field(..., description="Event type")
    timestamp: datetime = Field(..., description="Event timestamp")
    token_id: int = Field(..., description="NFT token ID")
    tx_hash: str = Field(..., description="Transaction hash")

    # For "opened" events
    capital_deployed_usd: Optional[Decimal] = Field(None, description="Capital deployed (for 'opened' events)")

    # For "closed" events
    capital_returned_usd: Optional[Decimal] = Field(None, description="Capital returned (for 'closed' events)")
    pnl_usd: Optional[Decimal] = Field(None, description="PnL in USD (for 'closed' events)")

    # For "rebalanced" events
    capital_change_usd: Optional[Decimal] = Field(None, description="Capital change, positive=added, negative=removed (for 'rebalanced' events)")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": "opened",
                    "timestamp": "2025-10-11T17:20:00Z",
                    "token_id": 28460398,
                    "tx_hash": "0xabc123...",
                    "capital_deployed_usd": 50.0
                },
                {
                    "type": "closed",
                    "timestamp": "2025-10-11T18:30:00Z",
                    "token_id": 28460398,
                    "tx_hash": "0xdef456...",
                    "capital_returned_usd": 52.5,
                    "pnl_usd": 2.5
                }
            ]
        }
    )


class PositionEventResponse(BaseModel):
    """Response after processing a position event."""
    success: bool = Field(..., description="Whether event was processed successfully")
    strategy_code: str = Field(..., description="Strategy code (e.g., 'h3')")
    deployed_capital_usd: Decimal = Field(..., description="Updated deployed capital for strategy")
    available_capital_usd: Decimal = Field(..., description="Updated available capital for strategy")
    message: Optional[str] = Field(None, description="Additional information")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "strategy_code": "h3",
                "deployed_capital_usd": 50.0,
                "available_capital_usd": 50.0,
                "message": "Position opened successfully"
            }
        }
    )


class AllocationUpdateRequest(BaseModel):
    """Request to update capital allocation for a strategy."""
    allocated_capital_usd: Decimal = Field(..., description="New allocated capital amount", gt=0)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "allocated_capital_usd": 150.0
            }
        }
    )


class AllocationUpdateResponse(BaseModel):
    """Response after updating capital allocation."""
    success: bool = Field(..., description="Whether update was successful")
    strategy_code: str = Field(..., description="Strategy code")
    allocated_capital_usd: Decimal = Field(..., description="Updated allocated capital")
    deployed_capital_usd: Decimal = Field(..., description="Current deployed capital")
    available_capital_usd: Decimal = Field(..., description="Available capital (allocated - deployed)")
    message: Optional[str] = Field(None, description="Additional information")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "strategy_code": "h3",
                "allocated_capital_usd": 150.0,
                "deployed_capital_usd": 30.0,
                "available_capital_usd": 120.0,
                "message": "Allocation updated successfully"
            }
        }
    )
