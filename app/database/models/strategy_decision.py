from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, DateTime, Numeric, Integer, Boolean, Index, JSON, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped
import uuid
from app.database.base import Base


class StrategyDecision(Base):
    """Table to track strategy API decisions and recommendations."""
    __tablename__ = "strategy_decisions"
    
    # Primary key
    decision_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Request information
    request_id = Column(String, nullable=True, index=True)
    user_id = Column(String, nullable=True, index=True)
    
    # Decision details
    decision_type = Column(String, nullable=False)  # e.g., "entry", "exit", "rebalance"
    pool_address = Column(String, nullable=False, index=True)
    action_recommended = Column(String, nullable=False)  # e.g., "enter_position", "exit_position", "hold"
    
    # Position parameters (if applicable)
    recommended_amount_usdc = Column(Numeric(precision=20, scale=6), nullable=True)
    recommended_tick_lower = Column(Integer, nullable=True)
    recommended_tick_upper = Column(Integer, nullable=True)
    
    # Market conditions at decision time
    pool_tvl = Column(Numeric(precision=20, scale=2), nullable=True)
    pool_volume_24h = Column(Numeric(precision=20, scale=2), nullable=True)
    pool_apr = Column(Numeric(precision=10, scale=2), nullable=True)
    current_tick = Column(Integer, nullable=True)
    
    # Risk metrics
    risk_score = Column(Numeric(precision=5, scale=2), nullable=True)  # 0-100
    confidence_score = Column(Numeric(precision=5, scale=2), nullable=True)  # 0-100
    expected_return = Column(Numeric(precision=10, scale=2), nullable=True)  # Percentage
    
    # Reasoning and metadata
    reasoning = Column(Text, nullable=True)  # Explanation for the decision
    decision_metadata = Column(JSON, nullable=True)  # Additional data
    
    # Execution tracking
    was_executed = Column(Boolean, default=False, nullable=False)
    execution_tx_hash = Column(String, nullable=True)
    execution_time = Column(DateTime(timezone=True), nullable=True)
    execution_result = Column(String, nullable=True)  # "success", "failed", "partial"
    
    # Performance tracking (post-execution)
    actual_pnl = Column(Numeric(precision=20, scale=6), nullable=True)
    actual_apr = Column(Numeric(precision=10, scale=2), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    
    # Indexes for performance
    __table_args__ = (
        Index("idx_strategy_decision_created", "created_at"),
        Index("idx_strategy_decision_type", "decision_type"),
        Index("idx_strategy_decision_pool", "pool_address"),
        Index("idx_strategy_decision_executed", "was_executed"),
        Index("idx_strategy_decision_user", "user_id"),
        Index("idx_strategy_decision_action", "action_recommended"),
    )
    
    def __repr__(self):
        return f"<StrategyDecision(id={self.decision_id}, type={self.decision_type}, action={self.action_recommended}, executed={self.was_executed})>"