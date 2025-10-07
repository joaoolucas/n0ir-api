#!/usr/bin/env python3
"""
Delete the misidentified swap transaction.
"""

import asyncio
import asyncpg

async def delete_swap():
    """Delete the swap transaction."""
    
    # Use the public database URL
    database_url = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"
    
    tx_id = '13431200-06a6-4a99-98f4-5406404d2810'
    
    print(f"REMOVING MISIDENTIFIED SWAP TRANSACTION")
    print("="*60)
    print(f"Transaction ID: {tx_id}")
    
    print("Connecting to database...")
    conn = await asyncpg.connect(database_url)
    
    try:
        # First check if it exists
        existing = await conn.fetchrow(
            "SELECT id, tx_type, amount_usdc, created_at FROM transactions WHERE id = $1",
            tx_id
        )
        
        if existing:
            print(f"Found transaction:")
            print(f"  Type: {existing['tx_type']}")
            print(f"  Amount: {existing['amount_usdc']} USDC")
            print(f"  Created: {existing['created_at']}")
            
            # Delete it
            deleted = await conn.fetchval(
                "DELETE FROM transactions WHERE id = $1 RETURNING id",
                tx_id
            )
            
            if deleted:
                print(f"\n✅ Successfully deleted transaction: {deleted}")
        else:
            print(f"ℹ️ Transaction not found in database (may have been already deleted)")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()
        print("\nDatabase connection closed.")

if __name__ == "__main__":
    asyncio.run(delete_swap())
