#!/usr/bin/env python3
"""Reset all database tables except users."""

import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def reset_tables():
    """Reset all tables except users."""
    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set in environment")
    
    # Convert to async URL if needed
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
    elif database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://")
    
    # Create async engine
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    try:
        async with async_session() as session:
            async with session.begin():
                logger.info("Starting table reset...")
                
                # Delete all transactions first (they reference positions)
                result = await session.execute(text("DELETE FROM transactions"))
                transactions_deleted = result.rowcount
                logger.info(f"Deleted {transactions_deleted} transactions")
                
                # Delete all positions after transactions are gone
                result = await session.execute(text("DELETE FROM positions"))
                positions_deleted = result.rowcount
                logger.info(f"Deleted {positions_deleted} positions")
                
                # Check which columns exist in users table and reset them
                result = await session.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'users' 
                    AND column_name IN ('realized_pnl_usd', 'unrealized_pnl_usd', 
                                       'realized_pnl_percentage', 'unrealized_pnl_percentage')
                """))
                columns_to_reset = [row[0] for row in result]
                
                if columns_to_reset:
                    # Build dynamic UPDATE statement based on existing columns
                    set_clauses = [f"{col} = 0" for col in columns_to_reset]
                    where_clauses = [f"{col} IS NOT NULL" for col in columns_to_reset]
                    
                    update_query = f"""
                        UPDATE users SET 
                            {', '.join(set_clauses)}
                        WHERE {' OR '.join(where_clauses)}
                    """
                    
                    result = await session.execute(text(update_query))
                    users_updated = result.rowcount
                    logger.info(f"Reset PnL fields ({', '.join(columns_to_reset)}) for {users_updated} users")
                else:
                    users_updated = 0
                    logger.info("No PnL fields found in users table to reset")
                
                # Count remaining users
                result = await session.execute(text("SELECT COUNT(*) FROM users"))
                user_count = result.scalar()
                logger.info(f"Kept {user_count} users")
                
                # Commit is automatic with session.begin()
                logger.info("Table reset completed successfully!")
                
                # Show summary
                print("\n" + "="*50)
                print("DATABASE RESET SUMMARY")
                print("="*50)
                print(f"✅ Positions deleted: {positions_deleted}")
                print(f"✅ Transactions deleted: {transactions_deleted}")
                print(f"✅ User PnL reset: {users_updated}")
                print(f"✅ Users preserved: {user_count}")
                print("="*50)
                
    except Exception as e:
        logger.error(f"Error resetting tables: {e}")
        raise
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(reset_tables())