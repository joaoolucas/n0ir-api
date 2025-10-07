"""Background position syncer to keep user data warm."""

import asyncio
from loguru import logger


async def sync_active_users():
    """
    Background task to sync all active users every 30 seconds.

    This keeps the cache warm so that most user requests can skip the sync entirely,
    resulting in much faster response times.
    """
    # Import here to avoid circular dependencies and ensure init happens first
    from app.database.session import async_session_maker
    from app.services.user_service import UserService

    # Wait for database initialization
    await asyncio.sleep(5)

    while True:
        try:
            # Import fresh each time to get current session maker
            from app.database.session import async_session_maker

            # Check if session maker is initialized
            if async_session_maker is None:
                logger.warning("Database not initialized, skipping background sync")
                await asyncio.sleep(30)
                continue

            async with async_session_maker() as db:
                service = UserService(db)
                users = await service.list_all_users()

                synced_count = 0
                skipped_count = 0
                error_count = 0

                for user in users:
                    try:
                        result = await service.sync_blockchain_data(user.user_id)
                        if result.get('skipped'):
                            skipped_count += 1
                        elif result.get('success'):
                            synced_count += 1
                        else:
                            error_count += 1
                    except Exception as e:
                        logger.error(f"Failed to sync user {user.user_id}: {e}")
                        error_count += 1

                logger.info(
                    f"Background sync completed: {synced_count} synced, "
                    f"{skipped_count} skipped, {error_count} errors (total: {len(users)} users)"
                )

        except Exception as e:
            logger.error(f"Background syncer error: {e}")

        # Run every 30 seconds
        await asyncio.sleep(30)
