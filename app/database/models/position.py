"""Simplified Position model with integrated hedge data."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING, List
from sqlalchemy import Column, String, DateTime, ForeignKey, Index, Numeric, Integer, Boolean, BigInteger
from sqlalchemy.orm import relationship, Mapped
from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.user import User
    from app.database.models.transaction import Transaction


class Position(Base):
    """Uniswap V3 positions with integrated hedge tracking."""
    __tablename__ = "positions"
    
    # Primary key - NFT token ID from blockchain
    token_id = Column(Integer, primary_key=True)
    
    # Foreign key to user
    user_id = Column(String(42), ForeignKey("users.user_id"), nullable=False, index=True)
    
    # Pool information
    pool_address = Column(String(42), nullable=False, index=True)
    pool_name = Column(String(100), nullable=True)
    pool_fee_tier = Column(Integer, nullable=True)  # 3000 = 0.3%
    
    # Token information
    token0_address = Column(String(42), nullable=True)
    token1_address = Column(String(42), nullable=True)
    token0_symbol = Column(String(20), nullable=True)
    token1_symbol = Column(String(20), nullable=True)
    
    # Position range
    tick_lower = Column(Integer, nullable=True)
    tick_upper = Column(Integer, nullable=True)
    liquidity = Column(String(80), nullable=True)  # uint256 as string
    
    # Price tracking
    price_lower = Column(Numeric(precision=20, scale=8), nullable=True)
    price_upper = Column(Numeric(precision=20, scale=8), nullable=True)
    price_current = Column(Numeric(precision=20, scale=8), nullable=True)
    
    # Value tracking
    entry_amount_usdc = Column(Numeric(precision=20, scale=6), default=0, nullable=False)
    current_value_usdc = Column(Numeric(precision=20, scale=6), nullable=True)
    total_value_usdc = Column(Numeric(precision=20, scale=6), nullable=True)
    
    # P&L tracking
    fees_earned_usdc = Column(Numeric(precision=20, scale=6), default=0, nullable=False)
    rewards_earned_usdc = Column(Numeric(precision=20, scale=6), default=0, nullable=False)
    realized_pnl_usdc = Column(Numeric(precision=20, scale=6), default=0, nullable=False)
    net_pnl_usdc = Column(Numeric(precision=20, scale=6), nullable=True)
    net_pnl_pct = Column(Numeric(precision=10, scale=4), nullable=True)
    
    # Staking information
    staked = Column(Boolean, default=False, nullable=False)
    gauge_address = Column(String(42), nullable=True)
    
    # Hedge information (nullable - only for hedged positions)
    hedge_id = Column(BigInteger, nullable=True, index=True)
    hedge_enabled = Column(Boolean, default=False, nullable=False)
    hedge_size_usdc = Column(Numeric(precision=20, scale=6), nullable=True)
    hedge_collateral_usdc = Column(Numeric(precision=20, scale=6), nullable=True)
    hedge_leverage = Column(Integer, nullable=True)
    hedge_pair_index = Column(Integer, nullable=True)  # 0 = ETH/USD, 1 = BTC/USD
    hedge_market = Column(String(20), nullable=True)  # 'ETH-USD', 'BTC-USD'
    hedge_entry_price = Column(Numeric(precision=20, scale=8), nullable=True)
    hedge_current_price = Column(Numeric(precision=20, scale=8), nullable=True)
    hedge_pnl_usdc = Column(Numeric(precision=20, scale=6), nullable=True)
    hedge_funding_paid_usdc = Column(Numeric(precision=20, scale=6), nullable=True)
    hedge_status = Column(String(20), nullable=True)  # active, closed, liquidated
    hedge_closed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Transaction hashes
    entry_tx_hash = Column(String(66), nullable=True)
    exit_tx_hash = Column(String(66), nullable=True)
    
    # Position status
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)  # ACTIVE, CLOSED, LIQUIDATED
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    entry_date = Column(DateTime(timezone=True), nullable=True)
    exit_date = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="positions")
    transactions: Mapped[List["Transaction"]] = relationship("Transaction", back_populates="position")
    
    # Indexes
    __table_args__ = (
        Index("idx_positions_user_status", "user_id", "status"),
        Index("idx_positions_status", "status"),
        Index("idx_positions_pool_user", "pool_address", "user_id"),
        Index("idx_positions_status_updated", "status", "updated_at"),
        Index("idx_positions_hedge_status", "hedge_status", postgresql_where="hedge_status IS NOT NULL"),
        Index("idx_positions_hedge_id", "hedge_id", postgresql_where="hedge_id IS NOT NULL"),
    )
    
    @property
    def hedge_health_ratio(self) -> Optional[float]:
        """Calculate health ratio for the hedge position."""
        if not self.hedge_collateral_usdc or not self.hedge_pnl_usdc:
            return None
        
        collateral = float(self.hedge_collateral_usdc)
        pnl = float(self.hedge_pnl_usdc)
        
        if collateral == 0:
            return 0
            
        return (collateral + pnl) / collateral
    
    @property
    def hedge_is_at_risk(self) -> bool:
        """Check if hedge position is at liquidation risk."""
        ratio = self.hedge_health_ratio
        return ratio is not None and ratio < 0.2
    
    @property
    def hedge_net_pnl(self) -> Optional[Decimal]:
        """Calculate net P&L for hedge including funding."""
        if self.hedge_pnl_usdc is None:
            return None
        
        pnl = self.hedge_pnl_usdc or Decimal(0)
        funding = self.hedge_funding_paid_usdc or Decimal(0)
        return pnl - funding
    
    @property
    def total_pnl_usdc(self) -> Decimal:
        """Calculate total P&L including LP and hedge positions."""
        lp_pnl = (self.net_pnl_usdc or Decimal(0))
        hedge_pnl = (self.hedge_net_pnl or Decimal(0))
        return lp_pnl + hedge_pnl
    
    @property
    def is_hedged(self) -> bool:
        """Check if position has an active hedge."""
        return self.hedge_enabled and self.hedge_status == 'active'
    
    def __repr__(self):
        hedge_info = f", hedge_id={self.hedge_id}" if self.hedge_id else ""
        return f"<Position(token_id={self.token_id}, user={self.user_id}, status={self.status}{hedge_info})>"