#!/usr/bin/env python3
"""Fix all positions with missing strategy_type by mapping from pool names."""

import asyncpg
import asyncio

def determine_strategy_from_pool(pool_name):
    """Determine strategy type based on pool name/tokens."""
    if not pool_name:
        return None

    pool_name_lower = pool_name.lower()

    # Stable pairs - USDC with stablecoins
    if any(pair in pool_name_lower for pair in ['usdc/eurc', 'eurc/usdc']):
        return 'stable_usdc_eurc'
    if any(pair in pool_name_lower for pair in ['usdc/brz', 'brz/usdc']):
        return 'stable_usdc_brz'
    if any(pair in pool_name_lower for pair in ['usdc/msusd', 'msusd/usdc']):
        return 'stable_usdc_msusd'

    # Hedged pairs - typically involve USDC + volatile asset
    if any(pair in pool_name_lower for pair in ['usdc/weth', 'weth/usdc']):
        return 'hedged_weth_only'
    if any(pair in pool_name_lower for pair in ['usdc/cbbtc', 'cbbtc/usdc']):
        return 'hedged_cbbtc_only'

    # Non-hedged volatile pairs - both sides are volatile
    if any(pair in pool_name_lower for pair in ['cbltc/cbbtc', 'cbbtc/cbltc']):
        return 'nonhedged_cbltc_cbbtc'
    if any(pair in pool_name_lower for pair in ['cbada/cbbtc', 'cbbtc/cbada']):
        return 'nonhedged_cbada_cbbtc'
    if any(pair in pool_name_lower for pair in ['cbxrp/cbbtc', 'cbbtc/cbxrp']):
        return 'nonhedged_cbxrp_cbbtc'
    if any(pair in pool_name_lower for pair in ['cbdoge/cbbtc', 'cbbtc/cbdoge']):
        return 'nonhedged_cbdoge_cbbtc'

    return None

async def fix_missing_strategy_types():
    """Fix all positions with NULL or empty strategy_type."""
    database_url = "postgresql://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway"

    conn = await asyncpg.connect(database_url)

    try:
        print("Fixing positions with missing strategy_type\n")
        print("="*80)

        # Get all positions with missing strategy_type
        positions = await conn.fetch(
            """
            SELECT token_id, user_id, pool_name, status, entry_amount_usdc
            FROM positions
            WHERE strategy_type IS NULL
            ORDER BY created_at DESC
            """
        )

        print(f"Found {len(positions)} positions with missing strategy_type\n")

        fixed_count = 0
        skipped_count = 0

        for pos in positions:
            token_id = pos['token_id']
            pool_name = pos['pool_name']
            status = pos['status']

            strategy_type = determine_strategy_from_pool(pool_name)

            if strategy_type:
                print(f"Token {token_id} ({status}): {pool_name} → {strategy_type}")

                await conn.execute(
                    """
                    UPDATE positions
                    SET strategy_type = $1
                    WHERE token_id = $2
                    """,
                    strategy_type,
                    token_id
                )

                fixed_count += 1
            else:
                print(f"Token {token_id} ({status}): {pool_name} → UNKNOWN (skipped)")
                skipped_count += 1

        print(f"\n{'='*80}")
        print(f"✅ Fixed {fixed_count} positions")
        print(f"⚠️  Skipped {skipped_count} positions (unknown pool mapping)")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_missing_strategy_types())
