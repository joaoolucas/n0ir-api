"""rename wallet_address to cdp_wallet_address

Revision ID: d8de59893c30
Revises: 30ff38b3b56d
Create Date: 2025-08-19 18:04:04.835132

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd8de59893c30'
down_revision = '30ff38b3b56d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename wallet_address to cdp_wallet_address in users table
    op.alter_column('users', 'wallet_address', 
                    new_column_name='cdp_wallet_address',
                    existing_type=sa.String(),
                    existing_nullable=False)


def downgrade() -> None:
    # Rename back to wallet_address
    op.alter_column('users', 'cdp_wallet_address', 
                    new_column_name='wallet_address',
                    existing_type=sa.String(),
                    existing_nullable=False)