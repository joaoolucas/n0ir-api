from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict, model_validator
from uuid import UUID
import enum


# Enums matching database models
class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"


class TransactionType(str, enum.Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAW = "WITHDRAW"
    POSITION_CREATED = "POSITION_CREATED"
    POSITION_CLOSED = "POSITION_CLOSED"
    AERO_SWAP = "AERO_SWAP"


class TransactionStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PositionStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    LIQUIDATED = "LIQUIDATED"


class TimePeriod(str, enum.Enum):
    DAY_1 = "24h"
    DAY_7 = "7d"
    DAY_30 = "30d"
    ALL_TIME = "all"


# Request Models
class CreateUserRequest(BaseModel):
    user_id: str = Field(..., description="User's wallet address (EOA)")
    start_agent: bool = Field(True, description="Whether to start agent and create CDP wallet")


class UpdateUserRequest(BaseModel):
    status: Optional[UserStatus] = Field(None, description="User status")


class DepositRequest(BaseModel):
    amount_usdc: Decimal = Field(..., gt=0, description="Amount to deposit in USDC")
    tx_hash: Optional[str] = Field(None, description="Transaction hash")


class WithdrawRequest(BaseModel):
    amount_usdc: Decimal = Field(..., gt=0, description="Amount to withdraw in USDC")
    destination_address: Optional[str] = Field(None, description="Destination wallet address (defaults to user's address)")
    tx_hash: Optional[str] = Field(None, description="Transaction hash if already executed")
    force_close_positions: bool = Field(True, description="Automatically close positions if needed for withdrawal")
    max_slippage_percent: Decimal = Field(Decimal("0.5"), description="Maximum acceptable slippage when closing positions (%)")
    withdraw_all: bool = Field(False, description="Withdraw entire available balance after closing positions")


class WithdrawResponse(BaseModel):
    requested_amount: Decimal = Field(..., description="Amount requested to withdraw")
    withdrawn_amount: Decimal = Field(..., description="Actual amount withdrawn (may be less than requested)")
    remaining_balance: Decimal = Field(..., description="Remaining balance after withdrawal")
    positions_closed: int = Field(0, description="Number of positions closed for withdrawal")
    status: str = Field(..., description="Status: 'complete', 'partial', 'none', or 'error'")
    tx_hash: Optional[str] = Field(None, description="Transaction hash if executed")
    transaction_id: Optional[int] = Field(None, description="Transaction ID in database")
    message: Optional[str] = Field(None, description="Additional message or error details")

# Keep for backwards compatibility (deprecated)
class WithdrawPreviewResponse(BaseModel):
    requested_amount: Decimal = Field(..., description="Amount requested to withdraw")
    wallet_balance: Decimal = Field(..., description="Current wallet balance")
    positions_to_close: int = Field(..., description="Number of positions that need to be closed")
    positions_value: Decimal = Field(..., description="Total value of positions to be closed")
    estimated_gas_fees: Decimal = Field(..., description="Estimated gas fees for closing positions")
    estimated_slippage: Decimal = Field(..., description="Estimated slippage amount")
    estimated_available: Decimal = Field(..., description="Estimated total available after closing positions")
    can_withdraw: bool = Field(..., description="Whether withdrawal is possible")
    requires_position_closing: bool = Field(..., description="Whether positions need to be closed")
    warning_message: Optional[str] = Field(None, description="Warning message if any")


class CreatePositionRequest(BaseModel):
    nft_token_id: int = Field(..., description="Aerodrome NFT position ID")
    pool_address: str = Field(..., description="Pool contract address")
    pool_name: Optional[str] = Field(None, description="Pool name (e.g., 'WETH-USDC')")
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
    
    user_id: str  # The user's EOA wallet address
    cdp_wallet_address: Optional[str] = Field(None, description="CDP smart wallet managed by agent")
    cdp_wallet_name: Optional[str] = Field(None, description="CDP wallet name")
    status: Optional[UserStatus] = Field(UserStatus.ACTIVE, description="User status (default: active)")
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    user_id: str  # The user's EOA wallet address
    cdp_wallet_address: Optional[str] = Field(None, description="CDP smart wallet managed by agent")
    status: Optional[UserStatus] = Field(UserStatus.ACTIVE, description="User status")
    created_at: datetime
    
    # Financial metrics
    total_portfolio_value: Decimal = Field(..., description="Total value: wallet + all positions")
    
    # Position metrics
    active_positions_count: int = Field(0, description="Number of active positions")
    
    # Performance metrics
    total_pnl_usdc: Decimal = Field(Decimal(0), description="Total PnL in USDC")
    total_pnl_percentage: Decimal = Field(Decimal(0), description="Total PnL as percentage")
    
    # Agent status
    agent_active: bool = Field(False, description="Whether agent is active (has CDP wallet)")


class BalanceResponse(BaseModel):
    user_id: str
    wallet_balance_usdc: Decimal = Field(..., description="Current spendable balance in wallet")
    invested_amount_usdc: Decimal = Field(..., description="Total amount invested in active positions")
    current_positions_value_usdc: Decimal = Field(..., description="Real-time total value of all positions")
    total_portfolio_value_usdc: Decimal = Field(..., description="Wallet balance + positions value")


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    
    transaction_id: UUID = Field(validation_alias='id')
    user_id: str
    transaction_type: TransactionType = Field(validation_alias='tx_type')
    amount_usdc: Decimal
    pool_name: Optional[str] = Field(None, description="Pool name for position transactions")
    tx_hash: Optional[str]
    status: TransactionStatus
    event_data: Optional[Dict[str, Any]] = Field(default=None, description="Event data from blockchain")
    created_at: Optional[datetime] = Field(validation_alias='block_timestamp', description="Block timestamp of transaction")
    
    @model_validator(mode='before')
    @classmethod
    def normalize_transaction_type(cls, values):
        """Normalize transaction type from database to match enum and extract pool_name."""
        if isinstance(values, dict):
            # Extract pool_name from event_data if not directly available
            if 'pool_name' not in values or values.get('pool_name') is None:
                event_data = values.get('event_data', {})
                if event_data and isinstance(event_data, dict):
                    pool_name = event_data.get('pool_name')
                    if pool_name:
                        values['pool_name'] = pool_name

        if isinstance(values, dict) and 'tx_type' in values:
            tx_type = values['tx_type']
            type_mapping = {
                'withdraw': 'WITHDRAW',
                'WITHDRAW': 'WITHDRAW',
                'WITHDRAWAL': 'WITHDRAW',  # Map old WITHDRAWAL to new WITHDRAW
                'deposit': 'DEPOSIT',
                'DEPOSIT': 'DEPOSIT',
                'position_created': 'POSITION_CREATED',
                'POSITION_CREATED': 'POSITION_CREATED',
                'position_closed': 'POSITION_CLOSED',
                'POSITION_CLOSED': 'POSITION_CLOSED',
                'POSITION_OPENED': 'POSITION_CREATED',  # Map variations
                'position_opened': 'POSITION_CREATED',
                'STAKING': 'POSITION_CREATED',
                'staking': 'POSITION_CREATED',
                # Map swap types
                'aero_swap': 'AERO_SWAP',
                'AERO_SWAP': 'AERO_SWAP',
                'fee_collection': 'POSITION_CLOSED',
                'FEE_COLLECTION': 'POSITION_CLOSED',
                'PROTOCOL_FEE': 'POSITION_CLOSED',
                'protocol_fee': 'POSITION_CLOSED'
            }
            values['tx_type'] = type_mapping.get(tx_type, tx_type)
        return values


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    nft_token_id: int  # Primary key - Aerodrome NFT position ID
    user_id: str
    pool_address: str
    pool_name: Optional[str] = Field(None, description="Pool name (e.g. ZORA/USDC)")
    token0_address: str
    token1_address: str
    liquidity: str
    staked: bool
    gauge_address: Optional[str]
    entry_amount_usdc: Decimal
    current_value_usdc: Optional[Decimal]
    realized_pnl_usdc: Decimal
    unrealized_pnl_usdc: Decimal
    fees_earned_usdc: Decimal
    rewards_earned_usdc: Decimal
    total_pnl_usdc: Optional[Decimal] = Field(None, description="Total PNL")
    status: PositionStatus
    entry_date: Optional[datetime] = None
    exit_date: Optional[datetime] = None


class PnLResponse(BaseModel):
    """DEPRECATED: Use PerformanceResponse instead which includes all PnL data."""
    realized_pnl_usdc: Decimal
    unrealized_pnl_usdc: Decimal
    total_pnl_usdc: Decimal
    total_pnl_percentage: Decimal
    fees_earned_usdc: Decimal
    rewards_earned_usdc: Decimal


class PerformanceResponse(BaseModel):
    # Core metrics
    apr: float
    balance: Decimal
    active_positions: int

    # PnL breakdown
    realized_pnl_usdc: Decimal
    unrealized_pnl_usdc: Decimal
    total_pnl_usdc: Decimal  # realized + unrealized + fees + rewards
    total_pnl_percentage: Decimal

    # Earnings
    fees_earned_usdc: Decimal
    rewards_earned_usdc: Decimal

    # Legacy fields for backwards compatibility
    pnl_usdc: Decimal  # Same as total_pnl_usdc
    pnl_pct: Decimal  # Same as total_pnl_percentage


# List Response Models
class TransactionListResponse(BaseModel):
    transactions: List[TransactionResponse]
    total: int
    offset: int
    limit: int


class PositionListResponse(BaseModel):
    positions: List[PositionResponse]
    total: int
