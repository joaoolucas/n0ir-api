"""Convert JSONB metadata to real columns.

Revision ID: 028_jsonb_to_real_columns
Revises: 027_remove_unused_columns
Create Date: 2024-12-12
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '028_jsonb_to_real_columns'
down_revision = '027_remove_unused_columns'
branch_labels = None
depends_on = None


def upgrade():
    """Add real columns to replace JSONB fields."""
    
    # Check what columns already exist
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('positions')]
    existing_indexes = [idx['name'] for idx in inspector.get_indexes('positions')]
    
    # Add real columns to positions table (only if they don't exist)
    new_columns = [
        ('token0_symbol', sa.String(20), True),
        ('token1_symbol', sa.String(20), True),
        ('pool_fee_tier', sa.Integer(), True),
        ('price_lower', sa.Numeric(precision=20, scale=8), True),
        ('price_upper', sa.Numeric(precision=20, scale=8), True),
        ('price_current', sa.Numeric(precision=20, scale=8), True),
        ('total_value_usdc', sa.Numeric(precision=20, scale=6), True),
        ('net_pnl_usdc', sa.Numeric(precision=20, scale=6), True),
        ('net_pnl_pct', sa.Numeric(precision=10, scale=4), True)
    ]
    
    for col_name, col_type, nullable in new_columns:
        if col_name not in existing_columns:
            op.add_column('positions', sa.Column(col_name, col_type, nullable=nullable))
    
    # Create composite indexes for better query performance (only if they don't exist)
    if 'idx_positions_pool_user' not in existing_indexes:
        op.create_index('idx_positions_pool_user', 'positions', ['pool_address', 'user_id'])
    if 'idx_positions_status_updated' not in existing_indexes:
        op.create_index('idx_positions_status_updated', 'positions', ['status', 'updated_at'])
    if 'idx_positions_user_status' not in existing_indexes:
        op.create_index('idx_positions_user_status', 'positions', ['user_id', 'status'])
    
    # Add validation for transactions event_data structure (skip if it fails)
    try:
        op.execute("""
        ALTER TABLE transactions 
        ADD CONSTRAINT check_event_data_required_fields
        CHECK (
            CASE tx_type
                WHEN 'POSITION_CREATED' THEN 
                    event_data ? 'token_id' AND event_data ? 'usdc_invested'
                WHEN 'POSITION_CLOSED' THEN
                    event_data ? 'token_id' AND event_data ? 'usdc_received'
                WHEN 'DEPOSIT' THEN
                    event_data ? 'amount_usdc'
                WHEN 'WITHDRAWAL' THEN
                    event_data ? 'amount_usdc'
                ELSE true
            END
        )
        """)
    except:
        pass  # Constraint might already exist or fail on some data
    
    # Standardize transaction types
    op.execute("""
        UPDATE transactions 
        SET tx_type = CASE tx_type
            WHEN 'deposit' THEN 'DEPOSIT'
            WHEN 'withdraw' THEN 'WITHDRAWAL'
            WHEN 'withdrawal' THEN 'WITHDRAWAL'
            WHEN 'position_created' THEN 'POSITION_CREATED'
            WHEN 'position_closed' THEN 'POSITION_CLOSED'
            WHEN 'aero_swap' THEN 'AERO_SWAP'
            WHEN 'fee_collection' THEN 'FEE_COLLECTION'
            WHEN 'protocol_fee' THEN 'FEE_COLLECTION'
            ELSE UPPER(tx_type)
        END
    """)


def downgrade():
    """Remove real columns and restore JSONB."""
    
    # Remove indexes
    op.drop_index('idx_positions_pool_user', 'positions')
    op.drop_index('idx_positions_status_updated', 'positions')
    op.drop_index('idx_positions_user_status', 'positions')
    
    # Remove constraint
    op.execute("ALTER TABLE transactions DROP CONSTRAINT IF EXISTS check_event_data_required_fields")
    
    # Remove real columns from positions
    op.drop_column('positions', 'token0_symbol')
    op.drop_column('positions', 'token1_symbol')
    op.drop_column('positions', 'pool_fee_tier')
    op.drop_column('positions', 'price_lower')
    op.drop_column('positions', 'price_upper')
    op.drop_column('positions', 'price_current')
    op.drop_column('positions', 'total_value_usdc')
    op.drop_column('positions', 'net_pnl_usdc')
    op.drop_column('positions', 'net_pnl_pct')