from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import Column, String, DateTime, Enum as SQLEnum, ForeignKey, Index, Numeric, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped
import enum
import uuid

from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.user import User


class TransactionType(enum.Enum):
    DEPOSIT = "deposit"
    WITHDRAW = "withdraw"
    POSITION_ENTRY = "position_entry"
    POSITION_EXIT = "position_exit"
    PROTOCOL_FEE = "protocol_fee"  # Protocol fee collection from profitable positions


class TransactionStatus(enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Transaction(Base):
    __tablename__ = "transactions"
    
    # Primary key
    transaction_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign key to user
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False, index=True)
    
    # Transaction details
    transaction_type = Column(SQLEnum(TransactionType), nullable=False)
    amount_usdc = Column(Numeric(precision=20, scale=6), nullable=False)
    
    # Pool information (for position entry/exit transactions)
    pool_name = Column(String, nullable=True)  # e.g., "WETH-USDC"
    
    # Related position (for entry/exit/fee transactions)
    related_position_id = Column(Integer, ForeignKey("positions.nft_token_id"), nullable=True, index=True)
    
    # Blockchain information
    tx_hash = Column(String, unique=True, nullable=True, index=True)
    block_number = Column(Integer, nullable=True)
    gas_used = Column(Integer, nullable=True)
    gas_price = Column(Numeric(precision=20, scale=9), nullable=True)  # In Gwei
    
    # Status
    status = Column(SQLEnum(TransactionStatus), default=TransactionStatus.PENDING, nullable=False)
    
    # Additional metadata (JSON field for flexibility)
    tx_metadata = Column(String, nullable=True)  # Store as JSON string
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="transactions")
    
    # Indexes
    __table_args__ = (
        Index("idx_transaction_user_id", "user_id"),
        Index("idx_transaction_type", "transaction_type"),
        Index("idx_transaction_status", "status"),
        Index("idx_transaction_created_at", "created_at"),
        Index("idx_transaction_confirmed_at", "confirmed_at"),
        Index("idx_transaction_user_type", "user_id", "transaction_type"),
    )
    
    def __repr__(self):
        return f"<Transaction(id={self.transaction_id}, type={self.transaction_type}, amount={self.amount_usdc}, status={self.status})>"