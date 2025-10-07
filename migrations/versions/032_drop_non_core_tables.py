"""Drop non-core tables to simplify schema

Revision ID: 032_drop_non_core_tables
Revises: 031_cleanup_redundant_fields
Create Date: 2024-01-16

This migration removes all non-essential tables, keeping only:
- users (core user data)
- positions (liquidity positions)
- transactions (all events)

Tables being dropped:
- daily_metrics (analytics - can be calculated on demand)
- pool_metrics (analytics - can be fetched from pools service)
- executor_stats (monitoring - not essential)
- blockchain_sync (sync status - can use metadata instead)
- wallet_transactions (CDP sync - redundant with transactions)
- liquidity_events (CDP sync - redundant with transactions)
- strategy_decisions (AI logs - can use external logging)
"""

from alembic import op
import sqlalchemy as sa

revision = '032_drop_non_core_tables'
down_revision = '031_cleanup_redundant_fields'
branch_labels = None
depends_on = None


def upgrade():
    """Drop all non-core tables."""
    
    # Drop tables in order (considering foreign key constraints)
    op.drop_table('strategy_decisions')
    op.drop_table('executor_stats')
    op.drop_table('pool_metrics')
    op.drop_table('daily_metrics')
    op.drop_table('liquidity_events')
    op.drop_table('wallet_transactions')
    op.drop_table('blockchain_sync')
    
    print("✅ Dropped 7 non-core tables")
    print("✅ Schema simplified to 3 core tables: users, positions, transactions")


def downgrade():
    """Recreate dropped tables."""
    
    # Recreate blockchain_sync
    op.create_table('blockchain_sync',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('sync_type', sa.String(50), nullable=False),
        sa.Column('user_id', sa.String(42), nullable=True),
        sa.Column('wallet_address', sa.String(42), nullable=True),
        sa.Column('last_synced_block', sa.BigInteger(), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sync_status', sa.String(20), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Recreate wallet_transactions
    op.create_table('wallet_transactions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('transaction_hash', sa.String(66), nullable=False),
        sa.Column('block_number', sa.BigInteger(), nullable=False),
        sa.Column('from_address', sa.String(42), nullable=False),
        sa.Column('to_address', sa.String(42), nullable=True),
        sa.Column('value', sa.String(78), nullable=True),
        sa.Column('gas', sa.BigInteger(), nullable=True),
        sa.Column('gas_price', sa.BigInteger(), nullable=True),
        sa.Column('gas_cost_eth', sa.Numeric(20, 10), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_agent_wallet', sa.Boolean(), nullable=True),
        sa.Column('user_id', sa.String(42), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('transaction_hash')
    )
    
    # Recreate liquidity_events
    op.create_table('liquidity_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('transaction_hash', sa.String(66), nullable=False),
        sa.Column('block_number', sa.BigInteger(), nullable=False),
        sa.Column('log_index', sa.Integer(), nullable=False),
        sa.Column('event_signature', sa.String(255), nullable=False),
        sa.Column('event_name', sa.String(100), nullable=True),
        sa.Column('owner_address', sa.String(42), nullable=True),
        sa.Column('token_id', sa.BigInteger(), nullable=True),
        sa.Column('tick_lower', sa.Integer(), nullable=True),
        sa.Column('tick_upper', sa.Integer(), nullable=True),
        sa.Column('liquidity', sa.String(78), nullable=True),
        sa.Column('amount0', sa.String(78), nullable=True),
        sa.Column('amount1', sa.String(78), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('user_id', sa.String(42), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('transaction_hash', 'log_index')
    )
    
    # Recreate daily_metrics
    op.create_table('daily_metrics',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('user_id', sa.String(42), nullable=False),
        sa.Column('portfolio_value_usd', sa.Numeric(20, 2), nullable=True),
        sa.Column('daily_pnl_usd', sa.Numeric(20, 2), nullable=True),
        sa.Column('daily_pnl_pct', sa.Numeric(10, 4), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('date', 'user_id')
    )
    
    # Recreate pool_metrics
    op.create_table('pool_metrics',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('pool_address', sa.String(42), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('tvl_usd', sa.Numeric(20, 2), nullable=True),
        sa.Column('volume_24h_usd', sa.Numeric(20, 2), nullable=True),
        sa.Column('apr', sa.Numeric(10, 4), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Recreate executor_stats
    op.create_table('executor_stats',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('executor_id', sa.String(100), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('success_count', sa.Integer(), nullable=True),
        sa.Column('failure_count', sa.Integer(), nullable=True),
        sa.Column('gas_used', sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Recreate strategy_decisions
    op.create_table('strategy_decisions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.String(42), nullable=False),
        sa.Column('decision_type', sa.String(50), nullable=False),
        sa.Column('decision_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )