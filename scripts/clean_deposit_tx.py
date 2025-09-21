#!/usr/bin/env python3
"""
Clean up DEPOSIT transactions that have unnecessary position/pool data.
"""

import asyncio
import asyncpg
import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


async def clean_deposit():
    """Clean up the DEPOSIT transaction."""

    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        database_url = os.getenv('DATABASE_PRIVATE_URL')

    if not database_url:
        print("❌ No database URL found in environment")
        return

    conn = await asyncpg.connect(database_url)

    try:
        print("="*60)
        print("CLEANING DEPOSIT TRANSACTION")
        print("="*60)

        tx_hash = '0xf725a10996cdba4ea34962fd5f5db9ef52c4d59d37cb17350dd4d8721cffb053'

        # Update the transaction to remove position/pool data
        update_query = """
        UPDATE transactions
        SET
            position_id = NULL,
            event_data = jsonb_build_object(
                'cdp_wallet', event_data->>'cdp_wallet',
                'amount_usdc', (event_data->>'amount_usdc')::float,
                'usdc_in', (event_data->>'usdc_in')::bigint,
                'description', 'USDC deposit from owner wallet',
                'categorized_by', 'wallet_transaction_service',
                'corrected_from', 'POSITION_CLOSED'
            )
        WHERE tx_hash = $1
        RETURNING id, event_data
        """

        result = await conn.fetchrow(update_query, tx_hash)

        if result:
            print(f"✅ Cleaned DEPOSIT transaction")
            print(f"   Removed: position_id, pool_name, nft_token_id, pool, token_id")
            print(f"   Kept only: cdp_wallet, amount_usdc, usdc_in, description")
        else:
            print(f"❌ Transaction not found")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(clean_deposit())