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
    NONHEDGED_WETH = "nonhedged_weth_only"
    NONHEDGED_CBBTC = "nonhedged_cbbtc_only"
    NONHEDGED_CBLTC = "nonhedged_cbltc_cbbtc"
    NONHEDGED_CBADA = "nonhedged_cbada_cbbtc"
    NONHEDGED_CBXRP = "nonhedged_cbxrp_cbbtc"
    NONHEDGED_CBDOGE = "nonhedged_cbdoge_cbbtc"
    STABLE_USDC_EURC = "stable_usdc_eurc"
    STABLE_USDC_MSUSD = "stable_usdc_msusd"

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
    "n1": "nonhedged_weth_only",
    "n2": "nonhedged_cbbtc_only",
    "n3": "nonhedged_cbltc_cbbtc",
    "n4": "nonhedged_cbada_cbbtc",
    "n5": "nonhedged_cbxrp_cbbtc",
    "n6": "nonhedged_cbdoge_cbbtc",
    "s1": "stable_usdc_eurc",
    "s2": "stable_usdc_msusd",
}

# Mapping from pool address to strategy short code
# Each strategy only opens positions in specific pools
POOL_TO_STRATEGY = {
    "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59": ["h1", "n1"],  # WETH/USDC (hedged or non-hedged)
    "0x4e962bb3889bf030368f56810a9c96b83cb3e778": ["h2", "n2"],  # cbBTC/USDC (hedged or non-hedged)
    "0xe846373c1a92b167b4e9cd5d8e4d6b1db9e90ec7": ["s1"],  # USDC/EURC
    "0x7501bc8bb51616f79bfa524e464fb7b41f0b10fb": ["s2"],  # USDC/msUSD
    "0x6044c817e55a03dadc5f6b8b7045af1985ae90fa": ["n3"],  # cbLTC/cbBTC
    "0x8782d97c8b25b4d17dbfbaa03f25dc18e51e909d": ["n4"],  # cbADA/cbBTC
    "0x95ff4985af7ed78421215be100c18a2b987f7e90": ["n5"],  # cbXRP/cbBTC
    "0x363d1607b8da83d6b6ea76d017ceecf1316bb08a": ["n6"],  # cbDOGE/cbBTC
}


def infer_strategy_from_pool(pool_address: str, active_strategies: dict) -> Optional[str]:
    """
    Infer which strategy opened a position based on pool address.

    Args:
        pool_address: Pool contract address (case-insensitive)
        active_strategies: User's active_strategies dict {strategy_code: {...}}

    Returns:
        Strategy short code (e.g., "s1") or None if cannot determine

    Example:
        If pool is EURC/USDC and user has s1 active → returns "s1"
        If pool is WETH/USDC and user has both h1 and n1 active → returns None (ambiguous)
    """
    pool_lower = pool_address.lower()

    # Get possible strategies for this pool
    possible_strategies = POOL_TO_STRATEGY.get(pool_lower, [])

    if not possible_strategies:
        return None

    # Filter to only strategies that are active for this user
    active_matches = [s for s in possible_strategies if s in active_strategies]

    # If exactly one match, we know which strategy opened it
    if len(active_matches) == 1:
        return active_matches[0]

    # Ambiguous (multiple active strategies for same pool) or no active match
    return None


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
    allocated_capital_usd: Decimal = Field(..., description="Maximum capital allocated to this strategy")
    deployed_capital_usd: Decimal = Field(default=Decimal(0), description="Capital currently deployed in active positions")
    created_at: str = Field(..., description="ISO timestamp when strategy was activated")
    updated_at: str = Field(..., description="ISO timestamp when strategy was last updated")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "strategy_type": "hedged_blueprint",
                "status": "active",
                "allocated_capital_usd": 1000.0,
                "deployed_capital_usd": 300.0,
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
