"""Fix position primary key

Revision ID: 003_fix_position_primary_key
Revises: 002_simplify_schema
Create Date: 2025-08-22 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '003_fix_position_primary_key'
down_revision = 'd8de59893c30'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Change positions table to use nft_token_id as primary key."""
    
    # Get the connection
    conn = op.get_bind()
    
    # Check if position_id column exists
    result = conn.execute(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'positions' 
        AND column_name = 'position_id'
    """))
    has_position_id = result.fetchone() is not None
    
    if not has_position_id:
        print("position_id column doesn't exist, skipping migration")
        return
    
    # Check for existing primary key constraint
    result = conn.execute(text("""
        SELECT constraint_name 
        FROM information_schema.table_constraints 
        WHERE table_name = 'positions' 
        AND constraint_type = 'PRIMARY KEY'
    """))
    pk_constraint = result.fetchone()
    
    # Check for foreign key constraint
    result = conn.execute(text("""
        SELECT constraint_name 
        FROM information_schema.table_constraints 
        WHERE table_name = 'transactions' 
        AND constraint_name = 'fk_transaction_position'
    """))
    has_fk = result.fetchone() is not None
    
    # 1. Drop foreign key constraint if it exists
    if has_fk:
        op.drop_constraint('fk_transaction_position', 'transactions', type_='foreignkey')
    
    # 2. Drop the primary key constraint if it exists
    if pk_constraint:
        op.drop_constraint(pk_constraint[0], 'positions', type_='primary')
    
    # 3. Drop the position_id column
    op.drop_column('positions', 'position_id')
    
    # 4. Check if nft_token_id already has a primary key
    result = conn.execute(text("""
        SELECT constraint_name 
        FROM information_schema.table_constraints 
        WHERE table_name = 'positions' 
        AND constraint_type = 'PRIMARY KEY'
        AND constraint_name = 'positions_pkey'
    """))
    has_new_pk = result.fetchone() is not None
    
    if not has_new_pk:
        # Create new primary key on nft_token_id
        op.create_primary_key('positions_pkey', 'positions', ['nft_token_id'])
    
    # 5. Check if index already exists
    result = conn.execute(text("""
        SELECT indexname 
        FROM pg_indexes 
        WHERE tablename = 'positions' 
        AND indexname = 'idx_position_nft_token_id'
    """))
    has_index = result.fetchone() is not None
    
    if not has_index:
        op.create_index('idx_position_nft_token_id', 'positions', ['nft_token_id'], unique=True)
    
    # 6. Check if related_position_id column exists in transactions
    result = conn.execute(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'transactions' 
        AND column_name = 'related_position_id'
    """))
    has_related_position = result.fetchone() is not None
    
    if has_related_position:
        # Recreate the foreign key for transactions using nft_token_id
        op.create_foreign_key(
            'fk_transaction_position',
            'transactions', 'positions',
            ['related_position_id'], ['nft_token_id']
        )
    
    print("Successfully migrated positions table to use nft_token_id as primary key")


def downgrade() -> None:
    """Revert to using position_id as primary key."""
    
    # Get the connection
    conn = op.get_bind()
    
    # Check if foreign key exists
    result = conn.execute(text("""
        SELECT constraint_name 
        FROM information_schema.table_constraints 
        WHERE table_name = 'transactions' 
        AND constraint_name = 'fk_transaction_position'
    """))
    has_fk = result.fetchone() is not None
    
    if has_fk:
        op.drop_constraint('fk_transaction_position', 'transactions', type_='foreignkey')
    
    # Drop the primary key on nft_token_id
    op.drop_constraint('positions_pkey', 'positions', type_='primary')
    
    # Drop the index if it exists
    result = conn.execute(text("""
        SELECT indexname 
        FROM pg_indexes 
        WHERE tablename = 'positions' 
        AND indexname = 'idx_position_nft_token_id'
    """))
    has_index = result.fetchone() is not None
    
    if has_index:
        op.drop_index('idx_position_nft_token_id', 'positions')
    
    # Add back the position_id column
    op.add_column('positions', sa.Column('position_id', sa.UUID(), nullable=False))
    
    # Create primary key on position_id
    op.create_primary_key('pk_positions', 'positions', ['position_id'])
    
    # Recreate the foreign key for transactions using position_id
    result = conn.execute(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'transactions' 
        AND column_name = 'related_position_id'
    """))
    has_related_position = result.fetchone() is not None
    
    if has_related_position:
        op.create_foreign_key(
            'fk_transaction_position',
            'transactions', 'positions',
            ['related_position_id'], ['position_id']
        )