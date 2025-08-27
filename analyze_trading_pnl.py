#!/usr/bin/env python3
"""Analyze actual trading PnL from positions."""

import asyncio
import asyncpg
from urllib.parse import urlparse
from decimal import Decimal

# Database URL from Railway staging
DATABASE_URL = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"


async def analyze_pnl():
    """Analyze trading PnL from positions."""
    
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
        # Get all positions for the user
        positions = await conn.fetch("""
            SELECT 
                token_id,
                pool_address,
                pool_name,
                entry_amount_usdc,
                current_value_usdc,
                realized_pnl_usd,
                unrealized_pnl_usd,
                fees_earned_usdc,
                rewards_earned_usdc,
                status,
                entry_date,
                exit_date,
                closed_at
            FROM positions 
            WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
            ORDER BY created_at ASC
        """)
        
        print(f"\n📊 Found {len(positions)} positions for user")
        
        total_in = Decimal('0')
        total_out = Decimal('0')
        total_pnl = Decimal('0')
        
        print("\n=== Position Analysis ===")
        for pos in positions:
            entry_amount = Decimal(str(pos['entry_amount_usdc'] or 0))
            current_value = Decimal(str(pos['current_value_usdc'] or 0))
            realized_pnl = Decimal(str(pos['realized_pnl_usd'] or 0))
            unrealized_pnl = Decimal(str(pos['unrealized_pnl_usd'] or 0))
            fees = Decimal(str(pos['fees_earned_usdc'] or 0))
            rewards = Decimal(str(pos['rewards_earned_usdc'] or 0))
            
            total_in += entry_amount
            if pos['status'] == 'CLOSED':
                # For closed positions, current_value is the exit amount
                total_out += current_value
            total_pnl += realized_pnl
            
            if entry_amount > 0:
                print(f"\nPosition {pos['token_id']}")
                print(f"  Pool: {pos['pool_name']}")
                print(f"  Entry Amount: {entry_amount:.6f} USDC")
                print(f"  Current/Exit Value: {current_value:.6f} USDC")
                print(f"  Realized PnL: {realized_pnl:.6f} USD")
                print(f"  Unrealized PnL: {unrealized_pnl:.6f} USD")
                print(f"  Fees Earned: {fees:.6f} USDC")
                print(f"  Rewards: {rewards:.6f} USDC")
                print(f"  Status: {pos['status']}")
        
        print(f"\n📊 TOTALS:")
        print(f"  Total Money IN to positions: {total_in:.6f} USDC")
        print(f"  Total Money OUT from positions: {total_out:.6f} USDC")
        print(f"  Total Realized PnL (from DB): {total_pnl:.6f} USDC")
        print(f"  Calculated PnL (OUT - IN): {total_out - total_in:.6f} USDC")
        
        # Now let's see how this relates to wallet balance
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
        
        print(f"\n💰 WALLET ANALYSIS:")
        print(f"  Total Deposits: {deposits:.6f} USDC")
        print(f"  Total Withdrawals: {withdrawals:.6f} USDC")
        print(f"  Current Balance: {balance:.6f} USDC")
        
        # The formula should be:
        # Balance = Deposits - Withdrawals + Trading PnL
        expected_balance = deposits - withdrawals + (total_out - total_in)
        
        print(f"\n🔍 RECONCILIATION:")
        print(f"  Expected: Deposits ({deposits:.2f}) - Withdrawals ({withdrawals:.2f}) + PnL ({total_out - total_in:.2f})")
        print(f"  Expected Balance: {expected_balance:.6f} USDC")
        print(f"  Actual Balance: {balance:.6f} USDC")
        print(f"  Difference: {balance - expected_balance:.6f} USDC")
        
        # Check for open positions
        open_positions = await conn.fetch("""
            SELECT 
                token_id,
                pool_name,
                entry_amount_usdc,
                current_value_usdc,
                unrealized_pnl_usd
            FROM positions 
            WHERE user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
            AND status = 'OPEN'
        """)
        
        if open_positions:
            print(f"\n⚠️ Found {len(open_positions)} OPEN positions:")
            open_value = Decimal('0')
            for pos in open_positions:
                entry = Decimal(str(pos['entry_amount_usdc'] or 0))
                current = Decimal(str(pos['current_value_usdc'] or 0))
                unrealized = Decimal(str(pos['unrealized_pnl_usd'] or 0))
                open_value += current
                print(f"  - {pos['pool_name']}: Entry {entry:.6f} → Current {current:.6f} (PnL: {unrealized:.6f})")
            print(f"  Total value in open positions: {open_value:.6f} USDC")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise
    finally:
        await conn.close()
        print("\n✅ Analysis complete")


if __name__ == "__main__":
    print("🔍 Analyzing trading PnL from positions")
    asyncio.run(analyze_pnl())