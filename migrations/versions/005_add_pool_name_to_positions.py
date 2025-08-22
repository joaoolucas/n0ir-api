"""Add pool_name field to positions table

Revision ID: 005
Revises: 004
Create Date: 2025-01-22

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '005_add_pool_name_to_positions'
down_revision = '004_add_user_pnl_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add pool_name column to positions table."""
    op.add_column('positions', 
        sa.Column('pool_name', sa.String(), nullable=True)
    )


def downgrade() -> None:
    """Remove pool_name column from positions table."""
    op.drop_column('positions', 'pool_name')