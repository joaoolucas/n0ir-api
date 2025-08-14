"""Initial database schema

Revision ID: 001
Revises: 
Create Date: 2024-08-14 12:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table('users',
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('wallet_address', sa.String(), nullable=False),
        sa.Column('cdp_wallet_name', sa.String(), nullable=False),
        sa.Column('cdp_owner_wallet_address', sa.String(), nullable=False),
        sa.Column('cdp_owner_wallet_name', sa.String(), nullable=False),
        sa.Column('status', sa.Enum('ACTIVE', 'SUSPENDED', 'CLOSED', name='userstatus'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('user_id')
    )
    op.create_index('idx_user_cdp_owner', 'users', ['cdp_owner_wallet_address'], unique=False)
    op.create_index('idx_user_created_at', 'users', ['created_at'], unique=False)
    op.create_index('idx_user_status', 'users', ['status'], unique=False)
    op.create_index(op.f('ix_users_user_id'), 'users', ['user_id'], unique=False)
    op.create_index(op.f('ix_users_wallet_address'), 'users', ['wallet_address'], unique=True)

    # Create transactions table
    op.create_table('transactions',
        sa.Column('transaction_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('transaction_type', sa.Enum('DEPOSIT', 'WITHDRAW', 'POSITION_ENTRY', 'POSITION_EXIT', 'FEE_COLLECTION', name='transactiontype'), nullable=False),
        sa.Column('amount_usdc', sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column('tx_hash', sa.String(), nullable=True),
        sa.Column('block_number', sa.Integer(), nullable=True),
        sa.Column('gas_used', sa.Integer(), nullable=True),
        sa.Column('gas_price', sa.Numeric(precision=20, scale=9), nullable=True),
        sa.Column('status', sa.Enum('PENDING', 'CONFIRMED', 'FAILED', 'CANCELLED', name='transactionstatus'), nullable=False),
        sa.Column('tx_metadata', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
        sa.PrimaryKeyConstraint('transaction_id')
    )
    op.create_index('idx_transaction_confirmed_at', 'transactions', ['confirmed_at'], unique=False)
    op.create_index('idx_transaction_created_at', 'transactions', ['created_at'], unique=False)
    op.create_index('idx_transaction_status', 'transactions', ['status'], unique=False)
    op.create_index('idx_transaction_type', 'transactions', ['transaction_type'], unique=False)
    op.create_index('idx_transaction_user_id', 'transactions', ['user_id'], unique=False)
    op.create_index('idx_transaction_user_type', 'transactions', ['user_id', 'transaction_type'], unique=False)
    op.create_index(op.f('ix_transactions_tx_hash'), 'transactions', ['tx_hash'], unique=True)

    # Create positions table
    op.create_table('positions',
        sa.Column('position_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('nft_token_id', sa.Integer(), nullable=False),
        sa.Column('pool_address', sa.String(), nullable=False),
        sa.Column('token0_address', sa.String(), nullable=False),
        sa.Column('token1_address', sa.String(), nullable=False),
        sa.Column('tick_lower', sa.Integer(), nullable=False),
        sa.Column('tick_upper', sa.Integer(), nullable=False),
        sa.Column('tick_spacing', sa.Integer(), nullable=False),
        sa.Column('liquidity', sa.String(), nullable=False),
        sa.Column('staked', sa.Boolean(), nullable=False),
        sa.Column('gauge_address', sa.String(), nullable=True),
        sa.Column('entry_amount_usdc', sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column('current_value_usdc', sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column('realized_pnl_usdc', sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column('unrealized_pnl_usdc', sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column('fees_earned_usdc', sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column('rewards_earned_usdc', sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column('status', sa.Enum('ACTIVE', 'CLOSED', 'LIQUIDATED', name='positionstatus'), nullable=False),
        sa.Column('entry_tx_hash', sa.String(), nullable=True),
        sa.Column('exit_tx_hash', sa.String(), nullable=True),
        sa.Column('entry_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('exit_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_updated', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
        sa.PrimaryKeyConstraint('position_id')
    )
    op.create_index('idx_position_entry_date', 'positions', ['entry_date'], unique=False)
    op.create_index('idx_position_exit_date', 'positions', ['exit_date'], unique=False)
    op.create_index('idx_position_pool', 'positions', ['pool_address'], unique=False)
    op.create_index('idx_position_staked', 'positions', ['staked'], unique=False)
    op.create_index('idx_position_status', 'positions', ['status'], unique=False)
    op.create_index('idx_position_user_id', 'positions', ['user_id'], unique=False)
    op.create_index('idx_position_user_status', 'positions', ['user_id', 'status'], unique=False)
    op.create_index(op.f('ix_positions_entry_tx_hash'), 'positions', ['entry_tx_hash'], unique=False)
    op.create_index(op.f('ix_positions_exit_tx_hash'), 'positions', ['exit_tx_hash'], unique=False)
    op.create_index(op.f('ix_positions_nft_token_id'), 'positions', ['nft_token_id'], unique=True)

    # Create protocol_fees table
    op.create_table('protocol_fees',
        sa.Column('fee_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('position_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('position_profit_usdc', sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column('fee_amount_usdc', sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column('fee_percentage', sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column('collected', sa.Boolean(), nullable=False),
        sa.Column('collection_tx_hash', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('collected_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['position_id'], ['positions.position_id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
        sa.PrimaryKeyConstraint('fee_id')
    )
    op.create_index('idx_fee_collected', 'protocol_fees', ['collected'], unique=False)
    op.create_index('idx_fee_created_at', 'protocol_fees', ['created_at'], unique=False)
    op.create_index('idx_fee_user_collected', 'protocol_fees', ['user_id', 'collected'], unique=False)
    op.create_index('idx_fee_user_id', 'protocol_fees', ['user_id'], unique=False)
    op.create_index(op.f('ix_protocol_fees_collection_tx_hash'), 'protocol_fees', ['collection_tx_hash'], unique=False)
    op.create_index(op.f('ix_protocol_fees_position_id'), 'protocol_fees', ['position_id'], unique=True)


def downgrade() -> None:
    # Drop tables in reverse order due to foreign key constraints
    op.drop_index(op.f('ix_protocol_fees_position_id'), table_name='protocol_fees')
    op.drop_index(op.f('ix_protocol_fees_collection_tx_hash'), table_name='protocol_fees')
    op.drop_index('idx_fee_user_id', table_name='protocol_fees')
    op.drop_index('idx_fee_user_collected', table_name='protocol_fees')
    op.drop_index('idx_fee_created_at', table_name='protocol_fees')
    op.drop_index('idx_fee_collected', table_name='protocol_fees')
    op.drop_table('protocol_fees')
    
    op.drop_index(op.f('ix_positions_nft_token_id'), table_name='positions')
    op.drop_index(op.f('ix_positions_exit_tx_hash'), table_name='positions')
    op.drop_index(op.f('ix_positions_entry_tx_hash'), table_name='positions')
    op.drop_index('idx_position_user_status', table_name='positions')
    op.drop_index('idx_position_user_id', table_name='positions')
    op.drop_index('idx_position_status', table_name='positions')
    op.drop_index('idx_position_staked', table_name='positions')
    op.drop_index('idx_position_pool', table_name='positions')
    op.drop_index('idx_position_exit_date', table_name='positions')
    op.drop_index('idx_position_entry_date', table_name='positions')
    op.drop_table('positions')
    
    op.drop_index(op.f('ix_transactions_tx_hash'), table_name='transactions')
    op.drop_index('idx_transaction_user_type', table_name='transactions')
    op.drop_index('idx_transaction_user_id', table_name='transactions')
    op.drop_index('idx_transaction_type', table_name='transactions')
    op.drop_index('idx_transaction_status', table_name='transactions')
    op.drop_index('idx_transaction_created_at', table_name='transactions')
    op.drop_index('idx_transaction_confirmed_at', table_name='transactions')
    op.drop_table('transactions')
    
    op.drop_index(op.f('ix_users_wallet_address'), table_name='users')
    op.drop_index(op.f('ix_users_user_id'), table_name='users')
    op.drop_index('idx_user_status', table_name='users')
    op.drop_index('idx_user_created_at', table_name='users')
    op.drop_index('idx_user_cdp_owner', table_name='users')
    op.drop_table('users')
    
    # Drop enums
    op.execute('DROP TYPE IF EXISTS positionstatus')
    op.execute('DROP TYPE IF EXISTS transactionstatus')
    op.execute('DROP TYPE IF EXISTS transactiontype')
    op.execute('DROP TYPE IF EXISTS userstatus')