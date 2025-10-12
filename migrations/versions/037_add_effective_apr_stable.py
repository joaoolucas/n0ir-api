"""Add effective_apr_stable column

Revision ID: 037_add_effective_apr_stable
Revises: 035_add_user_strategies
Create Date: 2025-10-11

This migration adds effective_apr_stable column to apr_snapshots table.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '037_add_effective_apr_stable'
down_revision = '035_add_user_strategies'
branch_labels = None
depends_on = None


def upgrade():
    """Add effective_apr_stable column."""
    conn = op.get_bind()
    inspector = inspect(conn)

    # Check if column already exists
    columns = [col['name'] for col in inspector.get_columns('apr_snapshots')]

    if 'effective_apr_stable' not in columns:
        op.add_column(
            'apr_snapshots',
            sa.Column('effective_apr_stable', sa.Numeric(10, 4), nullable=True)
        )
        print("✅ Added effective_apr_stable column to apr_snapshots table")
    else:
        print("⚠️  effective_apr_stable column already exists, skipping")


def downgrade():
    """Remove effective_apr_stable column."""
    op.drop_column('apr_snapshots', 'effective_apr_stable')
