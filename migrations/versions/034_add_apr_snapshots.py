"""Add APR snapshots table

Revision ID: 034_add_apr_snapshots
Revises: 033_add_missing_user_columns
Create Date: 2025-10-09

This migration adds a table to capture historical APR snapshots from whitelisted pools.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '034_add_apr_snapshots'
down_revision = '033_add_missing_user_columns'
branch_labels = None
depends_on = None


def upgrade():
    """Create apr_snapshots table."""
    op.create_table(
        'apr_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('pool_address', sa.String(42), nullable=False, index=True),
        sa.Column('pool_symbol', sa.String(50), nullable=True),
        sa.Column('apr', sa.Numeric(10, 4), nullable=False),
        sa.Column('effective_apr_narrow', sa.Numeric(10, 4), nullable=True),
        sa.Column('effective_apr_standard', sa.Numeric(10, 4), nullable=True),
        sa.Column('effective_apr_wide', sa.Numeric(10, 4), nullable=True),
        sa.Column('tvl_usd', sa.Numeric(20, 2), nullable=True),
        sa.Column('volume_24h', sa.Numeric(20, 2), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'), index=True),
        sa.Column('pool_metadata', postgresql.JSONB, nullable=True),
    )

    # Create composite index for efficient queries by pool and time range
    op.create_index(
        'idx_apr_snapshots_pool_timestamp',
        'apr_snapshots',
        ['pool_address', 'timestamp']
    )

    print("✅ Created apr_snapshots table with indexes")


def downgrade():
    """Drop apr_snapshots table."""
    op.drop_index('idx_apr_snapshots_pool_timestamp')
    op.drop_table('apr_snapshots')
