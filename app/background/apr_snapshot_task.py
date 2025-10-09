"""Background task to capture APR snapshots hourly."""

import asyncio
from datetime import datetime
from app.core.logger import logger


async def capture_apr_snapshots_task():
    """
    Background task to capture APR snapshots for whitelisted pools every hour.

    This runs continuously and captures APR data including:
    - Base APR
    - Effective APR (narrow, standard, wide ranges)
    - TVL and 24h volume
    - Pool metadata
    """
    # Import here to avoid circular dependencies
    from app.database.session import async_session_maker
    from app.services.apr_snapshot_service import apr_snapshot_service

    # Wait for database initialization
    await asyncio.sleep(10)

    logger.info("APR snapshot background task started")

    while True:
        try:
            # Check if session maker is initialized
            if async_session_maker is None:
                logger.warning("Database not initialized, skipping APR snapshot capture")
                await asyncio.sleep(3600)  # Wait 1 hour
                continue

            logger.info("=" * 80)
            logger.info(f"Starting APR snapshot capture at {datetime.utcnow().isoformat()}")

            async with async_session_maker() as db:
                # Capture snapshots for all whitelisted pools
                snapshots = await apr_snapshot_service.capture_all_whitelisted(db)

                logger.info("-" * 80)
                logger.info(f"Successfully captured {len(snapshots)} APR snapshots:")
                for snapshot in snapshots:
                    logger.info(
                        f"  - {snapshot.pool_symbol} ({snapshot.pool_address[:10]}...): "
                        f"APR={snapshot.apr}%, Effective APR (std)={snapshot.effective_apr_standard}%"
                    )
                logger.info("=" * 80)

        except Exception as e:
            logger.error(f"Error in APR snapshot background task: {e}", exc_info=True)

        # Run every hour (3600 seconds)
        logger.info("Sleeping for 1 hour until next APR snapshot capture...")
        await asyncio.sleep(3600)
