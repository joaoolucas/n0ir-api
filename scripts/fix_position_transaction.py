#!/usr/bin/env python3
"""
Fix the incorrectly categorized position creation transaction.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.connection import get_async_session
from app.database.models import Transaction
from loguru import logger

async def fix_position_transaction():
    """Fix the specific transaction that was incorrectly categorized."""

    tx_hash = "0x49c3e50bc60da811383b20bdae51174c99a137c13a1bba155cda46735f3a908d"
    user_id = "0xdbe4e3bcb15b221324b776db6f0cbff24918ea51"

    async with get_async_session() as db:
        # First, check if the transaction exists
        stmt = select(Transaction).where(
            Transaction.tx_hash == tx_hash
        )
        result = await db.execute(stmt)
        transaction = result.scalar_one_or_none()

        if not transaction:
            logger.error(f"Transaction {tx_hash} not found in database")

            # Try to fetch and save it
            from app.services.wallet_transaction_service import WalletTransactionService

            # Get user's CDP wallet
            from app.database.models import User
            user_stmt = select(User).where(User.user_id == user_id)
            user_result = await db.execute(user_stmt)
            user = user_result.scalar_one_or_none()

            if not user or not user.cdp_wallet_address:
                logger.error(f"User {user_id} not found or no CDP wallet")
                return

            logger.info(f"User CDP wallet: {user.cdp_wallet_address}")

            # Sync transactions to pick up the missing one
            service = WalletTransactionService(db)
            result = await service.fetch_and_sync_transactions(
                user_id=user_id,
                cdp_wallet_address=user.cdp_wallet_address,
                limit=100
            )

            logger.info(f"Sync result: {result}")

            # Check again
            result = await db.execute(stmt)
            transaction = result.scalar_one_or_none()

            if not transaction:
                logger.error("Transaction still not found after sync")
                return

        logger.info(f"Found transaction: {transaction.id}")
        logger.info(f"Current type: {transaction.tx_type}")
        logger.info(f"Event data: {transaction.event_data}")

        # Check if it needs to be fixed
        if transaction.tx_type not in ["POSITION_CREATED", "POSITION_OPENED"]:
            logger.warning(f"Transaction type is {transaction.tx_type}, may need manual review")

        # Update the transaction type to POSITION_CREATED
        if transaction.tx_type != "POSITION_CREATED":
            transaction.tx_type = "POSITION_CREATED"

            # Update event data to indicate this was a position creation
            if not transaction.event_data:
                transaction.event_data = {}

            transaction.event_data["corrected"] = True
            transaction.event_data["previous_type"] = transaction.tx_type
            transaction.event_data["description"] = "Position opened via LiquidityManager"

            await db.commit()
            logger.success(f"Updated transaction {tx_hash} to POSITION_CREATED")
        else:
            logger.info("Transaction already has correct type")

if __name__ == "__main__":
    asyncio.run(fix_position_transaction())