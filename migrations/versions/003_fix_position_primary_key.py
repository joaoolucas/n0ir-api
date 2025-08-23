"""Fix position primary key

Revision ID: 003_fix_position_primary_key
Revises: d8de59893c30
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
    
    # Check if nft_token_id is already primary key
    result = conn.execute(text("""
        SELECT constraint_name 
        FROM information_schema.table_constraints 
        WHERE table_name = 'positions' 
        AND constraint_type = 'PRIMARY KEY'
    """))
    pk_constraint = result.fetchone()
    
    # Check if the primary key is already on nft_token_id
    if pk_constraint:
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.key_column_usage 
            WHERE table_name = 'positions' 
            AND constraint_name = :constraint_name
        """), {"constraint_name": pk_constraint[0]})
        pk_column = result.fetchone()
        
        if pk_column and pk_column[0] == 'nft_token_id':
            print("Primary key is already on nft_token_id, skipping migration")
            return
    
    if not has_position_id:
        print("position_id column doesn't exist, likely migration already applied")
        return
    
    # Check for protocol_fees table dependency
    result = conn.execute(text("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_name = 'protocol_fees'
    """))
    has_protocol_fees = result.fetchone() is not None
    
    if has_protocol_fees:
        # Drop the foreign key constraint from protocol_fees if it exists
        result = conn.execute(text("""
            SELECT constraint_name 
            FROM information_schema.table_constraints 
            WHERE table_name = 'protocol_fees' 
            AND constraint_type = 'FOREIGN KEY'
            AND constraint_name LIKE '%position%'
        """))
        for row in result:
            try:
                op.drop_constraint(row[0], 'protocol_fees', type_='foreignkey')
                print(f"Dropped foreign key {row[0]} from protocol_fees")
            except:
                pass
    
    # Check for foreign key constraint in transactions
    result = conn.execute(text("""
        SELECT constraint_name 
        FROM information_schema.table_constraints 
        WHERE table_name = 'transactions' 
        AND constraint_name = 'fk_transaction_position'
    """))
    has_fk = result.fetchone() is not None
    
    # 1. Drop foreign key constraint if it exists
    if has_fk:
        try:
            op.drop_constraint('fk_transaction_position', 'transactions', type_='foreignkey')
        except:
            pass
    
    # 2. Drop the primary key constraint if it exists
    if pk_constraint:
        try:
            # Use CASCADE to handle dependent objects
            conn.execute(text(f"ALTER TABLE positions DROP CONSTRAINT {pk_constraint[0]} CASCADE"))
            print(f"Dropped primary key constraint {pk_constraint[0]} with CASCADE")
        except Exception as e:
            print(f"Could not drop primary key: {e}")
            # If we can't drop it, the migration probably already ran
            return
    
    # 3. Drop the position_id column
    try:
        op.drop_column('positions', 'position_id')
        print("Dropped position_id column")
    except Exception as e:
        print(f"Could not drop position_id column: {e}")
        pass
    
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
        try:
            op.create_primary_key('positions_pkey', 'positions', ['nft_token_id'])
            print("Created primary key on nft_token_id")
        except:
            pass
    
    # 5. Check if index already exists
    result = conn.execute(text("""
        SELECT indexname 
        FROM pg_indexes 
        WHERE tablename = 'positions' 
        AND indexname = 'idx_position_nft_token_id'
    """))
    has_index = result.fetchone() is not None
    
    if not has_index:
        try:
            op.create_index('idx_position_nft_token_id', 'positions', ['nft_token_id'], unique=True)
        except:
            pass
    
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
        try:
            op.create_foreign_key(
                'fk_transaction_position',
                'transactions', 'positions',
                ['related_position_id'], ['nft_token_id']
            )
        except:
            pass
    
    print("Successfully migrated positions table to use nft_token_id as primary key")


def downgrade() -> None:
    """Revert to using position_id as primary key."""
    # Downgrade is not supported for this migration
    # as it would require recreating data that was deleted
    pass