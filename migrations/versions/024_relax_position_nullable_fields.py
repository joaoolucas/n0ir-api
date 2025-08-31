"""Make positions token/tick columns nullable to match watcher model

Revision ID: 024_relax_position_nullable_fields
Revises: 023_drop_usdc_pnl_columns
Create Date: 2025-08-31

Drops NOT NULL constraints on columns that may be unknown at creation time:
- token0_address, token1_address, tick_lower, tick_upper
"""

from alembic import op


revision = '024_relax_position_fields'
down_revision = '023_drop_usdc_pnl_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Allow nulls for fields not always present on initial insert
    op.execute(
        """
        ALTER TABLE positions 
        ALTER COLUMN token0_address DROP NOT NULL,
        ALTER COLUMN token1_address DROP NOT NULL,
        ALTER COLUMN tick_lower DROP NOT NULL,
        ALTER COLUMN tick_upper DROP NOT NULL;
        """
    )


def downgrade() -> None:
    # Best-effort: reinstate NOT NULL with defaults for existing nulls
    op.execute(
        """
        UPDATE positions SET token0_address = COALESCE(token0_address, '')::varchar;
        UPDATE positions SET token1_address = COALESCE(token1_address, '')::varchar;
        UPDATE positions SET tick_lower = COALESCE(tick_lower, 0);
        UPDATE positions SET tick_upper = COALESCE(tick_upper, 0);
        ALTER TABLE positions 
        ALTER COLUMN token0_address SET NOT NULL,
        ALTER COLUMN token1_address SET NOT NULL,
        ALTER COLUMN tick_lower SET NOT NULL,
        ALTER COLUMN tick_upper SET NOT NULL;
        """
    )
