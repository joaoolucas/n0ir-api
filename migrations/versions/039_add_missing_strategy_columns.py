"""Add missing strategy columns to users, transactions, and positions

Revision ID: 039_add_missing_strategy_columns
Revises: 037_add_effective_apr_stable
Create Date: 2025-10-12

This migration adds:
- active_strategies column to users table
- strategy_type column to transactions table
- strategy_type column to positions table (with indexes)
These columns are required by the code but missing in production.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

revision = '039_add_missing_strategy_columns'
down_revision = '037_add_effective_apr_stable'
branch_labels = None
depends_on = None


def upgrade():
    """Add missing strategy columns."""
    conn = op.get_bind()
    inspector = inspect(conn)

    print("🚀 Starting migration 039: Adding missing strategy columns...")

    # Step 1: Add active_strategies column to users table if it doesn't exist
    print("📝 Step 1: Checking users.active_strategies column...")
    users_columns = [col['name'] for col in inspector.get_columns('users')]

    if 'active_strategies' not in users_columns:
        print("➕ Adding users.active_strategies column...")
        op.add_column('users', sa.Column('active_strategies', postgresql.JSONB, nullable=True))
        print("✅ Added users.active_strategies column")
    else:
        print("⚠️  users.active_strategies column already exists, skipping")

    # Step 2: Add strategy_type column to transactions table if it doesn't exist
    print("📝 Step 2: Checking transactions.strategy_type column...")
    transactions_columns = [col['name'] for col in inspector.get_columns('transactions')]

    if 'strategy_type' not in transactions_columns:
        print("➕ Adding transactions.strategy_type column...")
        op.add_column('transactions', sa.Column('strategy_type', sa.String(50), nullable=True))
        print("✅ Added transactions.strategy_type column")
    else:
        print("⚠️  transactions.strategy_type column already exists, skipping")

    # Step 3: Add strategy_type column to positions table if it doesn't exist
    print("📝 Step 3: Checking positions.strategy_type column...")
    positions_columns = [col['name'] for col in inspector.get_columns('positions')]

    if 'strategy_type' not in positions_columns:
        print("➕ Adding positions.strategy_type column...")
        op.add_column('positions', sa.Column('strategy_type', sa.String(50), nullable=True))

        # Check if indexes already exist before creating them
        existing_indexes = [idx['name'] for idx in inspector.get_indexes('positions')]

        if 'idx_positions_strategy_type' not in existing_indexes:
            op.create_index('idx_positions_strategy_type', 'positions', ['strategy_type'], unique=False)
            print("✅ Created index idx_positions_strategy_type")

        if 'idx_positions_user_strategy' not in existing_indexes:
            op.create_index('idx_positions_user_strategy', 'positions', ['user_id', 'strategy_type'], unique=False)
            print("✅ Created index idx_positions_user_strategy")

        print("✅ Added positions.strategy_type column")
    else:
        print("⚠️  positions.strategy_type column already exists, skipping")

    print("✅ Migration 039 complete!")


def downgrade():
    """Remove strategy columns."""
    conn = op.get_bind()
    inspector = inspect(conn)

    print("⏮️  Rolling back migration 039...")

    # Remove strategy_type from positions
    positions_columns = [col['name'] for col in inspector.get_columns('positions')]
    if 'strategy_type' in positions_columns:
        op.drop_index('idx_positions_user_strategy', table_name='positions')
        op.drop_index('idx_positions_strategy_type', table_name='positions')
        op.drop_column('positions', 'strategy_type')
        print("✅ Dropped positions.strategy_type column")

    # Remove strategy_type from transactions
    transactions_columns = [col['name'] for col in inspector.get_columns('transactions')]
    if 'strategy_type' in transactions_columns:
        op.drop_column('transactions', 'strategy_type')
        print("✅ Dropped transactions.strategy_type column")

    # Remove active_strategies from users
    users_columns = [col['name'] for col in inspector.get_columns('users')]
    if 'active_strategies' in users_columns:
        op.drop_column('users', 'active_strategies')
        print("✅ Dropped users.active_strategies column")

    print("✅ Rollback complete")
