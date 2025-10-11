"""Add per-strategy capital allocation tracking

Revision ID: 038_add_capital_allocation
Revises: 037_add_effective_apr_stable
Create Date: 2025-10-11

This migration adds capital allocation tracking to active_strategies and creates
a strategy_positions table for tracking capital deployment per position.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect, text

revision = '038_add_capital_allocation'
down_revision = '037_add_effective_apr_stable'
branch_labels = None
depends_on = None


def upgrade():
    """Add capital allocation fields and strategy_positions table."""
    conn = op.get_bind()
    inspector = inspect(conn)

    print("🚀 Starting capital allocation migration...")

    # Step 1: Update active_strategies JSONB to add capital tracking fields
    print("📝 Step 1: Updating active_strategies with capital fields...")

    # Add allocated_capital_usd and deployed_capital_usd to each strategy in active_strategies
    # Default: allocated_capital_usd = 1000 (or sum of active positions), deployed_capital_usd = 0
    op.execute("""
        UPDATE users
        SET active_strategies = (
            SELECT jsonb_object_agg(
                key,
                value || jsonb_build_object(
                    'allocated_capital_usd',
                    COALESCE(
                        -- If user has active positions, use their total value
                        (SELECT SUM(entry_amount_usdc)
                         FROM positions
                         WHERE positions.user_id = users.user_id
                           AND positions.status = 'ACTIVE'),
                        1000  -- Default to 1000 if no positions
                    ),
                    'deployed_capital_usd', 0
                )
            )
            FROM jsonb_each(users.active_strategies)
        )
        WHERE active_strategies IS NOT NULL
          AND active_strategies != '{}'::jsonb
          -- Only update if fields don't already exist
          AND NOT EXISTS (
              SELECT 1
              FROM jsonb_each(active_strategies) AS j(key, value)
              WHERE value ? 'allocated_capital_usd'
          );
    """)

    print("✅ Updated active_strategies with capital allocation fields")

    # Step 2: Create strategy_positions tracking table
    print("📝 Step 2: Creating strategy_positions table...")

    # Check if table already exists
    if 'strategy_positions' not in inspector.get_table_names():
        op.create_table(
            'strategy_positions',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('user_id', sa.String(42), sa.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False),
            sa.Column('strategy_code', sa.String(10), nullable=False),
            sa.Column('token_id', sa.Integer, sa.ForeignKey('positions.token_id', ondelete='CASCADE'), nullable=False, unique=True),
            sa.Column('capital_deployed_usd', sa.Numeric(precision=20, scale=6), nullable=False),
            sa.Column('capital_returned_usd', sa.Numeric(precision=20, scale=6), nullable=True),
            sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('tx_hash', sa.String(66), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'))
        )

        # Create indexes for efficient queries
        op.create_index('idx_strategy_positions_user', 'strategy_positions', ['user_id'])
        op.create_index('idx_strategy_positions_user_strategy', 'strategy_positions', ['user_id', 'strategy_code'])
        op.create_index('idx_strategy_positions_token', 'strategy_positions', ['token_id'])
        op.create_index('idx_strategy_positions_tx_hash', 'strategy_positions', ['tx_hash'], unique=True)

        print("✅ Created strategy_positions table with indexes")
    else:
        print("⚠️  strategy_positions table already exists, skipping creation")

    # Step 3: Backfill strategy_positions for existing active positions
    print("📝 Step 3: Backfilling strategy_positions for existing positions...")

    # For each active position, create a strategy_positions record
    # Assumption: All existing positions belong to 'h3' (hedged_blueprint)
    op.execute("""
        INSERT INTO strategy_positions (user_id, strategy_code, token_id, capital_deployed_usd, tx_hash)
        SELECT
            p.user_id,
            'h3' as strategy_code,  -- Default to h3 for existing positions
            p.token_id,
            p.entry_amount_usdc as capital_deployed_usd,
            COALESCE(p.entry_tx_hash, 'migration_038_' || p.token_id::text) as tx_hash
        FROM positions p
        WHERE p.status = 'ACTIVE'
          AND NOT EXISTS (
              SELECT 1 FROM strategy_positions sp
              WHERE sp.token_id = p.token_id
          )
        ON CONFLICT (token_id) DO NOTHING;
    """)

    print("✅ Backfilled strategy_positions for existing active positions")

    # Step 4: Update deployed_capital_usd based on strategy_positions
    print("📝 Step 4: Calculating deployed capital per strategy...")

    op.execute("""
        UPDATE users
        SET active_strategies = (
            SELECT jsonb_object_agg(
                key,
                value || jsonb_build_object(
                    'deployed_capital_usd',
                    COALESCE(
                        (SELECT SUM(sp.capital_deployed_usd)
                         FROM strategy_positions sp
                         WHERE sp.user_id = users.user_id
                           AND sp.strategy_code = key
                           AND sp.closed_at IS NULL),
                        0
                    )
                )
            )
            FROM jsonb_each(users.active_strategies)
        )
        WHERE active_strategies IS NOT NULL
          AND active_strategies != '{}'::jsonb;
    """)

    print("✅ Updated deployed_capital_usd for all strategies")
    print("✅ Migration 038 complete!")


def downgrade():
    """Remove capital allocation tracking."""
    conn = op.get_bind()
    inspector = inspect(conn)

    print("⏮️  Rolling back capital allocation migration...")

    # Drop strategy_positions table
    if 'strategy_positions' in inspector.get_table_names():
        op.drop_index('idx_strategy_positions_tx_hash', 'strategy_positions')
        op.drop_index('idx_strategy_positions_token', 'strategy_positions')
        op.drop_index('idx_strategy_positions_user_strategy', 'strategy_positions')
        op.drop_index('idx_strategy_positions_user', 'strategy_positions')
        op.drop_table('strategy_positions')
        print("✅ Dropped strategy_positions table")

    # Remove capital fields from active_strategies JSONB
    op.execute("""
        UPDATE users
        SET active_strategies = (
            SELECT jsonb_object_agg(
                key,
                value - 'allocated_capital_usd' - 'deployed_capital_usd'
            )
            FROM jsonb_each(users.active_strategies)
        )
        WHERE active_strategies IS NOT NULL
          AND active_strategies != '{}'::jsonb;
    """)

    print("✅ Removed capital fields from active_strategies")
    print("✅ Rollback complete")
