"""Add user_strategies table and multi-strategy support

Revision ID: 035_add_user_strategies
Revises: 034_add_apr_snapshots
Create Date: 2025-10-10

This migration adds support for multiple concurrent strategies per user.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import inspect

revision = '035_add_user_strategies'
down_revision = '034_add_apr_snapshots'
branch_labels = None
depends_on = None


def upgrade():
    """Create user_strategies table and add strategy_id to positions."""
    conn = op.get_bind()
    inspector = inspect(conn)

    # Check if table already exists
    if 'user_strategies' in inspector.get_table_names():
        print("⚠️  user_strategies table already exists, skipping creation")
        return

    # Create strategy type enum
    op.execute("""
        CREATE TYPE IF NOT EXISTS strategy_type_enum AS ENUM (
            'hedged_weth_only',
            'hedged_cbbtc_only',
            'hedged_blueprint',
            'nonhedged_weth_only',
            'nonhedged_cbbtc_only',
            'nonhedged_blueprint',
            'stable_usdc_eurc',
            'stable_usdc_brz'
        )
    """)

    # Create strategy status enum
    op.execute("""
        CREATE TYPE IF NOT EXISTS strategy_status_enum AS ENUM (
            'active',
            'paused',
            'closed'
        )
    """)

    # Create user_strategies table
    op.create_table(
        'user_strategies',
        sa.Column('strategy_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.String(42), sa.ForeignKey('users.user_id'), nullable=False),
        sa.Column('strategy_type', postgresql.ENUM(
            'hedged_weth_only',
            'hedged_cbbtc_only',
            'hedged_blueprint',
            'nonhedged_weth_only',
            'nonhedged_cbbtc_only',
            'nonhedged_blueprint',
            'stable_usdc_eurc',
            'stable_usdc_brz',
            name='strategy_type_enum',
            create_type=False
        ), nullable=False),
        sa.Column('status', postgresql.ENUM(
            'active',
            'paused',
            'closed',
            name='strategy_status_enum',
            create_type=False
        ), nullable=False, server_default='active'),
        sa.Column('capital_allocated_usdc', sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'))
    )

    # Create indexes on user_strategies
    op.create_index('idx_user_strategies_user_id', 'user_strategies', ['user_id'])
    op.create_index('idx_user_strategies_status', 'user_strategies', ['status'])
    op.create_index('idx_user_strategies_user_status', 'user_strategies', ['user_id', 'status'])

    # Add strategy_id column to positions (nullable for backward compatibility)
    op.add_column('positions', sa.Column('strategy_id', postgresql.UUID(as_uuid=True), nullable=True))

    # Create foreign key constraint
    op.create_foreign_key(
        'fk_positions_strategy_id',
        'positions',
        'user_strategies',
        ['strategy_id'],
        ['strategy_id'],
        ondelete='SET NULL'
    )

    # Create index on positions.strategy_id
    op.create_index('idx_positions_strategy_id', 'positions', ['strategy_id'])

    # Create default strategies for users with existing positions
    op.execute("""
        INSERT INTO user_strategies (user_id, strategy_type, status, capital_allocated_usdc)
        SELECT DISTINCT
            p.user_id,
            'hedged_blueprint'::strategy_type_enum,
            'active'::strategy_status_enum,
            COALESCE(SUM(p.entry_amount_usdc), 0)
        FROM positions p
        WHERE p.status = 'ACTIVE'
        GROUP BY p.user_id
        HAVING COUNT(*) > 0
    """)

    # Link existing active positions to their user's default strategy
    op.execute("""
        UPDATE positions p
        SET strategy_id = us.strategy_id
        FROM user_strategies us
        WHERE p.user_id = us.user_id
            AND us.strategy_type = 'hedged_blueprint'
            AND p.status = 'ACTIVE'
            AND p.strategy_id IS NULL
    """)

    print("✅ Created user_strategies table with indexes")
    print("✅ Added strategy_id to positions table")
    print("✅ Created default strategies for users with existing positions")


def downgrade():
    """Drop user_strategies table and remove strategy_id from positions."""
    # Drop foreign key and column from positions
    op.drop_constraint('fk_positions_strategy_id', 'positions', type_='foreignkey')
    op.drop_index('idx_positions_strategy_id')
    op.drop_column('positions', 'strategy_id')

    # Drop indexes and table
    op.drop_index('idx_user_strategies_user_status')
    op.drop_index('idx_user_strategies_status')
    op.drop_index('idx_user_strategies_user_id')
    op.drop_table('user_strategies')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS strategy_type_enum')
    op.execute('DROP TYPE IF EXISTS strategy_status_enum')

    print("✅ Dropped user_strategies table and related objects")
