"""HedgeEvent model for tracking hedge-related events."""

from datetime import datetime
from typing import Optional, TYPE_CHECKING, Dict, Any
from sqlalchemy import Column, String, DateTime, ForeignKey, Index, Integer, BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, Mapped
from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.hedge_position import HedgePosition


class HedgeEvent(Base):
    """Track events related to hedge positions."""
    __tablename__ = "hedge_events"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # References
    nft_token_id = Column(Integer, nullable=False, index=True)
    hedge_id = Column(BigInteger, nullable=False, index=True)
    
    # Event details
    event_type = Column(String(50), nullable=True, index=True)  # opened, closed, rebalanced, liquidated, funding_paid
    
    # Transaction details
    tx_hash = Column(String(66), nullable=True)
    block_number = Column(BigInteger, nullable=True)
    block_timestamp = Column(DateTime(timezone=True), nullable=True, index=True)
    
    # Additional event data stored as JSONB
    data = Column(JSONB, default={}, nullable=False)
    # Expected data fields based on event_type:
    # - opened: {size_usdc, collateral_usdc, leverage, entry_price}
    # - closed: {exit_price, final_pnl, total_funding_paid}
    # - rebalanced: {old_size, new_size, adjustment_type, reason}
    # - liquidated: {liquidation_price, loss_amount}
    # - funding_paid: {amount, funding_rate, timestamp}
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    
    # Relationship to hedge position (optional - events may persist after position is deleted)
    hedge_position: Mapped[Optional["HedgePosition"]] = relationship(
        "HedgePosition",
        back_populates="hedge_events",
        foreign_keys=[nft_token_id],
        primaryjoin="HedgeEvent.nft_token_id == HedgePosition.nft_token_id",
        viewonly=True
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_hedge_events_composite", "nft_token_id", "event_type"),
        Index("idx_hedge_events_block", "block_number", "block_timestamp"),
    )
    
    @property
    def event_data(self) -> Dict[str, Any]:
        """Get typed event data."""
        return self.data or {}
    
    def set_event_data(self, **kwargs):
        """Set event data fields."""
        if self.data is None:
            self.data = {}
        self.data.update(kwargs)
    
    def __repr__(self):
        return f"<HedgeEvent(id={self.id}, nft={self.nft_token_id}, type={self.event_type}, block={self.block_number})>"