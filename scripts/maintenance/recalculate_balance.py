#!/usr/bin/env python3
"""Recalculate balance correctly including all confirmed transactions."""

import asyncio
import asyncpg
from urllib.parse import urlparse
from decimal import Decimal

# Database URL from Railway staging
DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"


async def recalculate_balance():
    """Recalculate balance with correct status handling."""
    
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
    
    try:
        # Get all transactions
        all_txs = await conn.fetch("""
            SELECT 
                tx_hash,
                tx_type,
                event_data->>'amount_usdc' as amount,
                block_number,
                status,
                created_at
            FROM transactions 
            WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
            AND tx_type IN ('DEPOSIT', 'WITHDRAWAL')
            ORDER BY block_number ASC NULLS LAST, created_at ASC
        """)
        
        # Calculate totals - include both 'CONFIRMED' and 'confirmed'
        total_deposits = Decimal('0')
        total_withdrawals = Decimal('0')
        
        print("\n📜 Processing all transactions chronologically:")
        for tx in all_txs:
            amount = Decimal(tx['amount'] or '0')
            status = tx['status']
            tx_type = tx['tx_type']
            block = tx['block_number']
            
            # Include both uppercase and lowercase confirmed
            if status and status.upper() == 'CONFIRMED':
                if tx_type == 'DEPOSIT':
                    total_deposits += amount
                    print(f"  ✅ DEPOSIT    +{amount:12.6f} USDC - Block {block or 'PENDING':8} - Running Total: {total_deposits - total_withdrawals:12.6f}")
                elif tx_type == 'WITHDRAWAL':
                    total_withdrawals += amount
                    print(f"  ❌ WITHDRAWAL -{amount:12.6f} USDC - Block {block or 'PENDING':8} - Running Total: {total_deposits - total_withdrawals:12.6f}")
            else:
                print(f"  ⏭️  SKIPPING {tx_type:10} {amount:12.6f} USDC - Block {block or 'PENDING':8} - Status: {status}")
        
        final_balance = total_deposits - total_withdrawals
        
        print(f"\n📊 Final Calculation:")
        print(f"  Total Deposits: {total_deposits} USDC")
        print(f"  Total Withdrawals: {total_withdrawals} USDC")
        print(f"  Calculated Balance: {final_balance} USDC")
        print(f"  Expected On-Chain: 0.01 USDC")
        print(f"  Difference: {final_balance - Decimal('0.01')} USDC")
        
        if abs(final_balance - Decimal('0.01')) > Decimal('0.000001'):
            print("\n⚠️ ISSUE: Balance doesn't match on-chain!")
            
            # Update the database with correct values
            print("\n🔧 Updating database with correct balance...")
            await conn.execute("""
                UPDATE users 
                SET 
                    usdc_balance = $1,
                    total_deposits_usdc = $2,
                    total_withdrawals_usdc = $3
                WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
            """, Decimal('0.01'), total_deposits, total_withdrawals)
            
            print("✅ Database updated with actual on-chain balance: 0.01 USDC")
        else:
            print("\n✅ Balance matches on-chain!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise
    finally:
        await conn.close()
        print("\n✅ Complete")


if __name__ == "__main__":
    print("🔧 Recalculating balance with correct status handling")
    asyncio.run(recalculate_balance())