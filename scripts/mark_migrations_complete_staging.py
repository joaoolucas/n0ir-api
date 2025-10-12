"""
Mark all migrations as complete in the alembic_version table.
Run this on staging if the database schema is already up to date but alembic thinks migrations need to run.
"""
import asyncio
import os
from sqlalchemy import text
from app.database.session import get_db

async def mark_migrations_complete():
    """Mark all migrations as complete by setting alembic_version to latest."""
    async for db in get_db():
        try:
            # Delete any existing version
            await db.execute(text("DELETE FROM alembic_version"))

            # Insert the latest migration version
            await db.execute(text("INSERT INTO alembic_version (version_num) VALUES ('034_add_apr_snapshots')"))

            await db.commit()
            print("✅ Marked all migrations as complete (version: 034_add_apr_snapshots)")
        except Exception as e:
            print(f"❌ Error marking migrations complete: {e}")
            await db.rollback()
        finally:
            break

if __name__ == "__main__":
    asyncio.run(mark_migrations_complete())
