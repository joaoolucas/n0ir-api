"""Add wallet balance tracking fields to users table for API service.

Revision ID: 015_add_wallet_balance_tracking
Revises: 013_fix_transaction_primary_key
Create Date: 2025-08-27 12:00:00.000000

This migration mirrors the watcher's wallet balance tracking fields in the API database,
ensuring schema consistency between services.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '015_add_wallet_balance_tracking'
down_revision = '013_fix_transaction_primary_key'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add wallet balance tracking fields to users table."""
    
    print("Adding wallet balance tracking fields to users table (API)...")
    
    # Add wallet balance tracking columns
    op.execute("""
        DO $$
        BEGIN
            -- Add USDC balance field
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'users' AND column_name = 'usdc_balance') THEN
                ALTER TABLE users ADD COLUMN usdc_balance NUMERIC(20,6) DEFAULT 0 NOT NULL;
            END IF;
            
            -- Add last deposit block
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'users' AND column_name = 'last_deposit_block') THEN
                ALTER TABLE users ADD COLUMN last_deposit_block INTEGER;
            END IF;
            
            -- Add last withdrawal block
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'users' AND column_name = 'last_withdrawal_block') THEN
                ALTER TABLE users ADD COLUMN last_withdrawal_block INTEGER;
            END IF;
            
            -- Add total deposits tracking
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'users' AND column_name = 'total_deposits_usdc') THEN
                ALTER TABLE users ADD COLUMN total_deposits_usdc NUMERIC(20,6) DEFAULT 0 NOT NULL;
            END IF;
            
            -- Add total withdrawals tracking
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'users' AND column_name = 'total_withdrawals_usdc') THEN
                ALTER TABLE users ADD COLUMN total_withdrawals_usdc NUMERIC(20,6) DEFAULT 0 NOT NULL;
            END IF;
            
            -- Add last scanned block for wallet monitoring
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'users' AND column_name = 'last_scanned_block') THEN
                ALTER TABLE users ADD COLUMN last_scanned_block INTEGER;
            END IF;
        END $$;
    """)
    
    print("✅ Added wallet balance tracking columns")
    
    # Create indexes for efficient queries
    print("Creating indexes for balance queries...")
    
    # Index for finding wallets that need scanning
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_last_scanned 
        ON users(last_scanned_block) 
        WHERE cdp_wallet_address IS NOT NULL;
    """)
    
    # Index for balance queries
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_balance 
        ON users(usdc_balance) 
        WHERE usdc_balance > 0;
    """)
    
    # Index for deposit/withdrawal tracking
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_last_deposit 
        ON users(last_deposit_block) 
        WHERE last_deposit_block IS NOT NULL;
    """)
    
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_last_withdrawal 
        ON users(last_withdrawal_block) 
        WHERE last_withdrawal_block IS NOT NULL;
    """)
    
    # Composite index for wallet queries
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_wallet_balance 
        ON users(cdp_wallet_address, usdc_balance) 
        WHERE cdp_wallet_address IS NOT NULL;
    """)
    
    print("✅ Created balance query indexes")
    
    # Initialize balance fields from existing transaction data if available
    print("Initializing balance fields from existing transaction data...")
    
    op.execute("""
        -- Update total deposits from existing DEPOSIT transactions
        WITH deposit_totals AS (
            SELECT 
                t.user_id,
                SUM((t.event_data->>'amount_usdc')::NUMERIC) as total_deposits,
                MAX(t.block_number) as last_deposit_block
            FROM transactions t
            WHERE t.tx_type = 'DEPOSIT'
            AND t.status = 'CONFIRMED'
            GROUP BY t.user_id
        )
        UPDATE users u
        SET 
            total_deposits_usdc = COALESCE(dt.total_deposits, 0),
            last_deposit_block = dt.last_deposit_block
        FROM deposit_totals dt
        WHERE u.user_id = dt.user_id;
    """)
    
    op.execute("""
        -- Update total withdrawals from existing WITHDRAWAL/WITHDRAW transactions
        WITH withdrawal_totals AS (
            SELECT 
                t.user_id,
                SUM((t.event_data->>'amount_usdc')::NUMERIC) as total_withdrawals,
                MAX(t.block_number) as last_withdrawal_block
            FROM transactions t
            WHERE t.tx_type IN ('WITHDRAWAL', 'WITHDRAW')
            AND t.status = 'CONFIRMED'
            GROUP BY t.user_id
        )
        UPDATE users u
        SET 
            total_withdrawals_usdc = COALESCE(wt.total_withdrawals, 0),
            last_withdrawal_block = wt.last_withdrawal_block
        FROM withdrawal_totals wt
        WHERE u.user_id = wt.user_id;
    """)
    
    op.execute("""
        -- Calculate current balance as deposits minus withdrawals
        UPDATE users
        SET usdc_balance = GREATEST(0, total_deposits_usdc - total_withdrawals_usdc)
        WHERE cdp_wallet_address IS NOT NULL;
    """)
    
    print("✅ Initialized balance fields from transaction history")
    
    print("✅ Wallet balance tracking migration completed successfully")
    print("📊 API can now read from watcher-owned balance fields:")
    print("   - users.usdc_balance for current balance")
    print("   - users.total_deposits_usdc / total_withdrawals_usdc for totals")
    print("   - users.last_deposit_block / last_withdrawal_block for tracking")


def downgrade() -> None:
    """Remove wallet balance tracking fields."""
    
    print("Removing wallet balance tracking fields...")
    
    # Drop indexes first
    op.execute("""
        DROP INDEX IF EXISTS idx_users_last_scanned;
        DROP INDEX IF EXISTS idx_users_balance;
        DROP INDEX IF EXISTS idx_users_last_deposit;
        DROP INDEX IF EXISTS idx_users_last_withdrawal;
        DROP INDEX IF EXISTS idx_users_wallet_balance;
    """)
    
    # Drop columns
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE users DROP COLUMN IF EXISTS usdc_balance;
            ALTER TABLE users DROP COLUMN IF EXISTS last_deposit_block;
            ALTER TABLE users DROP COLUMN IF EXISTS last_withdrawal_block;
            ALTER TABLE users DROP COLUMN IF EXISTS total_deposits_usdc;
            ALTER TABLE users DROP COLUMN IF EXISTS total_withdrawals_usdc;
            ALTER TABLE users DROP COLUMN IF EXISTS last_scanned_block;
        END $$;
    """)
    
    print("✅ Removed wallet balance tracking fields")