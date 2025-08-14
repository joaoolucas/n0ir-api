from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, DateTime, Numeric, Integer, Boolean, Index
from sqlalchemy.orm import Mapped
from app.database.base import Base


class PoolMetrics(Base):
    """Cache table for pool metrics to avoid frequent blockchain calls."""
    __tablename__ = "pool_metrics"
    
    # Primary key
    pool_address = Column(String, primary_key=True, index=True)
    
    # Financial metrics
    tvl_usd = Column(Numeric(precision=20, scale=2), nullable=True)
    volume_24h = Column(Numeric(precision=20, scale=2), nullable=True)
    apr = Column(Numeric(precision=10, scale=2), nullable=True)
    
    # Pool configuration (Aerodrome specific)
    tick_spacing = Column(Integer, nullable=True)
    fee_tier = Column(Integer, nullable=True)  # Fee in basis points
    is_stable = Column(Boolean, default=False, nullable=False)
    
    # Current state
    current_tick = Column(Integer, nullable=True)
    sqrt_price_x96 = Column(String, nullable=True)  # Store as string due to large number
    
    # Staking information
    gauge_address = Column(String, nullable=True)
    
    # Token pair
    token0_address = Column(String, nullable=True)
    token1_address = Column(String, nullable=True)
    token0_symbol = Column(String, nullable=True)
    token1_symbol = Column(String, nullable=True)
    
    # Cache control
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Indexes for performance
    __table_args__ = (
        Index("idx_pool_metrics_updated_at", "updated_at"),
        Index("idx_pool_metrics_tvl", "tvl_usd"),
        Index("idx_pool_metrics_volume", "volume_24h"),
        Index("idx_pool_metrics_apr", "apr"),
        Index("idx_pool_metrics_is_stable", "is_stable"),
        Index("idx_pool_metrics_gauge", "gauge_address"),
    )
    
    def __repr__(self):
        return f"<PoolMetrics(pool={self.pool_address[:10]}..., tvl=${self.tvl_usd}, apr={self.apr}%)>"