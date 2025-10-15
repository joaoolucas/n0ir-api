"""Add points tracking to users

Revision ID: 042_add_points_to_users
Revises: 041_add_rewards_to_positions
Create Date: 2025-10-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '042_add_points_to_users'
down_revision = '041_add_rewards_to_positions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add points and total_rewards_earned columns to users table
    # total_rewards_earned - cumulative rewards earned in USD (never reset)
    # points - total_rewards_earned * 100 (1 cent = 1 point)
    op.add_column('users', sa.Column('total_rewards_earned', sa.Numeric(precision=20, scale=6), nullable=True))
    op.add_column('users', sa.Column('points', sa.Integer(), nullable=True))

    # Set default values for existing rows
    op.execute("UPDATE users SET total_rewards_earned = 0 WHERE total_rewards_earned IS NULL")
    op.execute("UPDATE users SET points = 0 WHERE points IS NULL")

    # Make columns non-nullable after setting defaults
    op.alter_column('users', 'total_rewards_earned', nullable=False)
    op.alter_column('users', 'points', nullable=False)

    # Add index on points for leaderboard queries
    op.create_index('idx_users_points', 'users', ['points'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_users_points', table_name='users')
    op.drop_column('users', 'points')
    op.drop_column('users', 'total_rewards_earned')
