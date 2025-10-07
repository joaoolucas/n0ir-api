#!/usr/bin/env python3
"""
Script to fix existing STAKING transactions that are missing position_id and pool_name.
This script will re-analyze the transaction logs to extract the NFT token ID.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from web3 import Web3
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.database.base import get_db_context
from app.database.models import Transaction, Position
from app.core.config import settings


class StakingTransactionFixer:
    """Fix STAKING transactions missing position data."""

    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(settings.rpc_url))
        self.fixed_count = 0
        self.error_count = 0

    async def fix_all_staking_transactions(self, db: AsyncSession):
        """Find and fix all STAKING transactions missing position_id."""
        logger.info("Searching for STAKING transactions with missing position_id...")

        # Find all STAKING transactions with null position_id
        stmt = select(Transaction).where(
            and_(
                Transaction.tx_type == "STAKING",
                Transaction.position_id.is_(None)
            )
        ).order_by(Transaction.created_at.desc())

        result = await db.execute(stmt)
        transactions = result.scalars().all()

        logger.info(f"Found {len(transactions)} STAKING transactions to fix")

        for tx in transactions:
            await self.fix_transaction(db, tx)

        # Commit all changes
        await db.commit()

        logger.info(f"✅ Fixed {self.fixed_count} transactions")
        if self.error_count > 0:
            logger.warning(f"⚠️ Failed to fix {self.error_count} transactions")

    async def fix_transaction(self, db: AsyncSession, tx: Transaction):
        """Fix a single STAKING transaction by extracting NFT ID from logs."""
        logger.info(f"Processing transaction {tx.tx_hash[:10]}...")

        try:
            # Get transaction receipt from blockchain
            receipt = self.w3.eth.get_transaction_receipt(tx.tx_hash)

            # Look for ERC721 Transfer events
            nft_token_id = None
            gauge_address = tx.event_data.get('gauge_address') if tx.event_data else None

            for log in receipt['logs']:
                # ERC721 Transfer event signature
                transfer_sig = Web3.keccak(text="Transfer(address,address,uint256)").hex()

                if len(log['topics']) >= 4 and log['topics'][0].hex() == transfer_sig:
                    # Extract addresses from topics
                    from_addr = Web3.to_checksum_address('0x' + log['topics'][1].hex()[-40:])
                    to_addr = Web3.to_checksum_address('0x' + log['topics'][2].hex()[-40:])

                    # Check if this is a transfer from the CDP wallet to the gauge
                    cdp_wallet = tx.event_data.get('cdp_wallet') if tx.event_data else None

                    if cdp_wallet and from_addr.lower() == cdp_wallet.lower():
                        # Extract NFT token ID from topic[3]
                        nft_token_id = int(log['topics'][3].hex(), 16)

                        # The 'to' address is the gauge
                        if not gauge_address:
                            gauge_address = to_addr

                        logger.info(f"Found NFT token ID {nft_token_id} being staked to gauge {gauge_address}")
                        break

            if nft_token_id:
                # Update transaction with NFT token ID
                tx.position_id = nft_token_id

                # Update event_data
                if not tx.event_data:
                    tx.event_data = {}

                tx.event_data['nft_token_id'] = nft_token_id
                tx.event_data['tokenId'] = str(nft_token_id)
                tx.event_data['token_id'] = nft_token_id

                if gauge_address:
                    tx.event_data['gauge_address'] = gauge_address

                # Remove the needs_review flags since we found the ID
                if 'needs_review' in tx.event_data:
                    del tx.event_data['needs_review']
                if 'missing_fields' in tx.event_data:
                    del tx.event_data['missing_fields']
                if 'incomplete_reason' in tx.event_data:
                    del tx.event_data['incomplete_reason']
                if 'needs_manual_review' in tx.event_data:
                    del tx.event_data['needs_manual_review']

                # Try to find the position to get pool info
                stmt = select(Position).where(Position.token_id == nft_token_id)
                result = await db.execute(stmt)
                position = result.scalar_one_or_none()

                if position:
                    tx.pool_name = position.pool_name
                    tx.event_data['pool_name'] = position.pool_name
                    tx.event_data['pool'] = position.pool_address
                    logger.info(f"Found position {nft_token_id} with pool {position.pool_name}")

                    # Also update the position as staked if not already
                    if not position.staked:
                        position.staked = True
                        position.gauge_address = gauge_address
                        logger.info(f"Marked position {nft_token_id} as staked")
                else:
                    logger.warning(f"Position {nft_token_id} not found in database")

                self.fixed_count += 1
                logger.info(f"✅ Fixed transaction {tx.tx_hash[:10]}... with NFT ID {nft_token_id}")
            else:
                logger.warning(f"⚠️ Could not find NFT token ID in transaction {tx.tx_hash[:10]}...")
                self.error_count += 1

        except Exception as e:
            logger.error(f"Error processing transaction {tx.tx_hash[:10]}...: {e}")
            self.error_count += 1


async def main():
    """Main function."""
    logger.info("Starting STAKING transaction fix script...")

    fixer = StakingTransactionFixer()

    async with get_db_context() as db:
        await fixer.fix_all_staking_transactions(db)

    logger.info("Script completed!")


if __name__ == "__main__":
    asyncio.run(main())