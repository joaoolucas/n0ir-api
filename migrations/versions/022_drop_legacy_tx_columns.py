"""Drop legacy/unused columns from transactions to match staging

Revision ID: 022_drop_legacy_tx_columns
Revises: 021_normalize_production_schema
Create Date: 2025-08-31

Removes columns not present in the staging/target schema:
- amount_usdc, gas_price, confirmed_at, portfolio_value_at_time,
  cost_basis_withdrawn, realized_pnl_usdc
Also drops indexes that depend on these columns.
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = '022_drop_legacy_tx_columns'
down_revision = '021_normalize_production_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop dependent indexes if they exist
    op.execute("DROP INDEX IF EXISTS idx_transaction_confirmed_at;")

    # Drop legacy columns if they exist
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'transactions' AND column_name = 'amount_usdc') THEN
                ALTER TABLE transactions DROP COLUMN amount_usdc;
            END IF;
            IF EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'transactions' AND column_name = 'gas_price') THEN
                ALTER TABLE transactions DROP COLUMN gas_price;
            END IF;
            IF EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'transactions' AND column_name = 'confirmed_at') THEN
                ALTER TABLE transactions DROP COLUMN confirmed_at;
            END IF;
            IF EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'transactions' AND column_name = 'portfolio_value_at_time') THEN
                ALTER TABLE transactions DROP COLUMN portfolio_value_at_time;
            END IF;
            IF EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'transactions' AND column_name = 'cost_basis_withdrawn') THEN
                ALTER TABLE transactions DROP COLUMN cost_basis_withdrawn;
            END IF;
            IF EXISTS (SELECT 1 FROM information_schema.columns 
                      WHERE table_name = 'transactions' AND column_name = 'realized_pnl_usdc') THEN
                ALTER TABLE transactions DROP COLUMN realized_pnl_usdc;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Recreate columns as nullable numeric/timestamps (best effort)
    op.execute(
        """
        ALTER TABLE transactions 
        ADD COLUMN IF NOT EXISTS amount_usdc NUMERIC,
        ADD COLUMN IF NOT EXISTS gas_price NUMERIC,
        ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMP WITH TIME ZONE,
        ADD COLUMN IF NOT EXISTS portfolio_value_at_time NUMERIC,
        ADD COLUMN IF NOT EXISTS cost_basis_withdrawn NUMERIC,
        ADD COLUMN IF NOT EXISTS realized_pnl_usdc NUMERIC;
        """
    )

