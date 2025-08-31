"""Drop old status column from users table

Revision ID: 018_drop_status
Revises: 017_drop_wallet_address
Create Date: 2025-08-31

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '018_drop_status'
down_revision = '017_drop_wallet_address'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop the old status column if it exists."""
    # Drop the old status column if it exists
    op.execute("""
        ALTER TABLE users 
        DROP COLUMN IF EXISTS status CASCADE;
    """)
    
    print("✅ Dropped old status column if it existed")


def downgrade() -> None:
    """Re-add status column."""
    # Re-add the column in downgrade
    op.execute("""
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS status VARCHAR(50);
    """)