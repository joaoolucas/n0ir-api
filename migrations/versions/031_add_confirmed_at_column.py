"""Add confirmed_at column to transactions table

Revision ID: 031_add_confirmed_at_column
Revises: 030_add_blockchain_sync_tables
Create Date: 2025-09-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '031_add_confirmed_at_column'
down_revision = '030_add_blockchain_sync_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add confirmed_at column to transactions table if it doesn't exist."""
    # Check if column already exists
    conn = op.get_bind()
    result = conn.execute(
        sa.text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='transactions' 
            AND column_name='confirmed_at'
        """)
    )
    
    if not result.fetchone():
        # Add confirmed_at column
        op.add_column('transactions', 
            sa.Column('confirmed_at', 
                     sa.DateTime(timezone=True), 
                     nullable=True)
        )
        
        # Set confirmed_at to created_at for existing confirmed transactions
        op.execute("""
            UPDATE transactions 
            SET confirmed_at = created_at 
            WHERE status = 'CONFIRMED' 
            AND confirmed_at IS NULL
        """)
        
        print("✅ Added confirmed_at column to transactions table")
    else:
        print("ℹ️ confirmed_at column already exists, skipping")


def downgrade() -> None:
    """Remove confirmed_at column from transactions table."""
    op.drop_column('transactions', 'confirmed_at')
    print("✅ Removed confirmed_at column from transactions table")