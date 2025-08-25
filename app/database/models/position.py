"""Unified Position model matching 3-table architecture."""

from datetime import datetime
from typing import Optional, TYPE_CHECKING, List
from sqlalchemy import Column, String, DateTime, ForeignKey, Index, Numeric, Integer
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
    
    # Position status
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)  # ACTIVE, CLOSED, LIQUIDATED
    
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
        Index("idx_positions_status", "status", postgresql_where="status = 'ACTIVE'"),
        Index("idx_positions_pnl", "user_id", "unrealized_pnl_usd", 
              postgresql_where="status = 'ACTIVE'"),
    )
    
    # Computed properties for backward compatibility
    @property
    def nft_token_id(self) -> int:
        """Alias for token_id for backward compatibility."""
        return self.token_id
    
    @property
    def pool_name(self) -> Optional[str]:
        """Get pool name from position_data."""
        return self.position_data.get('pool_name') if self.position_data else None
    
    @property
    def entry_amount_usdc(self) -> float:
        """Get initial investment from position_data."""
        return float(self.position_data.get('initial_investment_usd', 0)) if self.position_data else 0
    
    @property
    def current_value_usdc(self) -> float:
        """Get current value from position_data."""
        return float(self.position_data.get('current_value_usd', 0)) if self.position_data else 0
    
    @property
    def fees_earned_usdc(self) -> float:
        """Get total fees earned from position_data."""
        if self.position_data and 'fees_earned' in self.position_data:
            return float(self.position_data['fees_earned'].get('total_fees_usd', 0))
        return 0
    
    @property
    def rewards_earned_usdc(self) -> float:
        """Get rewards earned from position_data."""
        return float(self.position_data.get('rewards_earned_usd', 0)) if self.position_data else 0
    
    @property
    def staked(self) -> bool:
        """Check if position is staked."""
        if self.position_data and 'gauge_info' in self.position_data:
            return self.position_data['gauge_info'].get('staked', False)
        return False
    
    @property
    def gauge_address(self) -> Optional[str]:
        """Get gauge address if staked."""
        if self.position_data and 'gauge_info' in self.position_data:
            return self.position_data['gauge_info'].get('gauge_address')
        return None
    
    @property
    def entry_tx_hash(self) -> Optional[str]:
        """Get entry transaction hash."""
        return self.position_data.get('entry_tx_hash') if self.position_data else None
    
    @property
    def exit_tx_hash(self) -> Optional[str]:
        """Get exit transaction hash."""
        return self.position_data.get('exit_tx_hash') if self.position_data else None
    
    @property
    def entry_date(self) -> datetime:
        """Alias for created_at for backward compatibility."""
        return self.created_at
    
    @property
    def exit_date(self) -> Optional[datetime]:
        """Alias for closed_at for backward compatibility."""
        return self.closed_at
    
    @property
    def last_updated(self) -> datetime:
        """Alias for updated_at for backward compatibility."""
        return self.updated_at
    
    @property
    def total_pnl_usdc(self) -> float:
        """Calculate total PnL including fees and rewards."""
        unrealized = float(self.unrealized_pnl_usd or 0)
        realized = float(self.realized_pnl_usd or 0)
        return unrealized + realized if self.status == 'ACTIVE' else realized
    
    def __repr__(self):
        return f"<Position(token_id={self.token_id}, pool={self.pool_address[:10]}..., status={self.status}, pnl={self.total_pnl_usdc:.2f})>"