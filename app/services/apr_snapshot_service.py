"""Service for capturing and storing APR snapshots from whitelisted pools."""

from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from decimal import Decimal

from app.database.models import APRSnapshot
from app.core.pools_service import pools_service
from app.core.logger import logger


# Whitelisted pools to capture APR snapshots for
WHITELISTED_POOLS = [
    "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59",  # WETH/USDC
    "0x4e962bb3889bf030368f56810a9c96b83cb3e778",  # cbBTC/USDC
    "0xE846373C1a92B167b4E9cd5d8E4d6B1Db9E90EC7",  # USDC/EURC
    "0x7501bc8Bb51616F79bfA524E464fb7B41f0B10fB",  # USDC/msUSD
]


class APRSnapshotService:
    """Service for managing APR snapshots."""

    async def capture_snapshot(
        self,
        db: AsyncSession,
        pool_address: str
    ) -> Optional[APRSnapshot]:
        """
        Capture a single APR snapshot for a pool.

        Args:
            db: Database session
            pool_address: Pool address to capture snapshot for

        Returns:
            APRSnapshot object if successful, None otherwise
        """
        try:
            # Fetch pool data with effective APR
            pool_data = await pools_service.get_pool(
                address=pool_address,
                include_effective_apr=True
            )

            # Extract effective APR ranges
            effective_apr_range = pool_data.get("effective_apr_range")
            effective_apr_narrow = None
            effective_apr_standard = None
            effective_apr_wide = None
            effective_apr_stable = None

            if effective_apr_range:
                effective_apr_narrow = effective_apr_range.get("narrow")
                effective_apr_standard = effective_apr_range.get("standard")
                effective_apr_wide = effective_apr_range.get("wide")
                effective_apr_stable = effective_apr_range.get("stable")

            # Build metadata dict, only including keys that have values
            metadata = {}
            if pool_data.get("fee_tier") is not None:
                metadata["fee_tier"] = pool_data.get("fee_tier")
            if pool_data.get("tick_spacing") is not None:
                metadata["tick_spacing"] = pool_data.get("tick_spacing")
            if pool_data.get("is_stable") is not None:
                metadata["is_stable"] = pool_data.get("is_stable")
            if pool_data.get("current_tick") is not None:
                metadata["current_tick"] = pool_data.get("current_tick")

            # Create snapshot
            snapshot = APRSnapshot(
                pool_address=pool_address.lower(),
                pool_symbol=pool_data.get("symbol"),
                apr=Decimal(str(pool_data.get("apr", 0))),
                effective_apr_narrow=Decimal(str(effective_apr_narrow)) if effective_apr_narrow else None,
                effective_apr_standard=Decimal(str(effective_apr_standard)) if effective_apr_standard else None,
                effective_apr_wide=Decimal(str(effective_apr_wide)) if effective_apr_wide else None,
                effective_apr_stable=Decimal(str(effective_apr_stable)) if effective_apr_stable else None,
                tvl_usd=Decimal(str(pool_data.get("tvl_usd", 0))) if pool_data.get("tvl_usd") else None,
                volume_24h=Decimal(str(pool_data.get("volume_24h", 0))) if pool_data.get("volume_24h") else None,
                timestamp=datetime.utcnow(),
                pool_metadata=metadata if metadata else None
            )

            db.add(snapshot)
            await db.commit()
            await db.refresh(snapshot)

            logger.info(
                f"Captured APR snapshot for {pool_address}: "
                f"APR={snapshot.apr}%, Standard Effective APR={snapshot.effective_apr_standard}%"
            )

            return snapshot

        except Exception as e:
            logger.error(f"Failed to capture snapshot for {pool_address}: {e}", exc_info=True)
            await db.rollback()
            return None

    async def capture_all_whitelisted(
        self,
        db: AsyncSession
    ) -> List[APRSnapshot]:
        """
        Capture snapshots for all whitelisted pools.

        Args:
            db: Database session

        Returns:
            List of successfully captured snapshots
        """
        snapshots = []

        for pool_address in WHITELISTED_POOLS:
            snapshot = await self.capture_snapshot(db, pool_address)
            if snapshot:
                snapshots.append(snapshot)

        logger.info(f"Captured {len(snapshots)}/{len(WHITELISTED_POOLS)} snapshots")
        return snapshots

    async def get_snapshots(
        self,
        db: AsyncSession,
        pool_address: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[APRSnapshot]:
        """
        Retrieve APR snapshots with optional filters.

        Args:
            db: Database session
            pool_address: Filter by pool address
            start_time: Filter snapshots after this time
            end_time: Filter snapshots before this time
            limit: Maximum number of snapshots to return

        Returns:
            List of APRSnapshot objects
        """
        query = select(APRSnapshot)

        if pool_address:
            query = query.where(APRSnapshot.pool_address == pool_address.lower())

        if start_time:
            query = query.where(APRSnapshot.timestamp >= start_time)

        if end_time:
            query = query.where(APRSnapshot.timestamp <= end_time)

        query = query.order_by(APRSnapshot.timestamp.desc()).limit(limit)

        result = await db.execute(query)
        return result.scalars().all()

    async def get_latest_snapshot(
        self,
        db: AsyncSession,
        pool_address: str
    ) -> Optional[APRSnapshot]:
        """
        Get the most recent snapshot for a pool.

        Args:
            db: Database session
            pool_address: Pool address

        Returns:
            Latest APRSnapshot or None
        """
        query = (
            select(APRSnapshot)
            .where(APRSnapshot.pool_address == pool_address.lower())
            .order_by(APRSnapshot.timestamp.desc())
            .limit(1)
        )

        result = await db.execute(query)
        return result.scalar_one_or_none()


# Singleton instance
apr_snapshot_service = APRSnapshotService()
