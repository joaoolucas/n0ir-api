#!/usr/bin/env python3
"""Fix the user_id case in the database to match the wallet's original creator.

The wallet 0x7b3106f56447c9c313c19f519b290ff4e293d573 was created with mixed-case user ID:
0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51

But the database has it stored as lowercase. This script fixes that.
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor

def main():
    # Get DATABASE_URL from Railway environment
    database_url = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"

    # The correct mixed-case user ID that was used to create the wallet
    correct_user_id = "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51"
    lowercase_user_id = "0xdbe4e3bcb15b221324b776db6f0cbff24918ea51"
    wallet_address = "0x7b3106f56447c9c313c19f519b290ff4e293d573"

    print(f"Connecting to database...")
    conn = psycopg2.connect(database_url)
    conn.autocommit = False  # Use explicit transactions
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Check current state
        print(f"\n1. Checking current users table...")
        cur.execute("""
            SELECT user_id, cdp_wallet_address
            FROM users
            WHERE LOWER(user_id) = %s
        """, (lowercase_user_id,))

        users = cur.fetchall()
        for user in users:
            print(f"   Found user: {user['user_id']}, wallet: {user['cdp_wallet_address']}")

        # Check positions - first check what columns exist
        print(f"\n2. Checking positions...")
        try:
            # Try with different column names
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'positions'
                LIMIT 5
            """)
            cols = cur.fetchall()
            print(f"   Available columns: {[c['column_name'] for c in cols]}")

            # Now query positions with correct column names
            cur.execute("""
                SELECT token_id, user_id, status
                FROM positions
                WHERE LOWER(user_id) = %s
            """, (lowercase_user_id,))

            positions = cur.fetchall()
            for pos in positions:
                print(f"   Position token_id {pos['token_id']}: user_id={pos['user_id']}, status={pos['status']}")
        except Exception as e:
            print(f"   Error checking positions: {e}")
            positions = []

        # Check transactions
        print(f"\n3. Checking transactions...")
        cur.execute("""
            SELECT COUNT(*) as count
            FROM transactions
            WHERE LOWER(user_id) = %s
        """, (lowercase_user_id,))

        tx_count = cur.fetchone()['count']
        print(f"   Found {tx_count} transactions")

        # Now update everything to use the correct mixed-case user ID
        print(f"\n4. Updating to correct mixed-case user ID: {correct_user_id}")

        # Strategy: We'll temporarily remove constraints, do the updates, then restore

        # 1. First, drop the foreign key constraints temporarily
        print("   Temporarily dropping foreign key constraints...")
        cur.execute("""
            ALTER TABLE positions
            DROP CONSTRAINT IF EXISTS positions_user_id_fkey
        """)
        cur.execute("""
            ALTER TABLE transactions
            DROP CONSTRAINT IF EXISTS transactions_user_id_fkey
        """)

        # 2. Update the users table
        cur.execute("""
            UPDATE users
            SET user_id = %s
            WHERE user_id = %s
        """, (correct_user_id, lowercase_user_id))
        print(f"   Updated {cur.rowcount} users")

        # 3. Update positions
        cur.execute("""
            UPDATE positions
            SET user_id = %s
            WHERE user_id = %s
        """, (correct_user_id, lowercase_user_id))
        print(f"   Updated {cur.rowcount} positions")

        # 4. Update transactions
        cur.execute("""
            UPDATE transactions
            SET user_id = %s
            WHERE user_id = %s
        """, (correct_user_id, lowercase_user_id))
        print(f"   Updated {cur.rowcount} transactions")

        # 5. Restore the foreign key constraints
        print("   Restoring foreign key constraints...")
        cur.execute("""
            ALTER TABLE positions
            ADD CONSTRAINT positions_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        """)
        cur.execute("""
            ALTER TABLE transactions
            ADD CONSTRAINT transactions_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        """)

        # Commit changes
        conn.commit()
        print(f"\n✅ Successfully updated all records to use mixed-case user ID!")

        # Verify the changes
        print(f"\n5. Verifying changes...")
        cur.execute("""
            SELECT user_id, cdp_wallet_address
            FROM users
            WHERE user_id = %s
        """, (correct_user_id,))

        user = cur.fetchone()
        if user:
            print(f"   ✓ User now has correct ID: {user['user_id']}")
            print(f"   ✓ CDP wallet: {user['cdp_wallet_address']}")

        cur.execute("""
            SELECT COUNT(*) as pos_count
            FROM positions
            WHERE user_id = %s AND status = 'ACTIVE'
        """, (correct_user_id,))

        count = cur.fetchone()['pos_count']
        print(f"   ✓ Active positions: {count}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    print(f"\n🎯 Done! The user ID is now correctly stored as mixed-case.")
    print(f"   This matches the case that was used to create the CDP wallet.")

if __name__ == "__main__":
    main()