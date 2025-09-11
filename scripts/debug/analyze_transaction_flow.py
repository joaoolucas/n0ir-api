#!/usr/bin/env python3
"""Analyze transaction flow to identify incorrect categorization."""

from sqlalchemy import create_engine, text
from decimal import Decimal
from datetime import datetime

DATABASE_URL = "postgresql://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway"

def analyze_transactions():
    """Analyze transaction flow chronologically."""
    engine = create_engine(DATABASE_URL)
    
    user_id = "0xC2952cc28EDf37B053188D89e6ac888B9855d132"
    cdp_wallet = "0x1409f9dfb8c05a31a5fb4b3ffeea60298bef30bb"
    
    with engine.connect() as conn:
        # Get all transactions in chronological order
        result = conn.execute(text("""
            SELECT id, tx_type, status, event_data, created_at
            FROM transactions
            WHERE user_id = :user_id
            ORDER BY created_at ASC
        """), {"user_id": user_id})
        
        transactions = result.fetchall()
        
        # Track running balance
        user_deposits = Decimal(0)
        user_withdrawals = Decimal(0)
        
        print("=== TRANSACTION FLOW ANALYSIS ===")
        print(f"User: {user_id}")
        print(f"CDP Wallet: {cdp_wallet}")
        print("\nChronological transaction flow:\n")
        
        for tx in transactions:
            tx_id, tx_type, status, event_data, created_at = tx
            
            if status != 'CONFIRMED':
                continue
                
            amount = Decimal(0)
            if event_data and 'amount_usdc' in event_data:
                amount = Decimal(str(event_data['amount_usdc']))
            
            from_addr = event_data.get('from_address', '').lower() if event_data else ''
            to_addr = event_data.get('to_address', '').lower() if event_data else ''
            
            # Analyze flow
            flow_description = ""
            is_real_deposit = False
            is_real_withdrawal = False
            
            if tx_type == 'DEPOSIT':
                if from_addr == user_id.lower() and to_addr == cdp_wallet.lower():
                    # User depositing to CDP wallet - REAL DEPOSIT
                    is_real_deposit = True
                    user_deposits += amount
                    flow_description = f"✅ REAL USER DEPOSIT: User → CDP Wallet"
                elif to_addr == cdp_wallet.lower():
                    # Other deposits to CDP wallet (returns from positions, etc.)
                    flow_description = f"⚠️  INTERNAL FLOW: {from_addr[:10]}... → CDP Wallet"
                else:
                    flow_description = f"❓ OTHER: {from_addr[:10]}... → {to_addr[:10]}..."
                    
            elif tx_type in ['WITHDRAWAL', 'WITHDRAW']:
                if to_addr == user_id.lower() and from_addr == cdp_wallet.lower():
                    # CDP wallet withdrawing to user - REAL WITHDRAWAL
                    is_real_withdrawal = True
                    user_withdrawals += amount
                    flow_description = f"✅ REAL USER WITHDRAWAL: CDP Wallet → User"
                elif from_addr == cdp_wallet.lower():
                    # CDP wallet sending elsewhere (not to user)
                    flow_description = f"⚠️  INTERNAL FLOW: CDP Wallet → {to_addr[:10]}..."
                else:
                    flow_description = f"❓ OTHER: {from_addr[:10]}... → {to_addr[:10]}..."
            
            elif tx_type == 'POSITION_CREATED':
                flow_description = f"📊 Position created (Token ID: {event_data.get('tokenId', 'N/A')})"
                
            elif tx_type == 'POSITION_CLOSED':
                flow_description = f"📊 Position closed (Token ID: {event_data.get('tokenId', 'N/A')})"
                
            elif tx_type == 'AERO_SWAP':
                flow_description = f"🔄 AERO rewards swap"
                
            elif tx_type == 'FEE_COLLECTION':
                flow_description = f"💰 Protocol fee collection"
            
            print(f"{created_at.strftime('%Y-%m-%d %H:%M')} | {tx_type:20} | ${amount:10.2f} | {flow_description}")
            if is_real_deposit:
                print(f"                       Running User Balance: ${user_deposits - user_withdrawals:.2f}")
            elif is_real_withdrawal:
                print(f"                       Running User Balance: ${user_deposits - user_withdrawals:.2f}")
        
        print(f"\n=== CORRECTED TOTALS ===")
        print(f"REAL User Deposits (User → CDP): ${user_deposits:.2f}")
        print(f"REAL User Withdrawals (CDP → User): ${user_withdrawals:.2f}")
        print(f"Net Deposits (should be ~0): ${user_deposits - user_withdrawals:.2f}")
        
        # Compare with DB values
        result = conn.execute(text("""
            SELECT total_deposits_usdc, total_withdrawals_usdc
            FROM users
            WHERE user_id = :user_id
        """), {"user_id": user_id})
        
        db_values = result.fetchone()
        
        print(f"\n=== DATABASE VALUES (INCORRECT) ===")
        print(f"DB Total Deposits: ${db_values[0]:.2f}")
        print(f"DB Total Withdrawals: ${db_values[1]:.2f}")
        print(f"DB Net Deposits: ${Decimal(str(db_values[0])) - Decimal(str(db_values[1])):.2f}")
        
        print(f"\n=== ISSUE IDENTIFIED ===")
        print(f"The system is counting ALL deposits/withdrawals to/from the CDP wallet,")
        print(f"including internal flows (position closes, AERO swaps, etc.) as user deposits/withdrawals.")
        print(f"\nIt should ONLY count:")
        print(f"  - DEPOSITS: User wallet → CDP wallet")
        print(f"  - WITHDRAWALS: CDP wallet → User wallet")

if __name__ == "__main__":
    analyze_transactions()