"""Add missing user columns

Revision ID: 033_add_missing_user_columns
Revises: 032_drop_non_core_tables
Create Date: 2025-10-07

This migration adds columns that exist in the User model but are missing from production:
- owner_wallet_address
- agent_started_at
- agent_stopped_at
- last_balance_check
- agent_metadata
- unrealized_pnl_usd
- unrealized_pnl_pct
- realized_pnl_usd
- realized_pnl_pct
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '033_add_missing_user_columns'
down_revision = '032_drop_non_core_tables'
branch_labels = None
depends_on = None


def upgrade():
    """Add missing columns to users table."""

    # Get list of existing columns
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('users')]

    # Add owner_wallet_address if missing
    if 'owner_wallet_address' not in existing_columns:
        op.add_column('users', sa.Column('owner_wallet_address', sa.String(42), nullable=True))
        print("✅ Added owner_wallet_address column")

    # Add agent timing columns if missing
    if 'agent_started_at' not in existing_columns:
        op.add_column('users', sa.Column('agent_started_at', sa.DateTime(timezone=True), nullable=True))
        print("✅ Added agent_started_at column")

    if 'agent_stopped_at' not in existing_columns:
        op.add_column('users', sa.Column('agent_stopped_at', sa.DateTime(timezone=True), nullable=True))
        print("✅ Added agent_stopped_at column")

    if 'last_balance_check' not in existing_columns:
        op.add_column('users', sa.Column('last_balance_check', sa.DateTime(timezone=True), nullable=True))
        print("✅ Added last_balance_check column")

    # Add agent_metadata if missing
    if 'agent_metadata' not in existing_columns:
        op.add_column('users', sa.Column('agent_metadata', postgresql.JSONB, nullable=True))
        print("✅ Added agent_metadata column")

    # Add PnL columns if missing
    if 'unrealized_pnl_usd' not in existing_columns:
        op.add_column('users', sa.Column('unrealized_pnl_usd', sa.Numeric(20, 2), nullable=True, server_default='0'))
        print("✅ Added unrealized_pnl_usd column")

    if 'unrealized_pnl_pct' not in existing_columns:
        op.add_column('users', sa.Column('unrealized_pnl_pct', sa.Numeric(10, 4), nullable=True, server_default='0'))
        print("✅ Added unrealized_pnl_pct column")

    if 'realized_pnl_usd' not in existing_columns:
        op.add_column('users', sa.Column('realized_pnl_usd', sa.Numeric(20, 2), nullable=True, server_default='0'))
        print("✅ Added realized_pnl_usd column")

    if 'realized_pnl_pct' not in existing_columns:
        op.add_column('users', sa.Column('realized_pnl_pct', sa.Numeric(10, 4), nullable=True, server_default='0'))
        print("✅ Added realized_pnl_pct column")

    print("✅ All missing user columns added")


def downgrade():
    """Remove the added columns."""
    op.drop_column('users', 'realized_pnl_pct')
    op.drop_column('users', 'realized_pnl_usd')
    op.drop_column('users', 'unrealized_pnl_pct')
    op.drop_column('users', 'unrealized_pnl_usd')
    op.drop_column('users', 'agent_metadata')
    op.drop_column('users', 'last_balance_check')
    op.drop_column('users', 'agent_stopped_at')
    op.drop_column('users', 'agent_started_at')
    op.drop_column('users', 'owner_wallet_address')
