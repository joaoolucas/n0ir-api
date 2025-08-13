from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Column, String, DateTime, Enum as SQLEnum, ForeignKey, Index, Numeric, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum
import uuid

from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.user import User
    from app.database.models.fee import ProtocolFee


class PositionStatus(enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    LIQUIDATED = "liquidated"


class Position(Base):
    __tablename__ = "positions"
    
    # Primary key
    position_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign key to user
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False, index=True)
    
    # Aerodrome NFT position ID
    nft_token_id = Column(Integer, unique=True, nullable=False, index=True)
    
    # Pool information
    pool_address = Column(String, nullable=False, index=True)
    token0_address = Column(String, nullable=False)
    token1_address = Column(String, nullable=False)
    
    # Position parameters
    tick_lower = Column(Integer, nullable=False)
    tick_upper = Column(Integer, nullable=False)
    tick_spacing = Column(Integer, nullable=False)
    liquidity = Column(String, nullable=False)  # Store as string due to large numbers
    
    # Staking information
    staked = Column(Boolean, default=False, nullable=False)
    gauge_address = Column(String, nullable=True)
    
    # Financial tracking
    entry_amount_usdc = Column(Numeric(precision=20, scale=6), nullable=False)
    current_value_usdc = Column(Numeric(precision=20, scale=6), nullable=True)
    
    # Performance metrics
    realized_pnl_usdc = Column(Numeric(precision=20, scale=6), default=0, nullable=False)
    unrealized_pnl_usdc = Column(Numeric(precision=20, scale=6), default=0, nullable=False)
    fees_earned_usdc = Column(Numeric(precision=20, scale=6), default=0, nullable=False)
    rewards_earned_usdc = Column(Numeric(precision=20, scale=6), default=0, nullable=False)
    
    # Status
    status = Column(SQLEnum(PositionStatus), default=PositionStatus.ACTIVE, nullable=False)
    
    # Entry and exit transactions
    entry_tx_hash = Column(String, nullable=True, index=True)
    exit_tx_hash = Column(String, nullable=True, index=True)
    
    # Timestamps
    entry_date = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    exit_date = Column(DateTime(timezone=True), nullable=True)
    last_updated = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user: "User" = relationship("User", back_populates="positions")
    protocol_fee: Optional["ProtocolFee"] = relationship(
        "ProtocolFee",
        back_populates="position",
        uselist=False,
        cascade="all, delete-orphan"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_position_user_id", "user_id"),
        Index("idx_position_pool", "pool_address"),
        Index("idx_position_status", "status"),
        Index("idx_position_entry_date", "entry_date"),
        Index("idx_position_exit_date", "exit_date"),
        Index("idx_position_user_status", "user_id", "status"),
        Index("idx_position_staked", "staked"),
    )
    
    @property
    def total_pnl_usdc(self) -> float:
        """Calculate total PnL including fees and rewards."""
        return float(
            (self.realized_pnl_usdc or 0) + 
            (self.unrealized_pnl_usdc or 0) + 
            (self.fees_earned_usdc or 0) + 
            (self.rewards_earned_usdc or 0)
        )
    
    def __repr__(self):
        return f"<Position(id={self.position_id}, nft_id={self.nft_token_id}, pool={self.pool_address[:10]}..., status={self.status})>"