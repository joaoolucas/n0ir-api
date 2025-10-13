"""UserStrategy model for managing user's active trading strategies."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Column, String, DateTime, ForeignKey, Index, Numeric
from sqlalchemy.dialects.postgresql import UUID, ENUM
from sqlalchemy.orm import relationship, Mapped
from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.user import User

# Map strategy types to short codes
STRATEGY_TYPE_TO_CODE = {
    "hedged_weth_only": "h1",
    "hedged_cbbtc_only": "h2",
    "nonhedged_weth_only": "n1",
    "nonhedged_cbbtc_only": "n2",
    "nonhedged_cbltc_cbbtc": "n3",
    "nonhedged_cbada_cbbtc": "n4",
    "nonhedged_cbxrp_cbbtc": "n5",
    "nonhedged_cbdoge_cbbtc": "n6",
    "stable_usdc_eurc": "s1",
    "stable_usdc_msusd": "s2",
}


class UserStrategy(Base):
    """User's active trading strategies with capital allocation."""
    __tablename__ = "user_strategies"

    # Primary key
    strategy_id = Column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")

    # Foreign key to user
    user_id = Column(String(42), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)

    # Strategy configuration
    strategy_type = Column(
        ENUM(
            'hedged_weth_only',
            'hedged_cbbtc_only',
            'hedged_blueprint',
            'nonhedged_weth_only',
            'nonhedged_cbbtc_only',
            'nonhedged_blueprint',
            'stable_usdc_eurc',
            'stable_usdc_brz',
            'stable_usdc_msusd',
            'nonhedged_cbltc_cbbtc',
            'nonhedged_cbada_cbbtc',
            'nonhedged_cbxrp_cbbtc',
            'nonhedged_cbdoge_cbbtc',
            name='strategy_type_enum',
            create_type=False
        ),
        nullable=False,
        index=True
    )

    # Strategy status
    status = Column(
        ENUM(
            'active',
            'paused',
            'closed',
            name='strategy_status_enum',
            create_type=False
        ),
        nullable=False,
        server_default='active',
        index=True
    )

    # Capital allocation
    allocated_capital_usd = Column(Numeric(precision=20, scale=6), nullable=False, default=0)
    deployed_capital_usd = Column(Numeric(precision=20, scale=6), nullable=False, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="CURRENT_TIMESTAMP")
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default="CURRENT_TIMESTAMP", onupdate=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="strategies")

    # Indexes
    __table_args__ = (
        Index("idx_user_strategies_user_id", "user_id"),
        Index("idx_user_strategies_status", "status"),
        Index("idx_user_strategies_user_status", "user_id", "status"),
    )

    @property
    def strategy_code(self) -> str:
        """Get short code for this strategy (e.g., 'h1', 's1')."""
        return STRATEGY_TYPE_TO_CODE.get(self.strategy_type, self.strategy_type)

    @property
    def available_capital_usd(self) -> float:
        """Calculate available capital (allocated - deployed)."""
        return float(self.allocated_capital_usd - self.deployed_capital_usd)

    def to_dict(self) -> dict:
        """Convert to dictionary matching active_strategies JSONB format."""
        return {
            "strategy_type": self.strategy_type,
            "status": self.status,
            "allocated_capital_usd": float(self.allocated_capital_usd),
            "deployed_capital_usd": float(self.deployed_capital_usd),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return (
            f"<UserStrategy(user_id={self.user_id}, type={self.strategy_type}, "
            f"status={self.status}, allocated={float(self.allocated_capital_usd):.2f}, "
            f"deployed={float(self.deployed_capital_usd):.2f})>"
        )
