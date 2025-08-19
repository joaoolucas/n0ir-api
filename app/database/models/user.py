from datetime import datetime
from typing import List, TYPE_CHECKING
from sqlalchemy import Column, String, DateTime, Enum as SQLEnum, Index
from sqlalchemy.orm import relationship, Mapped
import enum
from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.transaction import Transaction
    from app.database.models.position import Position
    from app.database.models.fee import ProtocolFee


class UserStatus(enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class User(Base):
    __tablename__ = "users"
    
    # Primary key
    user_id = Column(String, primary_key=True, index=True)
    
    # CDP Wallet information
    wallet_address = Column(String, unique=True, nullable=False, index=True)
    cdp_wallet_name = Column(String, nullable=False)
    
    # User status
    status = Column(SQLEnum(UserStatus), default=UserStatus.ACTIVE, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select"
    )
    
    positions: Mapped[List["Position"]] = relationship(
        "Position",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_user_status", "status"),
        Index("idx_user_created_at", "created_at"),
    )
    
    def __repr__(self):
        return f"<User(user_id={self.user_id}, wallet_address={self.wallet_address}, status={self.status})>"