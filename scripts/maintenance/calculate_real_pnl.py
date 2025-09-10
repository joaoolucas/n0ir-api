#!/usr/bin/env python3
"""Calculate real PnL from position events."""

import asyncio
import asyncpg
from urllib.parse import urlparse
from decimal import Decimal

# Database URL from Railway staging
DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"


async def calculate_real_pnl():
    """Calculate real PnL from position created/closed events."""
    
    # Parse database URL
    parsed = urlparse(DATABASE_URL)
    
    # Connect to database
    conn = await asyncpg.connect(
        host=parsed.hostname,
        port=parsed.port,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip('/'),
        ssl='require'
    )
    
    print("Connected to staging database")
    
    try:
        # Get all position events
        events = await conn.fetch("""
            SELECT 
                tx_type,
                event_data,
                block_number,
                status
            FROM transactions 
            WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
            AND tx_type IN ('POSITION_CREATED', 'POSITION_CLOSED')
            AND status IN ('CONFIRMED', 'confirmed')
            ORDER BY block_number ASC
        """)
        
        positions = {}
        total_in = Decimal('0')
        total_out = Decimal('0')
        
        print("\n=== Position Flow Analysis ===")
        for event in events:
            import json
            event_data = event['event_data'] if isinstance(event['event_data'], dict) else json.loads(event['event_data']) if event['event_data'] else {}
            tx_type = event['tx_type']
            
            if tx_type == 'POSITION_CREATED':
                token_id = event_data.get('tokenId')
                if not token_id:
                    continue
                usdc_in = Decimal(str(event_data['usdcIn'])) / Decimal('1000000')  # Convert from wei
                positions[token_id] = {
                    'in': usdc_in,
                    'pool': event_data.get('pool_name', 'Unknown')
                }
                total_in += usdc_in
                print(f"OPEN  Position {token_id}: IN {usdc_in:.6f} USDC - {event_data.get('pool_name', '')}")
                
            elif tx_type == 'POSITION_CLOSED':
                token_id = event_data.get('tokenId')
                if not token_id:
                    continue
                usdc_out = Decimal(str(event_data['usdcOut'])) / Decimal('1000000')  # Convert from wei
                total_out += usdc_out
                
                if token_id in positions:
                    pos = positions[token_id]
                    pnl = usdc_out - pos['in']
                    pnl_pct = (pnl / pos['in'] * 100) if pos['in'] > 0 else 0
                    print(f"CLOSE Position {token_id}: OUT {usdc_out:.6f} USDC - PnL: {pnl:+.6f} ({pnl_pct:+.2f}%)")
                else:
                    print(f"CLOSE Position {token_id}: OUT {usdc_out:.6f} USDC (no open record)")
        
        total_pnl = total_out - total_in
        pnl_pct = (total_pnl / total_in * 100) if total_in > 0 else 0
        
        print(f"\n📊 ACTUAL TRADING RESULTS:")
        print(f"  Total IN:  {total_in:.6f} USDC")
        print(f"  Total OUT: {total_out:.6f} USDC")
        print(f"  Total PnL: {total_pnl:+.6f} USDC ({pnl_pct:+.2f}%)")
        
        # Now reconcile with wallet
        user = await conn.fetchrow("""
            SELECT 
                usdc_balance,
                total_deposits_usdc,
                total_withdrawals_usdc
            FROM users 
            WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
        """)
        
        deposits = Decimal(str(user['total_deposits_usdc']))
        withdrawals = Decimal(str(user['total_withdrawals_usdc']))
        balance = Decimal(str(user['usdc_balance']))
        
        print(f"\n💰 WALLET RECONCILIATION:")
        print(f"  Deposits:    +{deposits:.6f} USDC")
        print(f"  Withdrawals: -{withdrawals:.6f} USDC")
        print(f"  Trading IN:  -{total_in:.6f} USDC")
        print(f"  Trading OUT: +{total_out:.6f} USDC")
        print(f"  ─────────────────────────────")
        
        expected = deposits - withdrawals - total_in + total_out
        print(f"  Expected:    {expected:.6f} USDC")
        print(f"  Actual:      {balance:.6f} USDC")
        print(f"  Difference:  {balance - expected:.6f} USDC")
        
        if abs(balance - expected) < Decimal('0.01'):
            print(f"\n✅ Balance matches! Trading PnL is correctly tracked.")
        else:
            print(f"\n⚠️ Balance mismatch - there may be missing transactions.")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise
    finally:
        await conn.close()
        print("\n✅ Analysis complete")


if __name__ == "__main__":
    print("🔍 Calculating real PnL from position events")
    asyncio.run(calculate_real_pnl())