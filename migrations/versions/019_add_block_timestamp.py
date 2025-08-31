"""Add block_timestamp column to transactions table

Revision ID: 019_add_block_timestamp
Revises: 018_drop_status
Create Date: 2025-08-31

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '019_add_block_timestamp'
down_revision = '018_drop_status'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add block_timestamp column to transactions table."""
    # Add block_timestamp column if it doesn't exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'transactions' 
                AND column_name = 'block_timestamp'
            ) THEN
                ALTER TABLE transactions 
                ADD COLUMN block_timestamp TIMESTAMP WITH TIME ZONE;
                
                -- Create index for efficient queries
                CREATE INDEX idx_transactions_block_timestamp 
                ON transactions(block_timestamp) 
                WHERE block_timestamp IS NOT NULL;
            END IF;
        END $$;
    """)
    
    print("✅ Added block_timestamp column to transactions table")


def downgrade() -> None:
    """Remove block_timestamp column."""
    op.execute("""
        DROP INDEX IF EXISTS idx_transactions_block_timestamp;
        ALTER TABLE transactions 
        DROP COLUMN IF EXISTS block_timestamp CASCADE;
    """)