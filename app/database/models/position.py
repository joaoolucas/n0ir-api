"""Unified Position model matching 3-table architecture."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING, List
from sqlalchemy import Column, String, DateTime, ForeignKey, Index, Numeric, Integer, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, Mapped
from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.user import User
    from app.database.models.transaction import Transaction


class Position(Base):
    """Uniswap V3 positions with enriched data and PnL tracking."""
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
    tick_spacing = Column(Integer, nullable=True)
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
    
    # Protocol fee fields (already exist)
    protocol_fee_amount = Column(Numeric(precision=20, scale=6), default=0, nullable=False)
    protocol_fee_collected = Column(Boolean, default=False, nullable=False)
    protocol_fee_tx_hash = Column(String(66), nullable=True)
    
    # Position status
    status = Column(String(20), nullable=False, default="active", index=True)  # active, closed, liquidated
    
    # PnL tracking fields
    unrealized_pnl_usd = Column(Numeric(precision=20, scale=2), default=0, nullable=False)
    unrealized_pnl_pct = Column(Numeric(precision=10, scale=4), default=0, nullable=False)
    realized_pnl_usd = Column(Numeric(precision=20, scale=2), default=0, nullable=False)
    realized_pnl_pct = Column(Numeric(precision=10, scale=4), default=0, nullable=False)
    
    # Position details stored as JSONB for flexibility
    position_data = Column(JSONB, default={}, nullable=False)
    # Expected position_data fields:
    # - token0_address, token1_address
    # - token0_symbol, token1_symbol (e.g., "WETH", "USDC")
    # - pool_name (e.g., "WETH-USDC")
    # - pool_fee_tier (e.g., 3000 for 0.3%)
    # - tick_lower, tick_upper, tick_spacing
    # - liquidity (as string due to size)
    # - price_ranges: {lower_price, upper_price, current_price}
    # - initial_investment_usd
    # - current_value_usd
    # - total_deposits_usd, total_withdrawals_usd
    # - fees_earned: {token0_fees, token1_fees, total_fees_usd}
    # - rewards_earned_usd
    # - impermanent_loss_usd
    # - gauge_info: {gauge_address, staked, staked_amount, reward_rate, apr}
    # - entry_tx_hash, exit_tx_hash
    
    # Blockchain state stored separately
    blockchain_data = Column(JSONB, default={}, nullable=False)
    # Expected blockchain_data fields:
    # - last_synced_block
    # - creation_tx_hash
    # - close_tx_hash (if closed)
    # - all_tx_hashes (array)
    # - gas_spent
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    entry_date = Column(DateTime(timezone=True), nullable=True)  # Alias for created_at
    exit_date = Column(DateTime(timezone=True), nullable=True)   # Alias for closed_at
    last_updated = Column(DateTime(timezone=True), nullable=True)  # Alias for updated_at
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="positions")
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction",
        back_populates="position",
        cascade="all, delete-orphan",
        lazy="select"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_positions_user", "user_id", "status"),
        Index("idx_positions_pool", "pool_address"),
        Index("idx_positions_status", "status", postgresql_where="status = 'active'"),
        Index("idx_positions_pnl", "user_id", "unrealized_pnl_usd", 
              postgresql_where="status = 'active'"),
    )
    
    # Computed properties for backward compatibility
    @property
    def nft_token_id(self) -> int:
        """Alias for token_id for backward compatibility."""
        return self.token_id
    
    @property
    def unrealized_pnl_usdc(self) -> Decimal:
        """Return unrealized PnL as Decimal."""
        return self.unrealized_pnl_usd or Decimal(0)
    
    @property
    def realized_pnl_usdc(self) -> Decimal:
        """Return realized PnL as Decimal."""
        return self.realized_pnl_usd or Decimal(0)
    
    @property
    def total_pnl_usdc(self) -> float:
        """Calculate total PnL including fees and rewards."""
        unrealized = float(self.unrealized_pnl_usd or 0)
        realized = float(self.realized_pnl_usd or 0)
        return unrealized + realized if self.status == 'active' else realized
    
    def __repr__(self):
        return f"<Position(token_id={self.token_id}, pool={self.pool_address[:10]}..., status={self.status}, pnl={self.total_pnl_usdc:.2f})>"