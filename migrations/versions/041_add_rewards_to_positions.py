"""Add rewards tracking to positions

Revision ID: 041
Revises: 040
Create Date: 2025-10-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '041'
down_revision = '040'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add rewards columns to positions table
    # unclaimed_fees_usd - fees earned but not yet claimed
    # unclaimed_rewards_aero - AERO rewards earned but not yet claimed
    op.add_column('positions', sa.Column('unclaimed_fees_usd', sa.Numeric(precision=20, scale=6), nullable=True))
    op.add_column('positions', sa.Column('unclaimed_rewards_aero', sa.Numeric(precision=20, scale=6), nullable=True))

    # Set default values for existing rows
    op.execute("UPDATE positions SET unclaimed_fees_usd = 0 WHERE unclaimed_fees_usd IS NULL")
    op.execute("UPDATE positions SET unclaimed_rewards_aero = 0 WHERE unclaimed_rewards_aero IS NULL")

    # Make columns non-nullable after setting defaults
    op.alter_column('positions', 'unclaimed_fees_usd', nullable=False)
    op.alter_column('positions', 'unclaimed_rewards_aero', nullable=False)


def downgrade() -> None:
    op.drop_column('positions', 'unclaimed_rewards_aero')
    op.drop_column('positions', 'unclaimed_fees_usd')
