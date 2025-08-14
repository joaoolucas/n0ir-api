# n0ir API Database Schema

## Overview
Complete database schema for the n0ir API including user management, position tracking, metrics, and monitoring tables.

## Core Tables

### 1. users
User accounts with CDP wallet integration.

| Column | Type | Description |
|--------|------|-------------|
| user_id | VARCHAR (PK) | Unique user identifier |
| wallet_address | VARCHAR | CDP wallet address (unique) |
| cdp_wallet_name | VARCHAR | CDP wallet name |
| cdp_owner_wallet_address | VARCHAR | Owner EOA address |
| cdp_owner_wallet_name | VARCHAR | Owner EOA name |
| status | ENUM | active/suspended/closed |
| created_at | TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | Last update time |

**Indexes:** user_id, wallet_address, cdp_owner_wallet_address, status, created_at

### 2. transactions
Financial transaction records.

| Column | Type | Description |
|--------|------|-------------|
| transaction_id | UUID (PK) | Unique transaction ID |
| user_id | VARCHAR (FK) | References users.user_id |
| transaction_type | ENUM | deposit/withdraw/position_entry/position_exit/fee_collection |
| amount_usdc | DECIMAL(20,6) | Transaction amount in USDC |
| tx_hash | VARCHAR | Blockchain transaction hash |
| block_number | INTEGER | Block number |
| gas_used | INTEGER | Gas used |
| gas_price | DECIMAL(20,9) | Gas price in Gwei |
| status | ENUM | pending/confirmed/failed/cancelled |
| tx_metadata | JSON | Additional metadata |
| created_at | TIMESTAMP | Creation time |
| confirmed_at | TIMESTAMP | Confirmation time |

**Indexes:** user_id, transaction_type, status, tx_hash, created_at, confirmed_at

### 3. positions
Aerodrome liquidity positions.

| Column | Type | Description |
|--------|------|-------------|
| position_id | UUID (PK) | Unique position ID |
| user_id | VARCHAR (FK) | References users.user_id |
| nft_token_id | INTEGER | Aerodrome NFT ID (unique) |
| pool_address | VARCHAR | Pool contract address |
| token0_address | VARCHAR | Token 0 address |
| token1_address | VARCHAR | Token 1 address |
| tick_lower | INTEGER | Lower tick bound |
| tick_upper | INTEGER | Upper tick bound |
| tick_spacing | INTEGER | Tick spacing |
| liquidity | VARCHAR | Position liquidity |
| staked | BOOLEAN | Whether staked in gauge |
| gauge_address | VARCHAR | Gauge address if staked |
| entry_amount_usdc | DECIMAL(20,6) | Entry amount |
| current_value_usdc | DECIMAL(20,6) | Current value |
| realized_pnl_usdc | DECIMAL(20,6) | Realized P&L |
| unrealized_pnl_usdc | DECIMAL(20,6) | Unrealized P&L |
| fees_earned_usdc | DECIMAL(20,6) | Fees earned |
| rewards_earned_usdc | DECIMAL(20,6) | Rewards earned |
| status | ENUM | active/closed/liquidated |
| entry_tx_hash | VARCHAR | Entry transaction hash |
| exit_tx_hash | VARCHAR | Exit transaction hash |
| entry_date | TIMESTAMP | Entry date |
| exit_date | TIMESTAMP | Exit date |
| last_updated | TIMESTAMP | Last update time |

**Indexes:** user_id, pool_address, status, nft_token_id, staked, entry_date, exit_date

### 4. protocol_fees
Protocol fee tracking (5% on profits).

| Column | Type | Description |
|--------|------|-------------|
| fee_id | UUID (PK) | Unique fee ID |
| user_id | VARCHAR (FK) | References users.user_id |
| position_id | UUID (FK) | References positions.position_id (unique) |
| position_profit_usdc | DECIMAL(20,6) | Position profit |
| fee_amount_usdc | DECIMAL(20,6) | Fee amount (5% of profit) |
| fee_percentage | DECIMAL(5,4) | Fee percentage |
| collected | BOOLEAN | Collection status |
| collection_tx_hash | VARCHAR | Collection transaction hash |
| created_at | TIMESTAMP | Creation time |
| collected_at | TIMESTAMP | Collection time |

**Indexes:** user_id, position_id, collected, created_at

## Cache & Monitoring Tables

### 5. pool_metrics
Pool metrics cache to reduce blockchain calls.

| Column | Type | Description |
|--------|------|-------------|
| pool_address | VARCHAR (PK) | Pool address |
| tvl_usd | DECIMAL(20,2) | Total Value Locked |
| volume_24h | DECIMAL(20,2) | 24-hour volume |
| apr | DECIMAL(10,2) | Annual Percentage Rate |
| tick_spacing | INTEGER | Tick spacing |
| fee_tier | INTEGER | Fee tier in basis points |
| is_stable | BOOLEAN | Stable/volatile pool |
| current_tick | INTEGER | Current tick |
| sqrt_price_x96 | VARCHAR | Square root price |
| gauge_address | VARCHAR | Gauge for staking |
| token0_address | VARCHAR | Token 0 address |
| token1_address | VARCHAR | Token 1 address |
| token0_symbol | VARCHAR | Token 0 symbol |
| token1_symbol | VARCHAR | Token 1 symbol |
| updated_at | TIMESTAMP | Last update |

**Indexes:** updated_at, tvl_usd, volume_24h, apr, is_stable, gauge_address

### 6. executor_stats
Executor pool monitoring.

