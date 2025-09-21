#!/usr/bin/env python3
"""
Create position that was minted by gauge contract.
"""

import asyncio
import asyncpg
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

# Load .env from project root
root_dir = Path(__file__).parent.parent
load_dotenv(root_dir / '.env')


async def create_position():
    """Create the position that was minted by gauge."""

    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        database_url = os.getenv('DATABASE_PRIVATE_URL')

    if not database_url:
        print("❌ No database URL found in environment")
        return

    # Get transaction details first
    rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
    w3 = Web3(Web3.HTTPProvider(rpc_url))

    tx_hash = '0x6760b89cbe37d7441dd49de1e1239f9362f0f9741c024f0ac93dec4b7bc46d00'
    position_id = 26256789
    user_id = '0xAC65e18F7f4e5eDEA297b9E5433C153f1d9a7764'
    cdp_wallet = '0x680214379083fa0d66d1EC030A045beEFB8Ec43f'

    print("="*60)
    print("CREATING GAUGE-MINTED POSITION")
    print("="*60)

    # Get transaction timestamp
    tx = w3.eth.get_transaction(tx_hash)
    receipt = w3.eth.get_transaction_receipt(tx_hash)
    block = w3.eth.get_block(receipt.blockNumber)
    timestamp = datetime.fromtimestamp(block.timestamp)

    print(f"\nPosition details:")
    print(f"   Token ID: {position_id}")
    print(f"   User: {user_id}")
    print(f"   CDP Wallet: {cdp_wallet}")
    print(f"   Entry TX: {tx_hash}")
    print(f"   Entry Date: {timestamp}")

    conn = await asyncpg.connect(database_url)

    try:
        # First check if it exists
        exists = await conn.fetchval(
            "SELECT token_id FROM positions WHERE token_id = $1",
            position_id
        )

        if exists:
            print(f"\n⚠️ Position {position_id} already exists")
            return

        # Find the pool from the logs (look for pool interactions)
        # The gauge at 0x827922686190790b37229fd06084350E74485b72 is for WETH/USDC pool
        pool_address = '0xb2cc224c1c9feE385f8ad6a55b4d94E92359DC59'  # WETH/USDC pool
        pool_name = 'WETH/USDC'

        # Create the position with all required fields
        insert_query = """
        INSERT INTO positions (
            token_id,
            user_id,
            pool_address,
            pool_name,
            gauge_address,
            entry_date,
            entry_tx_hash,
            entry_amount_usdc,
            current_value_usdc,
            fees_earned_usdc,
            rewards_earned_usdc,
            realized_pnl_usdc,
            status,
            staked,
            created_at,
            updated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, NOW(), NOW())
        RETURNING token_id
        """

        result = await conn.fetchval(
            insert_query,
            position_id,
            user_id,
            pool_address,
            pool_name,
            '0x827922686190790b37229fd06084350E74485b72',  # gauge address
            timestamp,
            tx_hash,
            0.0,  # No USDC in this transaction
            0.0,  # current_value_usdc
            0.0,  # fees_earned_usdc
            0.0,  # rewards_earned_usdc
            0.0,  # realized_pnl_usdc
            'ACTIVE',
            True  # Minted by gauge means it's staked
        )

        if result:
            print(f"\n✅ Created position {result}")

            # Also create the POSITION_CREATED transaction
            tx_insert = """
            INSERT INTO transactions (
                id,
                user_id,
                tx_hash,
                tx_type,
                amount_usdc,
                position_id,
                status,
                event_data,
                created_at,
                block_timestamp
            ) VALUES (
                gen_random_uuid(),
                $1, $2, $3, $4, $5, $6, $7, $8, $9
            )
            RETURNING id
            """

            event_data = {
                "nft_token_id": position_id,
                "pool": pool_address,
                "pool_name": pool_name,
                "gauge_address": "0x827922686190790b37229fd06084350E74485b72",
                "description": "Position created via gauge contract (unusual pattern)",
                "minted_by": "gauge",
                "categorized_by": "manual_fix"
            }

            import json
            tx_id = await conn.fetchval(
                tx_insert,
                user_id,
                tx_hash,
                'POSITION_CREATED',
                0.0,
                position_id,
                'CONFIRMED',
                json.dumps(event_data),  # Convert to JSON string
                timestamp,
                timestamp
            )

            if tx_id:
                print(f"✅ Created POSITION_CREATED transaction")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(create_position())