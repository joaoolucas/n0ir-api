#!/usr/bin/env python3
"""Fix user deposit/withdrawal totals to correct PnL calculation."""

import asyncio
import os
import sys
from decimal import Decimal
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.models import User, Transaction

# Simple logger
class Logger:
    def info(self, msg):
        print(f"[INFO] {msg}")
    def debug(self, msg):
        print(f"[DEBUG] {msg}")
    def error(self, msg):
        print(f"[ERROR] {msg}")

logger = Logger()

# Database connection from environment
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:iGipbjkDUDKforbKRzRUjDnXSIaXviyi@shuttle.proxy.rlwy.net:37929/railway")
# Convert to async URL
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

async def recalculate_user_totals(user_id: str):
    """Recalculate and fix deposit/withdrawal totals for a user."""
    
    # Create async engine
    engine = create_async_engine(DATABASE_URL, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with AsyncSessionLocal() as db:
        try:
            # Get user
            stmt = select(User).where(User.user_id == user_id)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                logger.error(f"User {user_id} not found")
                return
            
            logger.info(f"Found user {user_id}")
            logger.info(f"Current totals - Deposits: {user.total_deposits_usdc}, Withdrawals: {user.total_withdrawals_usdc}")
            
            # Get all confirmed deposit and withdrawal transactions
            stmt = select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.status == 'CONFIRMED',
                Transaction.tx_type.in_(['DEPOSIT', 'WITHDRAWAL', 'WITHDRAW'])
            )
            result = await db.execute(stmt)
            transactions = result.scalars().all()
            
            logger.info(f"Found {len(transactions)} deposit/withdrawal transactions")
            
            # Calculate actual totals
            cdp_wallet = user.cdp_wallet_address.lower() if user.cdp_wallet_address else None
            user_wallet = user_id.lower()
            
            total_deposits = Decimal(0)
            total_withdrawals = Decimal(0)
            
            for tx in transactions:
                if not tx.event_data:
                    continue
                
                # Get amount from event_data
                amount = Decimal(0)
                if 'amount_usdc' in tx.event_data:
                    amount = Decimal(str(tx.event_data['amount_usdc']))
                elif 'usdc_out' in tx.event_data:
                    amount = Decimal(str(tx.event_data['usdc_out'])) / Decimal('1000000')  # Convert from raw units
                elif 'usdc_in' in tx.event_data:
                    amount = Decimal(str(tx.event_data['usdc_in'])) / Decimal('1000000')  # Convert from raw units
                
                from_addr = tx.event_data.get('from_address', '').lower()
                to_addr = tx.event_data.get('to_address', '').lower()
                
                if tx.tx_type == 'DEPOSIT':
                    # Count if from user wallet to CDP wallet
                    if from_addr == user_wallet and to_addr == cdp_wallet:
                        total_deposits += amount
                        logger.debug(f"Deposit: {amount} USDC from {from_addr[:8]}... to {to_addr[:8]}...")
                elif tx.tx_type in ['WITHDRAWAL', 'WITHDRAW']:
                    # Count if from CDP wallet to user wallet
                    if from_addr == cdp_wallet and to_addr == user_wallet:
                        total_withdrawals += amount
                        logger.debug(f"Withdrawal: {amount} USDC from {from_addr[:8]}... to {to_addr[:8]}...")
            
            logger.info(f"Calculated totals - Deposits: {total_deposits}, Withdrawals: {total_withdrawals}")
            
            # Update user totals
            user.total_deposits_usdc = total_deposits
            user.total_withdrawals_usdc = total_withdrawals
            
            await db.commit()
            logger.info(f"Updated user {user_id} totals successfully")
            
            # Now recalculate PnL
            from app.services.user_service import UserService
            service = UserService(db)
            await service.recalculate_user_pnl(user_id)
            
            # Refresh user to get updated PnL values
            await db.refresh(user)
            
            logger.info(f"Updated PnL values:")
            logger.info(f"  Realized PnL: {user.realized_pnl_usd} ({user.realized_pnl_pct}%)")
            logger.info(f"  Unrealized PnL: {user.unrealized_pnl_usd} ({user.unrealized_pnl_pct}%)")
            
        except Exception as e:
            logger.error(f"Error updating user totals: {e}")
            await db.rollback()
            raise
        finally:
            await engine.dispose()


async def main():
    """Main function to fix specific user's totals."""
    user_id = "0xC2952cc28EDf37B053188D89e6ac888B9855d132"
    
    logger.info(f"Fixing deposit/withdrawal totals for user {user_id}")
    await recalculate_user_totals(user_id)
    logger.info("Done!")


if __name__ == "__main__":
    asyncio.run(main())