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
    """Migrate to unified 3-table schema - safe version."""
    
    print("Starting unified 3-table schema migration...")
    
    # 1. Add new columns to users table if they don't exist
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
            
            -- Add standardized PnL columns if missing (USD instead of USDC)
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
    
    # 2. Add new columns to positions table if they don't exist
    op.execute("""
        DO $$
        BEGIN
            -- Add standardized PnL columns if missing
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
    
    # 3. Add new columns to transactions table if they don't exist
    op.execute("""
        DO $$
        BEGIN
            -- Add tx_type if missing (might be transaction_type)
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'transactions' AND column_name = 'tx_type') THEN
                -- Check if we have transaction_type instead
                IF EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'transactions' AND column_name = 'transaction_type') THEN
                    ALTER TABLE transactions RENAME COLUMN transaction_type TO tx_type;
                ELSE
                    ALTER TABLE transactions ADD COLUMN tx_type VARCHAR(50);
                END IF;
            END IF;
            
            -- Add event_data JSONB if missing
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'transactions' AND column_name = 'event_data') THEN
                ALTER TABLE transactions ADD COLUMN event_data JSONB DEFAULT '{}';
            END IF;
            
            -- Add tx_metadata JSONB if missing (might be metadata)
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'transactions' AND column_name = 'tx_metadata') THEN
                IF EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'transactions' AND column_name = 'metadata') THEN
                    ALTER TABLE transactions RENAME COLUMN metadata TO tx_metadata;
                ELSE
                    ALTER TABLE transactions ADD COLUMN tx_metadata JSONB DEFAULT '{}';
                END IF;
            END IF;
            
            -- Add processed_at if missing
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'transactions' AND column_name = 'processed_at') THEN
                ALTER TABLE transactions ADD COLUMN processed_at TIMESTAMP;
            END IF;
        END $$;
    """)
    
    # 4. Create optimized indexes (idempotent with IF NOT EXISTS)
    print("Creating indexes...")
    
    # Users indexes - execute each separately
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_updated ON users(updated_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_cdp_wallet ON users(cdp_wallet_address)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_pnl ON users(unrealized_pnl_usd)")
    
    # Positions indexes - execute each separately
    op.execute("CREATE INDEX IF NOT EXISTS idx_positions_user ON positions(user_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_positions_pool ON positions(pool_address)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status) WHERE status = 'ACTIVE'")
    op.execute("CREATE INDEX IF NOT EXISTS idx_positions_pnl ON positions(user_id, unrealized_pnl_usd) WHERE status = 'ACTIVE'")
    
    # Transactions indexes - execute each separately (check column existence first)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'transactions' AND column_name = 'block_timestamp') THEN
                CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id, block_timestamp);
            ELSE
                CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id, created_at);
            END IF;
        END $$;
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_transactions_position ON transactions(position_id, tx_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_transactions_block ON transactions(block_number)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(tx_type, status)")
    
    # JSONB GIN indexes - execute each separately
    op.execute("CREATE INDEX IF NOT EXISTS idx_positions_data_gin ON positions USING gin(position_data)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_transactions_event_gin ON transactions USING gin(event_data)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_metadata_gin ON users USING gin(user_metadata)")
    
    print("Migration completed successfully!")


def downgrade() -> None:
    """Revert unified schema changes."""
    
    # Drop new indexes
    op.execute("""
        DROP INDEX IF EXISTS idx_users_updated;
        DROP INDEX IF EXISTS idx_users_cdp_wallet;
        DROP INDEX IF EXISTS idx_users_pnl;
        DROP INDEX IF EXISTS idx_positions_user;
        DROP INDEX IF EXISTS idx_positions_pool;
        DROP INDEX IF EXISTS idx_positions_status;
        DROP INDEX IF EXISTS idx_positions_pnl;
        DROP INDEX IF EXISTS idx_transactions_user;
        DROP INDEX IF EXISTS idx_transactions_position;
        DROP INDEX IF EXISTS idx_transactions_block;
        DROP INDEX IF EXISTS idx_transactions_type;
        DROP INDEX IF EXISTS idx_positions_data_gin;
        DROP INDEX IF EXISTS idx_transactions_event_gin;
        DROP INDEX IF EXISTS idx_users_metadata_gin;
    """)
    
    # Drop added columns
    op.execute("""
        DO $$
        BEGIN
            -- Users table
            ALTER TABLE users DROP COLUMN IF EXISTS cdp_wallet_address;
            ALTER TABLE users DROP COLUMN IF EXISTS cdp_wallet_name;
            ALTER TABLE users DROP COLUMN IF EXISTS unrealized_pnl_usd;
            ALTER TABLE users DROP COLUMN IF EXISTS unrealized_pnl_pct;
            ALTER TABLE users DROP COLUMN IF EXISTS realized_pnl_usd;
            ALTER TABLE users DROP COLUMN IF EXISTS realized_pnl_pct;
            ALTER TABLE users DROP COLUMN IF EXISTS user_metadata;
            
            -- Positions table
            ALTER TABLE positions DROP COLUMN IF EXISTS unrealized_pnl_usd;
            ALTER TABLE positions DROP COLUMN IF EXISTS unrealized_pnl_pct;
            ALTER TABLE positions DROP COLUMN IF EXISTS realized_pnl_usd;
            ALTER TABLE positions DROP COLUMN IF EXISTS realized_pnl_pct;
            ALTER TABLE positions DROP COLUMN IF EXISTS position_data;
            ALTER TABLE positions DROP COLUMN IF EXISTS blockchain_data;
            ALTER TABLE positions DROP COLUMN IF EXISTS closed_at;
            
            -- Transactions table
            ALTER TABLE transactions DROP COLUMN IF EXISTS event_data;
            ALTER TABLE transactions DROP COLUMN IF EXISTS tx_metadata;
            ALTER TABLE transactions DROP COLUMN IF EXISTS processed_at;
        END $$;
    """)