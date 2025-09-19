#!/usr/bin/env python3
"""Fix the user_id case for the position to match the actual wallet owner."""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def fix_user_case():
    """Update position user_id from lowercase to mixed case."""

    # Database connection
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        return

    conn = psycopg2.connect(db_url)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # The correct mixed-case user ID that generates wallet 0x7b3106F56447c9C313C19f519b290Ff4E293D573
        correct_user_id = "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51"
        lowercase_user_id = "0xdbe4e3bcb15b221324b776db6f0cbff24918ea51"

        # First, check current positions
        print(f"Checking positions for lowercase user_id: {lowercase_user_id}")
        cur.execute("""
            SELECT nft_token_id, user_id, pool_name, status, wallet_address
            FROM positions
            WHERE LOWER(user_id) = %s
        """, (lowercase_user_id,))

        positions = cur.fetchall()
        print(f"Found {len(positions)} positions")

        for pos in positions:
            print(f"  Position {pos['nft_token_id']}: user_id={pos['user_id']}, pool={pos['pool_name']}, status={pos['status']}")

        if positions:
            # Update positions to use correct mixed-case user_id
            print(f"\nUpdating positions to use correct user_id: {correct_user_id}")
            cur.execute("""
                UPDATE positions
                SET user_id = %s
                WHERE LOWER(user_id) = %s
            """, (correct_user_id, lowercase_user_id))

            updated = cur.rowcount
            print(f"Updated {updated} positions")

            # Also update users table if needed
            print(f"\nChecking users table...")
            cur.execute("""
                SELECT user_id, cdp_wallet_address
                FROM users
                WHERE LOWER(user_id) = %s
            """, (lowercase_user_id,))

            users = cur.fetchall()
            for user in users:
                print(f"  User: user_id={user['user_id']}, wallet={user['cdp_wallet_address']}")

            if users:
                print(f"\nUpdating users table to use correct user_id: {correct_user_id}")
                cur.execute("""
                    UPDATE users
                    SET user_id = %s
                    WHERE LOWER(user_id) = %s
                """, (correct_user_id, lowercase_user_id))

                updated = cur.rowcount
                print(f"Updated {updated} users")

            # Also update transactions if needed
            print(f"\nChecking transactions table...")
            cur.execute("""
                SELECT COUNT(*) as count
                FROM transactions
                WHERE LOWER(user_id) = %s
            """, (lowercase_user_id,))

            tx_count = cur.fetchone()['count']
            if tx_count > 0:
                print(f"Found {tx_count} transactions to update")
                cur.execute("""
                    UPDATE transactions
                    SET user_id = %s
                    WHERE LOWER(user_id) = %s
                """, (correct_user_id, lowercase_user_id))

                updated = cur.rowcount
                print(f"Updated {updated} transactions")

            # Commit all changes
            conn.commit()
            print("\n✅ All updates committed successfully!")

            # Verify the changes
            print("\nVerifying changes...")
            cur.execute("""
                SELECT nft_token_id, user_id, pool_name, status
                FROM positions
                WHERE user_id = %s
            """, (correct_user_id,))

            positions = cur.fetchall()
            print(f"Positions with correct user_id: {len(positions)}")
            for pos in positions:
                print(f"  Position {pos['nft_token_id']}: user_id={pos['user_id']}")

        else:
            print("No positions found to update")

    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    fix_user_case()