| Column | Type | Description |
|--------|------|-------------|
| executor_id | VARCHAR (PK) | Executor identifier |
| executor_name | VARCHAR | Executor name |
| executor_type | VARCHAR | Type (position_manager, rebalancer, etc.) |
| active_wallets | INTEGER | Active wallet count |
| total_positions | INTEGER | Total positions managed |
| active_positions | INTEGER | Active positions |
| total_volume_executed | DECIMAL(20,2) | Total volume |
| total_fees_collected | DECIMAL(20,2) | Total fees |
| success_rate | DECIMAL(5,2) | Success percentage |
| last_heartbeat | TIMESTAMP | Last heartbeat signal |
| is_healthy | BOOLEAN | Health status |
| error_count | INTEGER | Error count |
| last_error | VARCHAR | Last error message |
| last_error_time | TIMESTAMP | Last error time |
| config | JSON | Configuration |
| created_at | TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | Update time |

**Indexes:** last_heartbeat, is_healthy, executor_type, active_positions

### 7. strategy_decisions
Strategy API decision tracking.

| Column | Type | Description |
|--------|------|-------------|
| decision_id | UUID (PK) | Decision ID |
| request_id | VARCHAR | Request identifier |
| user_id | VARCHAR | User ID |
| decision_type | VARCHAR | entry/exit/rebalance |
| pool_address | VARCHAR | Pool address |
| action_recommended | VARCHAR | Recommended action |
| recommended_amount_usdc | DECIMAL(20,6) | Recommended amount |
| recommended_tick_lower | INTEGER | Lower tick |
| recommended_tick_upper | INTEGER | Upper tick |
| pool_tvl | DECIMAL(20,2) | Pool TVL at decision |
| pool_volume_24h | DECIMAL(20,2) | Pool volume |
| pool_apr | DECIMAL(10,2) | Pool APR |
| current_tick | INTEGER | Current tick |
| risk_score | DECIMAL(5,2) | Risk score (0-100) |
| confidence_score | DECIMAL(5,2) | Confidence (0-100) |
| expected_return | DECIMAL(10,2) | Expected return % |
| reasoning | TEXT | Decision reasoning |
| decision_metadata | JSON | Additional metadata |
| was_executed | BOOLEAN | Execution status |
| execution_tx_hash | VARCHAR | Execution tx hash |
| execution_time | TIMESTAMP | Execution time |
| execution_result | VARCHAR | success/failed/partial |
| actual_pnl | DECIMAL(20,6) | Actual P&L |
| actual_apr | DECIMAL(10,2) | Actual APR |
| created_at | TIMESTAMP | Creation time |

**Indexes:** created_at, decision_type, pool_address, was_executed, user_id, action_recommended

### 8. daily_metrics
Daily aggregated performance metrics.

| Column | Type | Description |
|--------|------|-------------|
| metric_date | DATE (PK) | Metric date |
| metric_type | VARCHAR (PK) | platform/user:{id}/pool:{address} |
| total_volume_usdc | DECIMAL(20,2) | Total volume |
| deposit_volume_usdc | DECIMAL(20,2) | Deposit volume |
| withdrawal_volume_usdc | DECIMAL(20,2) | Withdrawal volume |
| positions_opened | INTEGER | Positions opened |
| positions_closed | INTEGER | Positions closed |
| active_positions | INTEGER | Active positions |
| active_users | INTEGER | Active users |
| new_users | INTEGER | New users |
| total_users | INTEGER | Total users |
| total_tvl_usdc | DECIMAL(20,2) | Total TVL |
| total_fees_earned_usdc | DECIMAL(20,2) | Fees earned |
| total_rewards_earned_usdc | DECIMAL(20,2) | Rewards earned |
| protocol_fees_collected_usdc | DECIMAL(20,2) | Protocol fees |
| total_pnl_usdc | DECIMAL(20,2) | Total P&L |
| average_apr | DECIMAL(10,2) | Average APR |
| best_performing_pool | VARCHAR | Best pool |
| worst_performing_pool | VARCHAR | Worst pool |
| max_drawdown | DECIMAL(10,2) | Max drawdown % |
| sharpe_ratio | DECIMAL(10,4) | Sharpe ratio |
| total_transactions | INTEGER | Transaction count |
| failed_transactions | INTEGER | Failed count |
| average_gas_used | DECIMAL(20,9) | Avg gas used |
| created_at | TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | Update time |

**Indexes:** metric_date, metric_type, total_tvl_usdc, total_volume_usdc

## Database Features

### Relationships
- User → Transactions (1:N)
- User → Positions (1:N)
- User → Protocol Fees (1:N)
- Position → Protocol Fee (1:1)

### Indexes
All tables have appropriate indexes on:
- Primary keys
- Foreign keys
- Frequently queried fields
- Fields used in WHERE clauses
- Fields used in ORDER BY clauses

### Data Types
- **Financial amounts**: DECIMAL with appropriate precision
- **Timestamps**: All timezone-aware
- **Large numbers**: Stored as VARCHAR (e.g., liquidity, sqrt_price_x96)
- **Metadata**: JSON fields for flexibility

### Constraints
- Unique constraints on wallet addresses, NFT token IDs
- Foreign key constraints maintain referential integrity
- Check constraints on enums and percentages

## Migration Management

Migrations are managed with Alembic:
```bash
# Check current version
alembic current

# View history
alembic history

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

## Performance Considerations

1. **Connection Pooling**: Configured with pool_size=20
2. **Async Operations**: All database operations are async
3. **Indexes**: Strategic indexes on all frequently queried fields
4. **Cache Tables**: pool_metrics reduces blockchain calls
5. **Aggregation**: daily_metrics provides pre-computed analytics

## Security

1. **No direct SQL**: All queries use SQLAlchemy ORM
2. **Input validation**: Pydantic schemas validate all inputs
3. **Connection security**: SSL/TLS for production databases
4. **Secrets management**: Database credentials in environment variables