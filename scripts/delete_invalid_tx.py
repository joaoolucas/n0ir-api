import psycopg2

# Database connection
conn = psycopg2.connect(
    "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"
)
cur = conn.cursor()

transaction_id = 'e509fbad-d00c-4f0f-a04f-b962dd6ef07f'

print(f"Deleting invalid transaction: {transaction_id}")
print("=" * 80)

# First verify it exists and has no position_id
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
    print(f"  NFT Token ID in event_data: {event_data.get('nft_token_id')}")

    if position_id is None and not event_data.get('nft_token_id'):
        print(f"\nConfirmed: This is an invalid POSITION_CREATED transaction without an actual position.")
        print("Deleting...")

        cur.execute("""
            DELETE FROM transactions
            WHERE id = %s
        """, (transaction_id,))

        conn.commit()
        print(f"✅ Successfully deleted transaction {transaction_id}")
    else:
        print(f"⚠️  This transaction has a position_id or nft_token_id. Not deleting.")
else:
    print(f"Transaction {transaction_id} not found in database")

cur.close()
conn.close()