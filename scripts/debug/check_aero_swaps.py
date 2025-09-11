#!/usr/bin/env python3
import asyncio
import asyncpg
import os
from decimal import Decimal

async def main():
    DATABASE_URL = "postgresql://mortiee:a1zneGayTRR77c87@localhost/n0ir"
    conn = await asyncpg.connect(DATABASE_URL)
    
    user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
    
    print(f"\nChecking transactions for user: {user_id}\n")
    
    # Check for AERO_SWAP transactions
    aero_swaps = await conn.fetch('''
        SELECT tx_hash, event_data, block_number, created_at
        FROM transactions
        WHERE user_id = $1
        AND tx_type = 'AERO_SWAP'
        ORDER BY block_number DESC
        LIMIT 10
    ''', user_id)
    
    print(f"Found {len(aero_swaps)} AERO_SWAP transactions:")
    for swap in aero_swaps:
        amount = swap['event_data'].get('amount_usdc', 0)
        token_id = swap['event_data'].get('tokenId', 'N/A')
        print(f"  Block {swap['block_number']}: Token {token_id}, Amount: {amount} USDC")
    
    # Check if any POSITION_CLOSED have aero_swap_usdc
    position_closed_with_aero = await conn.fetch('''
        SELECT tx_hash, event_data, block_number
        FROM transactions
        WHERE user_id = $1
        AND tx_type = 'POSITION_CLOSED'
        AND event_data ? 'aero_swap_usdc'
        ORDER BY block_number DESC
        LIMIT 10
    ''', user_id)
    
    print(f"\nPOSITION_CLOSED with aero_swap_usdc field: {len(position_closed_with_aero)}")
    for pos in position_closed_with_aero:
        aero_amount = pos['event_data'].get('aero_swap_usdc', 0)
        token_id = pos['event_data'].get('tokenId', 'N/A')
        print(f"  Block {pos['block_number']}: Token {token_id}, AERO swap: {aero_amount} USDC")
    
    # Check recent POSITION_CLOSED transactions
    recent_closed = await conn.fetch('''
        SELECT tx_hash, event_data, block_number
        FROM transactions
        WHERE user_id = $1
        AND tx_type = 'POSITION_CLOSED'
        ORDER BY block_number DESC
        LIMIT 5
    ''', user_id)
    
    print(f"\nRecent POSITION_CLOSED transactions:")
    for pos in recent_closed:
        token_id = pos['event_data'].get('tokenId', 'N/A')
        usdc_out = pos['event_data'].get('usdcOut', 0)
        aero = pos['event_data'].get('aero_swap_usdc', None)
        print(f"  Block {pos['block_number']}: Token {token_id}")
        print(f"    - USDC out: {usdc_out}")
        print(f"    - AERO swap: {aero if aero is not None else 'NOT SET'}")
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())