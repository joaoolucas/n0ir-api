#!/usr/bin/env python3
"""
Remove the manually created gauge position and transaction.
"""

import asyncio
import asyncpg
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


async def remove_gauge_data():
    """Remove the manually created gauge data."""
    
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        database_url = os.getenv('DATABASE_PRIVATE_URL')
    
    if not database_url:
        print("❌ No database URL found")
        return
    
    tx_hash = '0x6760b89cbe37d7441dd49de1e1239f9362f0f9741c024f0ac93dec4b7bc46d00'
    position_id = 26256789
    
    print("REMOVING MANUALLY CREATED GAUGE DATA")
    print("="*60)
    
    conn = await asyncpg.connect(database_url)
    
    try:
        # Remove the transaction
        deleted_tx = await conn.fetchval(
            "DELETE FROM transactions WHERE tx_hash = $1 RETURNING id",
            tx_hash
        )
        
        if deleted_tx:
            print(f"✅ Deleted transaction: {deleted_tx}")
        else:
            print(f"ℹ️ No transaction found with hash: {tx_hash}")
        
        # Remove the position
        deleted_pos = await conn.fetchval(
            "DELETE FROM positions WHERE token_id = $1 RETURNING token_id",
            position_id
        )
        
        if deleted_pos:
            print(f"✅ Deleted position: {deleted_pos}")
        else:
            print(f"ℹ️ No position found with ID: {position_id}")
        
        print("\n✅ Cleanup complete. The API should now detect these automatically.")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(remove_gauge_data())
