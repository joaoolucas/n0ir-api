#!/usr/bin/env python3
"""Force delete the incorrectly classified transaction from production database."""

import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = "postgresql://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway"

def force_delete_transaction():
    """Force delete the incorrect transaction using psycopg2."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    transaction_id = "be62bcca-a12a-4f20-9336-d01cad5987fb"
    
    try:
        # First check if it exists
        cur.execute("""
            SELECT id, user_id, tx_type, event_data
            FROM transactions
            WHERE id = %s
        """, (transaction_id,))
        
        tx = cur.fetchone()
        
        if tx:
            print("=== TRANSACTION FOUND ===")
            print(f"ID: {tx['id']}")
            print(f"User: {tx['user_id']}")
            print(f"Type: {tx['tx_type']}")
            print(f"Amount: {tx['event_data'].get('amount_usdc', 'N/A') if tx['event_data'] else 'N/A'}")
            print(f"From: {tx['event_data'].get('from_address', 'N/A') if tx['event_data'] else 'N/A'}")
            
            # Delete it
            cur.execute("""
                DELETE FROM transactions
                WHERE id = %s
                RETURNING id
            """, (transaction_id,))
            
            deleted = cur.fetchone()
            
            if deleted:
                # Commit the deletion
                conn.commit()
                print(f"\n✅ Successfully deleted transaction {transaction_id}")
                
                # Verify it's gone
                cur.execute("SELECT COUNT(*) as count FROM transactions WHERE id = %s", (transaction_id,))
                count = cur.fetchone()
                if count['count'] == 0:
                    print("✅ Verified: Transaction is deleted from database")
                else:
                    print("❌ Warning: Transaction still exists after deletion")
            else:
                print("❌ Failed to delete transaction")
                conn.rollback()
        else:
            print(f"❌ Transaction {transaction_id} not found in database")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    force_delete_transaction()