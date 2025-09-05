#!/usr/bin/env python3
"""Delete the incorrectly classified transaction from production database."""

from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway"

def delete_transaction():
    """Delete the incorrect transaction."""
    engine = create_engine(DATABASE_URL)
    
    transaction_id = "be62bcca-a12a-4f20-9336-d01cad5987fb"
    
    with engine.connect() as conn:
        # First, verify the transaction exists and show its details
        result = conn.execute(text("""
            SELECT id, user_id, tx_type, event_data, created_at
            FROM transactions
            WHERE id = :tx_id
        """), {"tx_id": transaction_id})
        
        tx = result.fetchone()
        
        if tx:
            print("=== TRANSACTION TO DELETE ===")
            print(f"ID: {tx[0]}")
            print(f"User: {tx[1]}")
            print(f"Type: {tx[2]}")
            print(f"Event Data: {tx[3]}")
            print(f"Created: {tx[4]}")
            
            # Confirm it's the incorrect one (from liquidity manager)
            if tx[3] and tx[3].get('from_address', '').lower() == '0x00c1bc0ca9f703919c2ba320e5f200865f778aae':
                print("\n✅ Confirmed: This is the incorrect transaction from Liquidity Manager")
                
                # Delete the transaction
                with engine.begin() as txn:
                    result = conn.execute(text("""
                        DELETE FROM transactions
                        WHERE id = :tx_id
                        RETURNING id
                    """), {"tx_id": transaction_id})
                    
                    deleted = result.fetchone()
                    if deleted:
                        print(f"\n✅ Successfully deleted transaction {transaction_id}")
                    else:
                        print(f"\n❌ Failed to delete transaction")
            else:
                print("\n⚠️ Transaction doesn't match expected pattern, not deleting")
        else:
            print(f"❌ Transaction {transaction_id} not found in database")

if __name__ == "__main__":
    delete_transaction()