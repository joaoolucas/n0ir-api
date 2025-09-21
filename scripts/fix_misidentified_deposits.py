#!/usr/bin/env python3
"""
Fix transactions that were misidentified as POSITION_CLOSED when they're actually DEPOSIT.

A POSITION_CLOSED should either:
1. Have both USDC and AERO coming in
2. Be associated with an actual position that was closed
3. Have a reasonable amount relative to the position entry

A DEPOSIT is:
- USDC coming in from owner wallet to CDP wallet
- No AERO involved
- Often round numbers (like 50, 100, 1000 USDC)
"""

import asyncio
import asyncpg
import os
from datetime import datetime
from decimal import Decimal
from dotenv import load_dotenv
import sys
from pathlib import Path

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


async def fix_misidentified_deposits():
    """Find and fix POSITION_CLOSED transactions that are actually deposits."""

    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        database_url = os.getenv('DATABASE_PRIVATE_URL')

    if not database_url:
        print("❌ No database URL found in environment")
        return

    conn = await asyncpg.connect(database_url)

    try:
        print("="*60)
        print("FIXING MISIDENTIFIED DEPOSITS")
        print("="*60)

        # Find suspicious POSITION_CLOSED transactions
        # These are likely deposits if:
        # 1. USDC in, no AERO in
        # 2. Round USDC amounts (common for deposits)
        # 3. No matching position or position doesn't make sense

        query = """
        SELECT
            t.id,
            t.tx_hash,
            t.user_id,
            t.position_id,
            t.tx_type,
            t.event_data,
            t.created_at,
            t.block_timestamp,
            p.token_id as position_exists,
            p.entry_amount_usdc,
            p.status as position_status
        FROM transactions t
        LEFT JOIN positions p ON p.token_id = t.position_id AND p.user_id = t.user_id
        WHERE t.tx_type = 'POSITION_CLOSED'
        AND t.event_data->>'aero_in' = '0'  -- No AERO coming in
        AND CAST(t.event_data->>'usdc_in' AS BIGINT) > 0  -- USDC coming in
        ORDER BY t.created_at DESC
        """

        suspicious_txs = await conn.fetch(query)

        print(f"\n📊 Found {len(suspicious_txs)} POSITION_CLOSED transactions with no AERO")

        to_fix = []

        for tx in suspicious_txs:
            tx_id = tx['id']
            tx_hash = tx['tx_hash']
            position_id = tx['position_id']
            event_data = tx['event_data'] or {}

            # Parse event_data if it's a string
            import json
            if isinstance(event_data, str):
                try:
                    event_data = json.loads(event_data)
                except:
                    event_data = {}

            usdc_in = event_data.get('usdc_in', 0)

            # Convert to float for analysis
            if isinstance(usdc_in, str):
                usdc_amount = float(usdc_in) / 1_000_000  # Convert from base units
            else:
                usdc_amount = float(usdc_in) / 1_000_000

            # Check if this looks like a deposit
            is_likely_deposit = False
            reasons = []

            # Check 1: Round number (common for deposits)
            if usdc_amount in [10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000, 10000]:
                is_likely_deposit = True
                reasons.append(f"Round amount: {usdc_amount} USDC")

            # Check 2: No associated position
            if not tx['position_exists']:
                is_likely_deposit = True
                reasons.append("No matching position found")

            # Check 3: Position exists but amount doesn't match
            elif tx['entry_amount_usdc']:
                entry_amount = float(tx['entry_amount_usdc'])
                # If return is exactly a round number and very different from entry
                if abs(usdc_amount - entry_amount) > entry_amount * 0.5:
                    is_likely_deposit = True
                    reasons.append(f"Amount mismatch: entry={entry_amount:.2f}, return={usdc_amount:.2f}")

            # Check 4: Position is still ACTIVE (can't be closed)
            if tx['position_status'] == 'ACTIVE':
                is_likely_deposit = True
                reasons.append("Associated position is still ACTIVE")

            if is_likely_deposit:
                to_fix.append({
                    'id': tx_id,
                    'tx_hash': tx_hash,
                    'position_id': position_id,
                    'amount': usdc_amount,
                    'reasons': reasons,
                    'user_id': tx['user_id']
                })

        print(f"\n🔍 Found {len(to_fix)} transactions that are likely deposits")

        # Show what we're going to fix
        for item in to_fix[:10]:  # Show first 10
            print(f"\n📝 Transaction: {item['tx_hash'][:10]}...")
            print(f"   Amount: {item['amount']:.2f} USDC")
            print(f"   Position ID: {item['position_id'] or 'None'}")
            print(f"   Reasons: {', '.join(item['reasons'])}")

        if len(to_fix) > 10:
            print(f"\n... and {len(to_fix) - 10} more")

        # Ask for confirmation
        if to_fix:
            print("\n" + "="*60)

            # Check if --yes flag is passed
            if '--yes' in sys.argv:
                response = 'yes'
                print(f"Auto-fixing {len(to_fix)} transactions (--yes flag detected)")
            else:
                response = input(f"Fix {len(to_fix)} transactions from POSITION_CLOSED to DEPOSIT? (yes/no): ")

            if response.lower() == 'yes':
                fixed_count = 0

                for item in to_fix:
                    # Update the transaction
                    update_query = """
                    UPDATE transactions
                    SET
                        tx_type = 'DEPOSIT',
                        position_id = NULL,  -- Remove position association
                        event_data = jsonb_set(
                            jsonb_set(
                                event_data,
                                '{description}',
                                '"USDC deposit from owner wallet"'
                            ),
                            '{corrected_from}',
                            '"POSITION_CLOSED"'
                        )
                    WHERE id = $1
                    RETURNING id
                    """

                    result = await conn.fetchval(update_query, item['id'])

                    if result:
                        fixed_count += 1

                        # If there was a position associated, check if we need to reopen it
                        if item['position_id']:
                            # Check if position was incorrectly closed
                            reopen_query = """
                            UPDATE positions
                            SET
                                status = 'ACTIVE',
                                exit_date = NULL,
                                exit_tx_hash = NULL,
                                realized_pnl_usdc = 0
                            WHERE token_id = $1
                            AND user_id = $2
                            AND status = 'CLOSED'
                            AND exit_tx_hash = $3
                            RETURNING token_id
                            """

                            reopened = await conn.fetchval(
                                reopen_query,
                                item['position_id'],
                                item['user_id'],
                                item['tx_hash']
                            )

                            if reopened:
                                print(f"   ✅ Fixed TX {item['tx_hash'][:10]}... and reopened position {item['position_id']}")
                            else:
                                print(f"   ✅ Fixed TX {item['tx_hash'][:10]}...")
                    else:
                        print(f"   ❌ Failed to fix TX {item['tx_hash'][:10]}...")

                print(f"\n✅ Successfully fixed {fixed_count} transactions")
            else:
                print("❌ Fix cancelled")
        else:
            print("\n✅ No suspicious transactions found - everything looks correct!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()


async def main():
    await fix_misidentified_deposits()


if __name__ == "__main__":
    asyncio.run(main())