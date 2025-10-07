"""Optimized user service with simplified responses and better performance."""

from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from loguru import logger

from app.database.models import User, Position, Transaction
from app.schemas.simplified import (
    SimplifiedUserResponse,
    SimplifiedPositionResponse,
    SimplifiedTransactionResponse,
    SimplifiedBalanceResponse,
    SimplifiedPnLResponse,
    SimplifiedTransactionListResponse,
    SimplifiedPositionListResponse,
    TransactionType,
    PositionStatus
)
from app.core.cache import cache_service  # Assuming cache service exists


class OptimizedUserService:
    """Optimized service for user operations with better performance."""
    
    def __init__(self):
        self.pool_name_cache: Dict[str, str] = {}
        
    async def get_user_summary(
        self, 
        user_id: str, 
        db: AsyncSession
    ) -> SimplifiedUserResponse:
        """Get optimized user summary with essential information only."""
        
        # Use a single query with aggregations
        stmt = select(
            User,
            func.count(Position.token_id).filter(Position.status == 'ACTIVE').label('active_positions'),
            func.count(Position.token_id).label('total_positions'),
            func.coalesce(func.sum(Position.current_value_usdc).filter(Position.status == 'ACTIVE'), 0).label('positions_value')
        ).outerjoin(
            Position, User.user_id == Position.user_id
        ).where(
            User.user_id == user_id
        ).group_by(User.user_id)
        
        result = await db.execute(stmt)
        row = result.first()
        
        if not row:
            raise ValueError(f"User {user_id} not found")
            
        user = row[0]
        active_positions = row[1] or 0
        total_positions = row[2] or 0
        positions_value = Decimal(str(row[3] or 0))
        
        # Calculate portfolio value
        portfolio_value = (user.usdc_balance or Decimal(0)) + positions_value
        
        # Calculate total P&L
        total_pnl = (user.unrealized_pnl_usd or Decimal(0)) + (user.realized_pnl_usd or Decimal(0))
        
        # Calculate P&L percentage
        total_invested = user.total_deposits_usdc or Decimal(0)
        pnl_percentage = (total_pnl / total_invested * 100) if total_invested > 0 else Decimal(0)
        
        return SimplifiedUserResponse(
            user_id=user.user_id,
            cdp_wallet_address=user.cdp_wallet_address,
            balance_usdc=user.usdc_balance or Decimal(0),
            active_positions=active_positions,
            total_positions=total_positions,
            portfolio_value_usdc=portfolio_value,
            total_pnl_usdc=total_pnl,
            total_pnl_percentage=pnl_percentage,
            created_at=user.created_at
        )
    
    async def get_user_positions(
        self,
        user_id: str,
        db: AsyncSession,
        status: Optional[PositionStatus] = None,
        limit: int = 100,
        offset: int = 0
    ) -> SimplifiedPositionListResponse:
        """Get user positions with optimized response."""
        
        # Build query
        query = select(Position).where(Position.user_id == user_id)
        
        if status:
            query = query.where(Position.status == status.value)
            
        # Get total count
        count_stmt = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_stmt)
        total = total_result.scalar() or 0
        
        # Get positions with limit/offset
        query = query.order_by(Position.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(query)
        positions = result.scalars().all()
        
        # Convert to simplified responses
        simplified_positions = []
        total_value = Decimal(0)
        total_return = Decimal(0)
        
        for position in positions:
            # Get pool name from cache or generate
            pool_name = await self._get_pool_name(position, db)
            
            # Calculate total return
            total_return_usdc = (
                (position.realized_pnl_usdc or Decimal(0)) +
                (position.fees_earned_usdc or Decimal(0)) +
                (position.rewards_earned_usdc or Decimal(0))
            )
            
            # Calculate return percentage
            entry_amount = position.entry_amount_usdc or Decimal(1)  # Avoid division by zero
            return_percentage = (total_return_usdc / entry_amount * 100) if entry_amount > 0 else Decimal(0)
            
            simplified_positions.append(SimplifiedPositionResponse(
                token_id=position.token_id,
                user_id=position.user_id,
                pool_address=position.pool_address,
                pool_name=pool_name,
                entry_amount_usdc=position.entry_amount_usdc or Decimal(0),
                current_value_usdc=position.current_value_usdc or Decimal(0),
                total_return_usdc=total_return_usdc,
                return_percentage=return_percentage,
                fees_earned_usdc=position.fees_earned_usdc or Decimal(0),
                rewards_earned_usdc=position.rewards_earned_usdc or Decimal(0),
                status=PositionStatus(position.status),
                entry_date=position.entry_date or position.created_at,
                exit_date=position.exit_date
            ))
            
            # Update totals
            if position.status == 'ACTIVE':
                total_value += position.current_value_usdc or Decimal(0)
            total_return += total_return_usdc
        
        # Calculate average return
        avg_return = (total_return / len(simplified_positions) * 100) if simplified_positions else Decimal(0)
        
        return SimplifiedPositionListResponse(
            positions=simplified_positions,
            total=total,
            total_value_usdc=total_value,
            total_return_usdc=total_return,
            average_return_percentage=avg_return
        )
    
    async def get_user_transactions(
        self,
        user_id: str,
        db: AsyncSession,
        tx_type: Optional[TransactionType] = None,
        page: int = 1,
        page_size: int = 50
    ) -> SimplifiedTransactionListResponse:
        """Get user transactions with pagination."""
        
        # Build base query
        query = select(Transaction).where(Transaction.user_id == user_id)
        
        if tx_type:
            query = query.where(Transaction.tx_type == tx_type.value)
            
        # Get total count
        count_stmt = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_stmt)
        total = total_result.scalar() or 0
        
        # Calculate pagination
        offset = (page - 1) * page_size
        has_next = (page * page_size) < total
        
        # Get transactions with pagination
        query = query.order_by(Transaction.created_at.desc()).limit(page_size).offset(offset)
        result = await db.execute(query)
        transactions = result.scalars().all()
        
        # Convert to simplified responses
        simplified_transactions = []
        for tx in transactions:
            # Map database tx_type to enum (handle legacy types)
            tx_type_map = {
                'DEPOSIT': TransactionType.DEPOSIT,
                'WITHDRAW': TransactionType.WITHDRAW,
                'WITHDRAWAL': TransactionType.WITHDRAW,  # Handle legacy
                'POSITION_CREATED': TransactionType.POSITION_CREATED,
                'POSITION_OPENED': TransactionType.POSITION_CREATED,  # Handle legacy
                'POSITION_CLOSED': TransactionType.POSITION_CLOSED,
                'POSITION_EXIT': TransactionType.POSITION_CLOSED,  # Handle legacy
            }
            
            # Get the correct transaction type
            mapped_type = tx_type_map.get(tx.tx_type, TransactionType.DEPOSIT)
            
            # Extract amount from event_data if needed
            amount = Decimal(0)
            if tx.event_data:
                amount = Decimal(str(
                    tx.event_data.get('amount_usdc', 0) or
                    tx.event_data.get('usdc_in', 0) or
                    tx.event_data.get('usdc_out', 0) or
                    tx.event_data.get('total_return_usdc', 0) or
                    0
                ))
            
            simplified_transactions.append(SimplifiedTransactionResponse(
                id=tx.id,
                user_id=tx.user_id,
                type=mapped_type,
                amount_usdc=amount,
                tx_hash=tx.tx_hash,
                position_id=tx.position_id,
                created_at=tx.created_at,
                confirmed_at=tx.confirmed_at
            ))
        
        return SimplifiedTransactionListResponse(
            transactions=simplified_transactions,
            total=total,
            page=page,
            page_size=page_size,
            has_next=has_next
        )
    
    async def get_user_balance(
        self,
        user_id: str,
        db: AsyncSession
    ) -> SimplifiedBalanceResponse:
        """Get simplified user balance information."""
        
        # Get user and position values in one query
        stmt = select(
            User.usdc_balance,
            func.coalesce(func.sum(Position.current_value_usdc).filter(Position.status == 'ACTIVE'), 0)
        ).outerjoin(
            Position, and_(User.user_id == Position.user_id, Position.status == 'ACTIVE')
        ).where(
            User.user_id == user_id
        ).group_by(User.user_id)
        
        result = await db.execute(stmt)
        row = result.first()
        
        if not row:
            raise ValueError(f"User {user_id} not found")
            
        wallet_balance = Decimal(str(row[0] or 0))
        positions_value = Decimal(str(row[1] or 0))
        
        return SimplifiedBalanceResponse(
            user_id=user_id,
            wallet_balance_usdc=wallet_balance,
            positions_value_usdc=positions_value,
            total_value_usdc=wallet_balance + positions_value
        )
    
    async def get_user_pnl(
        self,
        user_id: str,
        db: AsyncSession
    ) -> SimplifiedPnLResponse:
        """Get simplified P&L information."""
        
        # Get user P&L and position counts in one query
        stmt = select(
            User.unrealized_pnl_usd,
            User.realized_pnl_usd,
            User.total_deposits_usdc,
            func.count(Position.token_id).filter(Position.status == 'ACTIVE').label('active_positions'),
            func.count(Position.token_id).filter(Position.status == 'CLOSED').label('closed_positions')
        ).outerjoin(
            Position, User.user_id == Position.user_id
        ).where(
            User.user_id == user_id
        ).group_by(User.user_id)
        
        result = await db.execute(stmt)
        row = result.first()
        
        if not row:
            raise ValueError(f"User {user_id} not found")
            
        unrealized_pnl = Decimal(str(row[0] or 0))
        realized_pnl = Decimal(str(row[1] or 0))
        total_deposits = Decimal(str(row[2] or 0))
        active_positions = row[3] or 0
        closed_positions = row[4] or 0
        
        total_pnl = unrealized_pnl + realized_pnl
        return_percentage = (total_pnl / total_deposits * 100) if total_deposits > 0 else Decimal(0)
        
        return SimplifiedPnLResponse(
            user_id=user_id,
            realized_pnl_usdc=realized_pnl,
            unrealized_pnl_usdc=unrealized_pnl,
            total_pnl_usdc=total_pnl,
            total_return_percentage=return_percentage,
            active_positions=active_positions,
            closed_positions=closed_positions
        )
    
    async def _get_pool_name(self, position: Position, db: AsyncSession) -> str:
        """Get pool name with caching."""
        
        # Check cache first
        if position.pool_address in self.pool_name_cache:
            return self.pool_name_cache[position.pool_address]
            
        # Use stored pool name if available
        if position.pool_name:
            self.pool_name_cache[position.pool_address] = position.pool_name
            return position.pool_name
            
        # Generate a default name
        pool_name = "Unknown Pool"
        
        # Cache and return
        self.pool_name_cache[position.pool_address] = pool_name
        return pool_name


# Create a singleton instance
optimized_user_service = OptimizedUserService()