#!/usr/bin/env python3
"""
Delete the misidentified swap transaction.
"""

import asyncio
import asyncpg
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')

async def delete_swap():
    """Delete the swap transaction."""
    
    # Use the Railway database URL from environment
    database_url = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@postgres.railway.internal:5432/railway"
    
    # Try external URL if internal doesn't work (for local testing)
    external_url = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@autorack.proxy.rlwy.net:23556/railway"
    
    tx_id = '13431200-06a6-4a99-98f4-5406404d2810'
    
    print(f"REMOVING MISIDENTIFIED SWAP TRANSACTION")
    print("="*60)
    print(f"Transaction ID: {tx_id}")
    
    # Try external URL for local access
    try:
        print("Connecting to database...")
        conn = await asyncpg.connect(external_url)
    except Exception as e:
        print(f"Failed with external URL: {e}")
        print("This script needs to be run from Railway environment or with proper DB access")
        return
    
    try:
        # First check if it exists
        existing = await conn.fetchrow(
            "SELECT id, tx_type, amount_usdc FROM transactions WHERE id = $1",
            tx_id
        )
        
        if existing:
            print(f"Found transaction: type={existing['tx_type']}, amount={existing['amount_usdc']}")
            
            # Delete it
            deleted = await conn.fetchval(
                "DELETE FROM transactions WHERE id = $1 RETURNING id",
                tx_id
            )
            
            if deleted:
                print(f"✅ Successfully deleted transaction: {deleted}")
        else:
            print(f"ℹ️ Transaction not found in database")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(delete_swap())
