"""Unified User model matching 3-table architecture."""

from datetime import datetime
from typing import List, TYPE_CHECKING
from sqlalchemy import Column, String, DateTime, Numeric, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, Mapped
from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.transaction import Transaction
    from app.database.models.position import Position


class User(Base):
    """User table with PnL tracking and CDP wallet information."""
    __tablename__ = "users"
    
    # Primary key - User's EOA wallet address
    user_id = Column(String(42), primary_key=True, index=True)
    
    # CDP Wallet information
    cdp_wallet_address = Column(String(42), unique=True, nullable=True, index=True)
    cdp_wallet_name = Column(String(100), nullable=True)
    
    # PnL tracking fields
    unrealized_pnl_usd = Column(Numeric(precision=20, scale=2), default=0, nullable=False)
    unrealized_pnl_pct = Column(Numeric(precision=10, scale=4), default=0, nullable=False)
    realized_pnl_usd = Column(Numeric(precision=20, scale=2), default=0, nullable=False)
    realized_pnl_pct = Column(Numeric(precision=10, scale=4), default=0, nullable=False)
    
    # Flexible metadata storage
    metadata = Column(JSONB, default={}, nullable=False)
    # Expected metadata fields:
    # - agent_status: not_started, starting, running, stopping, stopped, failed
    # - agent_started_at: timestamp
    # - agent_stopped_at: timestamp
    # - last_balance_check: timestamp
    # - total_positions: count
    # - total_volume: USD volume
    # - tags: array of labels
    # - preferences: user settings
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select"
    )
    
    positions: Mapped[List["Position"]] = relationship(
        "Position",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_users_updated", "updated_at"),
        Index("idx_users_cdp_wallet", "cdp_wallet_address"),
        Index("idx_users_pnl", "unrealized_pnl_usd"),
    )
    
    @property
    def agent_status(self) -> str:
        """Get agent status from metadata."""
        return self.metadata.get('agent_status', 'not_started') if self.metadata else 'not_started'
    
    @agent_status.setter
    def agent_status(self, value: str):
        """Set agent status in metadata."""
        if not self.metadata:
            self.metadata = {}
        self.metadata['agent_status'] = value
    
    @property
    def total_pnl_usd(self) -> float:
        """Calculate total PnL (unrealized + realized)."""
        return float((self.unrealized_pnl_usd or 0) + (self.realized_pnl_usd or 0))
    
    def __repr__(self):
        return f"<User(user_id={self.user_id}, cdp_wallet={self.cdp_wallet_address}, pnl={self.total_pnl_usd:.2f})>"