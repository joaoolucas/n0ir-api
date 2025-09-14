#!/usr/bin/env python3
"""Database utilities for analysis, maintenance, and debugging."""

import asyncio
import argparse
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.utils.config import get_async_database_url, get_database_url
from sqlalchemy import create_engine, text, select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from app.database.models.user import User
from app.database.models.position import Position
from app.database.models.transaction import Transaction
from app.core.logger import logger


class DatabaseUtils:
    """Utility class for database operations."""
    
    def __init__(self):
        """Initialize database connections."""
        self.async_engine = None
        self.sync_engine = None
        
    async def connect_async(self):
        """Connect to async database."""
        if not self.async_engine:
            self.async_engine = create_async_engine(
                get_async_database_url(),
                echo=False,
                pool_pre_ping=True
            )
            
    def connect_sync(self):
        """Connect to synchronous database."""
        if not self.sync_engine:
            self.sync_engine = create_engine(
                get_database_url(),
                echo=False,
                pool_pre_ping=True
            )
            
    async def check_balances(self, user_id: Optional[str] = None):
        """Check user balances and transactions.
        
        Args:
            user_id: Optional specific user ID to check
        """
        await self.connect_async()
        
        async with AsyncSession(self.async_engine) as session:
            # Get users to check
            query = select(User)
            if user_id:
                query = query.where(User.user_id == user_id)
            
            result = await session.execute(query)
            users = result.scalars().all()
            
            for user in users:
                print(f"\n{'='*60}")
                print(f"User: {user.user_id}")
                print(f"  Balance: {user.balance} USDC")
                print(f"  Has deposited 50+: {user.has_deposited_50_usdc}")
                print(f"  Total deposits: {user.total_deposited}")
                print(f"  Total withdrawals: {user.total_withdrawn}")
                print(f"  Trading PnL: {user.trading_pnl}")
                print(f"  AERO earned: {user.aero_earned}")
                
                # Get recent transactions
                tx_query = select(Transaction).where(
                    Transaction.user_id == user.user_id
                ).order_by(Transaction.timestamp.desc()).limit(5)
                
                tx_result = await session.execute(tx_query)
                transactions = tx_result.scalars().all()
                
                if transactions:
                    print(f"\n  Recent transactions:")
                    for tx in transactions:
                        print(f"    - {tx.type}: {tx.usdc_amount} USDC at {tx.timestamp}")
                        
    async def check_positions(self, user_id: Optional[str] = None, active_only: bool = False):
        """Check user positions.
        
        Args:
            user_id: Optional specific user ID to check
            active_only: Only show active positions
        """
        await self.connect_async()
        
        async with AsyncSession(self.async_engine) as session:
            query = select(Position)
            
            if user_id:
                query = query.where(Position.user_id == user_id)
            
            if active_only:
                query = query.where(Position.is_active == True)
                
            query = query.order_by(Position.created_at.desc())
            
            result = await session.execute(query)
            positions = result.scalars().all()
            
            print(f"\nFound {len(positions)} positions")
            
            for pos in positions[:10]:  # Show first 10
                print(f"\n{'='*60}")
                print(f"Position #{pos.token_id}")
                print(f"  User: {pos.user_id}")
                print(f"  Pool: {pos.pool_address}")
                print(f"  Active: {pos.is_active}")
                print(f"  Liquidity: {pos.liquidity}")
                print(f"  Range: [{pos.tick_lower}, {pos.tick_upper}]")
                print(f"  PnL: {pos.pnl_usd} USD")
                print(f"  Created: {pos.created_at}")
                
    async def fix_missing_fields(self):
        """Fix any missing or null fields in database."""
        await self.connect_async()
        
        async with AsyncSession(self.async_engine) as session:
            # Fix users with null balance
            users_updated = await session.execute(
                update(User)
                .where(User.balance == None)
                .values(balance=Decimal('0'))
            )
            
            # Fix positions with missing fields
            positions_updated = await session.execute(
                update(Position)
                .where(Position.pnl_usd == None)
                .values(pnl_usd=Decimal('0'))
            )
            
            await session.commit()
            
            print(f"Fixed {users_updated.rowcount} users with null balance")
            print(f"Fixed {positions_updated.rowcount} positions with null PnL")
            
    async def analyze_pnl(self, days: int = 7):
        """Analyze PnL over a time period.
        
        Args:
            days: Number of days to analyze
        """
        await self.connect_async()
        
        async with AsyncSession(self.async_engine) as session:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Get PnL summary
            result = await session.execute(
                select(
                    func.count(Position.token_id).label('total_positions'),
                    func.sum(Position.pnl_usd).label('total_pnl'),
                    func.avg(Position.pnl_usd).label('avg_pnl'),
                    func.min(Position.pnl_usd).label('min_pnl'),
                    func.max(Position.pnl_usd).label('max_pnl')
                ).where(Position.created_at >= cutoff_date)
            )
            
            stats = result.first()
            
            print(f"\nPnL Analysis (last {days} days)")
            print(f"{'='*40}")
            print(f"Total positions: {stats.total_positions or 0}")
            print(f"Total PnL: ${stats.total_pnl or 0:.2f}")
            print(f"Average PnL: ${stats.avg_pnl or 0:.2f}")
            print(f"Min PnL: ${stats.min_pnl or 0:.2f}")
            print(f"Max PnL: ${stats.max_pnl or 0:.2f}")
            
    async def cleanup_orphaned_records(self, dry_run: bool = True):
        """Clean up orphaned records in database.
        
        Args:
            dry_run: If True, only show what would be deleted
        """
        await self.connect_async()
        
        async with AsyncSession(self.async_engine) as session:
            # Find transactions without users
            orphaned_txs = await session.execute(
                select(func.count(Transaction.tx_hash))
                .outerjoin(User, Transaction.user_id == User.user_id)
                .where(User.user_id == None)
            )
            
            orphan_count = orphaned_txs.scalar()
            
            if orphan_count > 0:
                print(f"\nFound {orphan_count} orphaned transactions")
                
                if not dry_run:
                    # Delete orphaned transactions
                    await session.execute(
                        delete(Transaction)
                        .where(
                            ~Transaction.user_id.in_(
                                select(User.user_id)
                            )
                        )
                    )
                    await session.commit()
                    print(f"Deleted {orphan_count} orphaned transactions")
                else:
                    print("Run with --execute to delete orphaned records")
                    
    async def recalculate_user_totals(self, user_id: Optional[str] = None):
        """Recalculate user balance totals from transactions.
        
        Args:
            user_id: Optional specific user ID to recalculate
        """
        await self.connect_async()
        
        async with AsyncSession(self.async_engine) as session:
            query = select(User)
            if user_id:
                query = query.where(User.user_id == user_id)
                
            result = await session.execute(query)
            users = result.scalars().all()
            
            for user in users:
                # Calculate totals from transactions
                deposits_result = await session.execute(
                    select(func.sum(Transaction.usdc_amount))
                    .where(
                        Transaction.user_id == user.user_id,
                        Transaction.type == 'DEPOSIT'
                    )
                )
                total_deposits = deposits_result.scalar() or Decimal('0')
                
                withdrawals_result = await session.execute(
                    select(func.sum(Transaction.usdc_amount))
                    .where(
                        Transaction.user_id == user.user_id,
                        Transaction.type == 'WITHDRAWAL'
                    )
                )
                total_withdrawals = withdrawals_result.scalar() or Decimal('0')
                
                # Update user
                new_balance = total_deposits - total_withdrawals
                
                await session.execute(
                    update(User)
                    .where(User.user_id == user.user_id)
                    .values(
                        balance=new_balance,
                        total_deposited=total_deposits,
                        total_withdrawn=total_withdrawals
                    )
                )
                
                await session.commit()
                
                print(f"Updated {user.user_id}:")
                print(f"  New balance: {new_balance}")
                print(f"  Total deposits: {total_deposits}")
                print(f"  Total withdrawals: {total_withdrawals}")


