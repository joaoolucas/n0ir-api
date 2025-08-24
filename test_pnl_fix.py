#!/usr/bin/env python3
"""Test script to verify PNL calculation fixes."""

import asyncio
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.services.user_service import UserService
from app.database.models.position import Position, PositionStatus
from app.database.models.user import User
from app.database.models.transaction import Transaction, TransactionType, TransactionStatus
from app.core.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create async engine
engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def test_scenario_1():
    """Test: User with no deposits opens and closes position at same value."""
    logger.info("=" * 60)
    logger.info("Test Scenario 1: No deposits, position closed at entry value")
    logger.info("=" * 60)
    
    async with AsyncSessionLocal() as db:
        service = UserService(db)
        test_user_id = "0xtest_user_no_deposits"
        
        # Create test user
        user = User(user_id=test_user_id, balance_usdc=Decimal("10"))
        db.add(user)
        await db.commit()
        
        # Simulate position open (user has 10 USDC from external source)
        position = Position(
            nft_token_id=99991,
            user_id=test_user_id,
            pool_address="0xtest_pool",
            pool_name="TEST/USDC",
            token0_address="0xtoken0",
            token1_address="0xtoken1",
            tick_lower=-1000,
            tick_upper=1000,
            tick_spacing=10,
            liquidity="1000000",
            entry_amount_usdc=Decimal("10"),
            current_value_usdc=Decimal("10"),
            status=PositionStatus.ACTIVE
        )
        db.add(position)
        
        # Create POSITION_ENTRY transaction
        entry_tx = Transaction(
            user_id=test_user_id,
            transaction_type=TransactionType.POSITION_ENTRY,
            amount_usdc=Decimal("10"),
            status=TransactionStatus.CONFIRMED
        )
        db.add(entry_tx)
        await db.commit()
        
        # Close position at same value
        await service.close_position(
            user_id=test_user_id,
            nft_token_id=99991,
            final_value_usdc=Decimal("10")
        )
        
        # Recalculate PNL
        await service.recalculate_user_pnl(test_user_id)
        
        # Check results
        user = await service.get_user(test_user_id)
        logger.info(f"Expected PNL: 0 (no gain or loss)")
        logger.info(f"Actual Unrealized PNL: {user.unrealized_pnl_usdc}")
        logger.info(f"Actual Realized PNL: {user.realized_pnl_usdc}")
        
        assert user.unrealized_pnl_usdc == Decimal("0"), f"Unrealized PNL should be 0, got {user.unrealized_pnl_usdc}"
        assert user.realized_pnl_usdc == Decimal("0"), f"Realized PNL should be 0, got {user.realized_pnl_usdc}"
        logger.info("✅ Test passed!")
        
        # Cleanup
        await db.delete(user)
        await db.commit()


async def test_scenario_2():
    """Test: User deposits, opens profitable position, closes and withdraws."""
    logger.info("=" * 60)
    logger.info("Test Scenario 2: Profitable position")
    logger.info("=" * 60)
    
    async with AsyncSessionLocal() as db:
        service = UserService(db)
        test_user_id = "0xtest_user_profit"
        
        # Create test user
        user = User(user_id=test_user_id, balance_usdc=Decimal("0"))
        db.add(user)
        await db.commit()
        
        # Deposit
        deposit_tx = Transaction(
            user_id=test_user_id,
            transaction_type=TransactionType.DEPOSIT,
            amount_usdc=Decimal("100"),
            status=TransactionStatus.CONFIRMED
        )
        db.add(deposit_tx)
        await db.commit()
        
        # Open position
        position = Position(
            nft_token_id=99992,
            user_id=test_user_id,
            pool_address="0xtest_pool2",
            pool_name="TEST/USDC",
            token0_address="0xtoken0",
            token1_address="0xtoken1",
            tick_lower=-1000,
            tick_upper=1000,
            tick_spacing=10,
            liquidity="1000000",
            entry_amount_usdc=Decimal("100"),
            current_value_usdc=Decimal("100"),
            status=PositionStatus.ACTIVE
        )
        db.add(position)
        
        entry_tx = Transaction(
            user_id=test_user_id,
            transaction_type=TransactionType.POSITION_ENTRY,
            amount_usdc=Decimal("100"),
            status=TransactionStatus.CONFIRMED
        )
        db.add(entry_tx)
        await db.commit()
        
        # Close position with profit
        await service.close_position(
            user_id=test_user_id,
            nft_token_id=99992,
            final_value_usdc=Decimal("150")
        )
        
        # Check PNL after closing
        await service.recalculate_user_pnl(test_user_id)
        user = await service.get_user(test_user_id)
        
        logger.info(f"After position close:")
        logger.info(f"  Expected: Unrealized=0, Realized=50")
        logger.info(f"  Actual: Unrealized={user.unrealized_pnl_usdc}, Realized={user.realized_pnl_usdc}")
        
        assert user.unrealized_pnl_usdc == Decimal("0"), f"Unrealized PNL should be 0, got {user.unrealized_pnl_usdc}"
        assert user.realized_pnl_usdc == Decimal("50"), f"Realized PNL should be 50, got {user.realized_pnl_usdc}"
        
        # Withdraw all
        await service.withdraw_usdc(
            user_id=test_user_id,
            amount=Decimal("150"),
            tx_hash="0xtest_withdraw"
        )
        
        # Check PNL after withdrawal
        await service.recalculate_user_pnl(test_user_id)
        user = await service.get_user(test_user_id)
        
        logger.info(f"After withdrawal:")
        logger.info(f"  Expected: Unrealized=0, Realized=50 (unchanged)")
        logger.info(f"  Actual: Unrealized={user.unrealized_pnl_usdc}, Realized={user.realized_pnl_usdc}")
        
        assert user.unrealized_pnl_usdc == Decimal("0"), f"Unrealized PNL should be 0, got {user.unrealized_pnl_usdc}"
        assert user.realized_pnl_usdc == Decimal("50"), f"Realized PNL should be 50, got {user.realized_pnl_usdc}"
        logger.info("✅ Test passed!")
        
        # Cleanup
        await db.delete(user)
        await db.commit()


