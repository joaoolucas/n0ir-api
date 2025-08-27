#!/usr/bin/env python3
"""Remove fake BALANCE_SYNC transactions and recalculate totals."""

import asyncio
import asyncpg
from decimal import Decimal
from urllib.parse import urlparse

# Database URL from Railway staging
DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

async def remove_fake_transactions():
    """Remove fake transactions and recalculate user totals."""
    
    # Parse database URL
    parsed = urlparse(DATABASE_URL)
    
    # Connect to database
    conn = await asyncpg.connect(
        host=parsed.hostname,
        port=parsed.port,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip('/'),
        ssl='require'
    )
    
    print("Connected to staging database")
    print("=" * 80)
    
    try:
        user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
        
        # 1. Find fake transactions
        print("\n🔍 Finding fake transactions...")
        
        # Find transactions with fake tx_hash patterns or no block numbers
        fake_txs = await conn.fetch("""
            SELECT 
                id,
                tx_hash,
                tx_type,
                block_number,
                event_data->>'amount_usdc' as amount
            FROM transactions 
            WHERE user_id = $1
            AND (
                tx_hash LIKE '%BALANCE_SYNC%'
                OR tx_hash LIKE '0x%' AND LENGTH(tx_hash) != 66
                OR (block_number IS NULL AND status = 'CONFIRMED')
                OR tx_hash = '0x' || SUBSTRING(tx_hash FROM 3 FOR 8)
            )
            ORDER BY created_at DESC
        """, user_id)
        
        if fake_txs:
            print(f"\n⚠️ Found {len(fake_txs)} fake transactions:")
            for tx in fake_txs:
                hash_display = tx['tx_hash'][:30] if tx['tx_hash'] else 'None'
                print(f"  ID: {tx['id']}, Type: {tx['tx_type']}, Hash: {hash_display}..., Amount: {tx['amount']}")
            
            # 2. Delete fake transactions
            print(f"\n🗑️ Deleting fake transactions...")
            
            ids_to_delete = [tx['id'] for tx in fake_txs]
            deleted = await conn.execute("""
                DELETE FROM transactions 
                WHERE id = ANY($1::uuid[])
            """, ids_to_delete)
            
            count = int(deleted.split()[-1]) if deleted else 0
            print(f"  ✅ Deleted {count} fake transactions")
        else:
            print("  ✅ No fake transactions found")
        
        # 3. Also check for transactions without proper hashes
        print("\n🔍 Checking for transactions with invalid hashes...")
        
        invalid_txs = await conn.fetch("""
            SELECT 
                id,
                tx_hash,
                tx_type,
                block_number
            FROM transactions 
            WHERE user_id = $1
            AND status = 'CONFIRMED'
            AND (
                LENGTH(tx_hash) != 66 
                OR tx_hash NOT LIKE '0x%'
                OR tx_hash IS NULL
            )
        """, user_id)
        
        if invalid_txs:
            print(f"\n⚠️ Found {len(invalid_txs)} transactions with invalid hashes:")
            for tx in invalid_txs:
                print(f"  ID: {tx['id']}, Type: {tx['tx_type']}, Hash: {tx['tx_hash']}")
            
            print(f"\n🗑️ Deleting transactions with invalid hashes...")
            ids_to_delete = [tx['id'] for tx in invalid_txs]
            deleted = await conn.execute("""
                DELETE FROM transactions 
                WHERE id = ANY($1::uuid[])
            """, ids_to_delete)
            
            count = int(deleted.split()[-1]) if deleted else 0
            print(f"  ✅ Deleted {count} transactions with invalid hashes")
        
        # 4. Recalculate totals from remaining real transactions
        print("\n📊 Recalculating totals from real transactions only...")
        
        # Get real deposits total
        deposits_total = await conn.fetchval("""
            SELECT COALESCE(SUM((event_data->>'amount_usdc')::NUMERIC), 0)
            FROM transactions 
            WHERE user_id = $1
            AND tx_type = 'DEPOSIT'
            AND status = 'CONFIRMED'
            AND LENGTH(tx_hash) = 66
            AND tx_hash LIKE '0x%'
            AND block_number IS NOT NULL
        """, user_id)
        
        # Get real withdrawals total
        withdrawals_total = await conn.fetchval("""
            SELECT COALESCE(SUM((event_data->>'amount_usdc')::NUMERIC), 0)
            FROM transactions 
            WHERE user_id = $1
            AND tx_type = 'WITHDRAWAL'
            AND status = 'CONFIRMED'
            AND LENGTH(tx_hash) = 66
            AND tx_hash LIKE '0x%'
            AND block_number IS NOT NULL
        """, user_id)
        
        print(f"  Real Deposits Total: {deposits_total:.6f} USDC")
        print(f"  Real Withdrawals Total: {withdrawals_total:.6f} USDC")
        
        # 5. Update user record with correct totals
        print("\n🔧 Updating user record with correct totals...")
        
        await conn.execute("""
            UPDATE users 
            SET 
                total_deposits_usdc = $2,
                total_withdrawals_usdc = $3
            WHERE user_id = $1
        """, user_id, float(deposits_total), float(withdrawals_total))
        
        print("  ✅ Updated user totals")
        
        # 6. Recalculate balance with correct formula
        print("\n💰 Recalculating balance with correct formula...")
        
        # Get position totals
        position_in = await conn.fetchval("""
            SELECT COALESCE(SUM((event_data->>'usdcIn')::NUMERIC / 1000000), 0)
            FROM transactions 
            WHERE user_id = $1
            AND tx_type = 'POSITION_CREATED'
            AND status = 'CONFIRMED'
        """, user_id)
        
        position_out = await conn.fetchval("""
            SELECT COALESCE(SUM((event_data->>'usdcOut')::NUMERIC / 1000000), 0)
            FROM transactions 
            WHERE user_id = $1
            AND tx_type = 'POSITION_CLOSED'
            AND status = 'CONFIRMED'
        """, user_id)
        
        aero_swaps = await conn.fetchval("""
            SELECT COALESCE(SUM((event_data->>'amount_usdc')::NUMERIC), 0)
            FROM transactions 
            WHERE user_id = $1
            AND tx_type = 'AERO_SWAP'
            AND status = 'CONFIRMED'
        """, user_id)
        
        # Calculate correct balance
        balance = deposits_total - withdrawals_total - position_in + position_out + aero_swaps
        
        print(f"  Deposits:      +{deposits_total:.6f}")
        print(f"  Withdrawals:   -{withdrawals_total:.6f}")
        print(f"  Positions IN:  -{position_in:.6f}")
        print(f"  Positions OUT: +{position_out:.6f}")
        print(f"  AERO Swaps:    +{aero_swaps:.6f}")
        print(f"  ─────────────────────────")
        print(f"  Balance:       {balance:.6f} USDC")
        
        await conn.execute("""
            UPDATE users 
            SET usdc_balance = $2
            WHERE user_id = $1
        """, user_id, float(balance))
        
        print("\n✅ Balance updated")
        
        # 7. Final verification
        print("\n📊 FINAL VERIFICATION:")
        
        tx_counts = await conn.fetch("""
            SELECT 
                tx_type,
                COUNT(*) as count,
                COUNT(CASE WHEN LENGTH(tx_hash) = 66 THEN 1 END) as valid_hash,
                COUNT(block_number) as with_block
            FROM transactions 
            WHERE user_id = $1
            AND status = 'CONFIRMED'
            GROUP BY tx_type
            ORDER BY count DESC
        """, user_id)
        
        print("\nTransaction counts after cleanup:")
        for tc in tx_counts:
            print(f"  {tc['tx_type']:20} Total: {tc['count']:3}  Valid Hash: {tc['valid_hash']:3}  With Block: {tc['with_block']:3}")
        
        # Check final user values
        user = await conn.fetchrow("""
            SELECT 
                usdc_balance,
                total_deposits_usdc,
                total_withdrawals_usdc
            FROM users 
            WHERE user_id = $1
        """, user_id)
        
        print(f"\nFinal User Values:")
        print(f"  Balance: {user['usdc_balance']:.6f} USDC")
        print(f"  Total Deposits: {user['total_deposits_usdc']:.6f} USDC")
        print(f"  Total Withdrawals: {user['total_withdrawals_usdc']:.6f} USDC")
        
        print("\n✨ Cleanup completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise
    finally:
        await conn.close()
        print("\nDisconnected from database")


if __name__ == "__main__":
    print("🧹 Removing fake transactions and recalculating totals")
    print("=" * 80)
    asyncio.run(remove_fake_transactions())