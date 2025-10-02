"""
Schemas for vault hedge positions and account health.
"""
from typing import List, Optional
from decimal import Decimal
from pydantic import BaseModel, Field


class VaultPositionInfo(BaseModel):
    """Vault position hedge information."""
    token_id: int = Field(..., description="NFT token ID")
    collateral_usdc: Decimal = Field(..., description="Collateral amount in USDC")
    debt_amount: Decimal = Field(..., description="Debt amount in asset terms")
    debt_usd: Decimal = Field(..., description="Debt value in USD")
    hedged_asset: str = Field(..., description="Asset being hedged (address)")
    hedged_asset_symbol: str = Field(..., description="Asset symbol (e.g., WETH, cbBTC)")
    is_hedged: bool = Field(..., description="Whether position has an active hedge")
    exposure_usd: Optional[Decimal] = Field(None, description="LP exposure to the hedged asset in USD")
    net_delta_usd: Optional[Decimal] = Field(None, description="Net delta (debt - exposure)")
    collateral_supply_apy: Optional[Decimal] = Field(None, description="Current supply APY on USDC collateral (Aave)")
    hedged_asset_borrow_apy: Optional[Decimal] = Field(None, description="Current borrow APY on hedged asset (Aave)")


class GlobalHealthMetrics(BaseModel):
    """Global health metrics for all vault positions."""
    total_collateral_usd: Decimal = Field(..., description="Total collateral across all positions")
    total_debt_weth: Decimal = Field(..., description="Total WETH debt")
    total_debt_btc: Decimal = Field(..., description="Total BTC debt")
    health_factor: Decimal = Field(..., description="Protocol-wide health factor")
    available_borrows_usd: Decimal = Field(..., description="Available borrowing capacity in USD")
    is_at_risk: bool = Field(..., description="Whether protocol is at risk")


class HedgePositionResponse(BaseModel):
    """Complete hedge position response from vault contract."""
    wallet: str = Field(..., description="Wallet address")

    # Positions
    positions: List[VaultPositionInfo] = Field(default=[], description="List of hedged positions")

    # Global metrics
    global_health: GlobalHealthMetrics = Field(..., description="Protocol-wide health metrics")

    # Summary
    total_positions: int = Field(..., description="Total number of positions")
    total_collateral_usd: Decimal = Field(..., description="Total collateral in USD")
    total_debt_usd: Decimal = Field(..., description="Total debt in USD")
    net_value_usd: Decimal = Field(..., description="Net value (collateral - debt)")

    # Additional info
    timestamp: str = Field(..., description="Response timestamp")