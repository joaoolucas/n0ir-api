"""Add pool_name field to transactions table

Revision ID: 006
Revises: 005
Create Date: 2025-01-22

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '006_add_pool_name_to_transactions'
down_revision = '005_add_pool_name_to_positions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add pool_name column to transactions table."""
    op.add_column('transactions', 
        sa.Column('pool_name', sa.String(), nullable=True)
    )


def downgrade() -> None:
    """Remove pool_name column from transactions table."""
    op.drop_column('transactions', 'pool_name')