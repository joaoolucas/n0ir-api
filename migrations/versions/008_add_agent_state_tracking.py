"""Add agent state tracking columns

Revision ID: 008_add_agent_state_tracking
Revises: 007_add_realized_pnl_tracking
Create Date: 2025-08-23

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '008_add_agent_state_tracking'
down_revision = '007_add_realized_pnl_tracking'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add agent state tracking columns to users table."""
    
    # Create the enum type first
    agent_status_enum = postgresql.ENUM(
        'not_started', 'starting', 'running', 'stopping', 'stopped', 'failed',
        name='agent_status_enum'
    )
    agent_status_enum.create(op.get_bind())
    
    # Add agent state tracking columns to users table
    op.add_column('users', sa.Column('agent_status', 
                                      sa.Enum('not_started', 'starting', 'running', 'stopping', 'stopped', 'failed', 
                                             name='agent_status_enum'),
                                      nullable=True,
                                      server_default='not_started'))
    op.add_column('users', sa.Column('agent_started_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('agent_stopped_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('last_balance_check', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('agent_metadata', sa.JSON(), nullable=True))
    
    # Create agent_events table for audit trail
    op.create_table('agent_events',
        sa.Column('event_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', sa.String(42), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),  # started, stopped, failed, balance_triggered
        sa.Column('event_reason', sa.String(100), nullable=True),  # balance_increased, balance_decreased, manual, error
        sa.Column('balance_at_event', sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column('agent_status', sa.String(20), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('event_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
    )
    
    # Create indexes for better performance
    op.create_index('idx_agent_events_user_id', 'agent_events', ['user_id'])
    op.create_index('idx_agent_events_created_at', 'agent_events', ['created_at'])
    op.create_index('idx_users_agent_status', 'users', ['agent_status'])


def downgrade() -> None:
    """Remove agent state tracking."""
    
    # Drop indexes
    op.drop_index('idx_users_agent_status', 'users')
    op.drop_index('idx_agent_events_created_at', 'agent_events')
    op.drop_index('idx_agent_events_user_id', 'agent_events')
    
    # Drop agent_events table
    op.drop_table('agent_events')
    
    # Remove columns from users table
    op.drop_column('users', 'agent_metadata')
    op.drop_column('users', 'last_balance_check')
    op.drop_column('users', 'agent_stopped_at')
    op.drop_column('users', 'agent_started_at')
    op.drop_column('users', 'agent_status')
    
    # Drop the enum type
    op.execute('DROP TYPE IF EXISTS agent_status_enum')