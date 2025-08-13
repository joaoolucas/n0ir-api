from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
import enum


# Enums matching database models
class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class TransactionType(str, enum.Enum):
    DEPOSIT = "deposit"
    WITHDRAW = "withdraw"
    POSITION_ENTRY = "position_entry"
    POSITION_EXIT = "position_exit"
    FEE_COLLECTION = "fee_collection"


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PositionStatus(str, enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    LIQUIDATED = "liquidated"


# Request Models
class CreateUserRequest(BaseModel):
    user_id: str = Field(..., description="Unique user identifier")
    wallet_address: str = Field(..., description="CDP wallet address")
    cdp_wallet_name: str = Field(..., description="CDP wallet name")
    cdp_owner_wallet_address: str = Field(..., description="Owner EOA address")
    cdp_owner_wallet_name: str = Field(..., description="Owner EOA name")


class UpdateUserRequest(BaseModel):
    status: Optional[UserStatus] = Field(None, description="User status")


class DepositRequest(BaseModel):
    amount_usdc: Decimal = Field(..., gt=0, description="Amount to deposit in USDC")
    tx_hash: Optional[str] = Field(None, description="Transaction hash")


class WithdrawRequest(BaseModel):
    amount_usdc: Decimal = Field(..., gt=0, description="Amount to withdraw in USDC")
    destination_address: Optional[str] = Field(None, description="Destination wallet address")


class CreatePositionRequest(BaseModel):
    nft_token_id: int = Field(..., description="Aerodrome NFT position ID")
    pool_address: str = Field(..., description="Pool contract address")
    token0_address: str = Field(..., description="Token0 address")
    token1_address: str = Field(..., description="Token1 address")
    tick_lower: int = Field(..., description="Lower tick")
    tick_upper: int = Field(..., description="Upper tick")
    tick_spacing: int = Field(..., description="Tick spacing")
    liquidity: str = Field(..., description="Position liquidity")
    entry_amount_usdc: Decimal = Field(..., gt=0, description="Entry amount in USDC")
    entry_tx_hash: Optional[str] = Field(None, description="Entry transaction hash")
    staked: bool = Field(False, description="Whether position is staked")
    gauge_address: Optional[str] = Field(None, description="Gauge address if staked")


class UpdatePositionRequest(BaseModel):
    current_value_usdc: Optional[Decimal] = Field(None, description="Current value in USDC")
    unrealized_pnl_usdc: Optional[Decimal] = Field(None, description="Unrealized PnL in USDC")
    fees_earned_usdc: Optional[Decimal] = Field(None, description="Fees earned in USDC")
    rewards_earned_usdc: Optional[Decimal] = Field(None, description="Rewards earned in USDC")


class ClosePositionRequest(BaseModel):
    exit_tx_hash: str = Field(..., description="Exit transaction hash")
    realized_pnl_usdc: Decimal = Field(..., description="Realized PnL in USDC")
    final_value_usdc: Decimal = Field(..., description="Final position value in USDC")


# Response Models
class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    user_id: str
    wallet_address: str
    cdp_wallet_name: str
    cdp_owner_wallet_address: str
    cdp_owner_wallet_name: str
    status: UserStatus
    created_at: datetime
    updated_at: datetime


class BalanceResponse(BaseModel):
    user_id: str
    balance_usdc: Decimal
    available_balance_usdc: Decimal
    locked_in_positions_usdc: Decimal
    pending_deposits_usdc: Decimal
    pending_withdrawals_usdc: Decimal


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    transaction_id: UUID
    user_id: str
    transaction_type: TransactionType
    amount_usdc: Decimal
    tx_hash: Optional[str]
    block_number: Optional[int]
    gas_used: Optional[int]
    gas_price: Optional[Decimal]
    status: TransactionStatus
    metadata: Optional[str]
    created_at: datetime
    confirmed_at: Optional[datetime]


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    position_id: UUID
    user_id: str
    nft_token_id: int
    pool_address: str
    token0_address: str
    token1_address: str
    tick_lower: int
    tick_upper: int
    tick_spacing: int
    liquidity: str
    staked: bool
    gauge_address: Optional[str]
    entry_amount_usdc: Decimal
    current_value_usdc: Optional[Decimal]
    realized_pnl_usdc: Decimal
    unrealized_pnl_usdc: Decimal
    fees_earned_usdc: Decimal
    rewards_earned_usdc: Decimal
    status: PositionStatus
    entry_tx_hash: Optional[str]
    exit_tx_hash: Optional[str]
    entry_date: datetime
    exit_date: Optional[datetime]
    last_updated: datetime


class ProtocolFeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    fee_id: UUID
    user_id: str
    position_id: UUID
    position_profit_usdc: Decimal
    fee_amount_usdc: Decimal
    fee_percentage: Decimal
    collected: bool
    collection_tx_hash: Optional[str]
    created_at: datetime
    collected_at: Optional[datetime]


class PnLResponse(BaseModel):
    realized_pnl_usdc: Decimal
    unrealized_pnl_usdc: Decimal
    fees_earned_usdc: Decimal
    rewards_earned_usdc: Decimal
    total_pnl_usdc: Decimal
    protocol_fees_pending_usdc: Decimal
    net_pnl_usdc: Decimal


class PerformanceResponse(BaseModel):
    total_invested: float
    total_current_value: float
    total_realized_pnl: float
    total_unrealized_pnl: float
    total_fees_earned: float
    total_rewards_earned: float
    total_pnl: float
    total_protocol_fees_pending: float
    apr: float
    active_positions: int
    total_positions: int
    roi_percentage: float
    
    @classmethod
    def from_service_data(cls, data: Dict[str, Any]) -> "PerformanceResponse":
        """Create response from service layer data."""
        roi = 0.0
        if data["total_invested"] > 0:
            roi = (data["total_pnl"] / data["total_invested"]) * 100
        
        return cls(
            **data,
            roi_percentage=roi
        )


# List Response Models
class TransactionListResponse(BaseModel):
    transactions: List[TransactionResponse]
    total: int
    offset: int
    limit: int


class PositionListResponse(BaseModel):
    positions: List[PositionResponse]
    total: int


class ProtocolFeeListResponse(BaseModel):
    fees: List[ProtocolFeeResponse]
    total_pending: Decimal
    total_collected: Decimal