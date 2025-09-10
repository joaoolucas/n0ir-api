#!/usr/bin/env python3
from sqlalchemy import create_engine, text
import json

DATABASE_URL = "postgresql://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway"
engine = create_engine(DATABASE_URL)

user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
token_ids = ['23807591', '23695249', '23675645', '23672118', '23668153', '23642506', '23586039']

with engine.connect() as conn:
    print(f"\nChecking AERO_SWAP transactions for user {user_id[:10]}...\n")
    
    # Check all AERO_SWAP transactions for this user
    result = conn.execute(text("""
        SELECT tx_type, event_data, block_number
        FROM transactions
        WHERE user_id = :user_id
        AND tx_type = 'AERO_SWAP'
        ORDER BY block_number DESC
    """), {"user_id": user_id})
    
    aero_swaps = result.fetchall()
    print(f"Found {len(aero_swaps)} AERO_SWAP transactions total")
    
    if aero_swaps:
        print("\nAERO_SWAP transactions found:")
        for swap in aero_swaps:
            event_data = swap[1] if isinstance(swap[1], dict) else json.loads(swap[1]) if swap[1] else {}
            token_id = event_data.get('tokenId', 'N/A')
            amount = event_data.get('amount_usdc', 0)
            print(f"  Token {token_id}: {amount} USDC (Block {swap[2]})")
            
    print(f"\nChecking which closed positions have matching AERO swaps:")
    for tid in token_ids:
        result = conn.execute(text("""
            SELECT COUNT(*) 
            FROM transactions 
            WHERE user_id = :user_id 
            AND tx_type = 'AERO_SWAP' 
            AND event_data::jsonb->>'tokenId' = :token_id
        """), {"user_id": user_id, "token_id": tid})
        count = result.scalar()
        status = "✅ HAS AERO SWAP" if count > 0 else "❌ NO AERO SWAP"
        print(f"  Token {tid}: {status}")