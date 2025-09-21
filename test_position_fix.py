#!/usr/bin/env python3
"""Test script to verify position creation fix."""

import asyncio
import os
import sys
from datetime import datetime
from decimal import Decimal
import json

# Add the app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.session import engine
from app.database.models import Transaction, Position
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from loguru import logger

# Configure logger for debugging
logger.remove()
logger.add(sys.stdout, level="INFO")


async def test_position_creation():
    """Test position creation with sample data."""
    async with AsyncSession(engine) as db:
        try:
            # Find any POSITION_CREATED transaction
            result = await db.execute(text("""
                SELECT tx_hash, user_id, position_id, event_data
                FROM transactions
                WHERE tx_type = 'POSITION_CREATED'
                AND event_data IS NOT NULL
                LIMIT 5
            """))
            transactions = result.fetchall()

            if not transactions:
                logger.error("No POSITION_CREATED transactions found in database")
                return

            logger.info(f"Found {len(transactions)} POSITION_CREATED transactions")

            for tx in transactions:
                tx_hash, user_id, position_id, event_data = tx
                logger.info(f"\nChecking transaction {tx_hash[:10]}...")
                logger.info(f"  User: {user_id}")
                logger.info(f"  Position ID (column): {position_id}")

                # Parse event_data
                if isinstance(event_data, str):
                    event_data = json.loads(event_data)

                # Try to find position_id in event_data
                found_position_id = None
                for key in ['position_id', 'nft_token_id', 'tokenId', 'token_id']:
                    if key in event_data:
                        found_position_id = event_data.get(key)
                        logger.info(f"  Found position ID in event_data['{key}']: {found_position_id}")
                        break

                # Use position_id from column or event_data
                check_position_id = position_id or found_position_id

                if not check_position_id:
                    logger.warning(f"  No position ID found for this transaction")
                    continue

                # Convert to int if string
                if isinstance(check_position_id, str):
                    try:
                        check_position_id = int(check_position_id)
                    except ValueError:
                        logger.error(f"  Invalid position ID format: {check_position_id}")
                        continue

                # Check if position exists
                result2 = await db.execute(text("""
                    SELECT token_id, status, pool_name, entry_amount_usdc
                    FROM positions
                    WHERE token_id = :position_id
                    AND user_id = :user_id
                """), {"position_id": check_position_id, "user_id": user_id})

                position = result2.fetchone()

                if position:
                    logger.success(f"  ✓ Position {check_position_id} EXISTS")
                    logger.info(f"    Status: {position[1]}, Pool: {position[2]}, Amount: {position[3]}")
                else:
                    logger.error(f"  ✗ Position {check_position_id} MISSING")

                    # Show what data we have for creation
                    amount = event_data.get('amount_usdc', 0)
                    pool = event_data.get('pool', 'unknown')
                    pool_name = event_data.get('pool_name', 'unknown')
                    logger.info(f"    Would create with: amount={amount}, pool={pool}, pool_name={pool_name}")

        except Exception as e:
            logger.error(f"Error: {e}")
            import traceback
            logger.error(traceback.format_exc())


async def main():
    """Main entry point."""
    logger.info("Testing position creation fixes...")
    await test_position_creation()
    await engine.dispose()
    logger.info("\nTest complete!")


if __name__ == "__main__":
    asyncio.run(main())