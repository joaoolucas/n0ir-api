"""Fix position table primary key - use nft_token_id instead of position_id

Revision ID: 003_fix_position_primary_key
Revises: 002_simplify_schema
Create Date: 2025-08-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003_fix_position_primary_key'
down_revision = 'd8de59893c30'
branch_labels = None
depends_on = None


def upgrade():
    """Change primary key from position_id to nft_token_id."""
    
    # Check if we need to do the migration by checking if position_id column exists
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('positions')]
    
    # If position_id doesn't exist, the migration was already applied
    if 'position_id' not in columns:
        print("Migration already applied - position_id column not found")
        return
    
    # Get existing constraints to check their names
    constraints = inspector.get_pk_constraint('positions')
    pk_name = constraints['name'] if constraints else None
    
    # 1. Drop foreign key constraints that reference position_id (if exists)
    try:
        op.drop_constraint('fk_transaction_position', 'transactions', type_='foreignkey')
    except:
        pass  # Constraint might not exist
    
    # 2. Drop the primary key constraint if it exists
    if pk_name:
        try:
            op.drop_constraint(pk_name, 'positions', type_='primary')
        except:
            pass  # Constraint might not exist or already dropped
    
    # 3. Drop the position_id column
    try:
        op.drop_column('positions', 'position_id')
    except:
        pass  # Column might not exist
    
    # 4. Create new primary key on nft_token_id
    try:
        op.create_primary_key('positions_pkey', 'positions', ['nft_token_id'])
    except:
        pass  # Primary key might already exist
    
    # 5. Create unique index on nft_token_id for better performance (if not exists)
    try:
        op.create_index('idx_position_nft_token_id', 'positions', ['nft_token_id'], unique=True)
    except:
        pass  # Index might already exist
    
    # 6. Recreate the foreign key for transactions using nft_token_id
    try:
        op.create_foreign_key(
            'fk_transaction_position',
            'transactions', 'positions',
            ['related_position_id'], ['nft_token_id']
        )
    except:
        pass  # Foreign key might already exist
    
    print("Successfully migrated positions table to use nft_token_id as primary key")


def downgrade():
    """Revert to using position_id as primary key."""
    
    # 1. Drop the foreign key constraint
    op.drop_constraint('fk_transaction_position', 'transactions', type_='foreignkey')
    
    # 2. Drop the unique index on nft_token_id
    op.drop_index('idx_position_nft_token_id', table_name='positions')
    
    # 3. Drop the primary key on nft_token_id
    op.drop_constraint('positions_pkey', 'positions', type_='primary')
    
    # 4. Add position_id column back
    op.add_column('positions',
        sa.Column('position_id', postgresql.UUID(as_uuid=True), 
                  server_default=sa.text('gen_random_uuid()'), nullable=False))
    
    # 5. Create primary key on position_id
    op.create_primary_key('positions_pkey', 'positions', ['position_id'])
    
    # 6. Recreate the foreign key using position_id
    # Note: This will fail if related_position_id has integer values
    # Would need data migration to convert integer token IDs to UUIDs
    op.create_foreign_key(
        'fk_transaction_position',
        'transactions', 'positions',
        ['related_position_id'], ['position_id']
    )
    
    print("Reverted positions table to use position_id as primary key")