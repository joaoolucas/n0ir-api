from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict, model_validator
from uuid import UUID
import enum


# Enums matching database models
class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
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
    CANCELLED = "CANCELLED"


class PositionStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class TimePeriod(str, enum.Enum):
    DAY_1 = "24h"
    DAY_7 = "7d"
    DAY_30 = "30d"
    ALL_TIME = "all"


# Moonwell Strategy Models
class MoonwellCollateral(BaseModel):
    """Moonwell collateral details"""
    market: str = Field(..., description="Market name (e.g., 'mUSDC')")
    amount_usdc: Decimal = Field(..., description="Amount in USDC")


class MoonwellBorrow(BaseModel):
    """Moonwell borrow details"""
    market: str = Field(..., description="Market name (e.g., 'mWETH')")
    amount_weth: Optional[Decimal] = Field(None, description="Amount in WETH")
    amount_usd: Decimal = Field(..., description="USD value")
    post_borrow_action: str = Field(..., description="Action after borrowing")


class MoonwellAllocation(BaseModel):
    """Moonwell allocation details"""
    protocol: str = Field(default="moonwell")
    collateral: MoonwellCollateral
    borrow: MoonwellBorrow


class AerodromeLP(BaseModel):
    """Aerodrome LP allocation details"""
    protocol: str = Field(default="aerodrome")
    pool: str = Field(..., description="Pool name (e.g., 'WETH-USDC')")
    pool_address: Optional[str] = Field(None, description="Pool contract address")
    amount_usdc: Decimal = Field(..., description="Amount in USDC")
    range_percentage: int = Field(..., description="Suggested range percentage based on pool metrics")
    effective_apr: Optional[Decimal] = Field(None, description="Effective APR with range adjustment")


class RecommendedPosition(BaseModel):
    """Recommended position allocation for dual strategy"""
    pool_name: str = Field(..., description="Pool name (e.g., 'WETH/USDC')")
    pool_address: str = Field(..., description="Pool contract address")
    allocation_percentage: int = Field(..., description="Percentage of capital to allocate (e.g., 70)")
    allocation_usdc: Decimal = Field(..., description="USDC amount for this position")


class PositionParams(BaseModel):
    """Parameters for a single position"""
    pool: str = Field(..., description="Pool address")
    pool_name: str = Field(..., description="Pool name (e.g., 'WETH/USDC')")
    usdc_amount: Decimal = Field(..., description="USDC amount to deploy")
    range_percentage: int = Field(..., description="Range percentage for the position (e.g., 10 = ±5%)")
    deadline: int = Field(..., description="Unix timestamp deadline for transaction")
    slippage_bps: int = Field(default=50, description="Slippage tolerance in basis points (e.g., 50 = 0.5%)")
    hedge_ratio: int = Field(..., description="Hedge ratio in basis points (e.g., 9200 = 92%)")
    collateral_ratio_bps: int = Field(..., description="Collateral ratio in basis points (e.g., 6500 = 65%)")


class ContractParameters(BaseModel):
    """Parameters for calling createPosition on the vault contract"""
    pool: Optional[str] = Field(None, description="Aerodrome pool address (only for single position)")
    range_percentage: Optional[int] = Field(None, description="Range percentage for the position (only for single position)")
    deadline: Optional[int] = Field(None, description="Unix timestamp deadline for transaction")
    usdc_amount: Optional[Decimal] = Field(None, description="USDC amount to deploy (only for single position)")
    slippage_bps: Optional[int] = Field(None, description="Slippage tolerance in basis points (only for single position)")
    hedge_ratio: Optional[int] = Field(None, description="Hedge ratio in basis points (only for single position)")
    collateral_ratio_bps: Optional[int] = Field(None, description="Collateral ratio in basis points (only for single position)")
    position_1: Optional['PositionParams'] = Field(None, description="First position params (for open_dual)")
    position_2: Optional['PositionParams'] = Field(None, description="Second position params (for open_dual)")
    positions_to_close: Optional[List[int]] = Field(None, description="NFT token IDs to close (for action='close')")


