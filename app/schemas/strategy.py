"""Pydantic schemas for multi-strategy support."""

from enum import Enum
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class StrategyTypeEnum(str, Enum):
    """Strategy types supported by the platform."""
    HEDGED_WETH = "hedged_weth_only"
    HEDGED_CBBTC = "hedged_cbbtc_only"
    HEDGED_BLUEPRINT = "hedged_blueprint"
    NONHEDGED_WETH = "nonhedged_weth_only"
    NONHEDGED_CBBTC = "nonhedged_cbbtc_only"
    NONHEDGED_BLUEPRINT = "nonhedged_blueprint"
    STABLE_USDC_EURC = "stable_usdc_eurc"
    STABLE_USDC_BRZ = "stable_usdc_brz"

    @property
    def is_hedged(self) -> bool:
        """Check if this strategy uses hedging."""
        return self.value.startswith("hedged_")

    @property
    def is_stable(self) -> bool:
        """Check if this is a stable pair strategy."""
        return self.value.startswith("stable_")


# Mapping from short codes to full enum values
STRATEGY_SHORT_CODES = {
    "h1": "hedged_weth_only",
    "h2": "hedged_cbbtc_only",
    "h3": "hedged_blueprint",
    "n1": "nonhedged_weth_only",
    "n2": "nonhedged_cbbtc_only",
    "n3": "nonhedged_blueprint",
    "s1": "stable_usdc_eurc",
    "s2": "stable_usdc_brz",
}


def parse_strategy_type(strategy_input: str) -> StrategyTypeEnum:
    """
    Parse strategy type from either short code or full name.

    Args:
        strategy_input: Short code (e.g., "h1") or full name (e.g., "hedged_weth_only")

    Returns:
        StrategyTypeEnum

    Raises:
        ValueError: If strategy type is invalid
    """
    # Try short code first
    if strategy_input in STRATEGY_SHORT_CODES:
        strategy_value = STRATEGY_SHORT_CODES[strategy_input]
    else:
        strategy_value = strategy_input

    # Validate against enum
    try:
        return StrategyTypeEnum(strategy_value)
    except ValueError:
        raise ValueError(
            f"Invalid strategy type: {strategy_input}. "
            f"Valid short codes: {', '.join(STRATEGY_SHORT_CODES.keys())}. "
            f"Valid full names: {', '.join([s.value for s in StrategyTypeEnum])}"
        )


class StrategyStatusEnum(str, Enum):
    """Strategy status values."""
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"


# Request Schemas
class CreateStrategyRequest(BaseModel):
    """Request to create a new strategy."""
    strategy_type: StrategyTypeEnum = Field(..., description="Type of strategy to create")
    capital_usdc: Decimal = Field(..., gt=0, description="Initial capital allocation in USDC")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "strategy_type": "hedged_blueprint",
                "capital_usdc": 1000.0
            }
        }
    )


class UpdateStrategyStatusRequest(BaseModel):
    """Request to update strategy status."""
    status: StrategyStatusEnum = Field(..., description="New status for the strategy")


class UpdateStrategyCapitalRequest(BaseModel):
    """Request to update strategy capital allocation."""
    capital_usdc: Decimal = Field(..., gt=0, description="New capital allocation in USDC")


# Response Schemas
class StrategyResponse(BaseModel):
    """Response schema for a single strategy."""
    strategy_id: UUID = Field(..., description="Unique strategy ID")
    user_id: str = Field(..., description="User wallet address")
    strategy_type: StrategyTypeEnum = Field(..., description="Strategy type")
    status: StrategyStatusEnum = Field(..., description="Current status")
    capital_allocated_usdc: Decimal = Field(..., description="Capital allocated in USDC")
    created_at: datetime = Field(..., description="Strategy creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = ConfigDict(from_attributes=True)


class StrategyListResponse(BaseModel):
    """Response schema for list of strategies."""
    strategies: List[StrategyResponse] = Field(..., description="List of user strategies")
    total_count: int = Field(..., description="Total number of strategies")


class PositionSummary(BaseModel):
    """Summary of a position for strategy details."""
    token_id: int = Field(..., description="NFT token ID")
    pool_address: str = Field(..., description="Pool address")
    pool_name: Optional[str] = Field(None, description="Pool name")
    status: str = Field(..., description="Position status")
    entry_amount_usdc: Decimal = Field(..., description="Entry amount in USDC")
    current_value_usdc: Optional[Decimal] = Field(None, description="Current value in USDC")
    unrealized_pnl_usdc: Decimal = Field(..., description="Unrealized PnL in USDC")

    model_config = ConfigDict(from_attributes=True)


class StrategyPerformance(BaseModel):
    """Performance metrics for a strategy."""
    total_positions: int = Field(..., description="Total number of positions (active + closed)")
    active_positions: int = Field(..., description="Number of active positions")
    total_deployed_usdc: Decimal = Field(..., description="Total capital deployed")
    current_value_usdc: Decimal = Field(..., description="Current value of all positions")
    unrealized_pnl_usdc: Decimal = Field(..., description="Unrealized PnL")
    unrealized_pnl_pct: Optional[Decimal] = Field(None, description="Unrealized PnL percentage")
    realized_pnl_usdc: Decimal = Field(..., description="Realized PnL")
    realized_pnl_pct: Optional[Decimal] = Field(None, description="Realized PnL percentage")
    total_pnl_usdc: Decimal = Field(..., description="Total PnL (realized + unrealized)")
    total_pnl_pct: Optional[Decimal] = Field(None, description="Total PnL percentage")


class StrategyWithPositionsResponse(BaseModel):
    """Detailed strategy response with positions and performance."""
    strategy_id: UUID = Field(..., description="Unique strategy ID")
    user_id: str = Field(..., description="User wallet address")
    strategy_type: StrategyTypeEnum = Field(..., description="Strategy type")
    status: StrategyStatusEnum = Field(..., description="Current status")
    capital_allocated_usdc: Decimal = Field(..., description="Capital allocated in USDC")
    created_at: datetime = Field(..., description="Strategy creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    positions: List[PositionSummary] = Field(default_factory=list, description="List of positions")
    performance: StrategyPerformance = Field(..., description="Strategy performance metrics")

    model_config = ConfigDict(from_attributes=True)


class ExecuteStrategyRequest(BaseModel):
    """Request to execute or rebalance a strategy."""
    force_rebalance: bool = Field(default=False, description="Force rebalance even if not needed")


class ExecuteStrategyResponse(BaseModel):
    """Response from strategy execution."""
    strategy_id: UUID = Field(..., description="Strategy ID that was executed")
    action_taken: str = Field(..., description="Action taken: 'opened', 'rebalanced', 'no_action'")
    positions_created: List[int] = Field(default_factory=list, description="List of new position token IDs")
    positions_closed: List[int] = Field(default_factory=list, description="List of closed position token IDs")
    message: str = Field(..., description="Human-readable result message")
