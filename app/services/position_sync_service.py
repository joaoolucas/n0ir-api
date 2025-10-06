"""
Service for synchronizing Position records with POSITION_CREATED transactions.
Extracts NFT token_id from blockchain and creates corresponding Position records.
"""

import asyncio
from typing import Optional, Dict, Any, List
from decimal import Decimal
from datetime import datetime
from web3 import Web3
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from loguru import logger

from app.database.models import Transaction, Position, User
from app.core.config import settings
from app.core.positions_service import PositionsService

class PositionSyncService:
    """
    Service responsible for synchronizing Position records with POSITION_CREATED transactions.
    Extracts NFT token_id from blockchain and creates corresponding Position records.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.w3 = Web3(Web3.HTTPProvider(settings.rpc_url))
        self.positions_service = PositionsService()
        self.liquidity_manager_address = settings.liquidity_manager_address.lower()
        self.position_manager_address = "0x827922686190790b37229fd06084350E74485b72".lower()

    async def sync_pending_positions(self) -> Dict[str, Any]:
        """
        Main sync method to process POSITION_CREATED transactions without Position records.
        Returns summary of synced positions.
        """
        # Find unsynced POSITION_CREATED transactions
        stmt = select(Transaction).where(
            and_(
                Transaction.tx_type == "POSITION_CREATED",
                Transaction.status == "CONFIRMED",
                Transaction.position_id.is_(None)  # No linked position yet
            )
        ).order_by(Transaction.block_number.asc())

        result = await self.db.execute(stmt)
        unsynced_transactions = result.scalars().all()

        if not unsynced_transactions:
            return {"synced": 0, "failed": 0, "skipped": 0}

        synced = 0
        failed = 0
        skipped = 0

        for tx in unsynced_transactions:
            try:
                result = await self._sync_position_for_transaction(tx)
                if result == "synced":
                    synced += 1
                elif result == "skipped":
                    skipped += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Failed to sync position for tx {tx.tx_hash}: {e}")
                failed += 1

        await self.db.commit()

        summary = {
            "synced": synced,
            "failed": failed,
            "skipped": skipped,
            "total": len(unsynced_transactions)
        }

        if synced > 0 or failed > 0:
            logger.info(f"Position sync completed: {summary}")

        return summary

    async def _sync_position_for_transaction(self, tx: Transaction) -> str:
        """
        Sync a single POSITION_CREATED transaction to create Position record.
        Returns: "synced", "skipped", or "failed"
        """
        try:
            # Extract token_id from transaction receipt
            token_id = await self._extract_token_id_from_tx(tx.tx_hash)

            if not token_id:
                # Mark transaction to avoid repeated attempts
                if not tx.event_data:
                    tx.event_data = {}
                tx.event_data["sync_failed"] = "no_token_id_found"
                return "failed"

            # Check if position already exists
            existing_position_stmt = select(Position).where(Position.token_id == token_id)
            result = await self.db.execute(existing_position_stmt)
            existing_position = result.scalar_one_or_none()

            if existing_position:
                # Link transaction to existing position
                tx.position_id = token_id
                return "skipped"

            # Get position details from blockchain
            try:
                position_info = await self.positions_service.get_position_by_id(token_id)
            except Exception as e:
                logger.error(f"Error fetching position {token_id} from blockchain: {e}")
                return "failed"

            if not position_info:
                logger.error(f"Position {token_id} not found on blockchain")
                return "failed"

            # Extract additional data from transaction event_data
            event_data = tx.event_data or {}

            # Calculate the actual invested amount
            usdc_out = Decimal(str(event_data.get("usdc_out", 0))) / Decimal(1_000_000)
            usdc_in = Decimal(str(event_data.get("usdc_in", 0))) / Decimal(1_000_000)
            amount_usdc = usdc_out - usdc_in  # Net amount invested

            # Get pool address from event data or position info
            pool_address = event_data.get("pool") or position_info.pool_address

            # Create Position record (no tick_spacing field in model)
            position = Position(
                user_id=tx.user_id,
                token_id=token_id,
                pool_address=pool_address,
                pool_name=position_info.pool_name if hasattr(position_info, 'pool_name') else None,
                token0_address=position_info.token0,
                token1_address=position_info.token1,
                tick_lower=position_info.tick_lower,
                tick_upper=position_info.tick_upper,
                liquidity=str(position_info.liquidity),
                entry_amount_usdc=amount_usdc,
                current_value_usdc=amount_usdc,  # Initialize with entry amount
                entry_tx_hash=tx.tx_hash,
                staked=position_info.staked if hasattr(position_info, 'staked') else False,
                gauge_address=position_info.gauge_address if hasattr(position_info, 'gauge_address') else None,
                status='ACTIVE',
                entry_date=tx.block_timestamp or datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            # Add position to database
            self.db.add(position)

            # Link transaction to position
            tx.position_id = token_id

            # Store token_id in event_data for reference
            if not tx.event_data:
                tx.event_data = {}
            tx.event_data["token_id"] = token_id

            await self.db.flush()  # Flush to get the position ID without committing
            return "synced"

        except Exception as e:
            logger.error(f"Error syncing position for tx {tx.tx_hash}: {e}")
            return "failed"

    async def _extract_token_id_from_tx(self, tx_hash: str) -> Optional[int]:
        """
        Extract NFT token_id from transaction receipt events.
        Looks for IncreaseLiquidity or Transfer events from PositionManager.
        """
        try:
            # Get transaction receipt
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)

            # Look for IncreaseLiquidity event (topic0 without 0x prefix)
            increase_liquidity_topic = "3067048beee31b25b2f1681f88dac838c8bba36af25bfb2b7cf7473a5847e35f"

            # Also look for Transfer event from PositionManager (NFT mint)
            # Transfer(address,address,uint256) topic (without 0x prefix)
            transfer_topic = "ddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

            for log in receipt.logs:
                log_address = log.address.lower()

                # Check if log is from PositionManager
                if log_address == self.position_manager_address:
                    if len(log.topics) > 0:
                        # Get topic0 and remove 0x prefix if present
                        topic0 = log.topics[0].hex()
                        if topic0.startswith("0x"):
                            topic0 = topic0[2:]

                        # IncreaseLiquidity event
                        if topic0 == increase_liquidity_topic and len(log.topics) >= 2:
                            # tokenId is the first indexed parameter (topic[1])
                            token_id = int(log.topics[1].hex(), 16)
                            return token_id

                        # Transfer event (NFT mint)
                        elif topic0 == transfer_topic and len(log.topics) >= 4:
                            # For NFT Transfer, tokenId is topic[3]
                            # Check if it's a mint (from address is 0x0)
                            from_address = log.topics[1].hex()
                            if from_address == "0" * 64:  # Mint from zero address (no 0x)
                                token_id = int(log.topics[3].hex(), 16)
                                return token_id

            # Alternative: Look for any Transfer event to the user's CDP wallet
            # Sometimes the position NFT is minted to an intermediate contract first
            for log in receipt.logs:
                log_address = log.address.lower()

                if log_address == self.position_manager_address:
                    if len(log.topics) > 0:
                        topic0 = log.topics[0].hex()
                        if topic0.startswith("0x"):
                            topic0 = topic0[2:]

                        if topic0 == transfer_topic and len(log.topics) >= 4:
                            # Extract the token_id regardless of from/to addresses
                            token_id = int(log.topics[3].hex(), 16)
                            return token_id

            logger.warning(f"No token_id found in events for tx {tx_hash}")
            return None

        except Exception as e:
            logger.error(f"Error extracting token_id from tx {tx_hash}: {e}")
            return None

# Background task runner
async def run_position_sync_task():
    """
    Background task to periodically sync positions.
    Should be added to your FastAPI startup.
    """
    from app.database.session import async_session_maker

    while True:
        try:
            async with async_session_maker() as db:
                sync_service = PositionSyncService(db)
                result = await sync_service.sync_pending_positions()

        except Exception as e:
            logger.error(f"Position sync task error: {e}")

        # Run every 30 seconds
        await asyncio.sleep(30)