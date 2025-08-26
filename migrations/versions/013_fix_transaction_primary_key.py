"""Fix transaction primary key column name

Revision ID: 013_fix_transaction_primary_key
Revises: 012_position_jsonb_to_columns
Create Date: 2025-08-25 20:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '013_fix_transaction_primary_key'
down_revision = '012_position_jsonb_to_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Ensure transactions table has 'id' as primary key column."""
    
    # Check what the actual primary key column is named and rename it to 'id'
    op.execute("""
        DO $$
        DECLARE
            pk_column_name text;
        BEGIN
            -- Find the current primary key column name
            SELECT kcu.column_name INTO pk_column_name
            FROM information_schema.table_constraints tc 
            JOIN information_schema.key_column_usage kcu 
              ON tc.constraint_name = kcu.constraint_name 
              AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY' 
              AND tc.table_name = 'transactions'
              AND tc.table_schema = 'public'
            LIMIT 1;
            
            RAISE NOTICE 'Current primary key column: %', pk_column_name;
            
            -- If it's not already 'id', rename it
            IF pk_column_name IS NOT NULL AND pk_column_name != 'id' THEN
                RAISE NOTICE 'Renaming % to id', pk_column_name;
                EXECUTE 'ALTER TABLE transactions RENAME COLUMN ' || pk_column_name || ' TO id';
            ELSIF pk_column_name IS NULL THEN
                RAISE NOTICE 'No primary key found, this is unexpected';
            ELSE
                RAISE NOTICE 'Primary key column is already named id';
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Revert primary key column name."""
    
    # Rename back to transaction_id if needed
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'transactions' AND column_name = 'id') THEN
                ALTER TABLE transactions RENAME COLUMN id TO transaction_id;
            END IF;
        END $$;
    """)