class VaultHedgeSimulation(BaseModel):
    """Vault hedge simulation results"""
    hedge_asset: str = Field(..., description="Asset being hedged (e.g., WETH)")
    collateral_amount: Decimal = Field(..., description="Collateral amount in USDC")
    borrow_amount_usd: Decimal = Field(..., description="Borrow amount in USD")
    borrow_amount_asset: Decimal = Field(..., description="Borrow amount in asset terms")
    total_lp_amount: Decimal = Field(..., description="Total LP amount in USDC")
    asset_exposure_usd: Decimal = Field(..., description="Asset exposure in USD")
    net_delta_usd: Decimal = Field(..., description="Net delta (debt - exposure)")
    expected_health_factor: Decimal = Field(..., description="Expected health factor")
    liquidation_price: Decimal = Field(..., description="Liquidation price for the asset")
    delta_neutral_score: Decimal = Field(..., description="Score from 0-1, where 1 is perfect delta neutral")




# Deprecated models (kept for backward compatibility)
class MoonwellAllocation(BaseModel):
    """Aave allocation details via vault (deprecated, renamed from Moonwell)"""
    protocol: str = Field(default="aave")
    collateral: MoonwellCollateral
    borrow: MoonwellBorrow


class StrategyAllocations(BaseModel):
    """Strategy allocations (deprecated)"""
    moonwell: Optional[MoonwellAllocation] = Field(None, description="Aave allocation via vault (deprecated)")
    vault: Optional[Dict] = Field(None, description="Vault allocation (deprecated)")
    aerodrome_lp: AerodromeLP


class DeprecatedCapitalInfo(BaseModel):
    """Capital information (deprecated - use app.schemas.capital.CapitalInfo)"""
    total_usd: Decimal = Field(..., description="Total capital in USD")
    base_asset: str = Field(default="USDC", description="Base asset")


class PositionAlert(BaseModel):
    """Alert for a position that needs attention"""
    position_id: int = Field(..., description="NFT token ID")
    pool_address: str = Field(..., description="Pool address")
    reason: str = Field(..., description="Reason for alert: 'neutral_ratio_breach' or 'out_of_range'")
    suggested_action: str = Field(default="close", description="Suggested action")
    current_in_range: bool = Field(..., description="Current in_range status")
    current_neutral_ratio: Optional[Decimal] = Field(None, description="Current neutral_ratio if hedged")
    threshold_min: Optional[Decimal] = Field(None, description="Minimum threshold for neutral_ratio (0.8)")
    threshold_max: Optional[Decimal] = Field(None, description="Maximum threshold for neutral_ratio (1.2)")


class MonitoringInfo(BaseModel):
    """Monitoring information"""
    alerts: List[PositionAlert] = Field(default_factory=list, description="List of position alerts")


class PerformanceData(BaseModel):
    """Performance metrics for no_action response"""
    apr: Optional[Decimal] = Field(None, description="Average APR across active positions")
    wallet_balance: Decimal = Field(..., description="Current wallet balance in USDC")
    positions_value: Decimal = Field(..., description="Total value of active positions in USDC")
    total_balance: Decimal = Field(..., description="Total portfolio value (wallet + positions)")
    active_positions: int = Field(..., description="Number of active positions")
    realized_pnl_usdc: Decimal = Field(..., description="Realized PnL in USDC")
    realized_pnl_pct: Optional[Decimal] = Field(None, description="Realized PnL percentage")
    pnl_usdc: Decimal = Field(..., description="Total PnL (realized + unrealized) in USDC")
    pnl_pct: Optional[Decimal] = Field(None, description="Total PnL percentage")


class VaultStrategyResponse(BaseModel):
    """Delta-neutral strategy response with vault contract parameters (uses Aave for hedging)"""
    user_id: str = Field(..., description="User ID")
    strategy_type: str = Field(default="delta_neutral", description="Strategy type")
    timestamp: str = Field(..., description="ISO timestamp")
    action: str = Field(..., description="Action: 'open', 'close', 'open_dual', 'no_action'")

    capital: Any = Field(..., description="Capital information - can be CapitalInfo from app.schemas.capital or DeprecatedCapitalInfo for backward compatibility")
    contract_params: Optional[ContractParameters] = Field(None, description="Parameters for calling vault contract (null when action='no_action')")
    monitoring: Optional[MonitoringInfo] = Field(None, description="Monitoring information")
    performance: Optional[PerformanceData] = Field(None, description="Performance metrics (when action='no_action')")


# Backward compatibility alias
MoonwellStrategyResponse = VaultStrategyResponse




# Request Models
class CreateUserRequest(BaseModel):
    pass  # Empty body, user_id is now a path parameter


