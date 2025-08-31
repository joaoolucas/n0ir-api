"""Drop old wallet_address column

Revision ID: 017
Revises: 016
Create Date: 2025-08-31

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '017_drop_wallet_address'
down_revision = '016_add_has_deposited_50_usdc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop the old wallet_address column if it exists."""
    # Drop the old wallet_address column if it exists
    op.execute("""
        ALTER TABLE users 
        DROP COLUMN IF EXISTS wallet_address CASCADE;
    """)
    
    print("✅ Dropped old wallet_address column if it existed")


def downgrade() -> None:
    """Re-add wallet_address column."""
    # Re-add the column in downgrade
    op.execute("""
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS wallet_address VARCHAR(42);
    """)