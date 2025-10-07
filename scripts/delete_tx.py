import psycopg2

# Database connection
conn = psycopg2.connect(
    "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"
)
cur = conn.cursor()

transaction_id = '5d9ba76f-d807-437f-8544-ff9331228eea'

print(f"Deleting transaction: {transaction_id}")
print("=" * 80)

# First verify it exists
cur.execute("""
    SELECT id, tx_hash, position_id, tx_type, event_data
    FROM transactions
    WHERE id = %s
""", (transaction_id,))

result = cur.fetchone()
if result:
    tx_id, tx_hash, position_id, tx_type, event_data = result
    print(f"Found transaction:")
    print(f"  Hash: {tx_hash}")
    print(f"  Type: {tx_type}")
    print(f"  Position ID: {position_id}")

    print("\nDeleting...")
    cur.execute("""
        DELETE FROM transactions
        WHERE id = %s
    """, (transaction_id,))

    conn.commit()
    print(f"✅ Successfully deleted transaction {transaction_id}")
else:
    print(f"Transaction {transaction_id} not found in database")

cur.close()
conn.close()