class UpdateUserRequest(BaseModel):
    status: Optional[UserStatus] = Field(None, description="User status")


class DepositRequest(BaseModel):
    amount_usdc: Decimal = Field(..., gt=0, description="Amount to deposit in USDC")
    tx_hash: Optional[str] = Field(None, description="Transaction hash")


class WithdrawRequest(BaseModel):
    amount_usdc: Decimal = Field(..., gt=0, description="Amount to withdraw in USDC")
    withdraw_all: bool = Field(False, description="Withdraw entire available balance after closing positions")


class WithdrawResponse(BaseModel):
    requested_amount: Decimal = Field(..., description="Amount requested to withdraw")
    withdrawn_amount: Decimal = Field(..., description="Actual amount withdrawn (may be less than requested)")
    remaining_balance: Decimal = Field(..., description="Remaining balance after withdrawal")
    positions_closed: int = Field(0, description="Number of positions closed for withdrawal")
    status: str = Field(..., description="Status: 'complete', 'partial', 'none', or 'error'")
    tx_hash: Optional[str] = Field(None, description="Transaction hash if executed")
    transaction_id: Optional[UUID] = Field(None, description="Transaction ID in database")
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

    # Points and rewards
    points: int = Field(0, description="Total points earned (1 cent in rewards = 1 point)")

    # Strategy configuration
    active_strategies: Dict[str, Any] = Field(default_factory=dict, description="User's active strategy configurations")


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
    position_id: Optional[int] = Field(None, description="NFT token ID for position-related transactions")  # Comes from DB column
    pool_name: Optional[str] = Field(None, description="Pool name for position transactions")
    in_range: Optional[bool] = Field(None, description="Whether the position is in range (for position-related transactions)")
    tx_hash: Optional[str]
    status: TransactionStatus
    event_data: Optional[Dict[str, Any]] = Field(default=None, description="Event data from blockchain")
    created_at: Optional[datetime] = Field(None, description="Transaction timestamp")

    @model_validator(mode='before')
    @classmethod
    def normalize_transaction_type(cls, values):
        """Normalize transaction type from database to match enum and extract fields from event_data."""
        if isinstance(values, dict):
            # Use block_timestamp if available, otherwise fall back to created_at
            if 'block_timestamp' in values and values['block_timestamp']:
                values['created_at'] = values['block_timestamp']
            elif 'created_at' not in values or values['created_at'] is None:
                # If neither block_timestamp nor created_at is set, check confirmed_at
                if 'confirmed_at' in values and values['confirmed_at']:
                    values['created_at'] = values['confirmed_at']
            event_data = values.get('event_data', {})

            # Parse event_data if it's a string (JSON)
            if isinstance(event_data, str):
                import json
                try:
                    event_data = json.loads(event_data)
                except (json.JSONDecodeError, TypeError):
                    event_data = {}

            # Extract pool_name from event_data if not directly available
            if 'pool_name' not in values or values.get('pool_name') is None:
                if event_data and isinstance(event_data, dict):
                    pool_name = event_data.get('pool_name')
                    if pool_name:
                        values['pool_name'] = pool_name

            # Note: position_id now comes directly from the database column,
            # no need to extract from event_data

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
                'fee_collection': 'POSITION_CLOSED',
                'FEE_COLLECTION': 'POSITION_CLOSED',
                'PROTOCOL_FEE': 'POSITION_CLOSED',
                'protocol_fee': 'POSITION_CLOSED'
            }
            values['tx_type'] = type_mapping.get(tx_type, tx_type)
        return values


