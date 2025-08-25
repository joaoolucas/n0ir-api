import asyncio
import asyncpg

async def check_schema():
    conn = await asyncpg.connect(
        "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"
    )
    
    # Check positions columns
    positions_columns = await conn.fetch("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'positions'
        ORDER BY ordinal_position
    """)
    
    print("Positions table columns:")
    for col in positions_columns:
        print(f"  - {col['column_name']}: {col['data_type']}")
    
    # Check transactions columns  
    tx_columns = await conn.fetch("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'transactions'  
        ORDER BY ordinal_position
    """)
    
    print("\nTransactions table columns:")
    for col in tx_columns:
        print(f"  - {col['column_name']}: {col['data_type']}")
    
    await conn.close()

asyncio.run(check_schema())