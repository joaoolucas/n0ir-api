#!/usr/bin/env python3
"""
SAFELY clean all data for user 0xC2952cc28EDf37B053188D89e6ac888B9855d132
WITHOUT affecting other users or dropping the user from users table.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from decimal import Decimal

DATABASE_URL = "postgresql://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway"

def clean_user_data():
    """Clean all data for specific user ONLY."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # THE ONLY USER WE'RE CLEANING
    user_id = "0xC2952cc28EDf37B053188D89e6ac888B9855d132"
    
    try:
        print(f"=== CLEANING DATA FOR USER: {user_id} ===\n")
        
        # 1. First, verify the user exists
        cur.execute("SELECT user_id, cdp_wallet_address FROM users WHERE user_id = %s", (user_id,))
        user = cur.fetchone()
        
        if not user:
            print(f"❌ User {user_id} not found!")
            return
        
        print(f"✅ Found user: {user['user_id']}")
        print(f"   CDP Wallet: {user['cdp_wallet_address']}\n")
        
        # 2. Count and delete transactions
        cur.execute("SELECT COUNT(*) as count FROM transactions WHERE user_id = %s", (user_id,))
        tx_count = cur.fetchone()['count']
        print(f"📊 Found {tx_count} transactions to delete")
        
        if tx_count > 0:
            # Show sample before deletion
            cur.execute("""
                SELECT id, tx_type, status 
                FROM transactions 
                WHERE user_id = %s 
                LIMIT 5
            """, (user_id,))
            samples = cur.fetchall()
            for s in samples:
                print(f"   - {s['id']}: {s['tx_type']} ({s['status']})")
            if tx_count > 5:
                print(f"   ... and {tx_count - 5} more")
            
            # DELETE transactions
            cur.execute("""
                DELETE FROM transactions 
                WHERE user_id = %s
                RETURNING id
            """, (user_id,))
            deleted_txs = cur.fetchall()
            print(f"✅ Deleted {len(deleted_txs)} transactions\n")
        
        # 3. Count and delete positions
        cur.execute("SELECT COUNT(*) as count FROM positions WHERE user_id = %s", (user_id,))
        pos_count = cur.fetchone()['count']
        print(f"📊 Found {pos_count} positions to delete")
        
        if pos_count > 0:
            # Show positions before deletion
            cur.execute("""
                SELECT token_id, pool_name, status 
                FROM positions 
                WHERE user_id = %s
            """, (user_id,))
            positions = cur.fetchall()
            for p in positions:
                print(f"   - Token {p['token_id']}: {p['pool_name']} ({p['status']})")
            
            # DELETE positions
            cur.execute("""
                DELETE FROM positions 
                WHERE user_id = %s
                RETURNING token_id
            """, (user_id,))
            deleted_pos = cur.fetchall()
            print(f"✅ Deleted {len(deleted_pos)} positions\n")
        
        # 4. Reset user balance fields (but keep the user!)
        print("🔄 Resetting user balance fields...")
        cur.execute("""
            UPDATE users 
            SET 
                total_deposits_usdc = 0,
                total_withdrawals_usdc = 0,
                unrealized_pnl_usd = 0,
                unrealized_pnl_pct = 0,
                realized_pnl_usd = 0,
                realized_pnl_pct = 0,
                updated_at = NOW()
            WHERE user_id = %s
            RETURNING user_id
        """, (user_id,))
        
        updated = cur.fetchone()
        if updated:
            print(f"✅ Reset balance fields for user {user_id}\n")
        
        # 5. Verify user still exists and show final state
        cur.execute("""
            SELECT user_id, cdp_wallet_address, 
                   total_deposits_usdc, total_withdrawals_usdc,
                   unrealized_pnl_usd, realized_pnl_usd
            FROM users 
            WHERE user_id = %s
        """, (user_id,))
        final_user = cur.fetchone()
        
        if final_user:
            print("=== FINAL USER STATE ===")
            print(f"✅ User still exists: {final_user['user_id']}")
            print(f"   CDP Wallet: {final_user['cdp_wallet_address']}")
            print(f"   Deposits: ${final_user['total_deposits_usdc']}")
            print(f"   Withdrawals: ${final_user['total_withdrawals_usdc']}")
            print(f"   Unrealized PnL: ${final_user['unrealized_pnl_usd']}")
            print(f"   Realized PnL: ${final_user['realized_pnl_usd']}")
        
        # COMMIT all changes
        conn.commit()
        print("\n✅ All changes committed successfully!")
        print("✅ User data cleaned WITHOUT affecting other users")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
        print("🔄 Rolled back all changes - no data was modified")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    # Safety confirmation
    print("⚠️  WARNING: This will delete all transactions and positions for user:")
    print("   0xC2952cc28EDf37B053188D89e6ac888B9855d132")
    print("   But will KEEP the user in the users table.\n")
    
    confirm = input("Type 'YES' to proceed: ")
    if confirm == "YES":
        clean_user_data()
    else:
        print("❌ Cancelled - no changes made")