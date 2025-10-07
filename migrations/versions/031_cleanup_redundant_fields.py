"""Remove redundant fields and simplify schema

Revision ID: 031_cleanup_redundant_fields
Revises: 030_consolidate_transactions
Create Date: 2024-01-16

This migration:
1. Removes unused PnL fields from users table (tracked in positions)
2. Removes unused agent timing fields from users (moved to metadata)
3. Removes all hedge-related fields from positions (not used)
4. Removes backward compatibility columns
5. Optimizes indexes
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '031_cleanup_redundant_fields'
down_revision = '031_add_confirmed_at_column'
branch_labels = None
depends_on = None


def upgrade():
    """Remove redundant fields and optimize schema."""
    
    # 1. Remove redundant PnL fields from users table
    # These are calculated from positions, no need to store
    op.drop_column('users', 'unrealized_pnl_usd')
    op.drop_column('users', 'unrealized_pnl_pct')
    op.drop_column('users', 'realized_pnl_usd')
    op.drop_column('users', 'realized_pnl_pct')
    
    # 2. Remove agent timing fields (moved to user_metadata JSONB)
    op.drop_column('users', 'agent_started_at')
    op.drop_column('users', 'agent_stopped_at')
    op.drop_column('users', 'last_balance_check')
    op.drop_column('users', 'agent_metadata')
    
    # 3. Drop unused indexes on removed columns
    op.drop_index('idx_users_pnl', 'users')
    
    # 4. Clean up positions table - protocol fees tracked in transactions now
    op.drop_column('positions', 'protocol_fee_amount')
    op.drop_column('positions', 'protocol_fee_collected')
    op.drop_column('positions', 'protocol_fee_tx_hash')
    
    # 5. Add optimized indexes for common queries
    op.create_index('idx_users_cdp_balance', 'users', ['cdp_wallet_address', 'usdc_balance'])
    op.create_index('idx_positions_user_active', 'positions', ['user_id', 'status'], 
                    postgresql_where=sa.text("status = 'ACTIVE'"))
    op.create_index('idx_transactions_user_type', 'transactions', ['user_id', 'tx_type', 'created_at'])
    
    # 6. Update any NULL statuses to have proper defaults
    op.execute("""
        UPDATE positions 
        SET status = 'ACTIVE' 
        WHERE status IS NULL
    """)
    
    op.execute("""
        UPDATE transactions 
        SET status = 'CONFIRMED' 
        WHERE status IS NULL AND tx_hash IS NOT NULL
    """)
    
    print("✅ Removed redundant fields from users and positions tables")
    print("✅ Optimized indexes for better query performance")


def downgrade():
    """Restore removed fields."""
    
    # Restore users columns
    op.add_column('users', sa.Column('unrealized_pnl_usd', sa.Numeric(20, 2), nullable=True, default=0))
    op.add_column('users', sa.Column('unrealized_pnl_pct', sa.Numeric(10, 4), nullable=True, default=0))
    op.add_column('users', sa.Column('realized_pnl_usd', sa.Numeric(20, 2), nullable=True, default=0))
    op.add_column('users', sa.Column('realized_pnl_pct', sa.Numeric(10, 4), nullable=True, default=0))
    op.add_column('users', sa.Column('agent_started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('agent_stopped_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('last_balance_check', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('agent_metadata', postgresql.JSONB, nullable=True))
    
    # Restore positions columns
    op.add_column('positions', sa.Column('protocol_fee_amount', sa.Numeric(20, 6), nullable=True, default=0))
    op.add_column('positions', sa.Column('protocol_fee_collected', sa.Boolean, nullable=True, default=False))
    op.add_column('positions', sa.Column('protocol_fee_tx_hash', sa.String(66), nullable=True))
    
    # Restore old indexes
    op.create_index('idx_users_pnl', 'users', ['unrealized_pnl_usd'])
    
    # Drop new indexes
    op.drop_index('idx_users_cdp_balance', 'users')
    op.drop_index('idx_positions_user_active', 'positions')
    op.drop_index('idx_transactions_user_type', 'transactions')