"""HedgePosition model for tracking delta-neutral hedge positions."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Column, String, DateTime, ForeignKey, Index, Numeric, Integer, Boolean, BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, Mapped
from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.position import Position


class HedgePosition(Base):
    """Track hedge positions linked to LP positions."""
    __tablename__ = "hedge_positions"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Link to LP position
    nft_token_id = Column(Integer, ForeignKey("positions.token_id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    
    # Hedge identifiers
    hedge_id = Column(BigInteger, nullable=False, index=True)
    hedge_enabled = Column(Boolean, default=True, nullable=False)
    
    # Hedge parameters
    hedge_size_usdc = Column(Numeric(precision=20, scale=6), nullable=True)
    collateral_usdc = Column(Numeric(precision=20, scale=6), nullable=True)
    leverage = Column(Integer, nullable=True)
    
    # Market info
    pair_index = Column(Integer, nullable=True)  # 0 = ETH/USD, 1 = BTC/USD
    market = Column(String(20), nullable=True)  # 'ETH-USD', 'BTC-USD'
    
    # Price tracking
    entry_price = Column(Numeric(precision=20, scale=8), nullable=True)
    current_price = Column(Numeric(precision=20, scale=8), nullable=True)
    
    # P&L tracking
    pnl_usdc = Column(Numeric(precision=20, scale=6), nullable=True)
    funding_paid_usdc = Column(Numeric(precision=20, scale=6), nullable=True)
    
    # Status
    status = Column(String(20), default='active', nullable=False, index=True)  # active, closed, liquidated
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    position: Mapped["Position"] = relationship("Position", back_populates="hedge_position")
    
    # Indexes
    __table_args__ = (
        Index("idx_hedge_positions_active", "status", postgresql_where="status = 'active'"),
        Index("idx_hedge_positions_pnl", "pnl_usdc", "status"),
    )
    
    @property
    def health_ratio(self) -> float:
        """Calculate health ratio for the hedge position."""
        if not self.collateral_usdc or not self.pnl_usdc:
            return 1.0
        
        # Health ratio = (collateral + pnl) / collateral
        # If < 0.2, position is at risk of liquidation
        collateral = float(self.collateral_usdc)
        pnl = float(self.pnl_usdc)
        
        if collateral == 0:
            return 0
            
        return (collateral + pnl) / collateral
    
    @property
    def is_at_risk(self) -> bool:
        """Check if position is at liquidation risk."""
        return self.health_ratio < 0.2
    
    @property
    def net_pnl(self) -> Decimal:
        """Calculate net P&L including funding."""
        pnl = self.pnl_usdc or Decimal(0)
        funding = self.funding_paid_usdc or Decimal(0)
        return pnl - funding
    
    def __repr__(self):
        return f"<HedgePosition(id={self.id}, nft={self.nft_token_id}, hedge_id={self.hedge_id}, status={self.status}, pnl={self.pnl_usdc})>"