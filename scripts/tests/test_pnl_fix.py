#!/usr/bin/env python3
"""Test the PnL calculation fix."""

import asyncio
from decimal import Decimal
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.services.user_service import UserService

DATABASE_URL = 'postgresql+asyncpg://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway'

async def test_pnl_fix():
    engine = create_async_engine(DATABASE_URL)
    async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session_factory() as session:
        user_service = UserService(session)
        user_id = '0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51'
        
        print("Testing PnL calculation fix...")
        print(f"User: {user_id}")
        
        # Get current user data
        user = await user_service.get_user(user_id)
        if not user:
            print("User not found!")
            return
        
        print(f"\nBefore PnL recalculation:")
        print(f"  Total deposits: {user.total_deposits_usdc} USDC")
        print(f"  Total withdrawals: {user.total_withdrawals_usdc} USDC")
        print(f"  Balance: {user.usdc_balance} USDC")
        print(f"  Realized PnL: {user.realized_pnl_usd} USDC")
        print(f"  Unrealized PnL: {user.unrealized_pnl_usd} USDC")
        
        # Recalculate PnL using the fixed logic
        await user_service.recalculate_user_pnl(user_id)
        
        # Get updated user data
        updated_user = await user_service.get_user(user_id)
        
        print(f"\nAfter PnL recalculation:")
        print(f"  Realized PnL: {updated_user.realized_pnl_usd} USDC")
        print(f"  Unrealized PnL: {updated_user.unrealized_pnl_usd} USDC")
        print(f"  Realized PnL %: {updated_user.realized_pnl_pct}%")
        print(f"  Unrealized PnL %: {updated_user.unrealized_pnl_pct}%")
        
        # Calculate expected values for verification
        net_expected = updated_user.total_withdrawals_usdc - updated_user.total_deposits_usdc
        print(f"\nExpected realized PnL (withdrawals - deposits): {net_expected} USDC")
        print(f"Actual realized PnL: {updated_user.realized_pnl_usd} USDC")
        
        # Check if values make sense
        if abs(updated_user.realized_pnl_usd) < 1.0:  # Should be close to 0 for this user
            print("✅ Realized PnL looks correct!")
        else:
            print("❌ Realized PnL still looks wrong")
        
        if updated_user.unrealized_pnl_usd == 0:  # User has no active positions
            print("✅ Unrealized PnL is correct (no active positions)")
        else:
            print("❓ User might have active positions")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(test_pnl_fix())
