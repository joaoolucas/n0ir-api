"""Add has_deposited_50_usdc field to users table.

Revision ID: 016_add_has_deposited_50_usdc
Revises: 015_add_wallet_balance_tracking
Create Date: 2025-08-29 10:00:00.000000

This migration adds a field to track whether users have NET deposits of 50+ USDC,
used to enforce initial deposit requirements for agent startup.
Net deposits = total_deposits_usdc - total_withdrawals_usdc
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '016_add_has_deposited_50_usdc'
down_revision = '015_add_wallet_balance_tracking'
branch_labels = None
depends_on = None


def upgrade():
    """Add has_deposited_50_usdc field to users table."""
    # Add the new column with default value False
    op.add_column(
        'users',
        sa.Column('has_deposited_50_usdc', sa.Boolean(), nullable=False, server_default='false')
    )
    
    # Update existing users based on their NET deposits (deposits - withdrawals)
    # Set to True for users who have net deposits of 50+ USDC
    op.execute("""
        UPDATE users 
        SET has_deposited_50_usdc = TRUE 
        WHERE (total_deposits_usdc - total_withdrawals_usdc) >= 50
    """)
    
    print("✅ Added has_deposited_50_usdc field to users table")


def downgrade():
    """Remove has_deposited_50_usdc field from users table."""
    op.drop_column('users', 'has_deposited_50_usdc')
    print("✅ Removed has_deposited_50_usdc field from users table")