class HedgeInfoResponse(BaseModel):
    """Hedge information for a position."""
    is_hedged: bool = Field(False, description="Whether position is hedged")
    lp_amount: Optional[Decimal] = Field(None, description="Amount in LP (USDC)")
    lp_current_value_usd: Optional[Decimal] = Field(None, description="Current LP position value in USD")
    collateral: Optional[Decimal] = Field(None, description="Collateral amount (USDC)")
    debt_asset: Optional[str] = Field(None, description="Borrowed asset (WETH/cbBTC)")
    debt_amount: Optional[Decimal] = Field(None, description="Debt amount in asset")
    debt_value_usd: Optional[Decimal] = Field(None, description="Debt value in USD")
    tick_lower: Optional[int] = Field(None, description="Lower tick")
    tick_upper: Optional[int] = Field(None, description="Upper tick")
    collateral_supply_apy: Optional[Decimal] = Field(None, description="Current USDC supply APY on Aave")
    hedged_asset_borrow_apy: Optional[Decimal] = Field(None, description="Current borrow APY on hedged asset (Aave)")
    unclaimed_fees_usd: Optional[Decimal] = Field(None, description="Unclaimed fees in USD")
    unclaimed_rewards_aero: Optional[Decimal] = Field(None, description="Unclaimed AERO rewards")


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nft_token_id: int  # Primary key - Aerodrome NFT position ID
    user_id: str
    pool_address: str
    pool_name: Optional[str] = Field(None, description="Pool name (e.g. ZORA/USDC)")
    staked: bool
    gauge_address: Optional[str]
    entry_amount_usdc: Decimal
    current_value_usdc: Optional[Decimal]
    realized_pnl_usdc: Decimal
    unrealized_pnl_usdc: Decimal
    total_pnl_usdc: Optional[Decimal] = Field(None, description="Total PNL")
    status: PositionStatus
    entry_date: Optional[datetime] = None
    exit_date: Optional[datetime] = None
    hedge: Optional[HedgeInfoResponse] = Field(None, description="Hedge information")
    pool_base_apr: Optional[Decimal] = Field(None, description="Pool base APR")
    effective_apr: Optional[Decimal] = Field(None, description="Effective APR with range adjustment")
    net_apr: Optional[Decimal] = Field(None, description="Net APR accounting for LP yield, collateral APY, and borrow costs")
    neutral_ratio: Optional[Decimal] = Field(None, description="Ratio of debt to hedged asset in LP (debt_amount / token_amount)")
    in_range: Optional[bool] = Field(None, description="Whether the position is in range")
    tick_lower: Optional[int] = Field(None, description="Lower tick boundary")
    tick_upper: Optional[int] = Field(None, description="Upper tick boundary")
    current_tick: Optional[int] = Field(None, description="Current pool tick")
    token0: Optional[str] = Field(None, description="Token0 address")
    token1: Optional[str] = Field(None, description="Token1 address")
    token0_amount: Optional[float] = Field(None, description="Amount of token0 in the position")
    token1_amount: Optional[float] = Field(None, description="Amount of token1 in the position")
    unclaimed_fees_usd: Optional[Decimal] = Field(None, description="Unclaimed fees in USD")
    unclaimed_rewards_aero: Optional[Decimal] = Field(None, description="Unclaimed AERO rewards")


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
    wallet_balance: Decimal  # Current USDC balance in wallet
    positions_value: Decimal  # Total value invested in positions
    total_balance: Decimal  # wallet_balance + positions_value (formerly just "balance")
    active_positions: int

    # PnL metrics
    realized_pnl_usdc: Decimal
    realized_pnl_pct: Decimal
    pnl_usdc: Decimal  # Total PnL (unrealized + realized)
    pnl_pct: Decimal   # Total PnL percentage


# List Response Models
class TransactionListResponse(BaseModel):
    transactions: List[TransactionResponse]
    total: int
    offset: int
    limit: int


class PositionListResponse(BaseModel):
    positions: List[PositionResponse]
    total: int


# User Creation Request/Response Models
class CreateRequest(BaseModel):
    """Request to create user and CDP wallet"""
    pass  # No parameters needed


class CreateResponse(BaseModel):
    """Response for user creation"""
    user_id: str
    cdp_wallet_address: str
    status: str = Field(..., description="Status: 'created', 'already_exists', 'error'")
    message: str


# Activation/Deactivation Request/Response Models
class ActivateRequest(BaseModel):
    """Request to activate user's trading agent"""
    strategy_type: str = Field("delta_neutral", description="Strategy type to use")


class ActivateResponse(BaseModel):
    """Response for agent activation"""
    user_id: str
    status: str = Field(..., description="Status: 'activated', 'already_active', 'error'")
    cdp_wallet_address: Optional[str] = None
    message: str


class DeactivateRequest(BaseModel):
    """Request to deactivate user's trading agent"""
    pass  # No parameters needed - always withdraws all funds


class DeactivateResponse(BaseModel):
    """Response for agent deactivation"""
    user_id: str
    status: str = Field(..., description="Status: 'deactivated', 'already_inactive', 'error'")
    withdrawn_amount: Optional[Decimal] = None
    tx_hash: Optional[str] = None
    message: str
