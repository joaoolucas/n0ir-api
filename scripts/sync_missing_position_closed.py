#!/usr/bin/env python3
"""Manually sync a missing POSITION_CLOSED transaction.

This script processes a specific transaction that contains a PositionClosed event
but wasn't captured by the CDP API sync.
"""

import asyncio
import sys
from web3 import Web3
from decimal import Decimal
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import init_db, async_session_maker
from app.database.models import Transaction, Position, User
from app.core.config import settings


async def process_position_closed_transaction(
    tx_hash: str,
    cdp_wallet: str
):
    """Process a POSITION_CLOSED transaction manually from RPC data."""

    # Initialize database
    init_db()

    async with async_session_maker() as session:
        # Check if transaction already exists
        result = await session.execute(
            select(Transaction).where(Transaction.tx_hash == tx_hash)
        )
        existing_tx = result.scalar_one_or_none()

        if existing_tx:
            print(f"Transaction {tx_hash[:10]}... already exists in database")
            print(f"  Type: {existing_tx.tx_type}")
            print(f"  Position ID: {existing_tx.position_id}")
            return

        # Get user by CDP wallet
        result = await session.execute(
            select(User).where(User.cdp_wallet_address == cdp_wallet.lower())
        )
        user = result.scalar_one_or_none()

        if not user:
            print(f"No user found with CDP wallet {cdp_wallet}")
            return

        print(f"Found user: {user.user_id}")

        # Connect to RPC and get transaction receipt
        w3 = Web3(Web3.HTTPProvider(settings.rpc_url))
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        tx = w3.eth.get_transaction(tx_hash)

        if receipt['status'] != 1:
            print(f"Transaction failed (status: {receipt['status']})")
            return

        print(f"Transaction status: SUCCESS")
        print(f"Total logs: {len(receipt.logs)}")

        # Look for PositionClosed event
        POSITION_CLOSED_EVENT = "0xfc4e6ac706594637404ad0c7694a5353537a522cc0cf04a16ca51a228b0f2bd4"
        LIQUIDITY_MANAGER = settings.liquidity_manager_address.lower()

        position_id = None
        pool_address = None
        usdc_returned = 0
        was_staked = False
        was_hedged = False
        hedge_collateral_returned = 0

        for log in receipt.logs:
            if log['address'].lower() != LIQUIDITY_MANAGER:
                continue

            topics = log['topics']
            event_sig = topics[0].hex() if hasattr(topics[0], 'hex') else topics[0]

            if event_sig.lower() == POSITION_CLOSED_EVENT.lower():
                # Parse event
                user_addr = "0x" + (topics[1].hex()[-40:] if hasattr(topics[1], 'hex') else topics[1][-40:])
                position_id = int(topics[2].hex(), 16) if hasattr(topics[2], 'hex') else int(topics[2], 16)
                pool_address = "0x" + (topics[3].hex()[-40:] if hasattr(topics[3], 'hex') else topics[3][-40:])

                # Parse data
                data = log['data'].hex() if hasattr(log['data'], 'hex') else log['data']
                data = data[2:] if data.startswith("0x") else data

                if len(data) >= 64:
                    usdc_returned = int(data[0:64], 16)
                    was_staked = bool(int(data[64:128], 16)) if len(data) >= 128 else False
                    was_hedged = bool(int(data[128:192], 16)) if len(data) >= 192 else False
                    hedge_collateral_returned = int(data[192:256], 16) if len(data) >= 256 else 0

                print(f"\nFound PositionClosed event:")
                print(f"  Position ID: {position_id}")
                print(f"  Pool: {pool_address}")
                print(f"  USDC returned: {usdc_returned / 1e6:.6f}")
                print(f"  Was staked: {was_staked}")
                print(f"  Was hedged: {was_hedged}")
                print(f"  Hedge collateral: {hedge_collateral_returned / 1e6:.6f}")
                break

        if not position_id:
            print("No PositionClosed event found in transaction")
            return

        # Check if position exists
        result = await session.execute(
            select(Position).where(
                and_(
                    Position.token_id == position_id,
                    Position.user_id == user.user_id
                )
            )
        )
        position = result.scalar_one_or_none()

        if not position:
            print(f"Position {position_id} not found for user {user.user_id}")
            return

        print(f"\nPosition {position_id} found:")
        print(f"  Status: {position.status}")
        print(f"  Pool: {position.pool_name}")
        print(f"  Entry amount: {position.entry_amount_usdc}")

        # Get block timestamp
        block = w3.eth.get_block(receipt['blockNumber'])
        block_timestamp = datetime.fromtimestamp(block['timestamp'])

        # Calculate amount in USDC
        amount_usdc = Decimal(usdc_returned) / Decimal(1e6)

        # Create transaction
        event_data = {
            "description": f"Position closed",
            "categorized_by": "manual_sync_script",
            "nft_token_id": position_id,
            "token_id": position_id,
            "position_id": position_id,
            "pool": pool_address,
            "pool_name": position.pool_name,
            "amount_usdc": float(amount_usdc),
            "usdc_returned": usdc_returned,
            "was_staked": was_staked,
            "was_hedged": was_hedged,
            "hedge_collateral_returned": hedge_collateral_returned,
            "usdc_in": usdc_returned,
            "usdc_out": 0
        }

        transaction = Transaction(
            tx_hash=tx_hash,
            user_id=user.user_id,
            tx_type="POSITION_CLOSED",
            status="CONFIRMED",
            block_number=receipt['blockNumber'],
            block_timestamp=block_timestamp,
            event_data=event_data,
            position_id=position_id
        )

        session.add(transaction)

        # Update position status if still ACTIVE
        if position.status == 'ACTIVE':
            realized_pnl = amount_usdc - position.entry_amount_usdc
            position.status = 'CLOSED'
            position.exit_date = block_timestamp
            position.exit_tx_hash = tx_hash
            position.realized_pnl_usdc = realized_pnl
            position.current_value_usdc = amount_usdc

            print(f"\nClosing position {position_id}:")
            print(f"  Entry: {position.entry_amount_usdc} USDC")
            print(f"  Exit: {amount_usdc} USDC")
            print(f"  Realized PnL: {realized_pnl} USDC")

        await session.commit()
        print(f"\n✅ Transaction created and position closed successfully")


async def main():
    """Main entry point."""
    tx_hash = "0x8554b6b8bfebde8c64271cbdd71fa81c663cb8ce0d897e26fac9d2b6f2ff516e"
    cdp_wallet = "0x7b3106f56447c9c313c19f519b290ff4e293d573"

    await process_position_closed_transaction(tx_hash, cdp_wallet)


if __name__ == "__main__":
    asyncio.run(main())
