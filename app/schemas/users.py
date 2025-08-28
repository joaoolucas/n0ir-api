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
    WITHDRAWAL = "WITHDRAWAL"
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


# Request Models
class CreateUserRequest(BaseModel):
    user_id: str = Field(..., description="User's wallet address (EOA)")
    start_agent: bool = Field(True, description="Whether to start agent and create CDP wallet")
    signature: Optional[str] = Field(None, description="Signature to prove wallet ownership (optional)")


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


class BalanceResponse(BaseModel):
    user_id: str
    wallet_balance_usdc: Decimal = Field(..., description="Current spendable balance in wallet")
    available_balance_usdc: Decimal = Field(..., description="Available for withdrawal/trading")
    invested_amount_usdc: Decimal = Field(..., description="Total amount invested in active positions")
    current_positions_value_usdc: Decimal = Field(..., description="Real-time total value of all positions")
    total_portfolio_value_usdc: Decimal = Field(..., description="Wallet balance + positions value")
    pending_deposits_usdc: Decimal
    pending_withdrawals_usdc: Decimal


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    transaction_id: UUID
    user_id: str
    transaction_type: TransactionType
    amount_usdc: Decimal
    pool_name: Optional[str] = Field(None, description="Pool name for position entry/exit transactions")
    tx_hash: Optional[str]
    block_number: Optional[int]
    block_timestamp: Optional[datetime] = Field(None, description="On-chain block timestamp")
    gas_used: Optional[int]
    gas_price: Optional[Decimal]
    status: TransactionStatus
    tx_metadata: Optional[Dict[str, Any]] = Field(None, description="Additional transaction metadata as JSON")
    event_data: Optional[Dict[str, Any]] = Field(None, description="Event data from blockchain")
    created_at: datetime
    confirmed_at: Optional[datetime]
    aero_swap_usdc: Optional[Decimal] = Field(None, description="AERO rewards swapped to USDC (for POSITION_CLOSED only)")
    total_amount_usdc: Optional[Decimal] = Field(None, description="Total amount including AERO swaps (for POSITION_CLOSED only)")
    
    @model_validator(mode='before')
    @classmethod
    def extract_aero_swap(cls, values):
        """Extract aero_swap_usdc from event_data if present and normalize transaction type."""
        if isinstance(values, dict):
            # Extract aero_swap_usdc from event_data if not already set
            event_data = values.get('event_data', {})
            if event_data and not values.get('aero_swap_usdc'):
                values['aero_swap_usdc'] = event_data.get('aero_swap_usdc', 0)
            
            # Normalize transaction type from database to match enum
            tx_type = values.get('tx_type') or values.get('transaction_type')
            if tx_type:
                type_mapping = {
                    'withdraw': 'WITHDRAWAL',
                    'WITHDRAW': 'WITHDRAWAL',
                    'WITHDRAWAL': 'WITHDRAWAL',
                    'deposit': 'DEPOSIT',
                    'DEPOSIT': 'DEPOSIT',
                    'position_created': 'POSITION_CREATED',
                    'POSITION_CREATED': 'POSITION_CREATED',
                    'position_closed': 'POSITION_CLOSED',
                    'POSITION_CLOSED': 'POSITION_CLOSED',
                    'aero_swap': 'AERO_SWAP',
                    'AERO_SWAP': 'AERO_SWAP'
                }
                normalized = type_mapping.get(tx_type, tx_type)
                values['transaction_type'] = normalized
                if 'tx_type' in values:
                    values['tx_type'] = normalized
        return values
    
    @model_validator(mode='after')
    def calculate_total_amount(self):
        """Calculate total_amount_usdc for POSITION_CLOSED transactions."""
        # Only calculate for POSITION_CLOSED transactions
        if self.transaction_type == TransactionType.POSITION_CLOSED or self.transaction_type == 'POSITION_CLOSED':
            # Use aero_swap_usdc if available
            aero_amount = Decimal(str(self.aero_swap_usdc or 0))
            
            # Calculate total
            self.total_amount_usdc = self.amount_usdc + aero_amount
        else:
            # For other transaction types, total is same as amount
            self.total_amount_usdc = self.amount_usdc
            
        return self


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    nft_token_id: int  # Primary key - Aerodrome NFT position ID
    user_id: str
    pool_address: str
    pool_name: Optional[str] = Field(None, description="Pool name (e.g. ZORA/USDC)")
    token0_address: str
    token1_address: str
    tick_lower: Optional[int] = None
    tick_upper: Optional[int] = None
    tick_spacing: Optional[int] = None
    liquidity: str
    staked: bool
    gauge_address: Optional[str]
    entry_amount_usdc: Decimal
    current_value_usdc: Optional[Decimal]
    current_total_value: Optional[Decimal] = Field(None, description="Total value including position value + staked emissions")
    realized_pnl_usdc: Decimal
    unrealized_pnl_usdc: Decimal
    fees_earned_usdc: Decimal
    rewards_earned_usdc: Decimal
    total_pnl_usdc: Optional[Decimal] = Field(None, description="Total PNL (unrealized + fees + rewards)")
    pnl_percentage: Optional[Decimal] = Field(None, description="PNL as percentage of entry amount")
    pool_base_apr: Optional[Decimal] = Field(None, description="Pool's base APR percentage")
    effective_apr: Optional[Decimal] = Field(None, description="Effective APR based on position range")
    protocol_fee_amount: Decimal  # 5% of profits
    protocol_fee_collected: bool
    protocol_fee_tx_hash: Optional[str]
    status: PositionStatus
    entry_tx_hash: Optional[str]
    exit_tx_hash: Optional[str]
    entry_date: datetime
    exit_date: Optional[datetime]
    last_updated: datetime


class ProtocolFeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    nft_token_id: int  # Aerodrome NFT position ID
    fee_amount_usdc: Decimal
    collected: bool
    collection_tx_hash: Optional[str]


class PnLResponse(BaseModel):
    realized_pnl_usdc: Decimal
    unrealized_pnl_usdc: Decimal
    unrealized_pnl_percentage: Decimal
    unrealized_pnl_pct: Decimal  # Alias for unrealized_pnl_percentage
    realized_pnl_percentage: Decimal
    fees_earned_usdc: Decimal
    rewards_earned_usdc: Decimal
    total_pnl_usdc: Decimal
    protocol_fees_pending_usdc: Decimal
    net_pnl_usdc: Decimal


class PerformanceResponse(BaseModel):
    apr: float
    balance: Decimal
    pnl_usdc: Decimal
    pnl_pct: Decimal
    active_positions: int


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
    total_pending_usdc: Decimal
    total_collected_usdc: Decimal