"""Consolidate related transactions into single records.

Revision ID: 029_consolidate_transactions
Revises: 028_jsonb_to_real_columns
Create Date: 2024-12-12
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '029_consolidate_transactions'
down_revision = '028_jsonb_to_real_columns'
branch_labels = None
depends_on = None


def upgrade():
    """Consolidate position create/close operations into single transactions."""
    
    # Add amount_usdc column for standardized amount tracking
    op.add_column('transactions', sa.Column('amount_usdc', sa.Numeric(precision=20, scale=6), nullable=True))
    
    # Update existing transactions to populate amount_usdc
    op.execute("""
        UPDATE transactions
        SET amount_usdc = CASE 
            WHEN event_data ? 'amount_usdc' THEN (event_data->>'amount_usdc')::numeric
            WHEN event_data ? 'usdc_invested' THEN (event_data->>'usdc_invested')::numeric
            WHEN event_data ? 'usdc_received' THEN (event_data->>'usdc_received')::numeric
            WHEN event_data ? 'usdc_out' THEN (event_data->>'usdc_out')::numeric
            WHEN event_data ? 'usdc_in' THEN (event_data->>'usdc_in')::numeric
            ELSE 0
        END
        WHERE amount_usdc IS NULL
    """)
    
    # Consolidate POSITION_CREATED + STAKE_CREATED transactions
    op.execute("""
        WITH stake_txs AS (
            SELECT t1.id as create_id, t2.id as stake_id, t2.event_data, t2.tx_hash as stake_hash
            FROM transactions t1
            JOIN transactions t2 ON t1.position_id = t2.position_id 
                AND t1.user_id = t2.user_id
            WHERE t1.tx_type = 'POSITION_CREATED' 
                AND t2.tx_type = 'STAKE_CREATED'
                AND ABS(EXTRACT(EPOCH FROM (t1.created_at - t2.created_at))) < 60
        )
        UPDATE transactions t
        SET event_data = t.event_data || jsonb_build_object(
            'staked', true,
            'stake_tx_hash', st.stake_hash,
            'gauge_address', st.event_data->>'gauge_address'
        )
        FROM stake_txs st
        WHERE t.id = st.create_id
    """)
    
    # Delete redundant STAKE_CREATED transactions
    op.execute("""
        DELETE FROM transactions t1
        WHERE t1.tx_type = 'STAKE_CREATED'
        AND EXISTS (
            SELECT 1 FROM transactions t2
            WHERE t2.position_id = t1.position_id
                AND t2.user_id = t1.user_id
                AND t2.tx_type = 'POSITION_CREATED'
                AND t2.event_data ? 'staked'
                AND ABS(EXTRACT(EPOCH FROM (t1.created_at - t2.created_at))) < 60
        )
    """)
    
    # Consolidate POSITION_CLOSED + SWAP_EXECUTED transactions
    op.execute("""
        WITH swap_txs AS (
            SELECT t1.id as close_id, t2.id as swap_id, t2.event_data, t2.tx_hash as swap_hash
            FROM transactions t1
            JOIN transactions t2 ON t1.position_id = t2.position_id 
                AND t1.user_id = t2.user_id
            WHERE t1.tx_type = 'POSITION_CLOSED' 
                AND t2.tx_type IN ('SWAP_EXECUTED', 'AERO_SWAP')
                AND ABS(EXTRACT(EPOCH FROM (t1.created_at - t2.created_at))) < 60
        )
        UPDATE transactions t
        SET event_data = t.event_data || jsonb_build_object(
            'aero_rewards', COALESCE((st.event_data->>'amount')::numeric, 0),
            'aero_swap_usdc', COALESCE((st.event_data->>'amount_out')::numeric, 0),
            'swap_tx_hash', st.swap_hash
        )
        FROM swap_txs st
        WHERE t.id = st.close_id
    """)
    
    # Delete redundant SWAP_EXECUTED/AERO_SWAP transactions
    op.execute("""
        DELETE FROM transactions t1
        WHERE t1.tx_type IN ('SWAP_EXECUTED', 'AERO_SWAP')
        AND EXISTS (
            SELECT 1 FROM transactions t2
            WHERE t2.position_id = t1.position_id
                AND t2.user_id = t1.user_id
                AND t2.tx_type = 'POSITION_CLOSED'
                AND t2.event_data ? 'swap_tx_hash'
                AND ABS(EXTRACT(EPOCH FROM (t1.created_at - t2.created_at))) < 60
        )
    """)
    
    # Add composite index for better query performance
    op.create_index('idx_transactions_composite', 'transactions', ['user_id', 'tx_type', 'block_timestamp'])


def downgrade():
    """Split consolidated transactions back into separate records."""
    
    # Remove index
    op.drop_index('idx_transactions_composite', 'transactions')
    
    # Re-create STAKE_CREATED transactions from consolidated data
    op.execute("""
        INSERT INTO transactions (id, tx_hash, user_id, position_id, tx_type, status, event_data, created_at)
        SELECT 
            gen_random_uuid(),
            event_data->>'stake_tx_hash',
            user_id,
            position_id,
            'STAKE_CREATED',
            status,
            jsonb_build_object(
                'position_id', position_id,
                'gauge_address', event_data->>'gauge_address'
            ),
            created_at + INTERVAL '1 second'
        FROM transactions
        WHERE tx_type = 'POSITION_CREATED'
            AND event_data ? 'staked'
            AND (event_data->>'staked')::boolean = true
    """)
    
    # Re-create AERO_SWAP transactions from consolidated data
    op.execute("""
        INSERT INTO transactions (id, tx_hash, user_id, position_id, tx_type, status, event_data, created_at)
        SELECT 
            gen_random_uuid(),
            event_data->>'swap_tx_hash',
            user_id,
            position_id,
            'AERO_SWAP',
            status,
            jsonb_build_object(
                'position_id', position_id,
                'amount', event_data->>'aero_rewards',
                'amount_out', event_data->>'aero_swap_usdc'
            ),
            created_at + INTERVAL '1 second'
        FROM transactions
        WHERE tx_type = 'POSITION_CLOSED'
            AND event_data ? 'swap_tx_hash'
    """)
    
    # Remove consolidated fields from original transactions
    op.execute("""
        UPDATE transactions
        SET event_data = event_data - 'staked' - 'stake_tx_hash' - 'gauge_address'
        WHERE tx_type = 'POSITION_CREATED'
    """)
    
    op.execute("""
        UPDATE transactions
        SET event_data = event_data - 'aero_rewards' - 'aero_swap_usdc' - 'swap_tx_hash'
        WHERE tx_type = 'POSITION_CLOSED'
    """)
    
    # Remove amount_usdc column
    op.drop_column('transactions', 'amount_usdc')