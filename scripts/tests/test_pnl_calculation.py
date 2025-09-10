#!/usr/bin/env python3
"""Test the fixed PNL calculation logic"""

import asyncio
import os
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.database.models.user import User
from app.database.models.transaction import Transaction
from app.services.user_service import UserService
from decimal import Decimal

async def test_pnl_calculation():
    """Test the PNL calculation for a specific user"""
    
    # Test user ID
    test_user = "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51"
    
    # Get database URL
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        db_url = "postgresql+asyncpg://n0ir_user:n0ir_pass@localhost/n0ir_db"
    
    # Convert to asyncpg URL if needed
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    print(f"Testing PNL calculation for user: {test_user}")
    print("=" * 60)
    
    # Create engine and session
    engine = create_async_engine(db_url)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Create UserService instance
        service = UserService(session)
        
        # Get user's current state BEFORE recalculation
        user = await service.get_user(test_user)
        if not user:
            print(f"User {test_user} not found!")
            return
        
        print("\n📊 BEFORE Recalculation:")
        print(f"  Realized PNL: ${user.realized_pnl_usd}")
        print(f"  Unrealized PNL: ${user.unrealized_pnl_usd}")
        
        # Get transaction details
        stmt = text('''
            SELECT 
                SUM(CASE WHEN tx_type = 'DEPOSIT' AND status = 'CONFIRMED' 
                    THEN (event_data->>'amount_usdc')::numeric ELSE 0 END) as total_deposits,
                SUM(CASE WHEN tx_type = 'WITHDRAWAL' AND status = 'CONFIRMED' 
                    THEN (event_data->>'amount_usdc')::numeric ELSE 0 END) as total_withdrawals
            FROM transactions 
            WHERE user_id = :user_id
        ''')
        
        result = await session.execute(stmt, {'user_id': test_user})
        sums = result.fetchone()
        
        total_deposits = sums.total_deposits or Decimal(0)
        total_withdrawals = sums.total_withdrawals or Decimal(0)
        net_cash_flow = total_withdrawals - total_deposits
        
        print(f"\n💰 Transaction Summary:")
        print(f"  Total Deposits: ${total_deposits}")
        print(f"  Total Withdrawals: ${total_withdrawals}")
        print(f"  Net Cash Flow (W-D): ${net_cash_flow}")
        
        # Get positions summary
        positions = await service.get_user_positions(test_user)
        closed_positions = [p for p in positions if p.status == 'closed']
        active_positions = [p for p in positions if p.status == 'active']
        
        closed_pnl = sum(p.realized_pnl_usdc or Decimal(0) for p in closed_positions)
        
        print(f"\n📈 Positions Summary:")
        print(f"  Active Positions: {len(active_positions)}")
        print(f"  Closed Positions: {len(closed_positions)}")
        print(f"  Closed Positions PNL: ${closed_pnl}")
        
        # Expected calculation
        expected_realized_pnl = net_cash_flow + closed_pnl
        print(f"\n🎯 Expected Realized PNL Calculation:")
        print(f"  Net Cash Flow (W-D): ${net_cash_flow}")
        print(f"  + Closed Positions PNL: ${closed_pnl}")
        print(f"  = Expected Realized PNL: ${expected_realized_pnl}")
        
        # Now recalculate PNL with the fixed logic
        print("\n🔄 Recalculating PNL with fixed logic...")
        await service.recalculate_user_pnl(test_user)
        
        # Commit changes
        await session.commit()
        
        # Refresh user to get updated values
        await session.refresh(user)
        
        print("\n📊 AFTER Recalculation:")
        print(f"  Realized PNL: ${user.realized_pnl_usd}")
        print(f"  Unrealized PNL: ${user.unrealized_pnl_usd}")
        
        # Verify the calculation
        print("\n✅ Verification:")
        if abs(user.realized_pnl_usd - expected_realized_pnl) < Decimal(0.01):
            print(f"  ✓ Realized PNL correctly calculated as (withdrawals - deposits) + closed_positions_pnl")
            print(f"  ✓ Value: ${user.realized_pnl_usd} matches expected ${expected_realized_pnl}")
        else:
            print(f"  ✗ Realized PNL mismatch!")
            print(f"    Expected: ${expected_realized_pnl}")
            print(f"    Got: ${user.realized_pnl_usd}")
            print(f"    Difference: ${abs(user.realized_pnl_usd - expected_realized_pnl)}")
    
    await engine.dispose()
    print("\n" + "=" * 60)
    print("Test completed!")

if __name__ == "__main__":
    asyncio.run(test_pnl_calculation())