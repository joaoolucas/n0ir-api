"""Unified Transaction model matching 3-table architecture."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Column, String, DateTime, ForeignKey, Index, Integer, Numeric
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
    
    # Transaction type - simplified to core types
    tx_type = Column(String(50), nullable=False, index=True)
    # Types:
    # DEPOSIT: User deposits USDC to the platform
    # WITHDRAW: User withdraws USDC from the platform
    # POSITION_CREATED: New liquidity position created
    # POSITION_CLOSED: Liquidity position closed (includes AERO swaps and fees)
    # TRANSFER_FEE: Fee transfers to 0xfD75350A7e2C4914908fF7E3082c45Af5762f5FE
    
    # Transaction status
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    # Status: PENDING, CONFIRMED, FAILED
    
    # Amount tracking
    amount_usdc = Column(Numeric(precision=20, scale=6), nullable=True)
    
    # Blockchain information
    block_number = Column(Integer, nullable=True, index=True)
    block_timestamp = Column(DateTime(timezone=True), nullable=True)
    
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
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="transactions")
    position: Mapped[Optional["Position"]] = relationship("Position", back_populates="transactions")
    
    # Indexes
    __table_args__ = (
        Index("idx_transactions_user", "user_id", "block_timestamp"),
        Index("idx_transactions_position", "position_id", "tx_type"),
        Index("idx_transactions_block", "block_number"),
        Index("idx_transactions_type", "tx_type", "status"),
        Index("idx_transactions_composite", "user_id", "tx_type", "block_timestamp"),
    )
    
    # Computed properties for backward compatibility
    @property
    def transaction_id(self) -> uuid.UUID:
        """Alias for id for backward compatibility."""
        return self.id
    
    @property
    def transaction_type(self) -> str:
        """Map tx_type to transaction_type enum values."""
        mapping = {
            'DEPOSIT': 'deposit',
            'WITHDRAWAL': 'withdraw',
            'WITHDRAW': 'withdraw',  # Handle both WITHDRAWAL and WITHDRAW
            'POSITION_CREATED': 'position_created',
            'POSITION_CLOSED': 'position_closed',
            'POSITION_ENTRY': 'position_created',  # Legacy support - map to position_created
            'POSITION_EXIT': 'position_closed',    # Legacy support - map to position_closed
            'PROTOCOL_FEE': 'position_closed',     # Fees are part of closing positions
            'FEE_COLLECTION': 'position_closed',   # Fees are part of closing positions
            'AERO_SWAP': 'position_closed',        # AERO swaps are part of closing positions
            'TRANSFER_FEE': 'transfer_fee'          # Fee transfers
        }
        return mapping.get(self.tx_type, self.tx_type.lower())
    
    @property
    def amount_usdc(self) -> float:
        """Get USDC amount from event_data.
        
        For POSITION_CLOSED transactions, returns total_return_usdc if available
        (which includes AERO swap proceeds), otherwise falls back to amount_usdc.
        """
        if self.event_data:
            # For POSITION_CLOSED, prioritize total_return_usdc which includes AERO swaps
            if self.tx_type == 'POSITION_CLOSED' and 'total_return_usdc' in self.event_data:
                return float(self.event_data['total_return_usdc'])
            
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
    def aero_swap_usdc(self) -> Optional[float]:
        """Get AERO swap amount for POSITION_CLOSED transactions."""
        if self.tx_type == 'POSITION_CLOSED' and self.event_data and 'aero_swap_usdc' in self.event_data:
            return float(self.event_data['aero_swap_usdc'])
        return None
    
    @property
    def realized_pnl_usdc(self) -> Optional[float]:
        """Get realized PnL from event_data."""
        if self.event_data and 'realized_pnl_usdc' in self.event_data:
            return float(self.event_data['realized_pnl_usdc'])
        return None
    
    @property
    def gas_price(self) -> Optional[float]:
        """Get gas price from event_data."""
        if self.event_data and 'gas_price' in self.event_data:
            return float(self.event_data['gas_price'])
        return None
    
    @property
    def gas_used(self) -> Optional[int]:
        """Get gas used from event_data."""
        if self.event_data and 'gas_used' in self.event_data:
            return int(self.event_data['gas_used'])
        return None
    
    @property
    def tx_metadata(self) -> Optional[dict]:
        """Alias for event_data for backward compatibility."""
        return self.event_data
    
    @property
    def related_position_id(self) -> Optional[int]:
        """Alias for position_id for backward compatibility."""
        return self.position_id
    
    # Removed conflicting property - confirmed_at is already a column
    
    @property
    def get_metadata(self) -> dict:
        """Get event_data for backward compatibility."""
        return self.event_data or {}
    
    def __repr__(self):
        return f"<Transaction(id={str(self.id)[:8]}..., type={self.tx_type}, status={self.status})>"