"""Unified three-table schema migration for n0ir-api.

Revision ID: 010_unified_three_table_schema
Revises: 008_add_agent_state_tracking
Create Date: 2025-08-25 16:00:00.000000

This migration consolidates the database to match the unified 3-table architecture.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '010_unified_three_table_schema'
down_revision = '008_add_agent_state_tracking'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Migrate to unified 3-table schema."""
    
    # 1. Update users table structure
    print("Updating users table...")
    
    # Add missing columns if they don't exist
    op.execute("""
        DO $$
        BEGIN
            -- Add cdp_wallet columns if missing
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'users' AND column_name = 'cdp_wallet_address') THEN
                ALTER TABLE users ADD COLUMN cdp_wallet_address VARCHAR(42) UNIQUE;
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'users' AND column_name = 'cdp_wallet_name') THEN
                ALTER TABLE users ADD COLUMN cdp_wallet_name VARCHAR(100);
            END IF;
            
            -- Add PnL columns if missing
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'users' AND column_name = 'unrealized_pnl_usd') THEN
                ALTER TABLE users ADD COLUMN unrealized_pnl_usd NUMERIC(20,2) DEFAULT 0;
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'users' AND column_name = 'unrealized_pnl_pct') THEN
                ALTER TABLE users ADD COLUMN unrealized_pnl_pct NUMERIC(10,4) DEFAULT 0;
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'users' AND column_name = 'realized_pnl_usd') THEN
                ALTER TABLE users ADD COLUMN realized_pnl_usd NUMERIC(20,2) DEFAULT 0;
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'users' AND column_name = 'realized_pnl_pct') THEN
                ALTER TABLE users ADD COLUMN realized_pnl_pct NUMERIC(10,4) DEFAULT 0;
            END IF;
            
            -- Add metadata column if missing
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'users' AND column_name = 'user_metadata') THEN
                ALTER TABLE users ADD COLUMN user_metadata JSONB DEFAULT '{}';
            END IF;
        END $$;
    """)
    
    # Migrate existing cdp_wallet data if it exists in different columns
    # First check if wallet_address column exists
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'wallet_address'
            ) THEN
                UPDATE users 
                SET cdp_wallet_address = COALESCE(cdp_wallet_address, wallet_address)
                WHERE cdp_wallet_address IS NULL AND wallet_address IS NOT NULL;
            END IF;
        END $$;
    """)
    
    # Migrate agent status to metadata
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'agent_status'
            ) THEN
                UPDATE users 
                SET user_metadata = COALESCE(user_metadata, '{}'::jsonb) || 
                               jsonb_build_object(
                                   'agent_status', COALESCE(agent_status::text, 'not_started'),
                                   'agent_started_at', agent_started_at,
                                   'agent_stopped_at', agent_stopped_at,
                                   'last_balance_check', last_balance_check
                               )
                WHERE agent_status IS NOT NULL OR agent_started_at IS NOT NULL;
            END IF;
        END $$;
    """)
    
    # Migrate PnL data from existing columns
    op.execute("""
        UPDATE users 
        SET unrealized_pnl_usd = COALESCE(unrealized_pnl_usdc, unrealized_pnl_usd, 0),
            realized_pnl_usd = COALESCE(realized_pnl_usdc, realized_pnl_usd, 0),
            unrealized_pnl_pct = COALESCE(unrealized_pnl_percentage, unrealized_pnl_pct, 0),
            realized_pnl_pct = COALESCE(realized_pnl_percentage, realized_pnl_pct, 0)
        WHERE unrealized_pnl_usdc IS NOT NULL OR realized_pnl_usdc IS NOT NULL;
    """)
    
    # 2. Update positions table structure
    print("Updating positions table...")
    
    # Rename columns to match new schema
    op.execute("""
        DO $$
        BEGIN
            -- Rename nft_token_id to token_id if needed
            IF EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'positions' AND column_name = 'nft_token_id') THEN
                ALTER TABLE positions RENAME COLUMN nft_token_id TO token_id;
            END IF;
            
            -- Add PnL columns if missing
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'unrealized_pnl_usd') THEN
                ALTER TABLE positions ADD COLUMN unrealized_pnl_usd NUMERIC(20,2) DEFAULT 0;
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'unrealized_pnl_pct') THEN
                ALTER TABLE positions ADD COLUMN unrealized_pnl_pct NUMERIC(10,4) DEFAULT 0;
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'realized_pnl_usd') THEN
                ALTER TABLE positions ADD COLUMN realized_pnl_usd NUMERIC(20,2) DEFAULT 0;
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'realized_pnl_pct') THEN
                ALTER TABLE positions ADD COLUMN realized_pnl_pct NUMERIC(10,4) DEFAULT 0;
            END IF;
            
            -- Add JSONB columns
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'position_data') THEN
                ALTER TABLE positions ADD COLUMN position_data JSONB DEFAULT '{}';
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'blockchain_data') THEN
                ALTER TABLE positions ADD COLUMN blockchain_data JSONB DEFAULT '{}';
            END IF;
            
            -- Add closed_at if missing
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'closed_at') THEN
                ALTER TABLE positions ADD COLUMN closed_at TIMESTAMP;
            END IF;
        END $$;
    """)
    
    # Migrate existing position data to JSONB
    op.execute("""
        UPDATE positions 
        SET position_data = COALESCE(position_data, '{}'::jsonb) || 
                           jsonb_build_object(
                               'token0_address', token0_address,
                               'token1_address', token1_address,
                               'pool_name', pool_name,
                               'pool_fee_tier', 3000,
                               'tick_lower', tick_lower,
                               'tick_upper', tick_upper,
                               'tick_spacing', tick_spacing,
                               'liquidity', liquidity,
                               'initial_investment_usd', entry_amount_usdc,
                               'current_value_usd', current_value_usdc,
                               'total_fees_usd', fees_earned_usdc,
                               'rewards_earned_usd', rewards_earned_usdc,
                               'entry_tx_hash', entry_tx_hash,
                               'exit_tx_hash', exit_tx_hash,
                               'gauge_info', CASE 
                                   WHEN staked = true THEN 
                                       jsonb_build_object('staked', true, 'gauge_address', gauge_address)
                                   ELSE NULL 
                               END
                           ),
            blockchain_data = jsonb_build_object(
                               'creation_tx_hash', entry_tx_hash,
                               'close_tx_hash', exit_tx_hash
                           ),
            unrealized_pnl_usd = COALESCE(unrealized_pnl_usdc, 0),
            realized_pnl_usd = COALESCE(realized_pnl_usdc, 0),
            closed_at = exit_date
        WHERE position_data IS NULL OR position_data = '{}'::jsonb;
    """)
    
    # 3. Update transactions table structure
    print("Updating transactions table...")
    
    # Add new columns to transactions
    op.execute("""
        DO $$
        BEGIN
            -- Rename transaction_id to id if needed
            IF EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'transactions' AND column_name = 'transaction_id') THEN
                ALTER TABLE transactions RENAME COLUMN transaction_id TO id;
            END IF;
            
            -- Add tx_type column if missing
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'transactions' AND column_name = 'tx_type') THEN
                ALTER TABLE transactions ADD COLUMN tx_type VARCHAR(50);
            END IF;
            
            -- Add position_id column if missing
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'transactions' AND column_name = 'position_id') THEN
                ALTER TABLE transactions ADD COLUMN position_id INTEGER REFERENCES positions(token_id);
            END IF;
            
            -- Add JSONB columns
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'transactions' AND column_name = 'event_data') THEN
                ALTER TABLE transactions ADD COLUMN event_data JSONB DEFAULT '{}';
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'transactions' AND column_name = 'tx_metadata') THEN
                ALTER TABLE transactions ADD COLUMN tx_metadata JSONB DEFAULT '{}';
            END IF;
            
            -- Add block_timestamp if missing
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'transactions' AND column_name = 'block_timestamp') THEN
                ALTER TABLE transactions ADD COLUMN block_timestamp TIMESTAMP;
            END IF;
            
            -- Add processed_at if missing
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'transactions' AND column_name = 'processed_at') THEN
                ALTER TABLE transactions ADD COLUMN processed_at TIMESTAMP;
            END IF;
        END $$;
    """)
    
    # Map old transaction_type to new tx_type
    op.execute("""
        DO $$
        BEGIN
            -- Only run this migration if the old columns exist
            IF EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'transactions' AND column_name = 'transaction_type') THEN
                UPDATE transactions 
                SET tx_type = CASE 
                    WHEN transaction_type::text = 'deposit' THEN 'DEPOSIT'
                    WHEN transaction_type::text = 'withdraw' THEN 'WITHDRAWAL'
                    WHEN transaction_type::text = 'position_entry' THEN 'POSITION_CREATED'
                    WHEN transaction_type::text = 'position_exit' THEN 'POSITION_CLOSED'
                    WHEN transaction_type::text = 'protocol_fee' THEN 'PROTOCOL_FEE'
                    ELSE UPPER(transaction_type::text)
                END
                WHERE tx_type IS NULL AND transaction_type IS NOT NULL;
            END IF;
            
            -- Migrate related_position_id if it exists
            IF EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'transactions' AND column_name = 'related_position_id') THEN
                UPDATE transactions 
                SET position_id = related_position_id
                WHERE position_id IS NULL AND related_position_id IS NOT NULL;
            END IF;
            
            -- Migrate amount and pool data if columns exist
            IF EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'transactions' AND column_name = 'amount_usdc') THEN
                UPDATE transactions 
                SET event_data = COALESCE(event_data, '{}'::jsonb) || 
                    jsonb_build_object(
                        'amount_usdc', amount_usdc,
                        'pool_name', pool_name
                    )
                WHERE event_data IS NULL OR event_data = '{}'::jsonb;
            END IF;
            
            -- Migrate metadata if columns exist
            IF EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'transactions' AND column_name = 'realized_pnl_usdc') THEN
                UPDATE transactions 
                SET tx_metadata = COALESCE(tx_metadata, '{}'::jsonb) || 
                    jsonb_build_object(
                        'realized_pnl_usdc', realized_pnl_usdc,
                        'portfolio_value_at_time', portfolio_value_at_time,
                        'cost_basis_withdrawn', cost_basis_withdrawn,
                        'gas_price', gas_price
                    )
                WHERE tx_metadata IS NULL OR tx_metadata = '{}'::jsonb;
            END IF;
            
            -- Migrate timestamps if columns exist
            IF EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'transactions' AND column_name = 'confirmed_at') THEN
                UPDATE transactions 
                SET block_timestamp = COALESCE(block_timestamp, confirmed_at),
                    processed_at = COALESCE(processed_at, confirmed_at)
                WHERE (block_timestamp IS NULL OR processed_at IS NULL) AND confirmed_at IS NOT NULL;
            END IF;
        END $$;
    """)
    
    # 4. Create new indexes
    print("Creating indexes...")
    
    # Users indexes
    op.create_index('idx_users_updated', 'users', ['updated_at'], if_not_exists=True)
    op.create_index('idx_users_cdp_wallet', 'users', ['cdp_wallet_address'], if_not_exists=True)
    op.create_index('idx_users_pnl', 'users', ['unrealized_pnl_usd'], if_not_exists=True)
    
    # Positions indexes
    op.create_index('idx_positions_user', 'positions', ['user_id', 'status'], if_not_exists=True)
    op.create_index('idx_positions_pool', 'positions', ['pool_address'], if_not_exists=True)
    op.create_index('idx_positions_status', 'positions', ['status'], 
                   postgresql_where=sa.text("status = 'ACTIVE'"), if_not_exists=True)
    op.create_index('idx_positions_pnl', 'positions', ['user_id', 'unrealized_pnl_usd'], 
                   postgresql_where=sa.text("status = 'ACTIVE'"), if_not_exists=True)
    
    # Transactions indexes
    op.create_index('idx_transactions_user', 'transactions', ['user_id', 'block_timestamp'], if_not_exists=True)
    op.create_index('idx_transactions_position', 'transactions', ['position_id', 'tx_type'], if_not_exists=True)
    op.create_index('idx_transactions_block', 'transactions', ['block_number'], if_not_exists=True)
    op.create_index('idx_transactions_type', 'transactions', ['tx_type', 'status'], if_not_exists=True)
    
    # JSONB GIN indexes
    op.create_index('idx_positions_data_gin', 'positions', ['position_data'], 
                   postgresql_using='gin', if_not_exists=True)
    op.create_index('idx_transactions_event_gin', 'transactions', ['event_data'], 
                   postgresql_using='gin', if_not_exists=True)
    op.create_index('idx_users_metadata_gin', 'users', ['user_metadata'], 
                   postgresql_using='gin', if_not_exists=True)
    
    # 5. Drop deprecated columns (careful - only after confirming data migration)
    print("Cleaning up deprecated columns...")
    
    # Drop old columns from users table
    columns_to_drop = [
        'unrealized_pnl_usdc', 'realized_pnl_usdc',
        'unrealized_pnl_percentage', 'realized_pnl_percentage',
        'agent_status', 'agent_started_at', 'agent_stopped_at',
        'last_balance_check', 'agent_metadata', 'status', 'wallet_address', 'metadata'
    ]
    
    for col in columns_to_drop:
        op.execute(f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'users' AND column_name = '{col}') THEN
                    ALTER TABLE users DROP COLUMN {col};
                END IF;
            END $$;
        """)
    
    # Drop old columns from positions table
    columns_to_drop = [
        'token0_address', 'token1_address', 'tick_lower', 'tick_upper',
        'tick_spacing', 'liquidity', 'staked', 'gauge_address',
        'entry_amount_usdc', 'current_value_usdc', 'unrealized_pnl_usdc',
        'realized_pnl_usdc', 'fees_earned_usdc', 'rewards_earned_usdc',
        'protocol_fee_amount', 'protocol_fee_collected', 'protocol_fee_tx_hash',
        'entry_tx_hash', 'exit_tx_hash', 'entry_date', 'exit_date',
        'last_updated', 'pool_name'
    ]
    
    for col in columns_to_drop:
        op.execute(f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = '{col}') THEN
                    ALTER TABLE positions DROP COLUMN {col};
                END IF;
            END $$;
        """)
    
    # Drop old columns from transactions table
    columns_to_drop = [
        'transaction_type', 'amount_usdc', 'pool_name',
        'realized_pnl_usdc', 'portfolio_value_at_time',
        'cost_basis_withdrawn', 'related_position_id',
        'gas_price', 'tx_metadata', 'confirmed_at', 'metadata'
    ]
    
    for col in columns_to_drop:
        op.execute(f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'transactions' AND column_name = '{col}') THEN
                    ALTER TABLE transactions DROP COLUMN {col};
                END IF;
            END $$;
        """)
    
    # 6. Drop deprecated tables
    print("Dropping deprecated tables...")
    tables_to_drop = [
        'agent_events', 'daily_metrics', 'executor_stats',
        'pool_metrics', 'strategy_decisions'
    ]
    
    for table in tables_to_drop:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    
    print("✅ Migration to unified 3-table schema completed successfully")


def downgrade() -> None:
    """Revert to previous schema."""
    # This is a major structural change, downgrade should be carefully planned
    # For safety, we're not implementing automatic downgrade
    raise NotImplementedError("Downgrade from unified schema not supported. Please restore from backup.")