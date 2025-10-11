"""Add effective_apr_stable column

Revision ID: 037_add_effective_apr_stable
Revises: 034_add_apr_snapshots
Create Date: 2025-10-11

This migration adds effective_apr_stable column to apr_snapshots table.
"""

from alembic import op
import sqlalchemy as sa

revision = '037_add_effective_apr_stable'
down_revision = '034_add_apr_snapshots'
branch_labels = None
depends_on = None


def upgrade():
    """Add effective_apr_stable column."""
    op.add_column(
        'apr_snapshots',
        sa.Column('effective_apr_stable', sa.Numeric(10, 4), nullable=True)
    )
    print("✅ Added effective_apr_stable column to apr_snapshots table")


def downgrade():
    """Remove effective_apr_stable column."""
    op.drop_column('apr_snapshots', 'effective_apr_stable')
