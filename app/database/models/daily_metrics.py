from datetime import datetime, date
from sqlalchemy import Column, String, DateTime, Date, Numeric, Integer, Index, UniqueConstraint
from sqlalchemy.orm import Mapped
from app.database.base import Base


class DailyMetrics(Base):
    """Table to track daily aggregated performance metrics."""
    __tablename__ = "daily_metrics"
    
    # Composite primary key
    metric_date = Column(Date, primary_key=True, nullable=False)
    metric_type = Column(String, primary_key=True, nullable=False)  # e.g., "platform", "user:{user_id}", "pool:{pool_address}"
    
    # Volume metrics
    total_volume_usdc = Column(Numeric(precision=20, scale=2), default=0, nullable=False)
    deposit_volume_usdc = Column(Numeric(precision=20, scale=2), default=0, nullable=False)
    withdrawal_volume_usdc = Column(Numeric(precision=20, scale=2), default=0, nullable=False)
    
    # Position metrics
    positions_opened = Column(Integer, default=0, nullable=False)
    positions_closed = Column(Integer, default=0, nullable=False)
    active_positions = Column(Integer, default=0, nullable=False)
    
    # User metrics
    active_users = Column(Integer, default=0, nullable=False)
    new_users = Column(Integer, default=0, nullable=False)
    total_users = Column(Integer, default=0, nullable=False)
    
    # Financial metrics
    total_tvl_usdc = Column(Numeric(precision=20, scale=2), default=0, nullable=False)
    total_fees_earned_usdc = Column(Numeric(precision=20, scale=2), default=0, nullable=False)
    total_rewards_earned_usdc = Column(Numeric(precision=20, scale=2), default=0, nullable=False)
    protocol_fees_collected_usdc = Column(Numeric(precision=20, scale=2), default=0, nullable=False)
    
    # Performance metrics
    total_pnl_usdc = Column(Numeric(precision=20, scale=2), default=0, nullable=False)
    average_apr = Column(Numeric(precision=10, scale=2), nullable=True)
    best_performing_pool = Column(String, nullable=True)
    worst_performing_pool = Column(String, nullable=True)
    
    # Risk metrics
    max_drawdown = Column(Numeric(precision=10, scale=2), nullable=True)  # Percentage
    sharpe_ratio = Column(Numeric(precision=10, scale=4), nullable=True)
    
    # Transaction metrics
    total_transactions = Column(Integer, default=0, nullable=False)
    failed_transactions = Column(Integer, default=0, nullable=False)
    average_gas_used = Column(Numeric(precision=20, scale=9), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Indexes and constraints
    __table_args__ = (
        UniqueConstraint("metric_date", "metric_type", name="uq_daily_metrics_date_type"),
        Index("idx_daily_metrics_date", "metric_date"),
        Index("idx_daily_metrics_type", "metric_type"),
        Index("idx_daily_metrics_tvl", "total_tvl_usdc"),
        Index("idx_daily_metrics_volume", "total_volume_usdc"),
    )
    
    def __repr__(self):
        return f"<DailyMetrics(date={self.metric_date}, type={self.metric_type}, tvl=${self.total_tvl_usdc})>"