async def main():
    """Main entry point for database utilities."""
    parser = argparse.ArgumentParser(description='Database utilities')
    parser.add_argument('command', choices=[
        'check-balances',
        'check-positions',
        'fix-fields',
        'analyze-pnl',
        'cleanup',
        'recalculate'
    ], help='Command to execute')
    
    parser.add_argument('--user-id', type=str, help='Specific user ID')
    parser.add_argument('--active-only', action='store_true', help='Only show active positions')
    parser.add_argument('--days', type=int, default=7, help='Number of days for analysis')
    parser.add_argument('--execute', action='store_true', help='Execute changes (not dry run)')
    
    args = parser.parse_args()
    
    utils = DatabaseUtils()
    
    try:
        if args.command == 'check-balances':
            await utils.check_balances(args.user_id)
        elif args.command == 'check-positions':
            await utils.check_positions(args.user_id, args.active_only)
        elif args.command == 'fix-fields':
            await utils.fix_missing_fields()
        elif args.command == 'analyze-pnl':
            await utils.analyze_pnl(args.days)
        elif args.command == 'cleanup':
            await utils.cleanup_orphaned_records(not args.execute)
        elif args.command == 'recalculate':
            await utils.recalculate_user_totals(args.user_id)
    except Exception as e:
        logger.error(f"Error executing command: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())