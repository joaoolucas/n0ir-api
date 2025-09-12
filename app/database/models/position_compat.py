"""Backward-compatible Position model that works with both old and new schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING, List
from sqlalchemy import Column, String, DateTime, ForeignKey, Index, Numeric, Integer, Boolean, BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, Mapped
from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.user import User
    from app.database.models.transaction import Transaction


class Position(Base):
    """Uniswap V3 positions - backward compatible version."""
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
    # tick_spacing removed in migration 027
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
    
    # Protocol fee fields (exist in old schema)
    protocol_fee_amount = Column(Numeric(precision=20, scale=6), default=0, nullable=False)
    protocol_fee_collected = Column(Boolean, default=False, nullable=False)
    protocol_fee_tx_hash = Column(String(66), nullable=True)
    
    # Position status
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)
    
    # PnL tracking fields - using OLD column names since migration 027 hasn't run
    # TODO: Change these to new names after fixing the database
    pnl_usdc = Column('unrealized_pnl_usd', Numeric(precision=20, scale=2), default=0, nullable=False)
    pnl_pct = Column('unrealized_pnl_pct', Numeric(precision=10, scale=4), default=0, nullable=False)
    realized_pnl_usdc = Column('realized_pnl_usd', Numeric(precision=20, scale=2), default=0, nullable=False)
    realized_pnl_pct = Column(Numeric(precision=10, scale=4), default=0, nullable=False)
    
    # JSONB fields (exist in old schema)
    position_data = Column(JSONB, default={}, nullable=False)
    blockchain_data = Column(JSONB, default={}, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="positions")
    transactions: Mapped[List["Transaction"]] = relationship("Transaction", back_populates="position")
    
    # Indexes
    __table_args__ = (
        Index("idx_positions_user_status", "user_id", "status"),
        Index("idx_positions_status", "status"),
    )
    
    # Properties for compatibility with new schema
    @property
    def pool_fee_tier(self) -> Optional[int]:
        """Get pool fee tier from position_data if available."""
        if self.position_data:
            return self.position_data.get('pool_fee_tier')
        return None
    
    @property
    def token0_symbol(self) -> Optional[str]:
        """Get token0 symbol from position_data if available."""
        if self.position_data:
            return self.position_data.get('token0_symbol')
        return None
    
    @property
    def token1_symbol(self) -> Optional[str]:
        """Get token1 symbol from position_data if available."""
        if self.position_data:
            return self.position_data.get('token1_symbol')
        return None
    
    @property
    def hedge_id(self) -> Optional[int]:
        """Get hedge ID if position has hedge (check related table or JSONB)."""
        return None  # No hedge in old schema
    
    @property
    def hedge_enabled(self) -> bool:
        """Check if hedge is enabled."""
        return False  # No hedge in old schema
    
    @property
    def hedge_status(self) -> Optional[str]:
        """Get hedge status."""
        return None  # No hedge in old schema
    
    @property
    def hedge_health_ratio(self) -> Optional[float]:
        """Get hedge health ratio."""
        return None  # No hedge in old schema
    
    @property
    def hedge_is_at_risk(self) -> bool:
        """Check if hedge is at risk."""
        return False  # No hedge in old schema
    
    @property
    def hedge_net_pnl(self) -> Optional[Decimal]:
        """Get hedge net P&L."""
        return None  # No hedge in old schema
    
    @property
    def hedge_pnl_usdc(self) -> Optional[Decimal]:
        """Get hedge P&L."""
        return None  # No hedge in old schema
    
    @property
    def hedge_collateral_usdc(self) -> Optional[Decimal]:
        """Get hedge collateral."""
        return None  # No hedge in old schema
    
    @property
    def hedge_funding_paid_usdc(self) -> Optional[Decimal]:
        """Get hedge funding paid."""
        return None  # No hedge in old schema
    
    @property
    def hedge_size_usdc(self) -> Optional[Decimal]:
        """Get hedge size."""
        return None  # No hedge in old schema
    
    @property
    def hedge_leverage(self) -> Optional[int]:
        """Get hedge leverage."""
        return None  # No hedge in old schema
    
    @property
    def hedge_market(self) -> Optional[str]:
        """Get hedge market."""
        return None  # No hedge in old schema
    
    @property
    def hedge_pair_index(self) -> Optional[int]:
        """Get hedge pair index."""
        return None  # No hedge in old schema
    
    @property
    def hedge_entry_price(self) -> Optional[Decimal]:
        """Get hedge entry price."""
        return None  # No hedge in old schema
    
    @property
    def hedge_current_price(self) -> Optional[Decimal]:
        """Get hedge current price."""
        return None  # No hedge in old schema
    
    @property
    def hedge_closed_at(self) -> Optional[datetime]:
        """Get hedge closed timestamp."""
        return None  # No hedge in old schema
    
    @property
    def price_lower(self) -> Optional[Decimal]:
        """Get lower price from position_data if available."""
        if self.position_data and 'price_ranges' in self.position_data:
            return self.position_data['price_ranges'].get('lower_price')
        return None
    
    @property
    def price_upper(self) -> Optional[Decimal]:
        """Get upper price from position_data if available."""
        if self.position_data and 'price_ranges' in self.position_data:
            return self.position_data['price_ranges'].get('upper_price')
        return None
    
    @property
    def price_current(self) -> Optional[Decimal]:
        """Get current price from position_data if available."""
        if self.position_data and 'price_ranges' in self.position_data:
            return self.position_data['price_ranges'].get('current_price')
        return None
    
    @property
    def total_value_usdc(self) -> Optional[Decimal]:
        """Get total value."""
        return self.current_value_usdc
    
    @property
    def net_pnl_usdc(self) -> Optional[Decimal]:
        """Calculate net P&L."""
        if self.current_value_usdc and self.entry_amount_usdc:
            return self.current_value_usdc - self.entry_amount_usdc + self.fees_earned_usdc + self.rewards_earned_usdc
        return None
    
    @property
    def net_pnl_pct(self) -> Optional[Decimal]:
        """Calculate net P&L percentage."""
        if self.net_pnl_usdc and self.entry_amount_usdc and self.entry_amount_usdc > 0:
            return (self.net_pnl_usdc / self.entry_amount_usdc) * 100
        return None
    
    
    @property
    def entry_date(self) -> Optional[datetime]:
        """Get entry date."""
        return self.created_at
    
    @property
    def exit_date(self) -> Optional[datetime]:
        """Get exit date."""
        return self.closed_at
    
    @property
    def total_pnl_usdc(self) -> Decimal:
        """Calculate total P&L including LP and hedge positions."""
        lp_pnl = (self.net_pnl_usdc or Decimal(0))
        hedge_pnl = (self.hedge_net_pnl or Decimal(0))
        return lp_pnl + hedge_pnl
    
    @property
    def is_hedged(self) -> bool:
        """Check if position has an active hedge."""
        return False  # No hedge in old schema
    
    def __repr__(self):
        return f"<Position(token_id={self.token_id}, user={self.user_id}, status={self.status})>"