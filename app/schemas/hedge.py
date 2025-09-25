"""
Schemas for Moonwell hedge positions and account health.
"""
from typing import List, Optional
from decimal import Decimal
from pydantic import BaseModel, Field


class SupplyPosition(BaseModel):
    """Supply position in a Moonwell market."""
    market: str = Field(..., description="Market identifier (e.g., 'mUSDC')")
    underlying_asset: str = Field(..., description="Underlying asset symbol (e.g., 'USDC')")
    mtoken_balance: Decimal = Field(..., description="Amount of mTokens held")
    exchange_rate: Decimal = Field(..., description="Current exchange rate")
    underlying_balance: Decimal = Field(..., description="Underlying balance with accrued interest")
    underlying_balance_usd: Decimal = Field(..., description="USD value of underlying balance")
    supply_apy: Decimal = Field(..., description="Current supply APY")


class BorrowPosition(BaseModel):
    """Borrow position in a Moonwell market."""
    market: str = Field(..., description="Market identifier (e.g., 'mWETH')")
    underlying_asset: str = Field(..., description="Underlying asset symbol (e.g., 'WETH')")
    borrow_balance: Decimal = Field(..., description="Current borrow balance with accrued interest")
    borrow_balance_usd: Decimal = Field(..., description="USD value of borrow balance")
    borrow_apy: Decimal = Field(..., description="Current borrow APY")


class AccountLiquidity(BaseModel):
    """Account liquidity and health information."""
    available_to_borrow_usd: Decimal = Field(..., description="Amount available to borrow in USD")
    shortfall_usd: Decimal = Field(..., description="Shortfall amount if underwater (0 if healthy)")
    is_liquidatable: bool = Field(..., description="Whether account is subject to liquidation")


class AccountHealth(BaseModel):
    """Account health metrics."""
    health_factor: Decimal = Field(..., description="Health factor (>1 is safe, <1 is liquidatable)")
    ltv: Decimal = Field(..., description="Current loan-to-value ratio")
    max_ltv: Decimal = Field(..., description="Maximum allowed loan-to-value ratio")
    liquidation_threshold: Decimal = Field(..., description="LTV at which liquidation occurs")


class PositionSummary(BaseModel):
    """Summary of all positions."""
    total_supply_usd: Decimal = Field(..., description="Total USD value of supplied assets")
    total_borrow_usd: Decimal = Field(..., description="Total USD value of borrowed assets")
    net_value_usd: Decimal = Field(..., description="Net position value (supply - borrow)")
    net_apy: Decimal = Field(..., description="Net APY considering supplies and borrows")


class HedgePositionResponse(BaseModel):
    """Complete hedge position response."""
    wallet: str = Field(..., description="Wallet address")

    # Positions
    supply_positions: List[SupplyPosition] = Field(..., description="List of supply positions")
    borrow_positions: List[BorrowPosition] = Field(..., description="List of borrow positions")

    # Summary
    summary: PositionSummary = Field(..., description="Position summary")

    # Health metrics
    liquidity: AccountLiquidity = Field(..., description="Account liquidity information")
    health: AccountHealth = Field(..., description="Account health metrics")

    # Additional info
    timestamp: str = Field(..., description="Response timestamp")


class MarketInfo(BaseModel):
    """Information about a Moonwell market."""
    market: str = Field(..., description="Market identifier")
    underlying_asset: str = Field(..., description="Underlying asset symbol")
    total_supply: Decimal = Field(..., description="Total supply in the market")
    total_borrows: Decimal = Field(..., description="Total borrows in the market")
    available_liquidity: Decimal = Field(..., description="Available liquidity to borrow")
    utilization: Decimal = Field(..., description="Utilization rate percentage")
    supply_apy: Decimal = Field(..., description="Current supply APY")
    borrow_apy: Decimal = Field(..., description="Current borrow APY")
    exchange_rate: Decimal = Field(..., description="Current exchange rate")