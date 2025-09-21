import psycopg2
import json
from datetime import datetime

# Database connection
conn = psycopg2.connect(
    "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"
)
cur = conn.cursor()

transaction_id = 'e509fbad-d00c-4f0f-a04f-b962dd6ef07f'

print(f"Investigating transaction: {transaction_id}\n")
print("=" * 80)

# Get transaction details
cur.execute("""
    SELECT * FROM transactions
    WHERE id = %s
""", (transaction_id,))

columns = [desc[0] for desc in cur.description]
transaction = cur.fetchone()

if transaction:
    print("TRANSACTION DETAILS:")
    for i, col in enumerate(columns):
        value = transaction[i]
        if isinstance(value, datetime):
            value = value.isoformat()
        print(f"  {col}: {value}")

    # Get position ID if exists
    position_id_idx = columns.index('position_id') if 'position_id' in columns else None
    position_id = transaction[position_id_idx] if position_id_idx is not None else None

    if position_id:
        print(f"\n\nRELATED POSITION (ID: {position_id}):")
        print("-" * 40)
        cur.execute("SELECT * FROM positions WHERE id = %s", (position_id,))
        position_cols = [desc[0] for desc in cur.description]
        position = cur.fetchone()
        if position:
            for i, col in enumerate(position_cols):
                value = position[i]
                if isinstance(value, datetime):
                    value = value.isoformat()
                print(f"  {col}: {value}")

    # Check for any related records
    print("\n\nCHECKING RELATED TABLES:")
    print("-" * 40)

    # Check if this transaction appears in any other tables
    cur.execute("""
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE column_name LIKE '%transaction%'
        AND table_schema = 'public'
    """)

    related_tables = cur.fetchall()
    for table, column in related_tables:
        if table != 'transactions':
            cur.execute(f"""
                SELECT COUNT(*) FROM {table}
                WHERE {column}::text = %s OR {column}::text LIKE %s
            """, (transaction_id, f'%{transaction_id}%'))
            count = cur.fetchone()[0]
            if count > 0:
                print(f"  Found {count} references in {table}.{column}")
else:
    print(f"Transaction {transaction_id} not found in database")

# Check transaction type and status
if transaction:
    print("\n\nTRANSACTION TYPE ANALYSIS:")
    print("-" * 40)
    type_idx = columns.index('type') if 'type' in columns else None
    status_idx = columns.index('status') if 'status' in columns else None
    hash_idx = columns.index('transaction_hash') if 'transaction_hash' in columns else None

    if type_idx is not None:
        print(f"  Type: {transaction[type_idx]}")
    if status_idx is not None:
        print(f"  Status: {transaction[status_idx]}")
    if hash_idx is not None:
        print(f"  Transaction Hash: {transaction[hash_idx]}")

cur.close()
conn.close()