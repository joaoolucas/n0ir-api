"""Fix missing columns and data type issues.

Revision ID: 011_fix_missing_columns
Revises: 010_unified_three_table_schema
Create Date: 2025-08-25 18:00:00.000000

This migration adds missing columns and fixes data type issues.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '011_fix_missing_columns'
down_revision = '010_unified_three_table_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add missing columns to match models."""
    
    print("Adding missing columns to positions table...")
    
    # Add created_at and updated_at to positions if they don't exist
    op.execute("""
        DO $$
        BEGIN
            -- Add created_at if missing
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'created_at') THEN
                ALTER TABLE positions ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL;
            END IF;
            
            -- Add updated_at if missing  
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'updated_at') THEN
                ALTER TABLE positions ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL;
            END IF;
            
            -- Copy data from entry_date to created_at if entry_date exists
            IF EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'positions' AND column_name = 'entry_date') THEN
                UPDATE positions SET created_at = entry_date WHERE created_at IS NULL;
            END IF;
            
            -- Copy data from exit_date to closed_at if both exist
            IF EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'positions' AND column_name = 'exit_date') 
               AND EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'closed_at') THEN
                UPDATE positions SET closed_at = exit_date WHERE exit_date IS NOT NULL AND closed_at IS NULL;
            END IF;
        END $$;
    """)
    
    # Remove old columns if they exist
    op.execute("""
        DO $$
        BEGIN
            -- Remove entry_date if it exists
            IF EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'positions' AND column_name = 'entry_date') THEN
                ALTER TABLE positions DROP COLUMN entry_date;
            END IF;
            
            -- Remove exit_date if it exists
            IF EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'positions' AND column_name = 'exit_date') THEN
                ALTER TABLE positions DROP COLUMN exit_date;
            END IF;
            
            -- Remove last_updated if it exists
            IF EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'positions' AND column_name = 'last_updated') THEN
                ALTER TABLE positions DROP COLUMN last_updated;
            END IF;
        END $$;
    """)
    
    # Drop and recreate transaction status enum as plain VARCHAR
    op.execute("""
        DO $$
        BEGIN
            -- Change status column to VARCHAR if it's an enum
            IF EXISTS (
                SELECT 1 FROM pg_type 
                WHERE typname = 'transactionstatus'
            ) THEN
                -- First, alter the column to use VARCHAR
                ALTER TABLE transactions 
                ALTER COLUMN status TYPE VARCHAR(20) 
                USING status::text;
                
                -- Drop the enum type
                DROP TYPE IF EXISTS transactionstatus;
            END IF;
        END $$;
    """)
    
    print("Migration completed successfully!")


def downgrade() -> None:
    """Revert column changes."""
    
    # Add back old columns
    op.execute("""
        DO $$
        BEGIN
            -- Add entry_date back
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'entry_date') THEN
                ALTER TABLE positions ADD COLUMN entry_date TIMESTAMP WITH TIME ZONE;
                UPDATE positions SET entry_date = created_at;
            END IF;
            
            -- Add exit_date back
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'positions' AND column_name = 'exit_date') THEN
                ALTER TABLE positions ADD COLUMN exit_date TIMESTAMP WITH TIME ZONE;
                UPDATE positions SET exit_date = closed_at WHERE closed_at IS NOT NULL;
            END IF;
            
            -- Remove created_at and updated_at
            ALTER TABLE positions DROP COLUMN IF EXISTS created_at;
            ALTER TABLE positions DROP COLUMN IF EXISTS updated_at;
        END $$;
    """)