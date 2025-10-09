#!/usr/bin/env python3
"""
Script to capture APR snapshots for whitelisted pools.
Can be run manually or scheduled via cron.

Usage:
    python scripts/capture_apr_snapshots.py

Recommended cron schedule (every hour):
    0 * * * * cd /path/to/n0ir-api && python scripts/capture_apr_snapshots.py >> logs/apr_snapshots.log 2>&1
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from datetime import datetime

from app.core.config import settings
from app.services.apr_snapshot_service import apr_snapshot_service
from app.core.logger import logger


async def main():
    """Main function to capture APR snapshots."""
    logger.info("=" * 80)
    logger.info(f"Starting APR snapshot capture at {datetime.utcnow().isoformat()}")
    logger.info("=" * 80)

    # Create async engine and session
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
    )

    async_session = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        async with async_session() as db:
            # Capture snapshots for all whitelisted pools
            snapshots = await apr_snapshot_service.capture_all_whitelisted(db)

            logger.info("-" * 80)
            logger.info(f"Successfully captured {len(snapshots)} snapshots:")
            for snapshot in snapshots:
                logger.info(
                    f"  - {snapshot.pool_symbol} ({snapshot.pool_address}): "
                    f"APR={snapshot.apr}%, Effective APR (standard)={snapshot.effective_apr_standard}%"
                )
            logger.info("=" * 80)

    except Exception as e:
        logger.error(f"Error capturing APR snapshots: {e}", exc_info=True)
        sys.exit(1)

    finally:
        await engine.dispose()

    logger.info(f"APR snapshot capture completed at {datetime.utcnow().isoformat()}")


if __name__ == "__main__":
    asyncio.run(main())
