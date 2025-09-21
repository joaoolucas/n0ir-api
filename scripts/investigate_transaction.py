#!/usr/bin/env python3
"""Script to investigate transaction e509fbad-d00c-4f0f-a04f-b962dd6ef07f"""

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.database.session import async_session_maker
from app.database.models import Transaction, Position
from loguru import logger
import json


async def investigate_transaction():
    """Investigate the specific transaction and see why it's in the database"""

    tx_hash = "e509fbad-d00c-4f0f-a04f-b962dd6ef07f"

    async with async_session_maker() as db:
        # Query the transaction
        stmt = select(Transaction).where(Transaction.tx_hash == tx_hash)
        result = await db.execute(stmt)
        transaction = result.scalar_one_or_none()

        if not transaction:
            logger.info(f"Transaction {tx_hash} not found in database")
            return

        logger.info("=" * 80)
        logger.info(f"Transaction found: {tx_hash}")
        logger.info("=" * 80)

        # Display transaction details
        logger.info(f"User ID: {transaction.user_id}")
        logger.info(f"Type: {transaction.tx_type}")
        logger.info(f"Amount USDC: {transaction.amount_usdc}")
        logger.info(f"Status: {transaction.status}")
        logger.info(f"Position ID: {transaction.position_id}")
        logger.info(f"Block Number: {transaction.block_number}")
        logger.info(f"Block Timestamp: {transaction.block_timestamp}")
        logger.info(f"Created At: {transaction.created_at}")
        logger.info(f"Updated At: {transaction.updated_at}")

        if transaction.event_data:
            logger.info("\nEvent Data:")
            logger.info(json.dumps(transaction.event_data, indent=2, default=str))

        # Check if there's a position linked
        if transaction.position_id:
            stmt = select(Position).where(Position.token_id == transaction.position_id)
            result = await db.execute(stmt)
            position = result.scalar_one_or_none()

            if position:
                logger.info("\n" + "=" * 80)
                logger.info(f"Linked Position: {position.token_id}")
                logger.info("=" * 80)
                logger.info(f"Pool: {position.pool_address}")
                logger.info(f"Pool Name: {position.pool_name}")
                logger.info(f"Status: {position.status}")
                logger.info(f"Entry Amount: {position.entry_amount_usdc}")
                logger.info(f"Entry TX Hash: {position.entry_tx_hash}")
            else:
                logger.warning(f"Position {transaction.position_id} referenced but not found")

        # Check for duplicate or related transactions
        logger.info("\n" + "=" * 80)
        logger.info("Checking for related transactions...")
        logger.info("=" * 80)

        # Find other POSITION_CREATED transactions for the same user around the same time
        if transaction.block_timestamp:
            stmt = select(Transaction).where(
                and_(
                    Transaction.user_id == transaction.user_id,
                    Transaction.tx_type == "POSITION_CREATED",
                    Transaction.tx_hash != tx_hash
                )
            ).order_by(Transaction.block_timestamp.asc())

            result = await db.execute(stmt)
            related_txs = result.scalars().all()

            if related_txs:
                logger.info(f"Found {len(related_txs)} other POSITION_CREATED transactions for user {transaction.user_id[:8]}...")
                for tx in related_txs[:5]:  # Show first 5
                    logger.info(f"  - {tx.tx_hash[:20]}... | Amount: {tx.amount_usdc} | Block: {tx.block_number} | Position: {tx.position_id}")

        # Analyze why this might be invalid
        logger.info("\n" + "=" * 80)
        logger.info("Analysis:")
        logger.info("=" * 80)

        issues = []

        # Check 1: Zero or negative amount
        if transaction.amount_usdc <= 0:
            issues.append(f"Invalid amount: {transaction.amount_usdc} USDC (should be positive)")

        # Check 2: No position linked for POSITION_CREATED
        if transaction.tx_type == "POSITION_CREATED" and not transaction.position_id:
            issues.append("POSITION_CREATED transaction has no linked position")

        # Check 3: Check event data for clues
        if transaction.event_data:
            usdc_in = transaction.event_data.get("usdc_in", 0)
            usdc_out = transaction.event_data.get("usdc_out", 0)

            # Convert to decimal if they're stored as strings
            if isinstance(usdc_in, str):
                usdc_in = Decimal(usdc_in) if usdc_in else 0
            if isinstance(usdc_out, str):
                usdc_out = Decimal(usdc_out) if usdc_out else 0

            net_amount = (usdc_out - usdc_in) / Decimal(1_000_000) if (usdc_out or usdc_in) else 0

            if net_amount <= 0:
                issues.append(f"Net USDC amount is zero or negative: usdc_out({usdc_out}) - usdc_in({usdc_in}) = {net_amount}")

            # Check for NFT token ID
            if not transaction.event_data.get("nft_token_id") and not transaction.event_data.get("token_id"):
                issues.append("No NFT token ID found in event data")

        if issues:
            logger.warning("Issues found:")
            for issue in issues:
                logger.warning(f"  ❌ {issue}")

            logger.info("\n" + "=" * 80)
            logger.info("Recommendation:")
            logger.info("=" * 80)
            logger.info("This transaction appears to be invalid because:")
            logger.info("1. It likely represents a position interaction with zero net investment")
            logger.info("2. The WalletTransactionService should have filtered it out (line 652-654)")
            logger.info("3. It may have been saved before the filtering logic was added")
            logger.info("\nThis transaction should be removed from the database.")
        else:
            logger.info("✓ No obvious issues found with this transaction")


if __name__ == "__main__":
    asyncio.run(investigate_transaction())