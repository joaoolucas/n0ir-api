#!/usr/bin/env python3
"""
Remove the misidentified swap transaction.
"""

import asyncio
import asyncpg
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')

async def remove_swap():
    """Remove the swap transaction."""
    
    # Try Railway database URL first
    database_url = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@postgres.railway.internal:5432/railway"
    
    tx_id = '13431200-06a6-4a99-98f4-5406404d2810'
    
    print(f"REMOVING MISIDENTIFIED SWAP TRANSACTION")
    print("="*60)
    print(f"Transaction ID: {tx_id}")
    
    conn = await asyncpg.connect(database_url)
    
    try:
        # Remove the transaction
        deleted = await conn.fetchval(
            "DELETE FROM transactions WHERE id = $1 RETURNING id",
            tx_id
        )
        
        if deleted:
            print(f"✅ Deleted transaction: {deleted}")
        else:
            print(f"ℹ️ Transaction not found: {tx_id}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(remove_swap())
