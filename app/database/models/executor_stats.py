from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, Numeric, Boolean, Index, JSON
from sqlalchemy.orm import Mapped
from app.database.base import Base


class ExecutorStats(Base):
    """Table to track executor pool statistics and health."""
    __tablename__ = "executor_stats"
    
    # Primary key
    executor_id = Column(String, primary_key=True, index=True)
    
    # Executor information
    executor_name = Column(String, nullable=True)
    executor_type = Column(String, nullable=True)  # e.g., "position_manager", "rebalancer", etc.
    
    # Activity metrics
    active_wallets = Column(Integer, default=0, nullable=False)
    total_positions = Column(Integer, default=0, nullable=False)
    active_positions = Column(Integer, default=0, nullable=False)
    
    # Performance metrics
    total_volume_executed = Column(Numeric(precision=20, scale=2), default=0, nullable=False)
    total_fees_collected = Column(Numeric(precision=20, scale=2), default=0, nullable=False)
    success_rate = Column(Numeric(precision=5, scale=2), default=100, nullable=False)  # Percentage
    
    # Health monitoring
    last_heartbeat = Column(DateTime(timezone=True), nullable=False)
    is_healthy = Column(Boolean, default=True, nullable=False)
    error_count = Column(Integer, default=0, nullable=False)
    last_error = Column(String, nullable=True)
    last_error_time = Column(DateTime(timezone=True), nullable=True)
    
    # Configuration (stored as JSON)
    config = Column(JSON, nullable=True)  # Store executor-specific configuration
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Indexes for performance
    __table_args__ = (
        Index("idx_executor_stats_heartbeat", "last_heartbeat"),
        Index("idx_executor_stats_healthy", "is_healthy"),
        Index("idx_executor_stats_type", "executor_type"),
        Index("idx_executor_stats_active", "active_positions"),
    )
    
    def is_alive(self, threshold_minutes: int = 5) -> bool:
        """Check if executor is alive based on heartbeat."""
        if not self.last_heartbeat:
            return False
        time_since_heartbeat = datetime.utcnow() - self.last_heartbeat
        return time_since_heartbeat.total_seconds() < (threshold_minutes * 60)
    
    def __repr__(self):
        return f"<ExecutorStats(id={self.executor_id}, wallets={self.active_wallets}, positions={self.active_positions}, healthy={self.is_healthy})>"