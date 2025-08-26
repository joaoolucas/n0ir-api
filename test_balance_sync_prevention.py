#!/usr/bin/env python3
"""Test script to verify BALANCE_SYNC prevention during withdrawals"""

import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, and_
import os
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.models import User, Transaction, Position
from app.services.user_service import UserService
from app.schemas.users import TransactionType, TransactionStatus

# Test database URL (using test database)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost/test_db")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Create async engine and session
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def test_balance_sync_prevention():
    """Test that BALANCE_SYNC is prevented during withdrawals"""
    async with AsyncSessionLocal() as db:
        service = UserService(db)
        
        # Test user ID
        test_user_id = "0xTestUser123"
        
        logger.info("=" * 60)
        logger.info("Testing BALANCE_SYNC prevention during withdrawals")
        logger.info("=" * 60)
        
        # Step 1: Create a test user if not exists
        user = await service.get_user(test_user_id)
        if not user:
            logger.info(f"Creating test user {test_user_id}")
            user = User(
                user_id=test_user_id,
                cdp_wallet_address="0xTestWallet123",
                cdp_wallet_name="test_wallet"
            )
            db.add(user)
            await db.commit()
        
        # Step 2: Create a recent withdrawal transaction (within 5 minutes)
        logger.info("\nStep 1: Creating a recent withdrawal transaction...")
        withdrawal = Transaction(
            user_id=test_user_id,
            tx_type='WITHDRAWAL',
            tx_hash="0xTestWithdrawalTx",
            status='pending',
            event_data={'amount_usdc': 100.0},
            created_at=datetime.now(timezone.utc)
        )
        db.add(withdrawal)
        await db.commit()
        logger.info(f"✓ Created pending withdrawal transaction")
        
        # Step 3: Try to sync balance - should be skipped
        logger.info("\nStep 2: Attempting balance sync with recent withdrawal...")
        sync_result = await service.sync_blockchain_balance(test_user_id)
        
        if sync_result.get("skipped"):
            logger.info(f"✓ Balance sync correctly skipped: {sync_result.get('reason')}")
        else:
            logger.error(f"✗ Balance sync was NOT skipped! Result: {sync_result}")
            
        # Step 4: Mark withdrawal as confirmed
        logger.info("\nStep 3: Marking withdrawal as confirmed...")
        withdrawal.status = 'confirmed'
        withdrawal.processed_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info("✓ Withdrawal marked as confirmed")
        
        # Step 5: Try sync again - should still be skipped (within 5 min window)
        logger.info("\nStep 4: Attempting balance sync with confirmed but recent withdrawal...")
        sync_result = await service.sync_blockchain_balance(test_user_id)
        
        if sync_result.get("skipped"):
            logger.info(f"✓ Balance sync correctly skipped: {sync_result.get('reason')}")
        else:
            logger.error(f"✗ Balance sync was NOT skipped! Result: {sync_result}")
        
        # Step 6: Update withdrawal timestamp to be older than 5 minutes
        logger.info("\nStep 5: Simulating old withdrawal (> 5 minutes ago)...")
        withdrawal.created_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        await db.commit()
        logger.info("✓ Withdrawal timestamp updated to 10 minutes ago")
        
        # Step 7: Try sync again - should NOT be skipped now
        logger.info("\nStep 6: Attempting balance sync with old withdrawal...")
        sync_result = await service.sync_blockchain_balance(test_user_id)
        
        if not sync_result.get("skipped"):
            logger.info(f"✓ Balance sync was NOT skipped (as expected for old withdrawal)")
            logger.info(f"  Sync result: blockchain_balance={sync_result.get('blockchain_balance')}, "
                       f"db_balance={sync_result.get('db_balance')}")
        else:
            logger.warning(f"⚠ Balance sync was skipped unexpectedly: {sync_result.get('reason')}")
        
        # Step 8: Test with POSITION_CLOSED transaction
        logger.info("\nStep 7: Testing with pending POSITION_CLOSED transaction...")
        position_close = Transaction(
            user_id=test_user_id,
            tx_type='POSITION_CLOSED',
            tx_hash="0xTestPositionCloseTx",
            status='pending',
            event_data={'amount_usdc': 50.0},
            created_at=datetime.now(timezone.utc)
        )
        db.add(position_close)
        await db.commit()
        logger.info("✓ Created pending POSITION_CLOSED transaction")
        
        sync_result = await service.sync_blockchain_balance(test_user_id)
        
        if sync_result.get("skipped"):
            logger.info(f"✓ Balance sync correctly skipped for pending position close: {sync_result.get('reason')}")
        else:
            logger.error(f"✗ Balance sync was NOT skipped for pending position close! Result: {sync_result}")
        
        # Cleanup
        logger.info("\n" + "=" * 60)
        logger.info("Test completed!")
        logger.info("=" * 60)
        
        # Clean up test data
        await db.execute(
            Transaction.__table__.delete().where(
                Transaction.user_id == test_user_id
            )
        )
        await db.execute(
            User.__table__.delete().where(
                User.user_id == test_user_id
            )
        )
        await db.commit()
        logger.info("Test data cleaned up")

if __name__ == "__main__":
    asyncio.run(test_balance_sync_prevention())