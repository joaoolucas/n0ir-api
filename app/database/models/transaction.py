"""Unified Transaction model matching 3-table architecture."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Column, String, DateTime, ForeignKey, Index, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, Mapped
import uuid
from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.user import User
    from app.database.models.position import Position


class Transaction(Base):
    """Universal event and transaction log."""
    __tablename__ = "transactions"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Blockchain transaction hash (unique when present)
    tx_hash = Column(String(66), unique=True, nullable=True, index=True)
    
    # Foreign keys
    user_id = Column(String(42), ForeignKey("users.user_id"), nullable=False, index=True)
    position_id = Column(Integer, ForeignKey("positions.token_id"), nullable=True, index=True)
    
    # Transaction type - comprehensive list
    tx_type = Column(String(50), nullable=False, index=True)
    # Types:
    # Position lifecycle: POSITION_CREATED, POSITION_MODIFIED, POSITION_CLOSED
    # Liquidity: LIQUIDITY_ADDED, LIQUIDITY_REMOVED
    # Financial: FEES_COLLECTED, SWAP_EXECUTED, REWARDS_CLAIMED
    # Staking: STAKE_CREATED, STAKE_REMOVED
    # User actions: DEPOSIT, WITHDRAWAL
    # Protocol: PROTOCOL_FEE
    
    # Transaction status
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    # Status: PENDING, CONFIRMED, FAILED
    
    # Blockchain information
    block_number = Column(Integer, nullable=True, index=True)
    block_timestamp = Column(DateTime(timezone=True), nullable=True)
    gas_used = Column(Integer, nullable=True)
    
    # Event data - flexible storage for type-specific data
    event_data = Column(JSONB, default={}, nullable=False)
    # Examples by tx_type:
    # POSITION_CREATED: {token_id, pool, tick_lower, tick_upper, liquidity, usdc_in}
    # POSITION_CLOSED: {token_id, usdc_out, final_fees}
    # LIQUIDITY_ADDED: {token_id, liquidity_delta, usdc_added}
    # FEES_COLLECTED: {token_id, token0_fees, token1_fees, fees_usd}
    # SWAP_EXECUTED: {token_in, token_out, amount_in, amount_out, price_impact}
    # REWARDS_CLAIMED: {token_address, amount, amount_usd, source}
    # STAKE_CREATED: {position_id, gauge_address, amount, apr}
    # DEPOSIT: {amount_usdc, from_address}
    # WITHDRAWAL: {amount_usdc, to_address}
    
    # Additional metadata
    tx_metadata = Column(JSONB, default={}, nullable=False)
    # Examples:
    # - usd_values: amounts in USD at transaction time
    # - price_impacts: for swaps
    # - related_tx_ids: linked transactions
    # - error_messages: if failed
    # - retry_count: for failed transactions
    # - gas_price: in Gwei
    # - realized_pnl_usdc: PnL realized in this transaction
    # - portfolio_value_at_time: for PnL tracking
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="transactions")
    position: Mapped[Optional["Position"]] = relationship("Position", back_populates="transactions")
    
    # Indexes
    __table_args__ = (
        Index("idx_transactions_user", "user_id", "block_timestamp"),
        Index("idx_transactions_position", "position_id", "tx_type"),
        Index("idx_transactions_block", "block_number"),
        Index("idx_transactions_type", "tx_type", "status"),
    )
    
    # Computed properties for backward compatibility
    @property
    def transaction_id(self) -> uuid.UUID:
        """Alias for id for backward compatibility."""
        return self.id
    
    @property
    def transaction_type(self) -> str:
        """Map tx_type to old transaction_type enum values."""
        mapping = {
            'DEPOSIT': 'deposit',
            'WITHDRAWAL': 'withdraw',
            'POSITION_CREATED': 'position_entry',
            'POSITION_CLOSED': 'position_exit',
            'PROTOCOL_FEE': 'protocol_fee'
        }
        return mapping.get(self.tx_type, self.tx_type.lower())
    
    @property
    def amount_usdc(self) -> float:
        """Get USDC amount from event_data."""
        if self.event_data:
            # Try different field names
            for field in ['amount_usdc', 'usdc_in', 'usdc_out', 'amount_usd']:
                if field in self.event_data:
                    return float(self.event_data[field])
        return 0
    
    @property
    def pool_name(self) -> Optional[str]:
        """Get pool name from event_data."""
        return self.event_data.get('pool_name') if self.event_data else None
    
    @property
    def realized_pnl_usdc(self) -> Optional[float]:
        """Get realized PnL from tx_metadata."""
        if self.tx_metadata and 'realized_pnl_usdc' in self.tx_metadata:
            return float(self.tx_metadata['realized_pnl_usdc'])
        return None
    
    @property
    def gas_price(self) -> Optional[float]:
        """Get gas price from tx_metadata."""
        if self.tx_metadata and 'gas_price' in self.tx_metadata:
            return float(self.tx_metadata['gas_price'])
        return None
    
    @property
    def related_position_id(self) -> Optional[int]:
        """Alias for position_id for backward compatibility."""
        return self.position_id
    
    @property
    def confirmed_at(self) -> Optional[datetime]:
        """Alias for processed_at for backward compatibility."""
        return self.processed_at
    
    @property
    def get_metadata(self) -> dict:
        """Get tx_metadata for backward compatibility."""
        return self.tx_metadata or {}
    
    def __repr__(self):
        return f"<Transaction(id={str(self.id)[:8]}..., type={self.tx_type}, status={self.status})>"