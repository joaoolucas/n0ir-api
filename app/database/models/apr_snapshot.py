"""APR Snapshot model for tracking historical pool APRs."""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, Numeric, Integer, Index
from sqlalchemy.dialects.postgresql import JSONB
from app.database.base import Base


class APRSnapshot(Base):
    """APR snapshots for whitelisted pools."""
    __tablename__ = "apr_snapshots"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Pool identification
    pool_address = Column(String(42), nullable=False, index=True)
    pool_symbol = Column(String(50), nullable=True)

    # APR data
    apr = Column(Numeric(precision=10, scale=4), nullable=False)
    effective_apr_narrow = Column(Numeric(precision=10, scale=4), nullable=True)
    effective_apr_standard = Column(Numeric(precision=10, scale=4), nullable=True)
    effective_apr_wide = Column(Numeric(precision=10, scale=4), nullable=True)

    # Pool metrics
    tvl_usd = Column(Numeric(precision=20, scale=2), nullable=True)
    volume_24h = Column(Numeric(precision=20, scale=2), nullable=True)

    # Timestamp
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True, default=datetime.utcnow)

    # Additional metadata (fee tier, tick spacing, etc.)
    metadata = Column(JSONB, nullable=True)

    # Composite index for efficient queries
    __table_args__ = (
        Index('idx_apr_snapshots_pool_timestamp', 'pool_address', 'timestamp'),
    )

    def __repr__(self):
        return f"<APRSnapshot(pool={self.pool_address}, apr={self.apr}, timestamp={self.timestamp})>"
