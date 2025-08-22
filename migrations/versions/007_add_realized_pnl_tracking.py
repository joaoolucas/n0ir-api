"""Add realized PnL tracking fields to transactions

Revision ID: 007
Revises: 006
Create Date: 2025-01-22

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '007_add_realized_pnl_tracking'
down_revision = '006_add_pool_name_to_txns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add realized PnL tracking columns to transactions table."""
    op.add_column('transactions', 
        sa.Column('realized_pnl_usdc', sa.Numeric(precision=20, scale=6), nullable=True)
    )
    op.add_column('transactions', 
        sa.Column('portfolio_value_at_time', sa.Numeric(precision=20, scale=6), nullable=True)
    )
    op.add_column('transactions', 
        sa.Column('cost_basis_withdrawn', sa.Numeric(precision=20, scale=6), nullable=True)
    )


def downgrade() -> None:
    """Remove realized PnL tracking columns from transactions table."""
    op.drop_column('transactions', 'realized_pnl_usdc')
    op.drop_column('transactions', 'portfolio_value_at_time')
    op.drop_column('transactions', 'cost_basis_withdrawn')