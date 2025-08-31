"""Normalize production schema to match staging/3-table design

Revision ID: 021_normalize_production_schema
Revises: 020_fix_transaction_type_enum
Create Date: 2025-08-31

This migration aligns production schema differences with staging:
- Make positions.token_id the primary key (drop nft_token_id)
- Convert positions.status enum to VARCHAR
- Ensure users.agent_metadata is JSONB
- Ensure transactions.tx_metadata is JSONB
- Make transactions.related_position_id BIGINT
- Add helpful index on (user_id, block_timestamp)
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = '021_normalize_production_schema'
down_revision = '020_fix_transaction_type_enum'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Positions primary key: switch from nft_token_id to token_id
    # First drop any foreign keys referencing positions(nft_token_id)
    op.execute(
        """
        DO $$
        DECLARE r RECORD;
        BEGIN
            FOR r IN 
                SELECT conname 
                FROM pg_constraint 
                WHERE conrelid = 'transactions'::regclass
                  AND confrelid = 'positions'::regclass
                  AND pg_get_constraintdef(oid) LIKE '%REFERENCES positions(nft_token_id)%'
            LOOP
                EXECUTE format('ALTER TABLE transactions DROP CONSTRAINT %I', r.conname);
            END LOOP;
        END $$;
        """
    )

    # Drop PK and indexes that reference nft_token_id if present
    op.execute("ALTER TABLE IF EXISTS positions DROP CONSTRAINT IF EXISTS positions_pkey;")
    op.execute("DROP INDEX IF EXISTS ix_positions_nft_token_id CASCADE;")
    op.execute("DROP INDEX IF EXISTS idx_position_nft_token_id CASCADE;")

    # Ensure token_id is not null and set as primary key
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'positions' AND column_name = 'token_id'
            ) THEN
                ALTER TABLE positions ALTER COLUMN token_id SET NOT NULL;
                ALTER TABLE positions ADD PRIMARY KEY (token_id);
            END IF;
        END $$;
        """
    )

    # Drop legacy nft_token_id column if it exists
    op.execute("ALTER TABLE IF EXISTS positions DROP COLUMN IF EXISTS nft_token_id;")

    # 2) Convert positions.status enum to VARCHAR if enum exists
    # Drop indexes that depend on enum-typed comparisons
    op.execute("DROP INDEX IF EXISTS idx_positions_pnl;")
    op.execute("DROP INDEX IF EXISTS idx_positions_status;")
    op.execute("DROP INDEX IF EXISTS idx_position_status;")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'positionstatus') THEN
                ALTER TABLE positions 
                ALTER COLUMN status TYPE VARCHAR(20) USING status::text;
                DROP TYPE IF EXISTS positionstatus CASCADE;
            END IF;
        END $$;
        """
    )

    # Recreate useful indexes with VARCHAR comparisons
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_positions_status 
        ON positions(status) 
        WHERE status = 'ACTIVE';
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_positions_pnl 
        ON positions(user_id, unrealized_pnl_usd) 
        WHERE status = 'ACTIVE';
        """
    )

    # 3) Ensure users.agent_metadata is JSONB
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'agent_metadata'
            ) THEN
                -- Convert json or text to jsonb safely
                BEGIN
                    ALTER TABLE users 
                    ALTER COLUMN agent_metadata TYPE JSONB 
                    USING agent_metadata::jsonb;
                EXCEPTION WHEN others THEN
                    -- Fallback: set to empty object if conversion fails
                    ALTER TABLE users 
                    ALTER COLUMN agent_metadata TYPE JSONB 
                    USING '{}'::jsonb;
                END;
            END IF;
        END $$;
        """
    )

    # 4) Ensure transactions.tx_metadata is JSONB
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'transactions' AND column_name = 'tx_metadata'
            ) THEN
                BEGIN
                    ALTER TABLE transactions 
                    ALTER COLUMN tx_metadata TYPE JSONB 
                    USING CASE 
                        WHEN tx_metadata IS NULL THEN '{}'::jsonb
                        ELSE tx_metadata::jsonb
                    END;
                EXCEPTION WHEN others THEN
                    ALTER TABLE transactions 
                    ALTER COLUMN tx_metadata TYPE JSONB 
                    USING '{}'::jsonb;
                END;
            END IF;
        END $$;
        """
    )

    # 5) Ensure transactions.related_position_id is BIGINT
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'transactions' AND column_name = 'related_position_id'
            ) THEN
                ALTER TABLE transactions 
                ALTER COLUMN related_position_id TYPE BIGINT;
            END IF;
        END $$;
        """
    )

    # 6) Add index on (user_id, block_timestamp) for transactions if missing
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_transactions_user 
        ON transactions(user_id, block_timestamp);
        """
    )


def downgrade() -> None:
    # Downgrade is best-effort. We won't recreate enum types or nft_token_id column.
    # Drop the added index
    op.execute("DROP INDEX IF EXISTS idx_transactions_user;")

    # Revert tx_metadata to TEXT (not recommended)
    op.execute(
        """
        ALTER TABLE transactions 
        ALTER COLUMN tx_metadata TYPE TEXT USING tx_metadata::text;
        """
    )

    # Revert agent_metadata to JSON (not recommended)
    op.execute(
        """
        ALTER TABLE users 
        ALTER COLUMN agent_metadata TYPE JSON USING agent_metadata::json;
        """
    )
