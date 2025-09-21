#!/usr/bin/env python3
"""Debug script to test position creation for a specific user."""

import asyncio
import os
import sys
from datetime import datetime
from decimal import Decimal

# Add the app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.session import get_db, engine
from app.database.models import Transaction, Position, User
from app.services.wallet_transaction_service import WalletTransactionService
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

# Configure logger for debugging
logger.remove()
logger.add(sys.stdout, level="DEBUG")


async def debug_position_creation(user_id: str):
    """Debug position creation for a specific user."""
    async with AsyncSession(engine) as db:
        try:
            # First, check if user exists
            stmt = select(User).where(User.user_id == user_id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                logger.error(f"User {user_id} not found")
                return

            logger.info(f"Found user: {user_id}, CDP wallet: {user.cdp_wallet_address}")

            # Check for POSITION_CREATED transactions with position 26295138
            stmt = select(Transaction).where(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.tx_type == "POSITION_CREATED"
                )
            )
            result = await db.execute(stmt)
            transactions = result.scalars().all()

            logger.info(f"Found {len(transactions)} POSITION_CREATED transactions")

            # Look for the specific position
            target_position_id = 26295138
            found_tx = None

            for tx in transactions:
                # Check position_id column
                if tx.position_id == target_position_id:
                    found_tx = tx
                    logger.info(f"Found transaction with position_id column = {target_position_id}")
                    break

                # Check event_data
                if tx.event_data:
                    for key in ['position_id', 'nft_token_id', 'tokenId', 'token_id']:
                        value = tx.event_data.get(key)
                        if value and (value == target_position_id or str(value) == str(target_position_id)):
                            found_tx = tx
                            logger.info(f"Found transaction with event_data['{key}'] = {value}")
                            break

            if not found_tx:
                logger.error(f"No POSITION_CREATED transaction found for position {target_position_id}")
                # List all position IDs found
                for tx in transactions:
                    pos_id = tx.position_id or "None"
                    event_ids = []
                    if tx.event_data:
                        for key in ['position_id', 'nft_token_id', 'tokenId', 'token_id']:
                            if key in tx.event_data:
                                event_ids.append(f"{key}={tx.event_data[key]}")
                    logger.info(f"  tx {tx.tx_hash[:10]}... position_id={pos_id}, event_data: {', '.join(event_ids)}")
                return

            logger.info(f"Transaction details:")
            logger.info(f"  tx_hash: {found_tx.tx_hash}")
            logger.info(f"  position_id column: {found_tx.position_id}")
            logger.info(f"  event_data: {found_tx.event_data}")

            # Check if position exists
            stmt = select(Position).where(
                and_(
                    Position.token_id == target_position_id,
                    Position.user_id == user_id
                )
            )
            result = await db.execute(stmt)
            position = result.scalar_one_or_none()

            if position:
                logger.success(f"✓ Position {target_position_id} EXISTS in database")
                logger.info(f"  Status: {position.status}")
                logger.info(f"  Pool: {position.pool_name or position.pool_address}")
                logger.info(f"  Entry amount: {position.entry_amount_usdc} USDC")
            else:
                logger.error(f"✗ Position {target_position_id} NOT FOUND in database")

                # Try to create it now
                logger.info("Attempting to create position manually...")

                # Get data from transaction
                amount_usdc = Decimal(str(found_tx.event_data.get('amount_usdc', 0))) if found_tx.event_data else Decimal(0)
                pool_address = found_tx.event_data.get('pool') if found_tx.event_data else None
                pool_name = found_tx.event_data.get('pool_name') if found_tx.event_data else None

                logger.info(f"  Creating with: amount={amount_usdc}, pool={pool_address}, pool_name={pool_name}")

                # Create the position
                wallet_service = WalletTransactionService(db)

                try:
                    await wallet_service._create_position_if_needed(
                        user_id=user_id,
                        position_id=target_position_id,
                        pool_address=pool_address,
                        pool_name=pool_name,
                        tx_hash=found_tx.tx_hash,
                        amount_usdc=amount_usdc
                    )

                    # Commit the change
                    await db.commit()

                    # Verify it was created
                    stmt = select(Position).where(
                        and_(
                            Position.token_id == target_position_id,
                            Position.user_id == user_id
                        )
                    )
                    result = await db.execute(stmt)
                    position = result.scalar_one_or_none()

                    if position:
                        logger.success(f"✓ Successfully created position {target_position_id}")
                    else:
                        logger.error(f"✗ Failed to create position {target_position_id}")

                except Exception as e:
                    logger.error(f"Error creating position: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    await db.rollback()

            # Now try the ensure_positions_for_transactions method
            logger.info("\nTesting ensure_positions_for_transactions method...")
            wallet_service = WalletTransactionService(db)
            await wallet_service.ensure_positions_for_transactions(user_id)
            await db.commit()

            # Final check
            stmt = select(Position).where(
                and_(
                    Position.token_id == target_position_id,
                    Position.user_id == user_id
                )
            )
            result = await db.execute(stmt)
            position = result.scalar_one_or_none()

            if position:
                logger.success(f"✓ Final check: Position {target_position_id} EXISTS")
            else:
                logger.error(f"✗ Final check: Position {target_position_id} STILL MISSING")

        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            import traceback
            logger.error(traceback.format_exc())


async def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python debug_position_creation.py <user_id>")
        sys.exit(1)

    user_id = sys.argv[1]
    logger.info(f"Debugging position creation for user: {user_id}")

    await debug_position_creation(user_id)

    # Clean up
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())