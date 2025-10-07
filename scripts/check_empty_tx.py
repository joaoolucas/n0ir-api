import psycopg2
import json

# Database connection
conn = psycopg2.connect(
    "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"
)
cur = conn.cursor()

tx_hash = '0x25c9cedd2c8cb5d74a4438a11795f5f95c5980a309a1becd683d1b5ad32cbf47'

print(f"Checking transaction: {tx_hash}")
print("=" * 80)

# Check for any POSITION_CREATED transactions with no position_id
cur.execute("""
    SELECT id, tx_hash, user_id, position_id, tx_type, event_data, created_at
    FROM transactions
    WHERE tx_type = 'POSITION_CREATED'
    AND position_id IS NULL
    ORDER BY created_at DESC
    LIMIT 10
""")

results = cur.fetchall()

print(f"\nFound {len(results)} POSITION_CREATED transactions with no position_id:")
print("-" * 80)

for row in results:
    tx_id, hash, user, pos_id, tx_type, event_data, created = row
    amount = event_data.get('amount_usdc', 0)
    usdc_out = event_data.get('usdc_out', 0)
    usdc_in = event_data.get('usdc_in', 0)

    print(f"\nTransaction ID: {tx_id}")
    print(f"  Hash: {hash}")
    print(f"  User: {user}")
    print(f"  Amount USDC: {amount}")
    print(f"  USDC Out: {usdc_out}")
    print(f"  USDC In: {usdc_in}")
    print(f"  Net USDC: {usdc_out - usdc_in}")
    print(f"  Created: {created}")

# Check if there are positions without matching transactions
print("\n" + "=" * 80)
print("Checking for actual positions created around the same time...")

cur.execute("""
    SELECT p.token_id, p.user_id, p.created_at, p.amount_usdc, p.pool_name
    FROM positions p
    WHERE p.created_at >= '2025-09-20 21:00:00'
    AND p.created_at <= '2025-09-20 22:30:00'
    ORDER BY p.created_at DESC
""")

positions = cur.fetchall()
print(f"\nFound {len(positions)} positions created in that timeframe:")
for pos in positions:
    print(f"  Position {pos[0]}: User {pos[1]}, Amount: {pos[3]} USDC, Pool: {pos[4]}, Created: {pos[2]}")

cur.close()
conn.close()