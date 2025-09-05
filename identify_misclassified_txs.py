#!/usr/bin/env python3
"""Identify misclassified transactions in the database."""

from sqlalchemy import create_engine, text
from decimal import Decimal

DATABASE_URL = "postgresql://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway"

def identify_misclassified():
    """Identify misclassified transactions."""
    engine = create_engine(DATABASE_URL)
    
    user_id = "0xC2952cc28EDf37B053188D89e6ac888B9855d132"
    cdp_wallet = "0x1409f9dfb8c05a31a5fb4b3ffeea60298bef30bb"
    
    with engine.connect() as conn:
        print("=== MISCLASSIFIED DEPOSITS ===")
        print("These DEPOSIT transactions should NOT count toward user deposits:\n")
        
        # Find all DEPOSIT transactions that are NOT from user to CDP wallet
        result = conn.execute(text("""
            SELECT id, event_data, created_at
            FROM transactions
            WHERE user_id = :user_id
              AND tx_type = 'DEPOSIT'
              AND status = 'CONFIRMED'
            ORDER BY created_at ASC
        """), {"user_id": user_id})
        
        misclassified_deposit_total = Decimal(0)
        real_deposit_total = Decimal(0)
        
        for tx in result.fetchall():
            tx_id, event_data, created_at = tx
            
            if not event_data:
                continue
                
            from_addr = event_data.get('from_address', '').lower()
            to_addr = event_data.get('to_address', '').lower()
            amount = Decimal(str(event_data.get('amount_usdc', 0)))
            
            if from_addr == user_id.lower() and to_addr == cdp_wallet.lower():
                # This is a REAL deposit
                real_deposit_total += amount
                print(f"✅ CORRECT: {created_at.strftime('%Y-%m-%d')} - ${amount:.2f} - User → CDP Wallet")
            else:
                # This is MISCLASSIFIED
                misclassified_deposit_total += amount
                source = "Unknown"
                if 'pool' in from_addr or 'b2cc224' in from_addr:
                    source = "Pool Return"
                elif 'a4fdd479' in from_addr:
                    source = "AERO Swap"
                elif '00c1bc0c' in from_addr:
                    source = "External Transfer"
                    
                print(f"❌ MISCLASSIFIED: {created_at.strftime('%Y-%m-%d')} - ${amount:.2f} - {source} ({from_addr[:10]}...)")
        
        print(f"\nTotal REAL deposits: ${real_deposit_total:.2f}")
        print(f"Total MISCLASSIFIED as deposits: ${misclassified_deposit_total:.2f}")
        print(f"DB shows total deposits: $9862.50")
        
        print("\n=== MISCLASSIFIED WITHDRAWALS ===")
        print("These WITHDRAWAL transactions should NOT count toward user withdrawals:\n")
        
        # Find all WITHDRAWAL transactions that are NOT from CDP wallet to user
        result = conn.execute(text("""
            SELECT id, event_data, created_at
            FROM transactions
            WHERE user_id = :user_id
              AND tx_type IN ('WITHDRAWAL', 'WITHDRAW')
              AND status = 'CONFIRMED'
            ORDER BY created_at ASC
        """), {"user_id": user_id})
        
        misclassified_withdrawal_total = Decimal(0)
        real_withdrawal_total = Decimal(0)
        
        for tx in result.fetchall():
            tx_id, event_data, created_at = tx
            
            if not event_data:
                continue
                
            from_addr = event_data.get('from_address', '').lower()
            to_addr = event_data.get('to_address', '').lower()
            amount = Decimal(str(event_data.get('amount_usdc', 0)))
            
            if from_addr == cdp_wallet.lower() and to_addr == user_id.lower():
                # This is a REAL withdrawal
                real_withdrawal_total += amount
                print(f"✅ CORRECT: {created_at.strftime('%Y-%m-%d')} - ${amount:.2f} - CDP Wallet → User")
            else:
                # This is MISCLASSIFIED
                misclassified_withdrawal_total += amount
                destination = "Unknown"
                if 'fd75350' in to_addr:
                    destination = "Protocol Fees"
                    
                print(f"❌ MISCLASSIFIED: {created_at.strftime('%Y-%m-%d')} - ${amount:.2f} - To {destination} ({to_addr[:10]}...)")
        
        print(f"\nTotal REAL withdrawals: ${real_withdrawal_total:.2f}")
        print(f"Total MISCLASSIFIED as withdrawals: ${misclassified_withdrawal_total:.2f}")
        print(f"DB shows total withdrawals: $11358.05")
        
        print("\n=== SUMMARY ===")
        print(f"CORRECT Net Deposits: ${real_deposit_total - real_withdrawal_total:.2f}")
        print(f"DB Net Deposits (WRONG): $-1495.56")
        print(f"\nThe issue: DB is counting internal transfers as user deposits/withdrawals")
        
        # Check how totals are calculated
        print("\n=== HOW TO FIX ===")
        print("Option 1: Fix get_deposit_withdrawal_totals() in user_service.py")
        print("         - Only count tx where from/to matches user wallet correctly")
        print("\nOption 2: Add transaction classification during event processing")
        print("         - Mark transactions as 'user_initiated' vs 'internal'")
        print("\nOption 3: Recalculate totals with a migration script")
        print("         - Fix historical data for all users")

if __name__ == "__main__":
    identify_misclassified()