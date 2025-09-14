#!/usr/bin/env python3
"""Data analysis utilities for metrics and reporting."""

import asyncio
import argparse
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pathlib import Path
import json

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.utils.config import get_async_database_url
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from app.database.models.user import User
from app.database.models.position import Position
from app.database.models.transaction import Transaction
from app.core.logger import logger


class DataAnalyzer:
    """Utility class for data analysis and reporting."""
    
    def __init__(self):
        """Initialize database connection."""
        self.engine = None
        
    async def connect(self):
        """Connect to database."""
        if not self.engine:
            self.engine = create_async_engine(
                get_async_database_url(),
                echo=False,
                pool_pre_ping=True
            )
            
    async def analyze_user_activity(self, days: int = 30):
        """Analyze user activity over time period.
        
        Args:
            days: Number of days to analyze
        """
        await self.connect()
        
        async with AsyncSession(self.engine) as session:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Get user statistics
            total_users = await session.execute(
                select(func.count(User.user_id))
            )
            
            active_users = await session.execute(
                select(func.count(func.distinct(Transaction.user_id)))
                .where(Transaction.timestamp >= cutoff_date)
            )
            
            # Get transaction statistics
            tx_stats = await session.execute(
                select(
                    Transaction.type,
                    func.count(Transaction.tx_hash).label('count'),
                    func.sum(Transaction.usdc_amount).label('total_amount'),
                    func.avg(Transaction.usdc_amount).label('avg_amount')
                )
                .where(Transaction.timestamp >= cutoff_date)
                .group_by(Transaction.type)
            )
            
            print(f"\n{'='*60}")
            print(f"User Activity Analysis (last {days} days)")
            print(f"{'='*60}")
            print(f"Total users: {total_users.scalar()}")
            print(f"Active users: {active_users.scalar()}")
            
            print(f"\nTransaction Summary:")
            for row in tx_stats:
                print(f"  {row.type}:")
                print(f"    Count: {row.count}")
                print(f"    Total: ${row.total_amount or 0:,.2f}")
                print(f"    Average: ${row.avg_amount or 0:,.2f}")
                
    async def analyze_pool_performance(self, top_n: int = 10):
        """Analyze pool performance metrics.
        
        Args:
            top_n: Number of top pools to show
        """
        await self.connect()
        
        async with AsyncSession(self.engine) as session:
            # Get pool statistics
            pool_stats = await session.execute(
                select(
                    Position.pool_address,
                    func.count(Position.token_id).label('position_count'),
                    func.sum(Position.pnl_usd).label('total_pnl'),
                    func.avg(Position.pnl_usd).label('avg_pnl'),
                    func.sum(Position.liquidity).label('total_liquidity')
                )
                .group_by(Position.pool_address)
                .order_by(func.count(Position.token_id).desc())
                .limit(top_n)
            )
            
            print(f"\n{'='*60}")
            print(f"Top {top_n} Pools by Position Count")
            print(f"{'='*60}")
            
            for i, row in enumerate(pool_stats, 1):
                print(f"\n{i}. Pool: {row.pool_address[:10]}...{row.pool_address[-8:]}")
                print(f"   Positions: {row.position_count}")
                print(f"   Total PnL: ${row.total_pnl or 0:,.2f}")
                print(f"   Avg PnL: ${row.avg_pnl or 0:,.2f}")
                print(f"   Total Liquidity: {row.total_liquidity or 0:,.0f}")
                
    async def analyze_trading_patterns(self, user_id: Optional[str] = None):
        """Analyze trading patterns and strategies.
        
        Args:
            user_id: Optional specific user to analyze
        """
        await self.connect()
        
        async with AsyncSession(self.engine) as session:
            # Base query for positions
            query = select(Position)
            if user_id:
                query = query.where(Position.user_id == user_id)
                
            result = await session.execute(query)
            positions = result.scalars().all()
            
            if not positions:
                print("No positions found")
                return
                
            # Calculate metrics
            total_positions = len(positions)
            active_positions = sum(1 for p in positions if p.is_active)
            profitable_positions = sum(1 for p in positions if p.pnl_usd and p.pnl_usd > 0)
            
            total_pnl = sum(p.pnl_usd or 0 for p in positions)
            avg_pnl = total_pnl / total_positions if total_positions > 0 else 0
            
            # Calculate holding periods
            holding_periods = []
            for p in positions:
                if p.created_at and p.exit_date:
                    period = (p.exit_date - p.created_at).total_seconds() / 3600  # hours
                    holding_periods.append(period)
                    
            avg_holding_period = sum(holding_periods) / len(holding_periods) if holding_periods else 0
            
            print(f"\n{'='*60}")
            print(f"Trading Pattern Analysis")
            if user_id:
                print(f"User: {user_id}")
            print(f"{'='*60}")
            
            print(f"\nPosition Statistics:")
            print(f"  Total positions: {total_positions}")
            print(f"  Active positions: {active_positions}")
            print(f"  Profitable positions: {profitable_positions} ({profitable_positions/total_positions*100:.1f}%)")
            
            print(f"\nPnL Statistics:")
            print(f"  Total PnL: ${total_pnl:,.2f}")
            print(f"  Average PnL: ${avg_pnl:,.2f}")
            
            if holding_periods:
                print(f"\nTiming Statistics:")
                print(f"  Avg holding period: {avg_holding_period:.1f} hours")
                print(f"  Min holding period: {min(holding_periods):.1f} hours")
                print(f"  Max holding period: {max(holding_periods):.1f} hours")
                
    async def generate_summary_report(self, output_file: Optional[str] = None):
        """Generate comprehensive summary report.
        
        Args:
            output_file: Optional file to save report
        """
        await self.connect()
        
        report = {
            'generated_at': datetime.utcnow().isoformat(),
            'metrics': {}
        }
        
        async with AsyncSession(self.engine) as session:
            # User metrics
            user_count = await session.execute(select(func.count(User.user_id)))
            report['metrics']['total_users'] = user_count.scalar()
            
            # Balance metrics
            balance_stats = await session.execute(
                select(
                    func.sum(User.balance).label('total_balance'),
                    func.avg(User.balance).label('avg_balance'),
                    func.max(User.balance).label('max_balance')
                )
            )
            stats = balance_stats.first()
            report['metrics']['total_balance'] = float(stats.total_balance or 0)
            report['metrics']['avg_balance'] = float(stats.avg_balance or 0)
            report['metrics']['max_balance'] = float(stats.max_balance or 0)
            
            # Position metrics
            position_count = await session.execute(select(func.count(Position.token_id)))
            report['metrics']['total_positions'] = position_count.scalar()
            
            active_positions = await session.execute(
                select(func.count(Position.token_id))
                .where(Position.is_active == True)
            )
            report['metrics']['active_positions'] = active_positions.scalar()
            
            # PnL metrics
            pnl_stats = await session.execute(
                select(
                    func.sum(Position.pnl_usd).label('total_pnl'),
                    func.avg(Position.pnl_usd).label('avg_pnl')
                )
            )
            pnl = pnl_stats.first()
            report['metrics']['total_pnl'] = float(pnl.total_pnl or 0)
            report['metrics']['avg_pnl'] = float(pnl.avg_pnl or 0)
            
            # Transaction metrics
            tx_count = await session.execute(select(func.count(Transaction.tx_hash)))
            report['metrics']['total_transactions'] = tx_count.scalar()
            
            # Display report
            print(f"\n{'='*60}")
            print(f"Summary Report")
            print(f"Generated: {report['generated_at']}")
            print(f"{'='*60}")
            
            for key, value in report['metrics'].items():
                formatted_key = key.replace('_', ' ').title()
                if 'balance' in key or 'pnl' in key:
                    print(f"{formatted_key}: ${value:,.2f}")
                else:
                    print(f"{formatted_key}: {value:,}")
                    
            # Save to file if requested
            if output_file:
                with open(output_file, 'w') as f:
                    json.dump(report, f, indent=2, default=str)
                print(f"\nReport saved to: {output_file}")
                
    async def find_anomalies(self):
        """Find data anomalies and inconsistencies."""
        await self.connect()
        
        async with AsyncSession(self.engine) as session:
            print(f"\n{'='*60}")
            print(f"Data Anomaly Detection")
            print(f"{'='*60}")
            
            # Check for users with negative balance
            negative_balance = await session.execute(
                select(func.count(User.user_id))
                .where(User.balance < 0)
            )
            count = negative_balance.scalar()
            if count > 0:
                print(f"⚠️  Users with negative balance: {count}")
                
            # Check for positions without users
            orphan_positions = await session.execute(
                select(func.count(Position.token_id))
                .outerjoin(User, Position.user_id == User.user_id)
                .where(User.user_id == None)
            )
            count = orphan_positions.scalar()
            if count > 0:
                print(f"⚠️  Orphaned positions: {count}")
                
            # Check for impossible PnL values
            extreme_pnl = await session.execute(
                select(func.count(Position.token_id))
                .where(or_(
                    Position.pnl_usd > 1000000,  # > $1M
                    Position.pnl_usd < -100000   # < -$100K
                ))
            )
            count = extreme_pnl.scalar()
            if count > 0:
                print(f"⚠️  Positions with extreme PnL: {count}")
                
            # Check for duplicate transactions
            duplicate_txs = await session.execute(
                select(
                    Transaction.tx_hash,
                    func.count(Transaction.tx_hash).label('count')
                )
                .group_by(Transaction.tx_hash)
                .having(func.count(Transaction.tx_hash) > 1)
            )
            duplicates = duplicate_txs.all()
            if duplicates:
                print(f"⚠️  Duplicate transactions found: {len(duplicates)}")
                
            print("\nAnomaly scan complete")


async def main():
    """Main entry point for data analysis utilities."""
    parser = argparse.ArgumentParser(description='Data analysis utilities')
    parser.add_argument('command', choices=[
        'user-activity',
        'pool-performance',
        'trading-patterns',
        'summary',
        'anomalies'
    ], help='Analysis command to execute')
    
    parser.add_argument('--days', type=int, default=30, help='Number of days to analyze')
    parser.add_argument('--user-id', type=str, help='Specific user ID')
    parser.add_argument('--top-n', type=int, default=10, help='Number of top items to show')
    parser.add_argument('--output', type=str, help='Output file for report')
    
    args = parser.parse_args()
    
    analyzer = DataAnalyzer()
    
    try:
        if args.command == 'user-activity':
            await analyzer.analyze_user_activity(args.days)
        elif args.command == 'pool-performance':
            await analyzer.analyze_pool_performance(args.top_n)
        elif args.command == 'trading-patterns':
            await analyzer.analyze_trading_patterns(args.user_id)
        elif args.command == 'summary':
            await analyzer.generate_summary_report(args.output)
        elif args.command == 'anomalies':
            await analyzer.find_anomalies()
    except Exception as e:
        logger.error(f"Error executing analysis: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())