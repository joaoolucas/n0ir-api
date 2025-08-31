"""Convert position JSONB data to real columns.

Revision ID: 012_position_jsonb_to_columns
Revises: 011_fix_missing_columns
Create Date: 2025-08-25 19:00:00.000000

This migration converts JSONB position_data fields to real database columns
for better performance, type safety, and ORM compatibility.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '012_position_jsonb_to_columns'
down_revision = '011_fix_missing_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add real columns for position data and migrate from JSONB."""
    
    print("Adding real columns to positions table...")
    
    # Add new columns
    op.execute("""
        DO $$
        BEGIN
            -- Token addresses
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'token0_address') THEN
                ALTER TABLE positions ADD COLUMN token0_address VARCHAR(42);
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'token1_address') THEN
                ALTER TABLE positions ADD COLUMN token1_address VARCHAR(42);
            END IF;
            
            -- Pool name
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'pool_name') THEN
                ALTER TABLE positions ADD COLUMN pool_name VARCHAR(100);
            END IF;
            
            -- Tick values
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'tick_lower') THEN
                ALTER TABLE positions ADD COLUMN tick_lower INTEGER;
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'tick_upper') THEN
                ALTER TABLE positions ADD COLUMN tick_upper INTEGER;
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'tick_spacing') THEN
                ALTER TABLE positions ADD COLUMN tick_spacing INTEGER;
            END IF;
            
            -- Liquidity (stored as string due to uint256 size)
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'liquidity') THEN
                ALTER TABLE positions ADD COLUMN liquidity VARCHAR(80);
            END IF;
            
            -- USD amounts
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'entry_amount_usdc') THEN
                ALTER TABLE positions ADD COLUMN entry_amount_usdc NUMERIC(20, 6) DEFAULT 0;
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'current_value_usdc') THEN
                ALTER TABLE positions ADD COLUMN current_value_usdc NUMERIC(20, 6);
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'fees_earned_usdc') THEN
                ALTER TABLE positions ADD COLUMN fees_earned_usdc NUMERIC(20, 6) DEFAULT 0;
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'rewards_earned_usdc') THEN
                ALTER TABLE positions ADD COLUMN rewards_earned_usdc NUMERIC(20, 6) DEFAULT 0;
            END IF;
            
            -- Staking info
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'staked') THEN
                ALTER TABLE positions ADD COLUMN staked BOOLEAN DEFAULT FALSE;
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'gauge_address') THEN
                ALTER TABLE positions ADD COLUMN gauge_address VARCHAR(42);
            END IF;
            
            -- Transaction hashes
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'entry_tx_hash') THEN
                ALTER TABLE positions ADD COLUMN entry_tx_hash VARCHAR(66);
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'exit_tx_hash') THEN
                ALTER TABLE positions ADD COLUMN exit_tx_hash VARCHAR(66);
            END IF;
            
            -- Add entry_date and exit_date if they don't exist
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'entry_date') THEN
                ALTER TABLE positions ADD COLUMN entry_date TIMESTAMP WITH TIME ZONE;
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'exit_date') THEN
                ALTER TABLE positions ADD COLUMN exit_date TIMESTAMP WITH TIME ZONE;
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'last_updated') THEN
                ALTER TABLE positions ADD COLUMN last_updated TIMESTAMP WITH TIME ZONE;
            END IF;
        END $$;
    """)
    
    print("Migrating data from JSONB to new columns...")
    
    # Migrate existing data from position_data JSONB to new columns
    op.execute("""
        UPDATE positions
        SET 
            token0_address = COALESCE(token0_address, position_data->>'token0_address'),
            token1_address = COALESCE(token1_address, position_data->>'token1_address'),
            pool_name = COALESCE(pool_name, position_data->>'pool_name'),
            tick_lower = COALESCE(tick_lower, (position_data->>'tick_lower')::INTEGER),
            tick_upper = COALESCE(tick_upper, (position_data->>'tick_upper')::INTEGER),
            tick_spacing = COALESCE(tick_spacing, (position_data->>'tick_spacing')::INTEGER),
            liquidity = COALESCE(liquidity, position_data->>'liquidity'),
            entry_amount_usdc = COALESCE(
                entry_amount_usdc, 
                CASE 
                    WHEN position_data->>'initial_investment_usd' IS NOT NULL 
                    THEN (position_data->>'initial_investment_usd')::NUMERIC
                    WHEN position_data->>'entry_amount_usdc' IS NOT NULL
                    THEN (position_data->>'entry_amount_usdc')::NUMERIC
                    ELSE 0
                END
            ),
            current_value_usdc = COALESCE(
                current_value_usdc,
                (position_data->>'current_value_usd')::NUMERIC
            ),
            fees_earned_usdc = COALESCE(
                fees_earned_usdc,
                CASE
                    WHEN position_data->'fees_earned'->>'total_fees_usd' IS NOT NULL
                    THEN (position_data->'fees_earned'->>'total_fees_usd')::NUMERIC
                    WHEN position_data->>'fees_earned_usd' IS NOT NULL
                    THEN (position_data->>'fees_earned_usd')::NUMERIC
                    ELSE 0
                END
            ),
            rewards_earned_usdc = COALESCE(
                rewards_earned_usdc,
                CASE
                    WHEN position_data->>'rewards_earned_usd' IS NOT NULL
                    THEN (position_data->>'rewards_earned_usd')::NUMERIC
                    ELSE 0
                END
            ),
            staked = COALESCE(
                staked,
                CASE
                    WHEN position_data->'gauge_info'->>'staked' = 'true' THEN TRUE
                    WHEN position_data->>'staked' = 'true' THEN TRUE
                    ELSE FALSE
                END
            ),
            gauge_address = COALESCE(
                gauge_address,
                COALESCE(
                    position_data->'gauge_info'->>'gauge_address',
                    position_data->>'gauge_address'
                )
            ),
            entry_tx_hash = COALESCE(entry_tx_hash, position_data->>'entry_tx_hash'),
            exit_tx_hash = COALESCE(exit_tx_hash, position_data->>'exit_tx_hash'),
            entry_date = COALESCE(entry_date, created_at),
            exit_date = COALESCE(exit_date, closed_at),
            last_updated = COALESCE(last_updated, updated_at)
        WHERE position_data IS NOT NULL;
    """)
    
    print("Fixing status values to lowercase...")
    
    # Fix status values to match enum (ACTIVE -> active, CLOSED -> closed, etc.)
    op.execute("""
        UPDATE positions
        SET status = LOWER(status::text)::positionstatus
        WHERE status::text IN ('ACTIVE', 'CLOSED', 'LIQUIDATED');
    """)
    
    print("Creating indexes for new columns...")
    
    # Create indexes for better query performance
    op.execute("CREATE INDEX IF NOT EXISTS idx_positions_token0 ON positions(token0_address)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_positions_token1 ON positions(token1_address)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_positions_staked ON positions(staked) WHERE staked = TRUE")
    op.execute("CREATE INDEX IF NOT EXISTS idx_positions_gauge ON positions(gauge_address) WHERE gauge_address IS NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS idx_positions_entry_date ON positions(entry_date DESC)")
    
    print("Migration completed successfully!")


