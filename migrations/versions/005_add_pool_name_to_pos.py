"""Add pool_name field to positions table

Revision ID: 005
Revises: 004
Create Date: 2025-01-22

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '005_add_pool_name_to_pos'
down_revision = '004_add_user_pnl_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add pool_name column to positions table."""
    # Check if column already exists
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('positions')]

    if 'pool_name' not in columns:
        op.add_column('positions',
            sa.Column('pool_name', sa.String(), nullable=True)
        )


def downgrade() -> None:
    """Remove pool_name column from positions table."""
    op.drop_column('positions', 'pool_name')