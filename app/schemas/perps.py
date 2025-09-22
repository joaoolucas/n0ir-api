"""Perpetuals (Perps) schemas for short positions."""

from typing import Optional, List
from pydantic import BaseModel, Field


class PerpsPosition(BaseModel):
    """Individual perpetual position details."""

    pair: str = Field(..., description="Trading pair (e.g., BTC/USD)")
    pair_index: int = Field(..., description="Avantis pair index")
    is_long: bool = Field(..., description="True for long, False for short")

    # Position details
    collateral_usdc: float = Field(..., description="Collateral amount in USDC")
    leverage: float = Field(..., description="Leverage multiplier")
    notional_value_usdc: float = Field(..., description="Total position exposure in USDC")
    position_size: float = Field(..., description="Position size in base asset")

    # Prices
    entry_price: float = Field(..., description="Entry price of the position")
    current_price: float = Field(..., description="Current market price")
    liquidation_price: float = Field(..., description="Liquidation price")

    # P&L
    pnl_usdc: float = Field(..., description="Profit/Loss in USDC")
    pnl_percentage: float = Field(..., description="Profit/Loss percentage")

    # Optional fields
    take_profit: Optional[float] = Field(None, description="Take profit price if set")
    stop_loss: Optional[float] = Field(None, description="Stop loss price if set")
    margin_fee: Optional[float] = Field(None, description="Margin/funding fee")
    open_interest_usdc: Optional[float] = Field(None, description="Open interest for this position")
    timestamp: Optional[int] = Field(None, description="Position open timestamp")


class PerpsPositionListResponse(BaseModel):
    """Response containing list of perpetual positions."""

    wallet_address: str = Field(..., description="Wallet address queried")
    positions: List[PerpsPosition] = Field(..., description="List of open positions")
    total_positions: int = Field(..., description="Total number of positions")

    # Aggregate statistics
    total_collateral_usdc: float = Field(..., description="Total collateral across all positions")
    total_notional_usdc: float = Field(..., description="Total notional exposure")
    total_pnl_usdc: float = Field(..., description="Total P&L in USDC")

    # Breakdown by type
    short_positions_count: int = Field(..., description="Number of short positions")
    long_positions_count: int = Field(..., description="Number of long positions")


class PerpsErrorResponse(BaseModel):
    """Error response for perps endpoints."""

    error: str = Field(..., description="Error message")
    details: Optional[dict] = Field(None, description="Additional error details")