"""Remove unused columns from all tables.

Revision ID: 027_remove_unused_columns  
Revises: 026_merge_hedge_into_positions
Create Date: 2024-12-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '027_remove_unused_columns'
down_revision = '026_merge_hedge_into_positions'
branch_labels = None
depends_on = None


def upgrade():
    """Remove unused columns from positions, transactions, and users tables."""
    
    # Remove unused columns from positions table
    op.drop_column('positions', 'unrealized_pnl_usd')
    op.drop_column('positions', 'unrealized_pnl_pct')
    op.drop_column('positions', 'realized_pnl_usd')
    op.drop_column('positions', 'realized_pnl_pct')
    op.drop_column('positions', 'protocol_fee_amount')
    op.drop_column('positions', 'protocol_fee_collected')
    op.drop_column('positions', 'protocol_fee_tx_hash')
    op.drop_column('positions', 'closed_at')  # Use exit_date instead
    op.drop_column('positions', 'tick_spacing')  # Can be derived from pool
    
    # Remove JSONB columns that will be replaced
    op.drop_column('positions', 'position_data')
    op.drop_column('positions', 'blockchain_data')
    
    # Remove unused columns from transactions table
    op.drop_column('transactions', 'tx_metadata')
    op.drop_column('transactions', 'processed_at')
    op.drop_column('transactions', 'gas_used')
    
    # Remove unused columns from users table
    op.drop_column('users', 'cdp_wallet_name')
    
    # Drop pool_metrics table if it exists
    op.execute("DROP TABLE IF EXISTS pool_metrics CASCADE")
    
    # Add missing columns for positions that we'll actually use
    op.add_column('positions', sa.Column('entry_date', sa.DateTime(timezone=True), nullable=True))
    op.add_column('positions', sa.Column('exit_date', sa.DateTime(timezone=True), nullable=True))
    op.add_column('positions', sa.Column('realized_pnl_usdc', sa.Numeric(precision=20, scale=6), nullable=False, server_default='0'))
    
    # Migrate data from old fields to new ones if needed
    op.execute("""
        UPDATE positions 
        SET entry_date = created_at 
        WHERE entry_date IS NULL AND created_at IS NOT NULL
    """)
    
    op.execute("""
        UPDATE positions 
        SET exit_date = updated_at 
        WHERE exit_date IS NULL AND status = 'CLOSED'
    """)


def downgrade():
    """Restore removed columns."""
    
    # Restore positions columns
    op.add_column('positions', sa.Column('unrealized_pnl_usd', sa.Numeric(precision=20, scale=2), nullable=False, server_default='0'))
    op.add_column('positions', sa.Column('unrealized_pnl_pct', sa.Numeric(precision=10, scale=4), nullable=False, server_default='0'))
    op.add_column('positions', sa.Column('realized_pnl_usd', sa.Numeric(precision=20, scale=2), nullable=False, server_default='0'))
    op.add_column('positions', sa.Column('realized_pnl_pct', sa.Numeric(precision=10, scale=4), nullable=False, server_default='0'))
    op.add_column('positions', sa.Column('protocol_fee_amount', sa.Numeric(precision=20, scale=6), nullable=False, server_default='0'))
    op.add_column('positions', sa.Column('protocol_fee_collected', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('positions', sa.Column('protocol_fee_tx_hash', sa.String(66), nullable=True))
    op.add_column('positions', sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('positions', sa.Column('tick_spacing', sa.Integer(), nullable=True))
    
    # Restore JSONB columns
    op.add_column('positions', sa.Column('position_data', postgresql.JSONB(), nullable=False, server_default='{}'))
    op.add_column('positions', sa.Column('blockchain_data', postgresql.JSONB(), nullable=False, server_default='{}'))
    
    # Restore transactions columns
    op.add_column('transactions', sa.Column('tx_metadata', postgresql.JSONB(), nullable=False, server_default='{}'))
    op.add_column('transactions', sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('transactions', sa.Column('gas_used', sa.Integer(), nullable=True))
    
    # Restore users columns
    op.add_column('users', sa.Column('cdp_wallet_name', sa.String(255), nullable=True))
    
    # Remove new columns
    op.drop_column('positions', 'entry_date')
    op.drop_column('positions', 'exit_date')
    op.drop_column('positions', 'realized_pnl_usdc')