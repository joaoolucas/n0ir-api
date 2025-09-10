#!/usr/bin/env python3
"""Fix status capitalization and check withdrawal issues in staging database."""

import asyncio
import asyncpg
from datetime import datetime, timedelta

# Database URL from Railway staging
DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"


async def fix_status_and_check_withdrawals():
    """Fix status capitalization and check recent withdrawals."""
    
    # Connect to database
    conn = await asyncpg.connect(DATABASE_URL, ssl='require')
    
    print("Connected to staging database")
    
    try:
        # Fix users table status - THIS IS THE CRITICAL FIX
        print("\n👤 Fixing users table status...")
        
        # First check current status values
        current_statuses = await conn.fetch("""
            SELECT status, COUNT(*) as count 
            FROM users 
            GROUP BY status 
            ORDER BY status
        """)
        print("  Current status distribution:")
        for row in current_statuses:
            print(f"    {row['status']}: {row['count']} records")
        
        # Update active status
        result = await conn.execute("""
            UPDATE users 
            SET status = 'ACTIVE'
            WHERE LOWER(status) = 'active'
        """)
        count = int(result.split()[-1]) if result else 0
        print(f"  Updated {count} users from 'active' to 'ACTIVE'")
        
        # Fix transactions table status
        print("\n📝 Fixing transactions table status...")
        
        # Update confirmed status
        result = await conn.execute("""
            UPDATE transactions 
            SET status = 'CONFIRMED'
            WHERE LOWER(status) = 'confirmed'
        """)
        count = int(result.split()[-1]) if result else 0
        print(f"  Updated {count} transactions from 'confirmed' to 'CONFIRMED'")
        
        # Fix positions table status
        print("\n📊 Fixing positions table status...")
        
        # Update active status
        result = await conn.execute("""
            UPDATE positions 
            SET status = 'ACTIVE'
            WHERE LOWER(status) = 'active'
        """)
        count = int(result.split()[-1]) if result else 0
        print(f"  Updated {count} positions from 'active' to 'ACTIVE'")
        
        # Update closed status
        result = await conn.execute("""
            UPDATE positions 
            SET status = 'CLOSED'
            WHERE LOWER(status) = 'closed'
        """)
        count = int(result.split()[-1]) if result else 0
        print(f"  Updated {count} positions from 'closed' to 'CLOSED'")
        
        # Verify the fix
        print("\n✅ Verification of users table:")
        user_statuses = await conn.fetch("""
            SELECT status, COUNT(*) as count 
            FROM users 
            GROUP BY status 
            ORDER BY status
        """)
        print("Users status distribution (AFTER FIX):")
        for row in user_statuses:
            print(f"  {row['status']}: {row['count']} records")
        
        # Check for recent withdrawals
        print("\n💰 Checking recent withdrawals (last 30 minutes)...")
        recent_withdrawals = await conn.fetch("""
            SELECT 
                transaction_id,
                user_id,
                tx_type,
                status,
                event_data,
                created_at,
                tx_hash
            FROM transactions 
            WHERE tx_type IN ('WITHDRAWAL', 'WITHDRAW')
                AND created_at > $1
            ORDER BY created_at DESC
            LIMIT 10
        """, datetime.now() - timedelta(minutes=30))
        
        if recent_withdrawals:
            print(f"Found {len(recent_withdrawals)} recent withdrawals:")
            for tx in recent_withdrawals:
                amount = 0
                if tx['event_data']:
                    amount = tx['event_data'].get('amount_usdc', tx['event_data'].get('usdc_out', 0))
                print(f"  - {tx['created_at']}: User {tx['user_id'][:8]}... withdrew {amount} USDC")
                print(f"    Status: {tx['status']}, Hash: {tx['tx_hash'][:10] if tx['tx_hash'] else 'None'}")
        else:
            print("  No withdrawals found in the last 30 minutes")
        
        # Check all withdrawals for specific user if needed
        print("\n🔍 Checking ALL withdrawals in database...")
        all_withdrawals = await conn.fetch("""
            SELECT 
                user_id,
                COUNT(*) as count,
                SUM((event_data->>'amount_usdc')::numeric) as total_usdc
            FROM transactions 
            WHERE tx_type IN ('WITHDRAWAL', 'WITHDRAW')
            GROUP BY user_id
        """)
        
        if all_withdrawals:
            print(f"Found withdrawals for {len(all_withdrawals)} users:")
            for row in all_withdrawals:
                print(f"  - User {row['user_id'][:8]}...: {row['count']} withdrawals, Total: {row['total_usdc'] or 0} USDC")
        else:
            print("  No withdrawals found in the entire database")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise
    finally:
        await conn.close()
        print("\n📊 Database check complete")


if __name__ == "__main__":
    print("🔧 Fixing status capitalization and checking withdrawals")
    print("   This specifically fixes the UserResponse validation error")
    asyncio.run(fix_status_and_check_withdrawals())