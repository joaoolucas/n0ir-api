#!/usr/bin/env python3
"""Direct fix for missing has_deposited_50_usdc column"""

import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def fix_missing_column():
    """Add the missing has_deposited_50_usdc column directly"""
    
    # Get database URL from environment
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set")
        return False
    
    # Convert to asyncpg URL if needed
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    print(f"Connecting to database...")
    
    try:
        # Create engine
        engine = create_async_engine(db_url)
        
        async with engine.begin() as conn:
            # Check if column exists
            result = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'users' 
                    AND column_name = 'has_deposited_50_usdc'
                )
            """))
            column_exists = result.scalar()
            
            if column_exists:
                print("✅ Column has_deposited_50_usdc already exists")
                await engine.dispose()
                return True
            
            print("Adding has_deposited_50_usdc column...")
            
            # Add the column
            await conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN has_deposited_50_usdc BOOLEAN NOT NULL DEFAULT FALSE
            """))
            
            print("Updating existing users based on net deposits...")
            
            # Update existing users based on their NET deposits
            await conn.execute(text("""
                UPDATE users 
                SET has_deposited_50_usdc = TRUE 
                WHERE (total_deposits_usdc - total_withdrawals_usdc) >= 50
            """))
            
            print("✅ Successfully added has_deposited_50_usdc column")
        
        await engine.dispose()
        return True
        
    except Exception as e:
        print(f"❌ Error adding column: {e}")
        return False

async def main():
    """Main function"""
    print("=== Fixing missing has_deposited_50_usdc column ===")
    success = await fix_missing_column()
    
    if not success:
        print("Failed to fix missing column")
        exit(1)
    else:
        print("✅ Column fix completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())