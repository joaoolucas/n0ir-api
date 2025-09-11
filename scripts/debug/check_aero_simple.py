#!/usr/bin/env python3
from sqlalchemy import create_engine, text
import json

DATABASE_URL = "postgresql://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway"
engine = create_engine(DATABASE_URL)

user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'

with engine.connect() as conn:
    # Check for AERO_SWAP transactions
    result = conn.execute(text("""
        SELECT tx_hash, event_data, block_number
        FROM transactions
        WHERE user_id = :user_id
        AND tx_type = 'AERO_SWAP'
        ORDER BY block_number DESC
        LIMIT 10
    """), {"user_id": user_id})
    
    aero_swaps = result.fetchall()
    print(f"\nFound {len(aero_swaps)} AERO_SWAP transactions:")
    for swap in aero_swaps:
        event_data = swap[1] if isinstance(swap[1], dict) else json.loads(swap[1])
        amount = event_data.get('amount_usdc', 0)
        token_id = event_data.get('tokenId', 'N/A')
        print(f"  Block {swap[2]}: Token {token_id}, Amount: {amount} USDC")
    
    # Check POSITION_CLOSED with aero_swap_usdc
    result = conn.execute(text("""
        SELECT tx_hash, event_data, block_number
        FROM transactions
        WHERE user_id = :user_id
        AND tx_type = 'POSITION_CLOSED'
        AND event_data::jsonb ? 'aero_swap_usdc'
        ORDER BY block_number DESC
        LIMIT 10
    """), {"user_id": user_id})
    
    with_aero = result.fetchall()
    print(f"\nPOSITION_CLOSED with aero_swap_usdc: {len(with_aero)}")
    for pos in with_aero:
        event_data = pos[1] if isinstance(pos[1], dict) else json.loads(pos[1])
        aero_amount = event_data.get('aero_swap_usdc', 0)
        token_id = event_data.get('tokenId', 'N/A')
        print(f"  Block {pos[2]}: Token {token_id}, AERO: {aero_amount} USDC")