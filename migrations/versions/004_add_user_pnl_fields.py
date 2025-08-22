"""Add PnL tracking fields to users table

Revision ID: 004
Revises: 003
Create Date: 2025-01-22

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '004_add_user_pnl_fields'
down_revision = '003_fix_position_primary_key'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add PnL tracking fields to users table."""
    # Add unrealized_pnl_usdc column
    op.add_column('users', 
        sa.Column('unrealized_pnl_usdc', 
                  sa.Numeric(precision=20, scale=6), 
                  nullable=False, 
                  server_default='0')
    )
    
    # Add realized_pnl_usdc column
    op.add_column('users', 
        sa.Column('realized_pnl_usdc', 
                  sa.Numeric(precision=20, scale=6), 
                  nullable=False, 
                  server_default='0')
    )
    
    # Add unrealized_pnl_percentage column
    op.add_column('users', 
        sa.Column('unrealized_pnl_percentage', 
                  sa.Numeric(precision=10, scale=2), 
                  nullable=False, 
                  server_default='0')
    )
    
    # Add realized_pnl_percentage column
    op.add_column('users', 
        sa.Column('realized_pnl_percentage', 
                  sa.Numeric(precision=10, scale=2), 
                  nullable=False, 
                  server_default='0')
    )


def downgrade() -> None:
    """Remove PnL tracking fields from users table."""
    op.drop_column('users', 'unrealized_pnl_usdc')
    op.drop_column('users', 'realized_pnl_usdc')
    op.drop_column('users', 'unrealized_pnl_percentage')
    op.drop_column('users', 'realized_pnl_percentage')