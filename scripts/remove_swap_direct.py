#!/usr/bin/env python3
"""
Remove the misidentified swap transaction using direct SQL.
"""

import subprocess
import os

tx_id = '13431200-06a6-4a99-98f4-5406404d2810'

print(f"REMOVING MISIDENTIFIED SWAP TRANSACTION")
print("="*60)
print(f"Transaction ID: {tx_id}")

# Use Railway CLI to run SQL directly
sql_command = f"DELETE FROM transactions WHERE id = '{tx_id}' RETURNING id, tx_type;"

# Execute via railway
result = subprocess.run(
    ['railway', 'run', 'psql', os.environ.get('DATABASE_URL', ''), '-c', sql_command],
    capture_output=True,
    text=True
)

if result.returncode == 0:
    print(f"✅ Successfully deleted transaction")
    print(result.stdout)
else:
    print(f"❌ Error: {result.stderr}")

# Also check if it exists first
check_sql = f"SELECT id, tx_type, amount_usdc FROM transactions WHERE id = '{tx_id}';"
check_result = subprocess.run(
    ['railway', 'run', 'psql', os.environ.get('DATABASE_URL', ''), '-c', check_sql],
    capture_output=True,
    text=True
)

if "0 rows" in check_result.stdout:
    print("✅ Transaction successfully removed from database")
else:
    print("Transaction status:")
    print(check_result.stdout)
