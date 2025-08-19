# n0ir Database Schema Documentation

The database serves as the persistent storage layer for all trading operations, user data, and system metrics. Below is a comprehensive overview of each table and its relationships.

---

## 1. USERS Table - User Account Management
**Purpose:** Stores user account information and wallet mappings

```
Table Structure:
├── user_id: Primary key, user's EOA wallet address (e.g., "0x742...")
├── wallet_address: CDP smart wallet address for trading operations
├── cdp_wallet_name: Human-readable identifier for CDP wallet
├── cdp_owner_wallet_address: User's external wallet (same as user_id)
├── status: Account status (active/suspended/closed)
└── created_at: Account creation timestamp
```

**Implementation Details:**
- Primary key uses wallet address for Web3-native authentication
- CDP wallet is programmatically generated for each user
- One-to-one relationship between user EOA and CDP trading wallet
- Status field enables account lifecycle management

---

## 2. TRANSACTIONS Table - Financial Transaction Ledger
**Purpose:** Immutable record of all financial movements within the system

```
Table Structure:
├── transaction_id: UUID primary key
├── user_id: Foreign key reference to USERS table
├── transaction_type: Enum (deposit/withdraw/position_entry/position_exit/fee_collection)
├── amount_usdc: Transaction amount in USDC (DECIMAL 20,6)
├── tx_hash: Blockchain transaction hash for verification
├── status: Transaction state (pending/confirmed/failed/cancelled)
├── gas_used: Gas consumption metrics
└── created_at/confirmed_at: Temporal tracking
```

**Technical Implementation:**
- Supports idempotency through unique tx_hash constraint
- Maintains audit trail for all fund movements
- Indexed on user_id and transaction_type for query optimization

---

## 3. POSITIONS Table - Liquidity Position Management
**Purpose:** Tracks all DeFi liquidity positions and their performance metrics

```
Table Structure:
├── position_id: UUID primary key
├── user_id: Foreign key reference to USERS table
├── nft_token_id: Unique Aerodrome NFT position identifier
├── pool_address: Smart contract address of liquidity pool
├── tick_lower/tick_upper: Concentrated liquidity range parameters
├── liquidity: Position size (stored as string for precision)
├── entry_amount_usdc: Initial capital deployment
├── realized_pnl_usdc: Actualized profits/losses
├── unrealized_pnl_usdc: Paper profits/losses
├── fees_earned_usdc: Accumulated trading fees
└── status: Position state (active/closed/liquidated)
```

**Technical Implementation:**
- Tracks Uniswap V3-style concentrated liquidity positions
- Maintains real-time P&L calculations
- NFT token ID enables on-chain position verification

---

## 4. PROTOCOL_FEES Table - Revenue Management
**Purpose:** Tracks protocol revenue from profitable positions

```
Table Structure:
├── fee_id: UUID primary key
├── user_id: Foreign key reference to USERS table
├── position_id: Foreign key reference to POSITIONS table (unique constraint)
├── position_profit_usdc: Base profit amount for fee calculation
├── fee_amount_usdc: Calculated protocol fee (default 5%)
├── fee_percentage: Configurable fee rate (DECIMAL 5,4)
├── collected: Boolean flag for collection status
└── collection_tx_hash: On-chain collection verification
```

**Technical Implementation:**
- Enforces one-to-one relationship with positions via unique constraint
- Supports variable fee structures through percentage field
- Enables deferred fee collection for gas optimization

---

## 5. DAILY_METRICS Table - Analytics Aggregation
**Purpose:** Time-series data warehouse for platform analytics

```
Table Structure:
├── metric_date: Date component of composite primary key
├── metric_type: Type identifier (platform/user:{id}/pool:{address})
├── total_volume_usdc: Daily trading volume aggregation
├── positions_opened/closed: Position lifecycle metrics
├── active_users: Daily active user count
├── total_tvl_usdc: Total value locked snapshot
├── average_apr: Weighted average annual percentage rate
├── sharpe_ratio: Risk-adjusted return metric
└── max_drawdown: Maximum observed loss percentage
```

