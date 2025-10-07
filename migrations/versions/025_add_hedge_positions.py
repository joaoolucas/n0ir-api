"""Add hedge positions tables for delta-neutral tracking

Revision ID: 025_add_hedge_positions
Revises: 024_relax_position_nullable_fields
Create Date: 2025-01-12 00:00:00

DISABLED: These tables are deprecated and merged into positions/transactions
See migration 026_merge_hedge_into_positions
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '025_add_hedge_positions'
down_revision = '024_relax_position_fields'
branch_labels = None
depends_on = None


def upgrade():
    # DISABLED: These tables are deprecated and merged into positions/transactions
    # See migration 026_merge_hedge_into_positions
    pass


def downgrade():
    # DISABLED: These tables are deprecated and merged into positions/transactions
    # See migration 026_merge_hedge_into_positions
    pass