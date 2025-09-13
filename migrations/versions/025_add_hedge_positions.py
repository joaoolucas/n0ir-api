"""Add hedge positions tables for delta-neutral tracking

Revision ID: 025_add_hedge_positions
Revises: 024_relax_position_nullable_fields
Create Date: 2025-01-12 00:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '025_add_hedge_positions'
down_revision = '024_relax_position_fields'
branch_labels = None
depends_on = None


def upgrade():
    # DISABLED: These tables are deprecated and merged into positions/transactions
    # See migration 026_merge_hedge_into_positions
    return
    
    # Check if tables already exist
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()
    
    # Create hedge_positions table if it doesn't exist
    if 'hedge_positions' not in existing_tables:
        op.create_table('hedge_positions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('nft_token_id', sa.Integer(), nullable=False),
        sa.Column('hedge_id', sa.BigInteger(), nullable=False),
        sa.Column('hedge_enabled', sa.Boolean(), server_default='TRUE', nullable=True),
        sa.Column('hedge_size_usdc', sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column('collateral_usdc', sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column('leverage', sa.Integer(), nullable=True),
        sa.Column('pair_index', sa.Integer(), nullable=True),
        sa.Column('market', sa.String(length=20), nullable=True),
        sa.Column('entry_price', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('current_price', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('pnl_usdc', sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column('funding_paid_usdc', sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='active', nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nft_token_id'),
        sa.ForeignKeyConstraint(['nft_token_id'], ['positions.token_id'], ondelete='CASCADE')
        )
        
        # Create indexes for hedge_positions
        op.create_index('idx_hedge_positions_status', 'hedge_positions', ['status'], unique=False)
        op.create_index('idx_hedge_positions_nft', 'hedge_positions', ['nft_token_id'], unique=False)
        op.create_index('idx_hedge_positions_hedge_id', 'hedge_positions', ['hedge_id'], unique=False)
    
    # Create hedge_events table for tracking if it doesn't exist
    if 'hedge_events' not in existing_tables:
        op.create_table('hedge_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('nft_token_id', sa.Integer(), nullable=False),
        sa.Column('hedge_id', sa.BigInteger(), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=True),
        sa.Column('tx_hash', sa.String(length=66), nullable=True),
        sa.Column('block_number', sa.BigInteger(), nullable=True),
        sa.Column('block_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
        
        # Create indexes for hedge_events
        op.create_index('idx_hedge_events_nft', 'hedge_events', ['nft_token_id'], unique=False)
        op.create_index('idx_hedge_events_hedge_id', 'hedge_events', ['hedge_id'], unique=False)
        op.create_index('idx_hedge_events_type', 'hedge_events', ['event_type'], unique=False)
        op.create_index('idx_hedge_events_timestamp', 'hedge_events', ['block_timestamp'], unique=False)


def downgrade():
    # Drop indexes for hedge_events
    op.drop_index('idx_hedge_events_timestamp', table_name='hedge_events')
    op.drop_index('idx_hedge_events_type', table_name='hedge_events')
    op.drop_index('idx_hedge_events_hedge_id', table_name='hedge_events')
    op.drop_index('idx_hedge_events_nft', table_name='hedge_events')
    
    # Drop hedge_events table
    op.drop_table('hedge_events')
    
    # Drop indexes for hedge_positions
    op.drop_index('idx_hedge_positions_hedge_id', table_name='hedge_positions')
    op.drop_index('idx_hedge_positions_nft', table_name='hedge_positions')
    op.drop_index('idx_hedge_positions_status', table_name='hedge_positions')
    
    # Drop hedge_positions table
    op.drop_table('hedge_positions')