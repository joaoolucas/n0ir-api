from datetime import datetime
from typing import List, TYPE_CHECKING, Optional
from sqlalchemy import Column, String, DateTime, Enum as SQLEnum, Index, Numeric, JSON
from sqlalchemy.orm import relationship, Mapped
import enum
from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.transaction import Transaction
    from app.database.models.position import Position
    from app.database.models.agent_event import AgentEvent


class UserStatus(enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class AgentStatus(enum.Enum):
    not_started = "not_started"
    starting = "starting"
    running = "running"
    stopping = "stopping"
    stopped = "stopped"
    failed = "failed"


class User(Base):
    __tablename__ = "users"
    
    # Primary key
    user_id = Column(String, primary_key=True, index=True)
    
    # CDP Wallet information
    cdp_wallet_address = Column(String, unique=True, nullable=False, index=True)
    cdp_wallet_name = Column(String, nullable=False)
    
    # User status
    status = Column(SQLEnum(UserStatus), default=UserStatus.ACTIVE, nullable=False)
    
    # PnL tracking fields
    unrealized_pnl_usdc = Column(Numeric(precision=20, scale=6), default=0, nullable=False)
    realized_pnl_usdc = Column(Numeric(precision=20, scale=6), default=0, nullable=False)
    unrealized_pnl_percentage = Column(Numeric(precision=10, scale=2), default=0, nullable=False)
    realized_pnl_percentage = Column(Numeric(precision=10, scale=2), default=0, nullable=False)
    
    # Agent state tracking
    agent_status = Column(SQLEnum(AgentStatus, name='agent_status_enum'), default=AgentStatus.not_started, nullable=False)
    agent_started_at = Column(DateTime(timezone=True), nullable=True)
    agent_stopped_at = Column(DateTime(timezone=True), nullable=True)
    last_balance_check = Column(DateTime(timezone=True), nullable=True)
    agent_metadata = Column(JSON, nullable=True)
    
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
    
    agent_events: Mapped[List["AgentEvent"]] = relationship(
        "AgentEvent",
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
        return f"<User(user_id={self.user_id}, cdp_wallet_address={self.cdp_wallet_address}, status={self.status})>"