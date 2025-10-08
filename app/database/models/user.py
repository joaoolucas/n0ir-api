"""Unified User model matching 3-table architecture."""

from datetime import datetime
from typing import List, TYPE_CHECKING
from sqlalchemy import Column, String, DateTime, Numeric, Index, Integer, Boolean
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
    owner_wallet_address = Column(String(42), nullable=True)  # Added missing column

    # Wallet balance tracking fields (watcher-owned) - these DO exist
    usdc_balance = Column(Numeric(precision=20, scale=6), default=0, nullable=False)
    last_deposit_block = Column(Integer, nullable=True)
    last_withdrawal_block = Column(Integer, nullable=True)
    total_deposits_usdc = Column(Numeric(precision=20, scale=6), default=0, nullable=False)
    total_withdrawals_usdc = Column(Numeric(precision=20, scale=6), default=0, nullable=False)
    last_scanned_block = Column(Integer, nullable=True)

    # PnL tracking fields - these exist in database
    unrealized_pnl_usd = Column(Numeric(precision=20, scale=2), default=0, nullable=False)
    unrealized_pnl_pct = Column(Numeric(precision=20, scale=2), default=0, nullable=False)
    realized_pnl_usd = Column(Numeric(precision=20, scale=2), default=0, nullable=False)
    realized_pnl_pct = Column(Numeric(precision=20, scale=2), default=0, nullable=False)

    # Agent startup requirement tracking
    has_deposited_50_usdc = Column(Boolean, default=False, nullable=False)

    # Agent tracking timestamps
    agent_started_at = Column(DateTime(timezone=True), nullable=True)
    agent_stopped_at = Column(DateTime(timezone=True), nullable=True)
    last_balance_check = Column(DateTime(timezone=True), nullable=True)

    # PnL is tracked in positions table, not here
    # Agent tracking moved to user_metadata JSONB field

    # Flexible metadata storage
    user_metadata = Column(JSONB, default={}, nullable=False)
    agent_metadata = Column(JSONB, nullable=True)
    # Expected user_metadata fields:
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
        Index("idx_users_cdp_balance", "cdp_wallet_address", "usdc_balance"),
        Index("idx_users_balance", "usdc_balance"),
        Index("idx_users_last_scanned", "last_scanned_block"),
    )
    
    @property
    def agent_status(self) -> str:
        """Get agent status from user_metadata."""
        return self.user_metadata.get('agent_status', 'not_started') if self.user_metadata else 'not_started'
    
    @agent_status.setter
    def agent_status(self, value: str):
        """Set agent status in user_metadata."""
        if not self.user_metadata:
            self.user_metadata = {}
        self.user_metadata['agent_status'] = value
    
    @property
    def status(self) -> str:
        """Get user status - for compatibility with UserResponse schema."""
        # Users default to INACTIVE until they activate their agent
        # Always return uppercase status for consistency with UserStatus enum
        status = self.user_metadata.get('status', 'INACTIVE') if self.user_metadata else 'INACTIVE'
        return status.upper() if isinstance(status, str) else 'INACTIVE'
    
    @status.setter
    def status(self, value: str):
        """Set user status in user_metadata."""
        if not self.user_metadata:
            self.user_metadata = {}
        # Always store uppercase status for consistency
        self.user_metadata['status'] = value.upper() if isinstance(value, str) else 'INACTIVE'

    @property
    def cdp_wallet_name(self) -> str:
        """Get CDP wallet name from user_metadata."""
        return self.user_metadata.get('cdp_wallet_name', None) if self.user_metadata else None

    @cdp_wallet_name.setter
    def cdp_wallet_name(self, value: str):
        """Set CDP wallet name in user_metadata."""
        if not self.user_metadata:
            self.user_metadata = {}
        self.user_metadata['cdp_wallet_name'] = value

    # PnL properties removed - calculated from positions instead

    def __repr__(self):
        return f"<User(user_id={self.user_id}, cdp_wallet={self.cdp_wallet_address}, balance={float(self.usdc_balance):.2f}, realized_pnl={float(self.realized_pnl_usd):.2f})>"