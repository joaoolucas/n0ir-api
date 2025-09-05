#!/usr/bin/env python3
"""Check user balance and transaction history in production DB."""

import asyncio
from sqlalchemy import create_engine, text
from decimal import Decimal

DATABASE_URL = "postgresql://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway"

def check_user_data():
    """Check user data and transactions."""
    engine = create_engine(DATABASE_URL)
    
    user_id = "0xC2952cc28EDf37B053188D89e6ac888B9855d132"
    
    with engine.connect() as conn:
        # Get user data
        result = conn.execute(text("""
            SELECT user_id, total_deposits_usdc, total_withdrawals_usdc, 
                   unrealized_pnl_usd, realized_pnl_usd, created_at
            FROM users 
            WHERE user_id = :user_id
        """), {"user_id": user_id})
        
        user = result.fetchone()
        
        print("=== USER DATA ===")
        if user:
            print(f"User ID: {user[0]}")
            print(f"Total Deposits: {user[1]}")
            print(f"Total Withdrawals: {user[2]}")
            net_deposits = Decimal(str(user[1] or 0)) - Decimal(str(user[2] or 0))
            print(f"Net Deposits (calculated): {net_deposits}")
            print(f"Unrealized PnL: {user[3]}")
            print(f"Realized PnL: {user[4]}")
            print(f"Created: {user[5]}")
        else:
            print("User not found")
            return
        
        print("\n=== TRANSACTIONS ===")
        # Get all transactions
        result = conn.execute(text("""
            SELECT id, tx_type, status, event_data, tx_metadata, created_at
            FROM transactions
            WHERE user_id = :user_id
            ORDER BY created_at DESC
        """), {"user_id": user_id})
        
        transactions = result.fetchall()
        
        manual_deposits = Decimal(0)
        manual_withdrawals = Decimal(0)
        
        for tx in transactions:
            tx_id, tx_type, status, event_data, tx_metadata, created_at = tx
            
            # Get amount from event_data
            amount = Decimal(0)
            if event_data and 'amount_usdc' in event_data:
                amount = Decimal(str(event_data['amount_usdc']))
            elif event_data and 'amount' in event_data:
                amount = Decimal(str(event_data['amount']))
            
            print(f"\nTx ID: {tx_id}")
            print(f"  Type: {tx_type}")
            print(f"  Status: {status}")
            print(f"  Amount: {amount}")
            print(f"  Created: {created_at}")
            print(f"  Event Data: {event_data}")
            
            # Calculate manual totals for CONFIRMED transactions only
            if status == 'CONFIRMED':
                if tx_type == 'DEPOSIT':
                    manual_deposits += amount
                elif tx_type in ['WITHDRAWAL', 'WITHDRAW']:
                    manual_withdrawals += amount
        
        print(f"\n=== MANUAL CALCULATION ===")
        print(f"Total Deposits (from txs): {manual_deposits}")
        print(f"Total Withdrawals (from txs): {manual_withdrawals}")
        print(f"Net Deposits (manual calc): {manual_deposits - manual_withdrawals}")
        
        print(f"\n=== DISCREPANCY CHECK ===")
        print(f"DB Total Deposits: {user[1]}")
        print(f"Manual Total Deposits: {manual_deposits}")
        print(f"Deposits Match: {Decimal(str(user[1] or 0)) == manual_deposits}")
        
        print(f"\nDB Total Withdrawals: {user[2]}")
        print(f"Manual Total Withdrawals: {manual_withdrawals}")
        print(f"Withdrawals Match: {Decimal(str(user[2] or 0)) == manual_withdrawals}")
        
        # Check positions
        print(f"\n=== POSITIONS ===")
        result = conn.execute(text("""
            SELECT token_id, status, entry_amount_usdc, current_value_usdc, 
                   realized_pnl_usd, unrealized_pnl_usd
            FROM positions
            WHERE user_id = :user_id
            ORDER BY created_at DESC
        """), {"user_id": user_id})
        
        positions = result.fetchall()
        total_position_value = Decimal(0)
        
        for pos in positions:
            token_id, status, entry_amount, current_value, realized_pnl, unrealized_pnl = pos
            print(f"\nPosition {token_id}:")
            print(f"  Status: {status}")
            print(f"  Entry Amount: {entry_amount}")
            print(f"  Current Value: {current_value}")
            print(f"  Realized PnL: {realized_pnl}")
            print(f"  Unrealized PnL: {unrealized_pnl}")
            
            if status == 'ACTIVE' and current_value:
                total_position_value += Decimal(str(current_value))
        
        print(f"\nTotal Active Position Value: {total_position_value}")
        
        # Calculate what unrealized PnL should be
        net_deposits_calc = manual_deposits - manual_withdrawals
        # Assuming wallet balance is 0 as stated
        wallet_balance = Decimal(0)
        portfolio_value = wallet_balance + total_position_value
        expected_unrealized_pnl = portfolio_value - net_deposits_calc
        
        print(f"\n=== EXPECTED PNL CALCULATION ===")
        print(f"Wallet Balance: {wallet_balance} (given as 0)")
        print(f"Active Position Value: {total_position_value}")
        print(f"Total Portfolio Value: {portfolio_value}")
        print(f"Net Deposits: {net_deposits_calc}")
        print(f"Expected Unrealized PnL: {expected_unrealized_pnl}")
        print(f"Actual Unrealized PnL in DB: {user[3]}")
        print(f"Difference: {Decimal(str(user[3] or 0)) - expected_unrealized_pnl}")

if __name__ == "__main__":
    check_user_data()