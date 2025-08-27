#!/usr/bin/env python3
"""Fix status capitalization inconsistency in database - convert all to uppercase."""

import psycopg2
from urllib.parse import urlparse

# Database URL from Railway staging
DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"


def fix_status_capitalization():
    """Fix all status fields to use uppercase values for consistency."""
    
    # Parse database URL
    parsed = urlparse(DATABASE_URL)
    
    # Connect to database
    conn = psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip('/'),
        sslmode='require'
    )
    cursor = conn.cursor()
    
    print("Connected to staging database")
    
    try:
        # Fix transactions table status
        print("\n📝 Fixing transactions table status...")
        
        # Update confirmed status
        cursor.execute("""
            UPDATE transactions 
            SET status = 'CONFIRMED'
            WHERE LOWER(status) = 'confirmed'
        """)
        print(f"  Updated {cursor.rowcount} transactions from 'confirmed' to 'CONFIRMED'")
        
        # Update pending status
        cursor.execute("""
            UPDATE transactions 
            SET status = 'PENDING'
            WHERE LOWER(status) = 'pending'
        """)
        print(f"  Updated {cursor.rowcount} transactions from 'pending' to 'PENDING'")
        
        # Update failed status
        cursor.execute("""
            UPDATE transactions 
            SET status = 'FAILED'
            WHERE LOWER(status) = 'failed'
        """)
        print(f"  Updated {cursor.rowcount} transactions from 'failed' to 'FAILED'")
        
        # Update cancelled status
        cursor.execute("""
            UPDATE transactions 
            SET status = 'CANCELLED'
            WHERE LOWER(status) = 'cancelled'
        """)
        print(f"  Updated {cursor.rowcount} transactions from 'cancelled' to 'CANCELLED'")
        
        # Fix positions table status
        print("\n📊 Fixing positions table status...")
        
        # Update active status
        cursor.execute("""
            UPDATE positions 
            SET status = 'ACTIVE'
            WHERE LOWER(status) = 'active'
        """)
        print(f"  Updated {cursor.rowcount} positions from 'active' to 'ACTIVE'")
        
        # Update closed status
        cursor.execute("""
            UPDATE positions 
            SET status = 'CLOSED'
            WHERE LOWER(status) = 'closed'
        """)
        print(f"  Updated {cursor.rowcount} positions from 'closed' to 'CLOSED'")
        
        # Update liquidated status
        cursor.execute("""
            UPDATE positions 
            SET status = 'LIQUIDATED'
            WHERE LOWER(status) = 'liquidated'
        """)
        print(f"  Updated {cursor.rowcount} positions from 'liquidated' to 'LIQUIDATED'")
        
        # Check users table status
        print("\n👤 Fixing users table status...")
        
        # Update active status
        cursor.execute("""
            UPDATE users 
            SET status = 'ACTIVE'
            WHERE LOWER(status) = 'active'
        """)
        print(f"  Updated {cursor.rowcount} users from 'active' to 'ACTIVE'")
        
        # Update suspended status
        cursor.execute("""
            UPDATE users 
            SET status = 'SUSPENDED'
            WHERE LOWER(status) = 'suspended'
        """)
        print(f"  Updated {cursor.rowcount} users from 'suspended' to 'SUSPENDED'")
        
        # Update closed status
        cursor.execute("""
            UPDATE users 
            SET status = 'CLOSED'
            WHERE LOWER(status) = 'closed'
        """)
        print(f"  Updated {cursor.rowcount} users from 'closed' to 'CLOSED'")
        
        # Commit all changes
        conn.commit()
        
        # Verify the fix
        print("\n✅ Verification:")
        
        # Check transactions
        cursor.execute("""
            SELECT status, COUNT(*) as count 
            FROM transactions 
            GROUP BY status 
            ORDER BY status
        """)
        tx_statuses = cursor.fetchall()
        print("\nTransactions status distribution:")
        for status, count in tx_statuses:
            print(f"  {status}: {count} records")
        
        # Check positions
        cursor.execute("""
            SELECT status, COUNT(*) as count 
            FROM positions 
            GROUP BY status 
            ORDER BY status
        """)
        pos_statuses = cursor.fetchall()
        print("\nPositions status distribution:")
        for status, count in pos_statuses:
            print(f"  {status}: {count} records")
        
        # Check users
        cursor.execute("""
            SELECT status, COUNT(*) as count 
            FROM users 
            GROUP BY status 
            ORDER BY status
        """)
        user_statuses = cursor.fetchall()
        print("\nUsers status distribution:")
        for status, count in user_statuses:
            print(f"  {status}: {count} records")
        
        print("\n✅ All status fields have been standardized to uppercase!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
        print("\n📊 Database migration complete")


if __name__ == "__main__":
    print("🔧 Fixing status capitalization inconsistency in database")
    print("   Converting all status values to UPPERCASE for consistency")
    fix_status_capitalization()