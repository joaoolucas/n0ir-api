#!/usr/bin/env python3
from sqlalchemy import create_engine, text
import json

# This is the staging database URL from the conversation
DATABASE_URL = "postgresql://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway"
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    # Check all tables in the database
    print("All tables in database:")
    result = conn.execute(text("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name
    """))
    tables = [row[0] for row in result]
    print(f"Tables: {tables}")
    
    # Check if the new transactions table exists (with event_data)
    print("\n\nChecking if new transactions schema exists...")
    result = conn.execute(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'transactions' 
        AND column_name IN ('tx_type', 'event_data', 'position_id')
        ORDER BY ordinal_position
    """))
    new_cols = [row[0] for row in result]
    if new_cols:
        print(f"Found new schema columns: {new_cols}")
    else:
        print("New schema not found - database has old schema")
    
    # First check what columns exist in positions table
    print("\n\nChecking positions table columns:")
    result = conn.execute(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'positions'
        ORDER BY ordinal_position
    """))
    columns = [row[0] for row in result]
    print(f"Columns: {columns}")
    
    print("\n\nChecking positions data:")
    result = conn.execute(text("""
        SELECT nft_token_id, pool_address, pool_name
        FROM positions
        WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
        LIMIT 5
    """))
    
    positions = result.fetchall()
    for row in positions:
        print(f"\nToken ID: {row[0]}")
        print(f"Pool Address: {row[1]}")
        print(f"Pool Name (column): {row[2]}")
        print("---")
    
    # Check transactions table columns
    print("\n\nChecking transactions table columns:")
    result = conn.execute(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'transactions'
        AND column_name LIKE '%type%'
    """))
    cols = [row[0] for row in result]
    print(f"Type columns: {cols}")
    
    # Check all transaction columns
    print("\n\nAll transaction columns:")
    result = conn.execute(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'transactions'
        ORDER BY ordinal_position
    """))
    all_cols = [row[0] for row in result]
    print(f"Columns: {all_cols}")
    
    # Check enum values
    print("\n\nChecking transaction_type enum values:")
    result = conn.execute(text("""
        SELECT DISTINCT transaction_type 
        FROM transactions 
        WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
    """))
    types = [row[0] for row in result]
    print(f"Transaction types in database: {types}")
    
    # Now check transactions with pool_name column
    print("\n\nChecking position transactions:")
    result = conn.execute(text("""
        SELECT transaction_type, pool_name, related_position_id, tx_metadata
        FROM transactions
        WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
        AND transaction_type IN ('position_entry', 'position_exit')
        LIMIT 5
    """))
    
    txs = result.fetchall()
    for tx in txs:
        print(f"\nTx Type: {tx[0]}")
        print(f"Pool Name: {tx[1]}")
        print(f"Related Position ID: {tx[2]}")
        print(f"TX Metadata: {tx[3]}")