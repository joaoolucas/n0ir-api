#!/usr/bin/env python3
"""Sync real on-chain balances for all active users."""

import asyncpg
import asyncio
from decimal import Decimal
from web3 import Web3
import os

async def sync_real_balances():
    """Sync on-chain USDC balances."""
    database_url = "postgresql://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway"

    # Setup Web3
    rpc_url = 'https://mainnet.base.org'
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    usdc_address = Web3.to_checksum_address("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
    usdc_abi = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]
    usdc_contract = w3.eth.contract(address=usdc_address, abi=usdc_abi)

    conn = await asyncpg.connect(database_url)

    try:
        print("Syncing real on-chain USDC balances\n")
        print("="*80)

        # Get all users with active strategies
        users = await conn.fetch(
            """
            SELECT DISTINCT u.user_id, u.cdp_wallet_address, u.usdc_balance
            FROM users u
            JOIN user_strategies us ON u.user_id = us.user_id
            WHERE us.status = 'active' AND u.cdp_wallet_address IS NOT NULL
            ORDER BY u.user_id
            """
        )

        for user in users:
            user_id = user['user_id']
            wallet = user['cdp_wallet_address']
            db_balance = user['usdc_balance']

            print(f"\n👤 User: {user_id}")
            print(f"   Wallet: {wallet}")
            print(f"   DB Balance: ${db_balance}")

            # Get real on-chain balance
            try:
                checksum_wallet = Web3.to_checksum_address(wallet)
                balance_wei = usdc_contract.functions.balanceOf(checksum_wallet).call()
                onchain_balance = Decimal(balance_wei) / Decimal(10 ** 6)
                print(f"   On-chain Balance: ${onchain_balance}")

                # Get active positions
                positions = await conn.fetch(
                    """
                    SELECT token_id, entry_amount_usdc, current_value_usdc
                    FROM positions
                    WHERE user_id = $1 AND status = 'ACTIVE'
                    """,
                    user_id
                )

                total_deployed = sum(Decimal(str(p['entry_amount_usdc'])) for p in positions)
                positions_current_value = sum(
                    Decimal(str(p['current_value_usdc'])) if p['current_value_usdc'] else Decimal('0')
                    for p in positions
                )

                total_portfolio = onchain_balance + positions_current_value

                print(f"   Active Positions: {len(positions)}")
                print(f"   Deployed Capital: ${total_deployed}")
                print(f"   Positions Value: ${positions_current_value}")
                print(f"   Total Portfolio: ${onchain_balance} + ${positions_current_value} = ${total_portfolio}")

                # Update database
                await conn.execute(
                    "UPDATE users SET usdc_balance = $1 WHERE user_id = $2",
                    onchain_balance,
                    user_id
                )

                # Update strategy
                await conn.execute(
                    """
                    UPDATE user_strategies
                    SET allocated_capital_usd = $1,
                        deployed_capital_usd = $2,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = $3 AND status = 'active'
                    """,
                    total_portfolio,
                    total_deployed,
                    user_id
                )

                print(f"   ✅ Updated: allocated=${total_portfolio}, deployed=${total_deployed}")

            except Exception as e:
                print(f"   ❌ Error: {e}")

            print("-"*80)

        print(f"\n{'='*80}")
        print("✅ All balances synced!")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(sync_real_balances())
