"""Fix transactiontype enum to include AERO_SWAP and cast column to varchar

Revision ID: 020_fix_transaction_type_enum
Revises: 019_add_block_timestamp
Create Date: 2025-08-31

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '020_fix_transaction_type_enum'
down_revision = '019_add_block_timestamp'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Convert tx_type to VARCHAR to handle all transaction types flexibly."""
    
    # First, alter the column to VARCHAR to avoid enum constraints
    # Convert tx_type column to VARCHAR (split into separate statements for asyncpg)
    op.execute(
        """
        ALTER TABLE transactions 
        ALTER COLUMN tx_type TYPE VARCHAR(50) 
        USING tx_type::text
        """
    )
    
    # Drop the old enum type if it exists
    op.execute("DROP TYPE IF EXISTS transactiontype CASCADE;")
    
    # Create index for performance
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_transactions_tx_type_varchar 
        ON transactions(tx_type)
        """
    )
    
    print("✅ Converted tx_type to VARCHAR(50) for flexibility")


def downgrade() -> None:
    """Revert to enum type."""
    op.execute("""
        -- Recreate the enum type
        CREATE TYPE transactiontype AS ENUM (
            'POSITION_CREATED', 'POSITION_MODIFIED', 'POSITION_CLOSED',
            'LIQUIDITY_ADDED', 'LIQUIDITY_REMOVED', 'FEES_COLLECTED',
            'SWAP_EXECUTED', 'STAKE_CREATED', 'STAKE_REMOVED',
            'REWARDS_CLAIMED', 'DEPOSIT', 'WITHDRAWAL', 'FEE_COLLECTION',
            'AERO_SWAP'
        );
        
        -- Convert back to enum
        ALTER TABLE transactions 
        ALTER COLUMN tx_type TYPE transactiontype 
        USING tx_type::transactiontype;
        
        -- Drop the varchar index
        DROP INDEX IF EXISTS idx_transactions_tx_type_varchar;
    """)
