from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import Column, String, DateTime, ForeignKey, Index, Numeric, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.user import User
    from app.database.models.position import Position


class ProtocolFee(Base):
    __tablename__ = "protocol_fees"
    
    # Primary key
    fee_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign keys
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False, index=True)
    position_id = Column(UUID(as_uuid=True), ForeignKey("positions.position_id"), nullable=False, unique=True, index=True)
    
    # Fee calculation
    position_profit_usdc = Column(Numeric(precision=20, scale=6), nullable=False)
    fee_amount_usdc = Column(Numeric(precision=20, scale=6), nullable=False)
    fee_percentage = Column(Numeric(precision=5, scale=4), default=0.05, nullable=False)  # 5% default
    
    # Collection status
    collected = Column(Boolean, default=False, nullable=False, index=True)
    collection_tx_hash = Column(String, nullable=True, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    collected_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user: "User" = relationship("User", back_populates="protocol_fees")
    position: "Position" = relationship("Position", back_populates="protocol_fee", uselist=False)
    
    # Indexes
    __table_args__ = (
        Index("idx_fee_user_id", "user_id"),
        Index("idx_fee_collected", "collected"),
        Index("idx_fee_created_at", "created_at"),
        Index("idx_fee_user_collected", "user_id", "collected"),
    )
    
    def calculate_fee(self, profit: float, percentage: float = 0.05) -> float:
        """Calculate protocol fee based on profit."""
        if profit <= 0:
            return 0.0
        return profit * percentage
    
    def __repr__(self):
        return f"<ProtocolFee(id={self.fee_id}, amount={self.fee_amount_usdc}, collected={self.collected})>"