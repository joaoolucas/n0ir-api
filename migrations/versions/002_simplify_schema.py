"""Simplify database schema

Revision ID: 002_simplify_schema
Revises: 001_initial
Create Date: 2025-08-19

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_simplify_schema'
down_revision = '001'  # Update this to your latest migration
branch_labels = None
depends_on = None


def upgrade():
    """Apply schema simplification."""

    # 1. Remove redundant columns from users table (if they exist)
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('users')]

    if 'cdp_owner_wallet_address' in columns:
        op.drop_column('users', 'cdp_owner_wallet_address')
    if 'cdp_owner_wallet_name' in columns:
        op.drop_column('users', 'cdp_owner_wallet_name')
    
    # 2. Add protocol fee tracking to positions table (if columns don't exist)
    columns = [col['name'] for col in inspector.get_columns('positions')]

    if 'protocol_fee_amount' not in columns:
        op.add_column('positions',
            sa.Column('protocol_fee_amount', sa.Numeric(precision=20, scale=6),
                      server_default='0', nullable=False))
    if 'protocol_fee_collected' not in columns:
        op.add_column('positions',
            sa.Column('protocol_fee_collected', sa.Boolean(),
                      server_default='false', nullable=False))
    if 'protocol_fee_tx_hash' not in columns:
        op.add_column('positions',
            sa.Column('protocol_fee_tx_hash', sa.String(), nullable=True))
    
    # 3. Add related position to transactions (if column doesn't exist)
    trans_columns = [col['name'] for col in inspector.get_columns('transactions')]

    if 'related_position_id' not in trans_columns:
        op.add_column('transactions',
            sa.Column('related_position_id', sa.Integer(), nullable=True))

        # Create foreign key after column exists
        op.create_foreign_key(
            'fk_transaction_position',
            'transactions', 'positions',
            ['related_position_id'], ['nft_token_id']
        )
    
    # 4. Create new indexes (if they don't exist)
    pos_indexes = [idx['name'] for idx in inspector.get_indexes('positions')]
    trans_indexes = [idx['name'] for idx in inspector.get_indexes('transactions')]

    if 'idx_position_protocol_fee_collected' not in pos_indexes:
        op.create_index('idx_position_protocol_fee_collected',
                        'positions', ['protocol_fee_collected'])
    if 'idx_position_protocol_fee_tx' not in pos_indexes:
        op.create_index('idx_position_protocol_fee_tx',
                        'positions', ['protocol_fee_tx_hash'])
    if 'idx_transaction_related_position' not in trans_indexes:
        op.create_index('idx_transaction_related_position',
                        'transactions', ['related_position_id'])
    
    # 5. Migrate data from protocol_fees table if it exists
    connection = op.get_bind()
    
    # Check if protocol_fees table exists
    inspector = sa.inspect(connection)
    if 'protocol_fees' in inspector.get_table_names():
        # Migrate fee data to positions
        connection.execute(sa.text("""
            UPDATE positions p
            SET protocol_fee_amount = pf.fee_amount_usdc,
                protocol_fee_collected = pf.collected,
                protocol_fee_tx_hash = pf.collection_tx_hash
            FROM protocol_fees pf
            WHERE p.position_id = pf.position_id
        """))
        
        # Skip creating transactions for now - table doesn't exist in clean DB
        # and enum type doesn't support 'protocol_fee' yet
        pass
        
        # Drop the protocol_fees table
        op.drop_table('protocol_fees')
    
    # 6. Update transaction type enum (only if transactions table exists and has transaction_type column)
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    if 'transactions' in inspector.get_table_names():
        trans_columns = [col['name'] for col in inspector.get_columns('transactions')]

        if 'transaction_type' in trans_columns:
            # First, create new enum type with lowercase values
            op.execute("CREATE TYPE transactiontype_new AS ENUM ('deposit', 'withdraw', 'position_entry', 'position_exit', 'protocol_fee')")

            # Convert column to new enum, converting uppercase to lowercase
            op.execute("""
                ALTER TABLE transactions
                ALTER COLUMN transaction_type TYPE transactiontype_new
                USING LOWER(transaction_type::text)::transactiontype_new
            """)

            # Drop old enum
            op.execute("DROP TYPE IF EXISTS transactiontype CASCADE")

            # Rename new enum
            op.execute("ALTER TYPE transactiontype_new RENAME TO transactiontype")
    
    # 7. Drop old indexes if they exist
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    indexes = inspector.get_indexes('users')
    if any(idx['name'] == 'idx_user_cdp_owner' for idx in indexes):
        op.drop_index('idx_user_cdp_owner', table_name='users')


def downgrade():
    """Revert schema changes."""
    
    # Restore columns to users table
    op.add_column('users',
        sa.Column('cdp_owner_wallet_address', sa.String(), nullable=True))
    op.add_column('users',
        sa.Column('cdp_owner_wallet_name', sa.String(), nullable=True))
    
    # Update with user_id values (since they're the same)
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE users 
        SET cdp_owner_wallet_address = user_id,
            cdp_owner_wallet_name = 'user-wallet-' || SUBSTR(user_id, 1, 8)
    """))
    
    # Make columns not nullable
    op.alter_column('users', 'cdp_owner_wallet_address', nullable=False)
    op.alter_column('users', 'cdp_owner_wallet_name', nullable=False)
    
    # Recreate protocol_fees table
    op.create_table('protocol_fees',
        sa.Column('fee_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.user_id'), nullable=False),
        sa.Column('position_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('positions.position_id'), nullable=False),
        sa.Column('position_profit_usdc', sa.Numeric(20, 6), nullable=False),
        sa.Column('fee_amount_usdc', sa.Numeric(20, 6), nullable=False),
        sa.Column('fee_percentage', sa.Numeric(5, 4), server_default='0.05', nullable=False),
        sa.Column('collected', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('collection_tx_hash', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('collected_at', sa.DateTime(timezone=True), nullable=True)
    )
    
    # Migrate data back from positions to protocol_fees
    connection.execute(sa.text("""
        INSERT INTO protocol_fees (
            fee_id,
            user_id,
            position_id,
            position_profit_usdc,
            fee_amount_usdc,
            collected,
            collection_tx_hash,
            created_at
        )
        SELECT 
            gen_random_uuid(),
            p.user_id,
            p.position_id,
            p.realized_pnl_usdc,
            p.protocol_fee_amount,
            p.protocol_fee_collected,
            p.protocol_fee_tx_hash,
            p.exit_date
        FROM positions p
        WHERE p.protocol_fee_amount > 0
    """))
    
    # Remove columns from positions
    op.drop_column('positions', 'protocol_fee_amount')
    op.drop_column('positions', 'protocol_fee_collected')
    op.drop_column('positions', 'protocol_fee_tx_hash')
    
    # Remove related_position_id from transactions
    op.drop_constraint('fk_transaction_position', 'transactions', type_='foreignkey')
    op.drop_column('transactions', 'related_position_id')
    
    # Restore old transaction type enum
    op.execute("CREATE TYPE transactiontype_old AS ENUM ('deposit', 'withdraw', 'position_entry', 'position_exit', 'fee_collection')")
    op.execute("ALTER TABLE transactions ALTER COLUMN transaction_type TYPE transactiontype_old USING transaction_type::text::transactiontype_old")
    op.execute("DROP TYPE transactiontype CASCADE")
    op.execute("ALTER TYPE transactiontype_old RENAME TO transactiontype")
    
    # Drop new indexes
    op.drop_index('idx_position_protocol_fee_collected', table_name='positions')
    op.drop_index('idx_position_protocol_fee_tx', table_name='positions')
    op.drop_index('idx_transaction_related_position', table_name='transactions')
    
    # Recreate old index
    op.create_index('idx_user_cdp_owner', 'users', ['cdp_owner_wallet_address'])