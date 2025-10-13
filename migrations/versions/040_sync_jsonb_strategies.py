"""Sync JSONB active_strategies to user_strategies relational table

Revision ID: 040_sync_jsonb_to_user_strategies
Revises: 039_add_missing_strategy_columns
Create Date: 2025-10-13

This migration synchronizes data from users.active_strategies JSONB column
to the user_strategies relational table, making the table the source of truth.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import text

revision = '040_sync_jsonb_strategies'
down_revision = '039_add_missing_strategy_columns'
branch_labels = None
depends_on = None


# Mapping from strategy short codes to full types
STRATEGY_CODE_TO_TYPE = {
    "h1": "hedged_weth_only",
    "h2": "hedged_cbbtc_only",
    "n1": "nonhedged_weth_only",
    "n2": "nonhedged_cbbtc_only",
    "n3": "nonhedged_cbltc_cbbtc",
    "n4": "nonhedged_cbada_cbbtc",
    "n5": "nonhedged_cbxrp_cbbtc",
    "n6": "nonhedged_cbdoge_cbbtc",
    "s1": "stable_usdc_eurc",
    "s2": "stable_usdc_msusd",
}


def upgrade():
    """Sync JSONB active_strategies to user_strategies table."""
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)

    print("🔄 Starting JSONB to relational table sync...")

    # Check if user_strategies table exists
    if 'user_strategies' not in inspector.get_table_names():
        print("⚠️  user_strategies table does not exist, creating it now...")

        # Ensure enums exist
        conn.execute(text("""
            DO $$ BEGIN
                CREATE TYPE strategy_type_enum AS ENUM (
                    'hedged_weth_only',
                    'hedged_cbbtc_only',
                    'hedged_blueprint',
                    'nonhedged_weth_only',
                    'nonhedged_cbbtc_only',
                    'nonhedged_blueprint',
                    'nonhedged_cbltc_cbbtc',
                    'nonhedged_cbada_cbbtc',
                    'nonhedged_cbxrp_cbbtc',
                    'nonhedged_cbdoge_cbbtc',
                    'stable_usdc_eurc',
                    'stable_usdc_brz',
                    'stable_usdc_msusd'
                );
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """))

        conn.execute(text("""
            DO $$ BEGIN
                CREATE TYPE strategy_status_enum AS ENUM (
                    'active',
                    'paused',
                    'closed'
                );
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """))

        # Create the table
        op.create_table(
            'user_strategies',
            sa.Column('strategy_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('user_id', sa.String(42), sa.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False),
            sa.Column('strategy_type', postgresql.ENUM(
                'hedged_weth_only',
                'hedged_cbbtc_only',
                'hedged_blueprint',
                'nonhedged_weth_only',
                'nonhedged_cbbtc_only',
                'nonhedged_blueprint',
                'nonhedged_cbltc_cbbtc',
                'nonhedged_cbada_cbbtc',
                'nonhedged_cbxrp_cbbtc',
                'nonhedged_cbdoge_cbbtc',
                'stable_usdc_eurc',
                'stable_usdc_brz',
                'stable_usdc_msusd',
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
            sa.Column('allocated_capital_usd', sa.Numeric(precision=20, scale=6), nullable=False, default=0),
            sa.Column('deployed_capital_usd', sa.Numeric(precision=20, scale=6), nullable=False, default=0),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'))
        )

        # Create indexes
        op.create_index('idx_user_strategies_user_id', 'user_strategies', ['user_id'])
        op.create_index('idx_user_strategies_status', 'user_strategies', ['status'])
        op.create_index('idx_user_strategies_user_status', 'user_strategies', ['user_id', 'status'])

        print("✅ Created user_strategies table with indexes")

    # Get all users with active_strategies in JSONB
    result = conn.execute(text("""
        SELECT user_id, active_strategies
        FROM users
        WHERE active_strategies IS NOT NULL
          AND active_strategies != '{}'::jsonb
    """))

    users_with_strategies = result.fetchall()
    print(f"Found {len(users_with_strategies)} users with active_strategies in JSONB")

    synced_count = 0
    skipped_count = 0
    error_count = 0

    for user_id, active_strategies_json in users_with_strategies:
        if not active_strategies_json:
            continue

        # Parse JSONB (it comes as a dict from SQLAlchemy)
        active_strategies = active_strategies_json

        for strategy_code, strategy_info in active_strategies.items():
            # Convert short code to full type
            strategy_type = STRATEGY_CODE_TO_TYPE.get(strategy_code)

            if not strategy_type:
                print(f"⚠️  Unknown strategy code '{strategy_code}' for user {user_id}, skipping")
                skipped_count += 1
                continue

            # Extract values with defaults
            allocated_capital = float(strategy_info.get('allocated_capital_usd', 0))
            deployed_capital = float(strategy_info.get('deployed_capital_usd', 0))
            status = strategy_info.get('status', 'active')
            created_at = strategy_info.get('created_at')
            updated_at = strategy_info.get('updated_at')

            # Check if strategy already exists
            check_result = conn.execute(text("""
                SELECT strategy_id FROM user_strategies
                WHERE user_id = :user_id AND strategy_type = :strategy_type
            """), {"user_id": user_id, "strategy_type": strategy_type})

            existing = check_result.fetchone()

            if existing:
                # Update existing strategy
                try:
                    conn.execute(text("""
                        UPDATE user_strategies
                        SET status = :status,
                            allocated_capital_usd = :allocated_capital,
                            deployed_capital_usd = :deployed_capital,
                            updated_at = COALESCE(:updated_at::timestamp, updated_at)
                        WHERE user_id = :user_id AND strategy_type = :strategy_type
                    """), {
                        "user_id": user_id,
                        "strategy_type": strategy_type,
                        "status": status,
                        "allocated_capital": allocated_capital,
                        "deployed_capital": deployed_capital,
                        "updated_at": updated_at
                    })
                    print(f"✅ Updated strategy {strategy_code} for user {user_id}")
                    synced_count += 1
                except Exception as e:
                    print(f"❌ Error updating strategy {strategy_code} for user {user_id}: {e}")
                    error_count += 1
            else:
                # Insert new strategy
                try:
                    # Use raw SQL without type casts to avoid parameter mixing issues
                    conn.execute(text("""
                        INSERT INTO user_strategies (
                            user_id, strategy_type, status,
                            allocated_capital_usd, deployed_capital_usd,
                            created_at, updated_at
                        ) VALUES (
                            :user_id,
                            CAST(:strategy_type AS strategy_type_enum),
                            CAST(:status AS strategy_status_enum),
                            :allocated_capital,
                            :deployed_capital,
                            COALESCE(CAST(:created_at AS timestamp with time zone), CURRENT_TIMESTAMP),
                            COALESCE(CAST(:updated_at AS timestamp with time zone), CURRENT_TIMESTAMP)
                        )
                    """), {
                        "user_id": user_id,
                        "strategy_type": strategy_type,
                        "status": status,
                        "allocated_capital": allocated_capital,
                        "deployed_capital": deployed_capital,
                        "created_at": created_at,
                        "updated_at": updated_at
                    })
                    print(f"✅ Inserted strategy {strategy_code} for user {user_id}")
                    synced_count += 1
                except Exception as e:
                    print(f"❌ Error inserting strategy {strategy_code} for user {user_id}: {e}")
                    error_count += 1

    print(f"\n📊 Migration complete:")
    print(f"   - Synced: {synced_count}")
    print(f"   - Skipped: {skipped_count}")
    print(f"   - Errors: {error_count}")


def downgrade():
    """
    Reverse sync: copy user_strategies back to JSONB.

    This is a safety measure but shouldn't normally be needed.
    """
    conn = op.get_bind()

    print("⏪ Reversing sync: user_strategies -> JSONB...")

    # Build JSONB from user_strategies table
    conn.execute(text("""
        UPDATE users
        SET active_strategies = (
            SELECT jsonb_object_agg(
                CASE strategy_type
                    WHEN 'hedged_weth_only' THEN 'h1'
                    WHEN 'hedged_cbbtc_only' THEN 'h2'
                    WHEN 'nonhedged_weth_only' THEN 'n1'
                    WHEN 'nonhedged_cbbtc_only' THEN 'n2'
                    WHEN 'nonhedged_cbltc_cbbtc' THEN 'n3'
                    WHEN 'nonhedged_cbada_cbbtc' THEN 'n4'
                    WHEN 'nonhedged_cbxrp_cbbtc' THEN 'n5'
                    WHEN 'nonhedged_cbdoge_cbbtc' THEN 'n6'
                    WHEN 'stable_usdc_eurc' THEN 's1'
                    WHEN 'stable_usdc_msusd' THEN 's2'
                    ELSE strategy_type::text
                END,
                jsonb_build_object(
                    'strategy_type', strategy_type::text,
                    'status', status::text,
                    'allocated_capital_usd', allocated_capital_usd::float,
                    'deployed_capital_usd', deployed_capital_usd::float,
                    'created_at', created_at::text,
                    'updated_at', updated_at::text
                )
            )
            FROM user_strategies
            WHERE user_strategies.user_id = users.user_id
              AND user_strategies.status = 'active'
        )
        WHERE EXISTS (
            SELECT 1 FROM user_strategies
            WHERE user_strategies.user_id = users.user_id
        )
    """))

    print("✅ Reversed sync complete")