**Technical Implementation:**
- Composite primary key (metric_date, metric_type) enables multi-dimensional analysis
- Supports hierarchical metrics aggregation
- Pre-computed metrics optimize dashboard query performance

---

## 6. EXECUTOR_STATS Table - Execution Engine Metrics
**Purpose:** Performance tracking for automated trading executors

```
Table Structure:
├── stat_id: UUID primary key
├── executor_id: Identifier for executor instance (maps to user_id in individual mode)
├── total_positions_created: Cumulative position count
├── successful_positions: Profitable position count
├── total_volume_traded: Cumulative volume in USDC
├── win_rate: Success ratio calculation
├── sharpe_ratio: Risk-adjusted performance metric
└── total_gas_spent: Cumulative transaction costs
```

**Technical Implementation:**
- Supports both shared and individual executor modes
- Maintains running totals for performance analysis
- Enables executor optimization through metric tracking

---

## 7. STRATEGY_DECISIONS Table - Decision Audit Log
**Purpose:** Captures algorithmic decision-making process for analysis and optimization

```
Table Structure:
├── decision_id: UUID primary key
├── executor_id: Reference to executor making decision
├── decision_type: Action taken (enter/exit/rebalance/skip)
├── pool_address: Target pool for decision
├── apr/tvl/volume_24h: Market conditions at decision time
├── confidence_score: Algorithm confidence level (0-100)
├── decision_reason: JSON structure with detailed reasoning
├── expected_return: Projected outcome
├── actual_return: Realized outcome for backtesting
└── execution_tx_hash: On-chain execution verification
```

**Technical Implementation:**
- Enables strategy backtesting and optimization
- JSON reasoning field provides algorithm transparency
- Supports A/B testing of strategy variations

---

## 8. POOL_METRICS Table - Liquidity Pool Analytics
**Purpose:** Time-series data for liquidity pool performance and characteristics

```
Table Structure:
├── pool_address: Pool identifier (part of composite primary key)
├── timestamp: Temporal component of composite primary key
├── token0_address/token1_address: Pair token contracts
├── fee_tier: Basis points fee structure
├── tvl_usd: Total value locked in USD
├── volume_24h_usd: Rolling 24-hour volume
├── fee_apr/reward_apr: Yield components
├── tick_current: Current price tick for concentrated liquidity
└── liquidity: Total liquidity units
```

**Technical Implementation:**
- Time-series structure enables historical analysis
- Composite key (pool_address, timestamp) for efficient querying
- Supports pool selection algorithms

---

## Database Relationships - Entity Relationship Model

```
USERS (You)
  ├── Has many TRANSACTIONS (your deposits/withdrawals)
  ├── Has many POSITIONS (your trades)
  └── Has many PROTOCOL_FEES (taxes on profits)

Each POSITION
  └── Has one PROTOCOL_FEE (if profitable)
```

---

## Transaction Flow Example:

1. **User Authentication** (Wallet: 0xABC...)
   - INSERT into USERS with wallet address as primary key

2. **Capital Deposit** ($1000 USDC)
   - INSERT into TRANSACTIONS (type: deposit)

3. **Position Entry** (ETH/USDC Liquidity Provision)
   - INSERT into POSITIONS with entry parameters
   - INSERT into STRATEGY_DECISIONS with algorithm reasoning

4. **Profit Realization** ($100 profit)
   - UPDATE POSITIONS with realized P&L
   - INSERT into PROTOCOL_FEES (5% of profit)

5. **Capital Withdrawal** ($1095 USDC)
   - INSERT into TRANSACTIONS (type: withdraw)

6. **Daily Aggregation**
   - INSERT/UPDATE DAILY_METRICS with aggregated statistics

---

## Key Technical Concepts:

1. **Normalization** - Data is structured to minimize redundancy and dependency
2. **Primary Keys** - Unique identifiers ensure data integrity (UUIDs for most tables)
3. **Foreign Keys** - Referential integrity maintained through table relationships
4. **Indexing Strategy** - Composite and single-column indexes optimize query performance
5. **Web3 Authentication** - Wallet addresses serve as user identifiers, eliminating traditional auth

The schema implements a comprehensive audit trail for all trading activities, enabling full transaction replay, performance analysis, and regulatory compliance.