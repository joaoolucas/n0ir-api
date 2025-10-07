import psycopg2
import json

# Database connection
conn = psycopg2.connect(
    "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"
)
cur = conn.cursor()

transaction_id = 'e509fbad-d00c-4f0f-a04f-b962dd6ef07f'

# Get event data
cur.execute("""
    SELECT event_data FROM transactions WHERE id = %s
""", (transaction_id,))
result = cur.fetchone()

if result:
    event_data = result[0]
    print("EVENT DATA:")
    print(json.dumps(event_data, indent=2))

    # Check the method signature
    method_sig = event_data.get('method_sig')
    print(f"\nMethod Signature: {method_sig}")

    # Check the amounts
    print(f"\nAmounts:")
    print(f"  USDC In: {event_data.get('usdc_in')}")
    print(f"  USDC Out: {event_data.get('usdc_out')}")
    print(f"  AERO In: {event_data.get('aero_in')}")
    print(f"  AERO Out: {event_data.get('aero_out')}")
    print(f"  Amount USDC: {event_data.get('amount_usdc')}")

cur.close()
conn.close()