"""Hybrid Position model that works with both old and new database schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING, List
from sqlalchemy import Column, String, DateTime, ForeignKey, Index, Numeric, Integer, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, Mapped
from sqlalchemy.ext.hybrid import hybrid_property
from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.user import User
    from app.database.models.transaction import Transaction


class Position(Base):
    """Uniswap V3 positions - hybrid version for both schemas."""
    __tablename__ = "positions"
    
    # Primary key - NFT token ID from blockchain
    token_id = Column(Integer, primary_key=True)
    
    # Foreign key to user
    user_id = Column(String(42), ForeignKey("users.user_id"), nullable=False, index=True)
    
    # Pool information
    pool_address = Column(String(42), nullable=False, index=True)
    pool_name = Column(String(100), nullable=True)
    
    # Token addresses
    token0_address = Column(String(42), nullable=True)
    token1_address = Column(String(42), nullable=True)
    
    # Tick and liquidity information
    tick_lower = Column(Integer, nullable=True)
    tick_upper = Column(Integer, nullable=True)
    liquidity = Column(String(80), nullable=True)  # Stored as string due to uint256 size
    
    # USD amounts
    entry_amount_usdc = Column(Numeric(precision=20, scale=6), default=0, nullable=False)
    current_value_usdc = Column(Numeric(precision=20, scale=6), nullable=True)
    fees_earned_usdc = Column(Numeric(precision=20, scale=6), default=0, nullable=False)
    rewards_earned_usdc = Column(Numeric(precision=20, scale=6), default=0, nullable=False)
    
    # Staking information
    staked = Column(Boolean, default=False, nullable=False)
    gauge_address = Column(String(42), nullable=True)
    
    # Transaction hashes
    entry_tx_hash = Column(String(66), nullable=True)
    exit_tx_hash = Column(String(66), nullable=True)
    
    # Protocol fees tracked in transactions table now
    
    # Position status
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)
    
    # The NEW PnL column that exists in the migrated database
    realized_pnl_usdc = Column(Numeric(precision=20, scale=6), default=0, nullable=False)

    # Protocol fee tracking (added by schema_fixes.py at runtime)
    protocol_fee_amount = Column(Numeric(precision=20, scale=6), default=0, nullable=True)
    protocol_fee_collected = Column(Boolean, default=False, nullable=True)
    protocol_fee_tx_hash = Column(String(66), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    entry_date = Column(DateTime(timezone=True), nullable=True)
    exit_date = Column(DateTime(timezone=True), nullable=True, index=True)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="positions")
    transactions: Mapped[List["Transaction"]] = relationship("Transaction", back_populates="position")
    
    # Indexes
    __table_args__ = (
        Index("idx_positions_user_status", "user_id", "status"),
        Index("idx_positions_status", "status"),
    )
    
    # Removed JSONB hybrid properties - not needed
    
    # Backward compatibility properties for schema validation
    @property
    def nft_token_id(self) -> int:
        """Alias for token_id to maintain compatibility with PositionResponse schema."""
        return self.token_id

    @property
    def unrealized_pnl_usdc(self) -> Decimal:
        """Calculate unrealized PnL from current value and entry amount."""
        if self.current_value_usdc and self.entry_amount_usdc:
            return self.current_value_usdc - self.entry_amount_usdc
        return Decimal(0)

    @property
    def last_updated(self) -> datetime:
        """Alias for updated_at to maintain compatibility."""
        return self.updated_at

    def __repr__(self):
        return f"<Position(token_id={self.token_id}, user={self.user_id}, status={self.status})>"