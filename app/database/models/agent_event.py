"""Agent event model for tracking agent lifecycle events."""

from datetime import datetime
from typing import Optional
import uuid
from sqlalchemy import Column, String, DateTime, Numeric, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database.base import Base


class AgentEvent(Base):
    """Model for tracking agent lifecycle events."""
    
    __tablename__ = "agent_events"
    
    # Primary key
    event_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign key to user
    user_id = Column(String(42), ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    
    # Event details
    event_type = Column(String(50), nullable=False)  # started, stopped, failed, balance_triggered
    event_reason = Column(String(100), nullable=True)  # balance_increased, balance_decreased, manual, error
    balance_at_event = Column(Numeric(precision=20, scale=6), nullable=True)
    agent_status = Column(String(20), nullable=True)
    error_message = Column(Text, nullable=True)
    metadata = Column(JSON, nullable=True)
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    
    # Relationship back to user
    user = relationship("User", back_populates="agent_events")
    
    def __repr__(self):
        return f"<AgentEvent(event_id={self.event_id}, user_id={self.user_id}, type={self.event_type})>"