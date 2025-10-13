"""Simplified database models with integrated hedge tracking."""

from app.database.models.user import User
from app.database.models.position import Position
from app.database.models.transaction import Transaction
from app.database.models.apr_snapshot import APRSnapshot
from app.database.models.user_strategy import UserStrategy

__all__ = [
    "User",
    "Position",
    "Transaction",
    "APRSnapshot",
    "UserStrategy"
]

# Note: The following models are deprecated and replaced by the unified schema:
# - AgentEvent: Events are now tracked in transactions table with appropriate tx_type
# - DailyMetrics: Metrics can be aggregated from transactions and positions
# - ExecutorStats: Stats are stored in user.metadata and position.metadata
# - PoolMetrics: Pool data is stored in position.position_data
# - StrategyDecision: Strategy data is stored in transaction.metadata
# - UserStatus/AgentStatus: Status is stored in user.metadata['agent_status']