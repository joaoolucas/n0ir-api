"""UserStrategy model for multi-strategy support."""

from datetime import datetime
from typing import List, TYPE_CHECKING
from uuid import uuid4
from sqlalchemy import Column, String, DateTime, ForeignKey, Index, Numeric, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped
from app.database.base import Base
import enum

if TYPE_CHECKING:
    from app.database.models.user import User
    from app.database.models.position import Position


class StrategyType(str, enum.Enum):
    """Strategy types supported by the platform."""
    HEDGED_WETH_ONLY = "hedged_weth_only"
    HEDGED_CBBTC_ONLY = "hedged_cbbtc_only"
    HEDGED_BLUEPRINT = "hedged_blueprint"
    NONHEDGED_WETH_ONLY = "nonhedged_weth_only"
    NONHEDGED_CBBTC_ONLY = "nonhedged_cbbtc_only"
    NONHEDGED_BLUEPRINT = "nonhedged_blueprint"
    STABLE_USDC_EURC = "stable_usdc_eurc"
    STABLE_USDC_BRZ = "stable_usdc_brz"


class StrategyStatus(str, enum.Enum):
    """Strategy status values."""
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"


class UserStrategy(Base):
    """User strategy configurations and tracking."""
    __tablename__ = "user_strategies"

    # Primary key
    strategy_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Foreign key to user
    user_id = Column(String(42), ForeignKey("users.user_id"), nullable=False, index=True)

    # Strategy configuration
    strategy_type = Column(
        SQLEnum(
            StrategyType,
            name='strategy_type_enum',
            create_type=False
        ),
        nullable=False
    )

    status = Column(
        SQLEnum(
            StrategyStatus,
            name='strategy_status_enum',
            create_type=False
        ),
        nullable=False,
        default=StrategyStatus.ACTIVE
    )

    # Capital allocation
    capital_allocated_usdc = Column(Numeric(precision=20, scale=6), nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="strategies")
    positions: Mapped[List["Position"]] = relationship("Position", back_populates="strategy", lazy="select")

    # Indexes
    __table_args__ = (
        Index("idx_user_strategies_user_id", "user_id"),
        Index("idx_user_strategies_status", "status"),
        Index("idx_user_strategies_user_status", "user_id", "status"),
    )

    @property
    def is_hedged(self) -> bool:
        """Check if this strategy uses hedging."""
        return self.strategy_type.value.startswith("hedged_")

    @property
    def is_stable(self) -> bool:
        """Check if this is a stable pair strategy."""
        return self.strategy_type.value.startswith("stable_")

    @property
    def is_active(self) -> bool:
        """Check if strategy is active."""
        return self.status == StrategyStatus.ACTIVE

    def __repr__(self):
        return f"<UserStrategy(id={self.strategy_id}, user={self.user_id}, type={self.strategy_type.value}, status={self.status.value})>"
