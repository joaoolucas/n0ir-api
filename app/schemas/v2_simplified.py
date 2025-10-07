"""Simplified v2 API response schemas - cleaner and more efficient."""

from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
import enum


# Reuse existing enums
class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"


class TransactionType(str, enum.Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAW = "WITHDRAW"
    POSITION_CREATED = "POSITION_CREATED"
    POSITION_CLOSED = "POSITION_CLOSED"


class TransactionStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"


class PositionStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


# Simplified Response Models

class UserResponseV2(BaseModel):
    """Simplified user response."""
    model_config = ConfigDict(from_attributes=True)
    
    user_id: str
    cdp_wallet_address: Optional[str]
    balance: Decimal = Field(..., description="Current USD balance")
    status: UserStatus = UserStatus.ACTIVE
    created_at: datetime


class BalanceResponseV2(BaseModel):
    """Simplified balance response with essential fields only."""
    user_id: str
    wallet_balance: Decimal = Field(..., description="Current spendable balance")
    positions_value: Decimal = Field(..., description="Total value of all positions")
    total_value: Decimal = Field(..., description="Wallet + positions")


class TransactionResponseV2(BaseModel):
    """Simplified transaction response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    type: TransactionType
    amount: Decimal = Field(..., description="Transaction amount in USD")
    status: TransactionStatus
    tx_hash: Optional[str] = None
    created_at: datetime
    
    # Optional enrichment for position transactions
    pool_name: Optional[str] = Field(None, description="Pool for position transactions")
    token_id: Optional[int] = Field(None, description="NFT token ID for positions")


class PositionResponseV2(BaseModel):
    """Simplified position response."""
    model_config = ConfigDict(from_attributes=True)
    
    token_id: int = Field(..., description="NFT position ID")
    pool_address: str
    pool_name: Optional[str]
    status: PositionStatus
    
    # Core financial data
    entry_amount: Decimal = Field(..., description="Amount invested")
    current_value: Decimal = Field(..., description="Current position value")
    pnl: Decimal = Field(..., description="Total P&L including fees")
    pnl_percent: Decimal = Field(..., description="P&L percentage")
    
    # Staking info
    staked: bool = False
    gauge_address: Optional[str] = None
    
    # Timestamps
    created_at: datetime
    closed_at: Optional[datetime] = None


class PnLResponseV2(BaseModel):
    """Simplified P&L response."""
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    total_pnl_percent: Decimal


class PerformanceResponseV2(BaseModel):
    """Simplified performance metrics."""
    balance: Decimal = Field(..., description="Total portfolio value")
    pnl: Decimal = Field(..., description="Total P&L in USD")
    pnl_percent: Decimal = Field(..., description="Total P&L percentage")
    apr: float = Field(..., description="Average APR across positions")
    active_positions: int


# List responses with proper pagination

class PaginationMeta(BaseModel):
    """Pagination metadata."""
    total: int
    offset: int
    limit: int
    has_next: bool
    has_prev: bool


class TransactionListResponseV2(BaseModel):
    """Transaction list with pagination."""
    transactions: List[TransactionResponseV2]
    meta: PaginationMeta


class PositionListResponseV2(BaseModel):
    """Position list response."""
    positions: List[PositionResponseV2]
    total: int