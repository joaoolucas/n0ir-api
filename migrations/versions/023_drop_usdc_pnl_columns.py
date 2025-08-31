"""Drop USDC-suffixed PnL columns from positions

Revision ID: 023_drop_usdc_pnl_columns
Revises: 022_drop_legacy_tx_columns
Create Date: 2025-08-31

These columns conflict with current watcher/API schema and cause NOT NULL errors:
- positions.realized_pnl_usdc
- positions.unrealized_pnl_usdc
They are not present in staging and are replaced by *_usd columns.
"""

from alembic import op


revision = '023_drop_usdc_pnl_columns'
down_revision = '022_drop_legacy_tx_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'positions' AND column_name = 'realized_pnl_usdc'
            ) THEN
                ALTER TABLE positions DROP COLUMN realized_pnl_usdc;
            END IF;
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'positions' AND column_name = 'unrealized_pnl_usdc'
            ) THEN
                ALTER TABLE positions DROP COLUMN unrealized_pnl_usdc;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Best-effort: re-add columns nullable with defaults
    op.execute(
        """
        ALTER TABLE positions 
        ADD COLUMN IF NOT EXISTS realized_pnl_usdc NUMERIC(20, 6),
        ADD COLUMN IF NOT EXISTS unrealized_pnl_usdc NUMERIC(20, 6);
        """
    )

