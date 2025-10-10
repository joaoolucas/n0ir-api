"""
Admin endpoints for maintenance tasks
"""
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import text
from app.database.session import get_db
from app.core.config import settings
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.post("/mark-migrations-complete")
async def mark_migrations_complete(
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Mark all migrations as complete in alembic_version table.
    This is useful when the database schema is already up to date but alembic thinks migrations need to run.

    Requires API_BEARER_TOKEN for authentication.
    """
    # Check authorization
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.replace("Bearer ", "")
    if token != settings.api_bearer_token:
        raise HTTPException(status_code=403, detail="Invalid token")

    try:
        # Create alembic_version table if it doesn't exist
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num VARCHAR(32) NOT NULL,
                CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
            )
        """))

        # Delete any existing version
        await db.execute(text("DELETE FROM alembic_version"))

        # Insert the latest migration version
        await db.execute(text("INSERT INTO alembic_version (version_num) VALUES ('034_add_apr_snapshots')"))

        await db.commit()

        return {
            "success": True,
            "message": "Marked all migrations as complete (version: 034_add_apr_snapshots)"
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error marking migrations complete: {str(e)}")
