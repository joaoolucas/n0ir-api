"""Refactor to hybrid strategy approach

Revision ID: 036_refactor_to_hybrid_strategy
Revises: 035_add_user_strategies
Create Date: 2025-10-10 16:00:00.000000

Changes:
- Add active_strategies JSONB column to users table
- Add strategy_type VARCHAR(50) column to positions table
- Add strategy_type VARCHAR(50) column to transactions table
- Migrate data from user_strategies to users.active_strategies
- Migrate positions.strategy_id to positions.strategy_type
- Drop user_strategies table and related enums

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect, text
from loguru import logger

# revision identifiers, used by Alembic.
revision = '036_refactor_to_hybrid_strategy'
down_revision = '035_add_user_strategies'
branch_labels = None
depends_on = None


def upgrade():
    """Refactor to hybrid strategy approach."""
    conn = op.get_bind()
    inspector = inspect(conn)

    # Step 1: Add active_strategies JSONB column to users table
    logger.info("Adding active_strategies column to users table...")
    columns = [col['name'] for col in inspector.get_columns('users')]
    if 'active_strategies' not in columns:
        op.add_column('users', sa.Column('active_strategies', postgresql.JSONB(), nullable=True))
        logger.info("✓ Added active_strategies column")
    else:
        logger.info("✓ active_strategies column already exists")

    # Step 2: Add strategy_type column to positions table
    logger.info("Adding strategy_type column to positions table...")
    positions_columns = [col['name'] for col in inspector.get_columns('positions')]
    if 'strategy_type' not in positions_columns:
        op.add_column('positions', sa.Column('strategy_type', sa.String(50), nullable=True))
        logger.info("✓ Added strategy_type column to positions")
    else:
        logger.info("✓ strategy_type column already exists in positions")

    # Step 3: Add strategy_type column to transactions table
    logger.info("Adding strategy_type column to transactions table...")
    transactions_columns = [col['name'] for col in inspector.get_columns('transactions')]
    if 'strategy_type' not in transactions_columns:
        op.add_column('transactions', sa.Column('strategy_type', sa.String(50), nullable=True))
        logger.info("✓ Added strategy_type column to transactions")
    else:
        logger.info("✓ strategy_type column already exists in transactions")

    # Step 4: Migrate data from user_strategies to users.active_strategies
    logger.info("Migrating data from user_strategies to users.active_strategies...")
    if 'user_strategies' in inspector.get_table_names():
        # Build active_strategies JSONB from user_strategies table
        conn.execute(text("""
            UPDATE users u
            SET active_strategies = (
                SELECT jsonb_object_agg(
                    s.strategy_type::text,
                    jsonb_build_object(
                        'strategy_type', s.strategy_type::text,
                        'capital_allocated_usdc', s.capital_allocated_usdc,
                        'status', s.status::text,
                        'created_at', s.created_at::text,
                        'updated_at', s.updated_at::text
                    )
                )
                FROM user_strategies s
                WHERE s.user_id = u.user_id
                GROUP BY s.user_id
            )
            WHERE EXISTS (
                SELECT 1 FROM user_strategies s WHERE s.user_id = u.user_id
            )
        """))
        logger.info("✓ Migrated user_strategies data to active_strategies")
    else:
        logger.info("✓ user_strategies table does not exist, skipping data migration")

    # Step 5: Migrate positions.strategy_id to positions.strategy_type
    logger.info("Migrating positions.strategy_id to positions.strategy_type...")
    if 'strategy_id' in positions_columns and 'user_strategies' in inspector.get_table_names():
        conn.execute(text("""
            UPDATE positions p
            SET strategy_type = s.strategy_type::text
            FROM user_strategies s
            WHERE p.strategy_id = s.strategy_id
            AND p.strategy_id IS NOT NULL
        """))
        logger.info("✓ Migrated positions.strategy_id to strategy_type")
    else:
        logger.info("✓ strategy_id column does not exist or already migrated")

    # Step 6: Drop strategy_id column from positions
    if 'strategy_id' in positions_columns:
        logger.info("Dropping strategy_id column from positions...")
        # Drop foreign key constraint first
        fks = inspector.get_foreign_keys('positions')
        for fk in fks:
            if 'strategy_id' in fk['constrained_columns']:
                logger.info(f"Dropping foreign key: {fk['name']}")
                op.drop_constraint(fk['name'], 'positions', type_='foreignkey')

        # Drop the column
        op.drop_column('positions', 'strategy_id')
        logger.info("✓ Dropped strategy_id column")
    else:
        logger.info("✓ strategy_id column already dropped")

    # Step 7: Drop user_strategies table
    if 'user_strategies' in inspector.get_table_names():
        logger.info("Dropping user_strategies table...")
        op.drop_table('user_strategies')
        logger.info("✓ Dropped user_strategies table")
    else:
        logger.info("✓ user_strategies table already dropped")

    # Step 8: Drop enum types if they exist
    logger.info("Dropping strategy enum types...")
    conn.execute(text("""
        DO $$ BEGIN
            DROP TYPE IF EXISTS strategy_type_enum CASCADE;
            DROP TYPE IF EXISTS strategy_status_enum CASCADE;
        EXCEPTION
            WHEN undefined_object THEN NULL;
        END $$;
    """))
    logger.info("✓ Dropped strategy enum types")

    logger.info("✅ Migration 036 completed successfully")


def downgrade():
    """Revert to separate user_strategies table."""
    conn = op.get_bind()

    # Recreate enum types
    conn.execute(text("""
        DO $$ BEGIN
            CREATE TYPE strategy_type_enum AS ENUM (
                'hedged_weth_only',
                'hedged_cbbtc_only',
                'hedged_blueprint',
                'nonhedged_weth_only',
                'nonhedged_cbbtc_only',
                'nonhedged_blueprint',
                'stable_usdc_eurc',
                'stable_usdc_brz'
            );
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
    """))

    conn.execute(text("""
        DO $$ BEGIN
            CREATE TYPE strategy_status_enum AS ENUM ('active', 'paused', 'closed');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
    """))

    # Recreate user_strategies table
    op.create_table(
        'user_strategies',
        sa.Column('strategy_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.String(42), nullable=False),
        sa.Column('strategy_type', postgresql.ENUM(name='strategy_type_enum', create_type=False), nullable=False),
        sa.Column('status', postgresql.ENUM(name='strategy_status_enum', create_type=False), nullable=False),
        sa.Column('capital_allocated_usdc', sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('strategy_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'])
    )

    # Migrate data back from users.active_strategies to user_strategies
    # This is lossy - we can't reconstruct UUIDs, so generate new ones
    conn.execute(text("""
        INSERT INTO user_strategies (strategy_id, user_id, strategy_type, status, capital_allocated_usdc, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            u.user_id,
            (value->>'strategy_type')::strategy_type_enum,
            (value->>'status')::strategy_status_enum,
            (value->>'capital_allocated_usdc')::numeric,
            (value->>'created_at')::timestamptz,
            (value->>'updated_at')::timestamptz
        FROM users u,
        jsonb_each(u.active_strategies) AS strategies(key, value)
        WHERE u.active_strategies IS NOT NULL
    """))

    # Add strategy_id column back to positions
    op.add_column('positions', sa.Column('strategy_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_positions_strategy_id_user_strategies', 'positions', 'user_strategies', ['strategy_id'], ['strategy_id'])

    # Drop new columns
    op.drop_column('transactions', 'strategy_type')
    op.drop_column('positions', 'strategy_type')
    op.drop_column('users', 'active_strategies')
