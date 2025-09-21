#!/usr/bin/env python3
"""
Test script to verify that position_id and pool_name are properly populated
for position-related transactions after the enhancement.
"""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg
from datetime import datetime, timedelta

async def check_position_transactions():
    """Check position-related transactions for missing data."""
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL not set")

    # Connect directly using asyncpg
    conn = await asyncpg.connect(database_url)

    try:
        print("=" * 80)
        print("POSITION DATA COMPLETENESS CHECK")
        print("=" * 80)

        # Get all position-related transactions
        position_tx_types = ['POSITION_CREATED', 'POSITION_CLOSED', 'STAKING']

        query = """
        SELECT id, tx_type, user_id, position_id, tx_hash, event_data, created_at
        FROM transactions
        WHERE tx_type = ANY($1::text[])
        ORDER BY created_at DESC
        """

        transactions = await conn.fetch(query, position_tx_types)

        print(f"\nTotal position-related transactions: {len(transactions)}")

        # Analyze completeness
        missing_position_id = []
        missing_pool_name = []
        fallback_pool_name = []
        needs_review = []
        complete = []

        for tx in transactions:
            has_position_id = tx['position_id'] is not None

            # Check pool_name in event_data
            event_data = tx['event_data'] or {}
            pool_name = event_data.get('pool_name')
            has_pool_name = pool_name is not None
            is_fallback = pool_name and pool_name.startswith('Pool-')

            # Check if flagged for review
            is_flagged = event_data.get('needs_review', False)

            if not has_position_id:
                missing_position_id.append(tx)

            if not has_pool_name:
                missing_pool_name.append(tx)
            elif is_fallback:
                fallback_pool_name.append(tx)

            if is_flagged:
                needs_review.append(tx)

            if has_position_id and has_pool_name and not is_fallback and not is_flagged:
                complete.append(tx)

        # Print statistics
        print(f"\n📊 STATISTICS:")
        print(f"  ✅ Complete transactions: {len(complete)} ({len(complete)*100/len(transactions):.1f}%)")
        print(f"  ❌ Missing position_id: {len(missing_position_id)} ({len(missing_position_id)*100/len(transactions):.1f}%)")
        print(f"  ❌ Missing pool_name: {len(missing_pool_name)} ({len(missing_pool_name)*100/len(transactions):.1f}%)")
        print(f"  ⚠️  Fallback pool_name: {len(fallback_pool_name)} ({len(fallback_pool_name)*100/len(transactions):.1f}%)")
        print(f"  🔍 Flagged for review: {len(needs_review)} ({len(needs_review)*100/len(transactions):.1f}%)")

        # Show examples of problematic transactions
        if missing_position_id:
            print(f"\n❌ TRANSACTIONS MISSING POSITION_ID (showing first 5):")
            for tx in missing_position_id[:5]:
                print(f"  - {tx['id']} | {tx['tx_type']} | User: {tx['user_id'][:8]}... | Hash: {tx['tx_hash'][:10] if tx['tx_hash'] else 'N/A'}...")
                event_data = tx['event_data'] or {}
                if event_data.get('missing_fields'):
                    print(f"    Missing fields: {', '.join(event_data['missing_fields'])}")

        if missing_pool_name:
            print(f"\n❌ TRANSACTIONS MISSING POOL_NAME (showing first 5):")
            for tx in missing_pool_name[:5]:
                print(f"  - {tx['id']} | {tx['tx_type']} | Position: {tx['position_id']} | Hash: {tx['tx_hash'][:10] if tx['tx_hash'] else 'N/A'}...")

        if fallback_pool_name:
            print(f"\n⚠️ TRANSACTIONS WITH FALLBACK POOL_NAME (showing first 5):")
            for tx in fallback_pool_name[:5]:
                event_data = tx['event_data'] or {}
                pool_name = event_data.get('pool_name', 'N/A')
                print(f"  - {tx['id']} | {tx['tx_type']} | Position: {tx['position_id']} | Pool: {pool_name}")

        if needs_review:
            print(f"\n🔍 TRANSACTIONS FLAGGED FOR REVIEW (showing first 5):")
            for tx in needs_review[:5]:
                event_data = tx['event_data'] or {}
                missing_fields = event_data.get('missing_fields', [])
                print(f"  - {tx['id']} | {tx['tx_type']} | Position: {tx['position_id']}")
                if missing_fields:
                    print(f"    Issues: {', '.join(missing_fields)}")

        # Check recent transactions to see if the fix is working
        recent_cutoff = datetime.utcnow() - timedelta(hours=1)
        recent_query = """
        SELECT id, tx_type, user_id, position_id, tx_hash, event_data, created_at
        FROM transactions
        WHERE tx_type = ANY($1::text[])
        AND created_at >= $2
        ORDER BY created_at DESC
        """

        recent_txs = await conn.fetch(recent_query, position_tx_types, recent_cutoff)

        if recent_txs:
            print(f"\n📅 RECENT TRANSACTIONS (last hour):")
            print(f"  Total: {len(recent_txs)}")

            recent_complete = sum(1 for tx in recent_txs
                                if tx['position_id'] and
                                tx['event_data'] and
                                tx['event_data'].get('pool_name') and
                                not tx['event_data'].get('pool_name', '').startswith('Pool-'))

            print(f"  Complete: {recent_complete} ({recent_complete*100/len(recent_txs):.1f}%)")

            for tx in recent_txs[:3]:
                event_data = tx['event_data'] or {}
                pool_name = event_data.get('pool_name')
                print(f"\n  Transaction {str(tx['id'])[:8]}...:")
                print(f"    Type: {tx['tx_type']}")
                print(f"    Position ID: {tx['position_id'] or 'MISSING'}")
                print(f"    Pool Name: {pool_name or 'MISSING'}")
                if event_data.get('needs_review'):
                    print(f"    ⚠️ Flagged for review: {event_data.get('missing_fields', [])}")

        return len(complete), len(transactions)

    finally:
        await conn.close()

async def main():
    try:
        complete, total = await check_position_transactions()

        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)

        completeness_rate = complete * 100 / total if total > 0 else 0

        if completeness_rate >= 95:
            print(f"✅ EXCELLENT: {completeness_rate:.1f}% of position transactions have complete data")
        elif completeness_rate >= 80:
            print(f"⚠️ GOOD: {completeness_rate:.1f}% of position transactions have complete data")
        else:
            print(f"❌ NEEDS IMPROVEMENT: Only {completeness_rate:.1f}% of position transactions have complete data")

        print("\n💡 The new auto-fetch logic will:")
        print("  1. Automatically discover missing position_ids")
        print("  2. Fetch pool names from multiple sources")
        print("  3. Use fallback values when APIs fail")
        print("  4. Flag problematic transactions for manual review")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)