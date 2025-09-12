"""Merge hedge data into positions table.

Revision ID: 026_merge_hedge_into_positions
Revises: 025_add_hedge_positions
Create Date: 2024-12-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '026_merge_hedge_into_positions'
down_revision = '025_add_hedge_positions'
branch_labels = None
depends_on = None


def upgrade():
    """Add hedge columns to positions table and migrate data."""
    
    # Check what columns already exist
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('positions')]
    existing_tables = inspector.get_table_names()
    
    # Add hedge columns to positions table (only if they don't exist)
    hedge_columns = [
        ('hedge_id', sa.BigInteger(), True),
        ('hedge_enabled', sa.Boolean(), False, 'false'),
        ('hedge_size_usdc', sa.Numeric(precision=20, scale=6), True),
        ('hedge_collateral_usdc', sa.Numeric(precision=20, scale=6), True),
        ('hedge_leverage', sa.Integer(), True),
        ('hedge_pair_index', sa.Integer(), True),
        ('hedge_market', sa.String(20), True),
        ('hedge_entry_price', sa.Numeric(precision=20, scale=8), True),
        ('hedge_current_price', sa.Numeric(precision=20, scale=8), True),
        ('hedge_pnl_usdc', sa.Numeric(precision=20, scale=6), True),
        ('hedge_funding_paid_usdc', sa.Numeric(precision=20, scale=6), True),
        ('hedge_status', sa.String(20), True),
        ('hedge_closed_at', sa.DateTime(timezone=True), True)
    ]
    
    for col_name, col_type, nullable, *default in hedge_columns:
        if col_name not in existing_columns:
            if default:
                op.add_column('positions', sa.Column(col_name, col_type, nullable=nullable, server_default=default[0]))
            else:
                op.add_column('positions', sa.Column(col_name, col_type, nullable=nullable))
    
    # Create indexes for hedge columns (only if they don't exist)
    existing_indexes = [idx['name'] for idx in inspector.get_indexes('positions')]
    if 'idx_positions_hedge_status' not in existing_indexes:
        op.create_index('idx_positions_hedge_status', 'positions', ['hedge_status'], 
                         postgresql_where=sa.text("hedge_status IS NOT NULL"))
    if 'idx_positions_hedge_id' not in existing_indexes:
        op.create_index('idx_positions_hedge_id', 'positions', ['hedge_id'],
                         postgresql_where=sa.text("hedge_id IS NOT NULL"))
    
    # Migrate data from hedge_positions to positions table (only if hedge_positions exists)
    if 'hedge_positions' in existing_tables:
        op.execute("""
        UPDATE positions p
        SET 
            hedge_id = hp.hedge_id,
            hedge_enabled = hp.hedge_enabled,
            hedge_size_usdc = hp.hedge_size_usdc,
            hedge_collateral_usdc = hp.collateral_usdc,
            hedge_leverage = hp.leverage,
            hedge_pair_index = hp.pair_index,
            hedge_market = hp.market,
            hedge_entry_price = hp.entry_price,
            hedge_current_price = hp.current_price,
            hedge_pnl_usdc = hp.pnl_usdc,
            hedge_funding_paid_usdc = hp.funding_paid_usdc,
            hedge_status = hp.status,
            hedge_closed_at = hp.closed_at
        FROM hedge_positions hp
        WHERE p.token_id = hp.nft_token_id
        """)
    
    # Migrate hedge events to transactions table (only if hedge_events exists)
    if 'hedge_events' in existing_tables:
        op.execute("""
        INSERT INTO transactions (
            id, 
            tx_hash, 
            user_id, 
            position_id, 
            tx_type, 
            status, 
            block_number,
            block_timestamp,
            event_data,
            created_at
        )
        SELECT 
            gen_random_uuid(),
            he.tx_hash,
            p.user_id,
            he.nft_token_id,
            CASE 
                WHEN he.event_type = 'opened' THEN 'HEDGE_OPENED'
                WHEN he.event_type = 'closed' THEN 'HEDGE_CLOSED'
                WHEN he.event_type = 'rebalanced' THEN 'HEDGE_REBALANCED'
                WHEN he.event_type = 'liquidated' THEN 'HEDGE_LIQUIDATED'
                WHEN he.event_type = 'funding_paid' THEN 'HEDGE_FUNDING'
                ELSE 'HEDGE_EVENT'
            END,
            'CONFIRMED',
            he.block_number,
            he.block_timestamp,
            jsonb_build_object(
                'hedge_id', he.hedge_id,
                'event_type', he.event_type,
                'data', he.data
            ),
            he.created_at
        FROM hedge_events he
        JOIN positions p ON p.token_id = he.nft_token_id
        WHERE he.tx_hash IS NOT NULL
        """)
    
    # Drop foreign key constraints first (only if table exists)
    if 'hedge_positions' in existing_tables:
        try:
            op.drop_constraint('hedge_positions_nft_token_id_fkey', 'hedge_positions', type_='foreignkey')
        except:
            pass  # Constraint might not exist
    
    # Drop the hedge tables (only if they exist)
    if 'hedge_events' in existing_tables:
        op.drop_table('hedge_events')
    if 'hedge_positions' in existing_tables:
        op.drop_table('hedge_positions')


def downgrade():
    """Restore hedge_positions and hedge_events tables."""
    
    # Recreate hedge_positions table
    op.create_table('hedge_positions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('nft_token_id', sa.Integer(), nullable=False),
        sa.Column('hedge_id', sa.BigInteger(), nullable=False),
        sa.Column('hedge_enabled', sa.Boolean(), nullable=False),
        sa.Column('hedge_size_usdc', sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column('collateral_usdc', sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column('leverage', sa.Integer(), nullable=True),
        sa.Column('pair_index', sa.Integer(), nullable=True),
        sa.Column('market', sa.String(20), nullable=True),
        sa.Column('entry_price', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('current_price', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('pnl_usdc', sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column('funding_paid_usdc', sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nft_token_id')
    )
    
    # Recreate hedge_events table
    op.create_table('hedge_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('nft_token_id', sa.Integer(), nullable=False),
        sa.Column('hedge_id', sa.BigInteger(), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=True),
        sa.Column('tx_hash', sa.String(66), nullable=True),
        sa.Column('block_number', sa.BigInteger(), nullable=True),
        sa.Column('block_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('data', postgresql.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Restore data from positions table
    op.execute("""
        INSERT INTO hedge_positions (
            nft_token_id, hedge_id, hedge_enabled, hedge_size_usdc,
            collateral_usdc, leverage, pair_index, market,
            entry_price, current_price, pnl_usdc, funding_paid_usdc,
            status, created_at, updated_at, closed_at
        )
        SELECT 
            token_id, hedge_id, hedge_enabled, hedge_size_usdc,
            hedge_collateral_usdc, hedge_leverage, hedge_pair_index, hedge_market,
            hedge_entry_price, hedge_current_price, hedge_pnl_usdc, hedge_funding_paid_usdc,
            hedge_status, created_at, updated_at, hedge_closed_at
        FROM positions
        WHERE hedge_id IS NOT NULL
    """)
    
    # Drop hedge columns from positions
    op.drop_index('idx_positions_hedge_status', 'positions')
    op.drop_index('idx_positions_hedge_id', 'positions')
    
    op.drop_column('positions', 'hedge_id')
    op.drop_column('positions', 'hedge_enabled')
    op.drop_column('positions', 'hedge_size_usdc')
    op.drop_column('positions', 'hedge_collateral_usdc')
    op.drop_column('positions', 'hedge_leverage')
    op.drop_column('positions', 'hedge_pair_index')
    op.drop_column('positions', 'hedge_market')
    op.drop_column('positions', 'hedge_entry_price')
    op.drop_column('positions', 'hedge_current_price')
    op.drop_column('positions', 'hedge_pnl_usdc')
    op.drop_column('positions', 'hedge_funding_paid_usdc')
    op.drop_column('positions', 'hedge_status')
    op.drop_column('positions', 'hedge_closed_at')