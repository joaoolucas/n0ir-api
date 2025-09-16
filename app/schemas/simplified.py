"""Simplified, optimized response schemas for the n0ir API."""

from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
import enum


class TransactionType(str, enum.Enum):
    """Simplified to just 4 core transaction types."""
    DEPOSIT = "DEPOSIT"
    WITHDRAW = "WITHDRAW"
    POSITION_CREATED = "POSITION_CREATED"
    POSITION_CLOSED = "POSITION_CLOSED"


class PositionStatus(str, enum.Enum):
    """Position status enum."""
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class SimplifiedUserResponse(BaseModel):
    """Optimized user response with essential fields only."""
    model_config = ConfigDict(from_attributes=True)
    
    user_id: str = Field(..., description="User's wallet address")
    cdp_wallet_address: Optional[str] = Field(None, description="CDP wallet if created")
    
    # Balance and positions
    balance_usdc: Decimal = Field(..., description="Current USDC balance")
    active_positions: int = Field(..., description="Number of active positions")
    total_positions: int = Field(..., description="Total positions ever created")
    
    # Portfolio value
    portfolio_value_usdc: Decimal = Field(..., description="Total portfolio value (balance + positions)")
    
    # Performance
    total_pnl_usdc: Decimal = Field(..., description="Total P&L across all positions")
    total_pnl_percentage: Decimal = Field(..., description="Total P&L as percentage")
    
    created_at: datetime


class SimplifiedPositionResponse(BaseModel):
    """Optimized position response with clear, non-redundant fields."""
    model_config = ConfigDict(from_attributes=True)
    
    # Identity
    token_id: int = Field(..., description="NFT token ID (primary key)")
    user_id: str = Field(..., description="Owner's wallet address")
    
    # Pool information
    pool_address: str = Field(..., description="Pool contract address")
    pool_name: str = Field(..., description="Human-readable pool name")
    
    # Position details
    entry_amount_usdc: Decimal = Field(..., description="Amount invested")
    current_value_usdc: Decimal = Field(..., description="Current position value")
    
    # Performance metrics - single source of truth
    total_return_usdc: Decimal = Field(..., description="Total return including fees and rewards")
    return_percentage: Decimal = Field(..., description="Return as percentage of entry amount")
    
    # Breakdown (optional)
    fees_earned_usdc: Optional[Decimal] = Field(0, description="Trading fees earned")
    rewards_earned_usdc: Optional[Decimal] = Field(0, description="Staking rewards earned")
    
    # Status and dates
    status: PositionStatus = Field(..., description="Position status")
    entry_date: datetime = Field(..., description="When position was created")
    exit_date: Optional[datetime] = Field(None, description="When position was closed")


class SimplifiedTransactionResponse(BaseModel):
    """Optimized transaction response with essential fields only."""
    model_config = ConfigDict(from_attributes=True)
    
    # Identity
    id: UUID = Field(..., description="Transaction ID")
    user_id: str = Field(..., description="User's wallet address")
    
    # Transaction details
    type: TransactionType = Field(..., description="Transaction type")
    amount_usdc: Decimal = Field(..., description="Transaction amount in USDC")
    
    # Blockchain info (optional)
    tx_hash: Optional[str] = Field(None, description="Blockchain transaction hash")
    
    # Related position (for position transactions)
    position_id: Optional[int] = Field(None, description="Related position token ID")
    
    # Timing
    created_at: datetime = Field(..., description="When transaction was created")
    confirmed_at: Optional[datetime] = Field(None, description="When transaction was confirmed")


class SimplifiedBalanceResponse(BaseModel):
    """Optimized balance response."""
    model_config = ConfigDict(from_attributes=True)
    
    user_id: str
    
    # Current state
    wallet_balance_usdc: Decimal = Field(..., description="Available balance in wallet")
    positions_value_usdc: Decimal = Field(..., description="Total value in positions")
    total_value_usdc: Decimal = Field(..., description="Total portfolio value")
    
    # Simplified - removed pending amounts, invested amounts, etc.


class SimplifiedPnLResponse(BaseModel):
    """Optimized P&L response."""
    model_config = ConfigDict(from_attributes=True)
    
    user_id: str
    
    # Current P&L
    realized_pnl_usdc: Decimal = Field(..., description="Realized P&L from closed positions")
    unrealized_pnl_usdc: Decimal = Field(..., description="Unrealized P&L from active positions")
    total_pnl_usdc: Decimal = Field(..., description="Total P&L")
    
    # Percentage returns
    total_return_percentage: Decimal = Field(..., description="Total return as percentage")
    
    # Position counts
    active_positions: int = Field(..., description="Number of active positions")
    closed_positions: int = Field(..., description="Number of closed positions")


class SimplifiedTransactionListResponse(BaseModel):
    """Paginated transaction list response."""
    
    transactions: List[SimplifiedTransactionResponse]
    total: int = Field(..., description="Total number of transactions")
    page: int = Field(..., description="Current page")
    page_size: int = Field(..., description="Items per page")
    has_next: bool = Field(..., description="Whether there are more pages")


class SimplifiedPositionListResponse(BaseModel):
    """Position list response."""
    
    positions: List[SimplifiedPositionResponse]
    total: int = Field(..., description="Total number of positions")
    
    # Summary metrics
    total_value_usdc: Decimal = Field(..., description="Total value of all positions")
    total_return_usdc: Decimal = Field(..., description="Total return across all positions")
    average_return_percentage: Decimal = Field(..., description="Average return percentage")