def downgrade() -> None:
    """Remove added columns and restore JSONB-only structure."""
    
    print("Saving column data back to JSONB...")
    
    # Save current column values back to position_data
    op.execute("""
        UPDATE positions
        SET position_data = position_data || 
            jsonb_build_object(
                'token0_address', token0_address,
                'token1_address', token1_address,
                'pool_name', pool_name,
                'tick_lower', tick_lower,
                'tick_upper', tick_upper,
                'tick_spacing', tick_spacing,
                'liquidity', liquidity,
                'initial_investment_usd', entry_amount_usdc,
                'current_value_usd', current_value_usdc,
                'fees_earned', jsonb_build_object('total_fees_usd', fees_earned_usdc),
                'rewards_earned_usd', rewards_earned_usdc,
                'gauge_info', jsonb_build_object(
                    'staked', staked,
                    'gauge_address', gauge_address
                ),
                'entry_tx_hash', entry_tx_hash,
                'exit_tx_hash', exit_tx_hash
            )
        WHERE token0_address IS NOT NULL OR token1_address IS NOT NULL;
    """)
    
    # Revert status back to uppercase
    op.execute("""
        UPDATE positions
        SET status = UPPER(status)
        WHERE status IN ('active', 'closed', 'liquidated');
    """)
    
    print("Dropping indexes...")
    
    # Drop indexes
    op.execute("DROP INDEX IF EXISTS idx_positions_token0")
    op.execute("DROP INDEX IF EXISTS idx_positions_token1")
    op.execute("DROP INDEX IF EXISTS idx_positions_staked")
    op.execute("DROP INDEX IF EXISTS idx_positions_gauge")
    op.execute("DROP INDEX IF EXISTS idx_positions_entry_date")
    
    print("Removing columns...")
    
    # Drop columns
    op.execute("""
        ALTER TABLE positions
        DROP COLUMN IF EXISTS token0_address,
        DROP COLUMN IF EXISTS token1_address,
        DROP COLUMN IF EXISTS pool_name,
        DROP COLUMN IF EXISTS tick_lower,
        DROP COLUMN IF EXISTS tick_upper,
        DROP COLUMN IF EXISTS tick_spacing,
        DROP COLUMN IF EXISTS liquidity,
        DROP COLUMN IF EXISTS entry_amount_usdc,
        DROP COLUMN IF EXISTS current_value_usdc,
        DROP COLUMN IF EXISTS fees_earned_usdc,
        DROP COLUMN IF EXISTS rewards_earned_usdc,
        DROP COLUMN IF EXISTS staked,
        DROP COLUMN IF EXISTS gauge_address,
        DROP COLUMN IF EXISTS entry_tx_hash,
        DROP COLUMN IF EXISTS exit_tx_hash,
        DROP COLUMN IF EXISTS entry_date,
        DROP COLUMN IF EXISTS exit_date,
        DROP COLUMN IF EXISTS last_updated;
    """)
    
    print("Downgrade completed!")