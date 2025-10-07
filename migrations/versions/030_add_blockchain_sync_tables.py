"""Add blockchain sync tables for CDP SQL API data

Revision ID: 030_add_blockchain_sync_tables
Revises: 029_consolidate_transactions
Create Date: 2025-01-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '030_add_blockchain_sync_tables'
down_revision = '029_consolidate_transactions'
branch_labels = None
depends_on = None

def upgrade():
    """Add tables for blockchain data synchronization."""
    
    # Create blockchain_sync table
    op.create_table('blockchain_sync',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sync_type', sa.String(50), nullable=False),
        sa.Column('last_block_number', sa.Integer(), nullable=True),
        sa.Column('last_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sync_status', sa.String(20), nullable=True),
        sa.Column('last_error', sa.String(500), nullable=True),
        sa.Column('error_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sync_type')
    )
    op.create_index('idx_blockchain_sync_type', 'blockchain_sync', ['sync_type'])
    op.create_index('idx_blockchain_sync_status', 'blockchain_sync', ['sync_status'])
    
    # Create wallet_transactions table
    op.create_table('wallet_transactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('transaction_hash', sa.String(66), nullable=False),
        sa.Column('block_number', sa.Integer(), nullable=False),
        sa.Column('from_address', sa.String(42), nullable=False),
        sa.Column('to_address', sa.String(42), nullable=True),
        sa.Column('value', sa.String(78), nullable=True),
        sa.Column('gas', sa.Integer(), nullable=True),
        sa.Column('gas_price', sa.Integer(), nullable=True),
        sa.Column('gas_cost_eth', sa.Numeric(precision=20, scale=18), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_agent_wallet', sa.Boolean(), nullable=True),
        sa.Column('user_id', sa.String(42), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('transaction_hash')
    )
    op.create_index('idx_wallet_tx_hash', 'wallet_transactions', ['transaction_hash'])
    op.create_index('idx_wallet_tx_block', 'wallet_transactions', ['block_number'])
    op.create_index('idx_wallet_tx_from', 'wallet_transactions', ['from_address'])
    op.create_index('idx_wallet_tx_to', 'wallet_transactions', ['to_address'])
    op.create_index('idx_wallet_tx_addresses', 'wallet_transactions', ['from_address', 'to_address'])
    op.create_index('idx_wallet_tx_timestamp', 'wallet_transactions', ['timestamp'])
    op.create_index('idx_wallet_tx_user', 'wallet_transactions', ['user_id'])
    
    # Create liquidity_events table
    op.create_table('liquidity_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('transaction_hash', sa.String(66), nullable=False),
        sa.Column('block_number', sa.Integer(), nullable=False),
        sa.Column('log_index', sa.Integer(), nullable=False),
        sa.Column('event_signature', sa.String(255), nullable=False),
        sa.Column('event_name', sa.String(100), nullable=True),
        sa.Column('contract_address', sa.String(42), nullable=False),
        sa.Column('parameters', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('topics', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('token_id', sa.Integer(), nullable=True),
        sa.Column('owner_address', sa.String(42), nullable=True),
        sa.Column('pool_address', sa.String(42), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('position_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.String(42), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_liquidity_event_unique', 'liquidity_events', ['transaction_hash', 'log_index'], unique=True)
    op.create_index('idx_liquidity_event_hash', 'liquidity_events', ['transaction_hash'])
    op.create_index('idx_liquidity_event_block', 'liquidity_events', ['block_number'])
    op.create_index('idx_liquidity_event_signature', 'liquidity_events', ['event_signature'])
    op.create_index('idx_liquidity_event_contract', 'liquidity_events', ['contract_address'])
    op.create_index('idx_liquidity_event_token', 'liquidity_events', ['token_id'])
    op.create_index('idx_liquidity_event_owner', 'liquidity_events', ['owner_address'])
    op.create_index('idx_liquidity_event_timestamp', 'liquidity_events', ['timestamp'])

def downgrade():
    """Remove blockchain sync tables."""
    op.drop_table('liquidity_events')
    op.drop_table('wallet_transactions')
    op.drop_table('blockchain_sync')