"""Pydantic schemas for multi-strategy support."""

from enum import Enum
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from typing import List, Optional, Dict
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


# Hybrid Strategy Schemas
class ActiveStrategyInfo(BaseModel):
    """Information about an active strategy in user's active_strategies."""
    strategy_type: str = Field(..., description="Full strategy type name")
    status: str = Field(..., description="Strategy status")
    capital_allocated_usdc: Optional[Decimal] = Field(None, description="Capital allocated (optional)")
    created_at: str = Field(..., description="ISO timestamp when strategy was activated")
    updated_at: str = Field(..., description="ISO timestamp when strategy was last updated")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "strategy_type": "hedged_blueprint",
                "status": "active",
                "capital_allocated_usdc": 1000.0,
                "created_at": "2025-10-10T12:00:00Z",
                "updated_at": "2025-10-10T12:00:00Z"
            }
        }
    )


class ActiveStrategiesResponse(BaseModel):
    """Response showing user's active strategies."""
    user_id: str = Field(..., description="User wallet address")
    active_strategies: Dict[str, ActiveStrategyInfo] = Field(..., description="Map of strategy short codes to strategy info")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "0x123...",
                "active_strategies": {
                    "h3": {
                        "strategy_type": "hedged_blueprint",
                        "status": "active",
                        "created_at": "2025-10-10T12:00:00Z",
                        "updated_at": "2025-10-10T12:00:00Z"
                    }
                }
            }
        }
    )