async def test_scenario_3():
    """Test: User deposits, opens losing position, closes and withdraws."""
    logger.info("=" * 60)
    logger.info("Test Scenario 3: Loss position")
    logger.info("=" * 60)
    
    async with AsyncSessionLocal() as db:
        service = UserService(db)
        test_user_id = "0xtest_user_loss"
        
        # Create test user
        user = User(user_id=test_user_id, balance_usdc=Decimal("0"))
        db.add(user)
        await db.commit()
        
        # Deposit
        deposit_tx = Transaction(
            user_id=test_user_id,
            transaction_type=TransactionType.DEPOSIT,
            amount_usdc=Decimal("100"),
            status=TransactionStatus.CONFIRMED
        )
        db.add(deposit_tx)
        await db.commit()
        
        # Open position
        position = Position(
            nft_token_id=99993,
            user_id=test_user_id,
            pool_address="0xtest_pool3",
            pool_name="TEST/USDC",
            token0_address="0xtoken0",
            token1_address="0xtoken1",
            tick_lower=-1000,
            tick_upper=1000,
            tick_spacing=10,
            liquidity="1000000",
            entry_amount_usdc=Decimal("100"),
            current_value_usdc=Decimal("100"),
            status=PositionStatus.ACTIVE
        )
        db.add(position)
        
        entry_tx = Transaction(
            user_id=test_user_id,
            transaction_type=TransactionType.POSITION_ENTRY,
            amount_usdc=Decimal("100"),
            status=TransactionStatus.CONFIRMED
        )
        db.add(entry_tx)
        await db.commit()
        
        # Close position with loss
        await service.close_position(
            user_id=test_user_id,
            nft_token_id=99993,
            final_value_usdc=Decimal("50")
        )
        
        # Check PNL after closing
        await service.recalculate_user_pnl(test_user_id)
        user = await service.get_user(test_user_id)
        
        logger.info(f"After position close:")
        logger.info(f"  Expected: Unrealized=0, Realized=-50")
        logger.info(f"  Actual: Unrealized={user.unrealized_pnl_usdc}, Realized={user.realized_pnl_usdc}")
        
        assert user.unrealized_pnl_usdc == Decimal("0"), f"Unrealized PNL should be 0, got {user.unrealized_pnl_usdc}"
        assert user.realized_pnl_usdc == Decimal("-50"), f"Realized PNL should be -50, got {user.realized_pnl_usdc}"
        
        # Withdraw all
        await service.withdraw_usdc(
            user_id=test_user_id,
            amount=Decimal("50"),
            tx_hash="0xtest_withdraw2"
        )
        
        # Check PNL after withdrawal
        await service.recalculate_user_pnl(test_user_id)
        user = await service.get_user(test_user_id)
        
        logger.info(f"After withdrawal:")
        logger.info(f"  Expected: Unrealized=0, Realized=-50 (unchanged)")
        logger.info(f"  Actual: Unrealized={user.unrealized_pnl_usdc}, Realized={user.realized_pnl_usdc}")
        
        assert user.unrealized_pnl_usdc == Decimal("0"), f"Unrealized PNL should be 0, got {user.unrealized_pnl_usdc}"
        assert user.realized_pnl_usdc == Decimal("-50"), f"Realized PNL should be -50, got {user.realized_pnl_usdc}"
        logger.info("✅ Test passed!")
        
        # Cleanup
        await db.delete(user)
        await db.commit()


async def main():
    """Run all test scenarios."""
    try:
        await test_scenario_1()
        await test_scenario_2()
        await test_scenario_3()
        
        logger.info("=" * 60)
        logger.info("🎉 All tests passed successfully!")
        logger.info("=" * 60)
        
    except AssertionError as e:
        logger.error(f"❌ Test failed: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())