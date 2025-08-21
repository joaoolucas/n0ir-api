from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
import uuid
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, or_, func, case
from sqlalchemy.orm import selectinload

from app.database.models import User, Transaction, Position
from app.database.models.user import UserStatus
from app.database.models.transaction import TransactionType, TransactionStatus
from app.database.models.position import PositionStatus
from app.core.logger import logger


class UserService:
    """Service layer for user management operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_user(
        self,
        user_id: str,
        cdp_wallet_address: str,
        cdp_wallet_name: str
    ) -> User:
        """Create a new user with CDP wallet information."""
        try:
            # Check if user already exists
            existing_user = await self.get_user(user_id)
            if existing_user:
                raise ValueError(f"User with ID {user_id} already exists")
            
            # Check if CDP wallet address is already registered (unless it's a pending placeholder)
            if not cdp_wallet_address.startswith("pending_"):
                stmt = select(User).where(User.cdp_wallet_address == cdp_wallet_address)
                result = await self.db.execute(stmt)
                if result.scalar_one_or_none():
                    raise ValueError(f"CDP wallet address {cdp_wallet_address} is already registered")
            
            # Create new user
            user = User(
                user_id=user_id,
                cdp_wallet_address=cdp_wallet_address,
                cdp_wallet_name=cdp_wallet_name,
                status=UserStatus.ACTIVE
            )
            
            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)
            
            logger.info(f"Created new user: {user_id} with CDP wallet: {cdp_wallet_address}")
            return user
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating user: {e}")
            raise
    
    async def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        stmt = select(User).where(User.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_user_by_wallet(self, wallet_address: str) -> Optional[User]:
        """Get user by wallet address."""
        stmt = select(User).where(User.wallet_address == wallet_address)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def update_user_status(self, user_id: str, status: UserStatus) -> Optional[User]:
        """Update user status."""
        user = await self.get_user(user_id)
        if not user:
            return None
        
        user.status = status
        user.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(user)
        return user
    
    async def update_user_wallet(self, user_id: str, wallet_address: str) -> Optional[User]:
        """Update user's CDP wallet address after wallet creation."""
        user = await self.get_user(user_id)
        if not user:
            logger.warning(f"User {user_id} not found for wallet update")
            return None
        
        # Only update if current wallet is a pending placeholder
        if user.cdp_wallet_address.startswith("pending_"):
            logger.info(f"Updating wallet for user {user_id}: {user.cdp_wallet_address} -> {wallet_address}")
            user.cdp_wallet_address = wallet_address
            user.wallet_created_at = datetime.utcnow()
            user.updated_at = datetime.utcnow()
            await self.db.commit()
            await self.db.refresh(user)
            logger.info(f"Successfully updated wallet for user {user_id}")
        else:
            logger.warning(f"User {user_id} already has wallet {user.cdp_wallet_address}, not updating to {wallet_address}")
        
        return user
    
    async def create_transaction(
        self,
        user_id: str,
        transaction_type: TransactionType,
        amount_usdc: Decimal,
        tx_hash: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Transaction:
        """Create a new transaction record."""
        transaction = Transaction(
            user_id=user_id,
            transaction_type=transaction_type,
            amount_usdc=amount_usdc,
            tx_hash=tx_hash,
            status=TransactionStatus.PENDING,
            tx_metadata=json.dumps(metadata) if metadata else None
        )
        
        self.db.add(transaction)
        await self.db.commit()
        await self.db.refresh(transaction)
        return transaction
    
    async def update_transaction_status(
        self,
        transaction_id: uuid.UUID,
        status: TransactionStatus,
        tx_hash: Optional[str] = None,
        block_number: Optional[int] = None,
        gas_used: Optional[int] = None,
        gas_price: Optional[Decimal] = None
    ) -> Optional[Transaction]:
        """Update transaction status and blockchain information."""
        stmt = select(Transaction).where(Transaction.transaction_id == transaction_id)
        result = await self.db.execute(stmt)
        transaction = result.scalar_one_or_none()
        
        if not transaction:
            return None
        
        transaction.status = status
        if tx_hash:
            transaction.tx_hash = tx_hash
        if block_number:
            transaction.block_number = block_number
        if gas_used:
            transaction.gas_used = gas_used
        if gas_price:
            transaction.gas_price = gas_price
        
        if status == TransactionStatus.CONFIRMED:
            transaction.confirmed_at = datetime.utcnow()
        
        await self.db.commit()
        await self.db.refresh(transaction)
        return transaction
    
    async def get_user_balance(self, user_id: str) -> Decimal:
        """Calculate user's current USDC balance from transactions."""
        stmt = select(
            func.sum(
                case(
                    (Transaction.transaction_type.in_([
                        TransactionType.DEPOSIT,
                        TransactionType.POSITION_EXIT
                    ]), Transaction.amount_usdc),
                    else_=-Transaction.amount_usdc
                )
            )
        ).where(
            and_(
                Transaction.user_id == user_id,
                Transaction.status == TransactionStatus.CONFIRMED
            )
        )
        
        result = await self.db.execute(stmt)
        balance = result.scalar_one()
        return balance or Decimal(0)
    
    async def get_user_transactions(
        self,
        user_id: str,
        transaction_type: Optional[TransactionType] = None,
        status: Optional[TransactionStatus] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Transaction]:
        """Get user transactions with optional filters."""
        stmt = select(Transaction).where(Transaction.user_id == user_id)
        
        if transaction_type:
            stmt = stmt.where(Transaction.transaction_type == transaction_type)
        if status:
            stmt = stmt.where(Transaction.status == status)
        
        stmt = stmt.order_by(Transaction.created_at.desc())
        stmt = stmt.limit(limit).offset(offset)
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def deposit_usdc(
        self,
        user_id: str,
        amount: Decimal,
        tx_hash: Optional[str] = None
    ) -> Transaction:
        """Process USDC deposit for user."""
        # Verify user exists
        user = await self.get_user(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        # Create deposit transaction
        transaction = await self.create_transaction(
            user_id=user_id,
            transaction_type=TransactionType.DEPOSIT,
            amount_usdc=amount,
            tx_hash=tx_hash,
            metadata={"type": "deposit"}
        )
        
        # If tx_hash provided, mark as confirmed (on-chain deposit)
        if tx_hash:
            transaction = await self.update_transaction_status(
                transaction_id=transaction.transaction_id,
                status=TransactionStatus.CONFIRMED,
                tx_hash=tx_hash
            )
        
        logger.info(f"Processed deposit of {amount} USDC for user {user_id}")
        return transaction
    
    async def withdraw_usdc(
        self,
        user_id: str,
        amount: Decimal,
        tx_hash: Optional[str] = None
    ) -> Transaction:
        """Process USDC withdrawal for user."""
        # Verify user exists
        user = await self.get_user(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        # Check user has sufficient balance
        balance = await self.get_user_balance(user_id)
        if balance < amount:
            raise ValueError(f"Insufficient balance. Available: {balance}, Requested: {amount}")
        
        # Create withdrawal transaction
        transaction = await self.create_transaction(
            user_id=user_id,
            transaction_type=TransactionType.WITHDRAWAL,
            amount_usdc=amount,
            tx_hash=tx_hash,
            metadata={"type": "withdrawal"}
        )
        
        # If tx_hash provided, mark as confirmed
        if tx_hash:
            transaction = await self.update_transaction_status(
                transaction_id=transaction.transaction_id,
                status=TransactionStatus.CONFIRMED,
                tx_hash=tx_hash
            )
        
        logger.info(f"Processed withdrawal of {amount} USDC for user {user_id}")
        return transaction
    
    async def calculate_user_pnl(self, user_id: str) -> Optional[Dict[str, Decimal]]:
        """Calculate user's P&L summary."""
        # Get all positions
        positions = await self.get_user_positions(user_id)
        
        if not positions:
            return {
                "realized": Decimal(0),
                "unrealized": Decimal(0),
                "fees": Decimal(0),
                "rewards": Decimal(0),
                "total": Decimal(0)
            }
        
        # Calculate totals
        total_realized = sum(p.realized_pnl_usdc for p in positions)
        total_unrealized = sum(p.unrealized_pnl_usdc for p in positions if p.status == PositionStatus.ACTIVE)
        total_fees = sum(p.fees_earned_usdc for p in positions)
        total_rewards = sum(p.rewards_earned_usdc for p in positions)
        
        return {
            "realized": total_realized,
            "unrealized": total_unrealized,
            "fees": total_fees,
            "rewards": total_rewards,
            "total": total_realized + total_unrealized + total_fees + total_rewards
        }
    
    async def get_performance_metrics(self, user_id: str) -> Dict[str, Any]:
        """Alias for calculate_user_performance for backward compatibility."""
        return await self.calculate_user_performance(user_id)
    
    async def create_position(
        self,
        user_id: str,
        nft_token_id: int,
        pool_address: str,
        token0_address: str,
        token1_address: str,
        tick_lower: int,
        tick_upper: int,
        tick_spacing: int,
        liquidity: str,
        entry_amount_usdc: Decimal,
        entry_tx_hash: Optional[str] = None,
        staked: bool = False,
        gauge_address: Optional[str] = None
    ) -> Position:
        """Create a new position."""
        position = Position(
            user_id=user_id,
            nft_token_id=nft_token_id,
            pool_address=pool_address,
            token0_address=token0_address,
            token1_address=token1_address,
            tick_lower=tick_lower,
            tick_upper=tick_upper,
            tick_spacing=tick_spacing,
            liquidity=liquidity,
            entry_amount_usdc=entry_amount_usdc,
            entry_tx_hash=entry_tx_hash,
            staked=staked,
            gauge_address=gauge_address,
            status=PositionStatus.ACTIVE
        )
        
        self.db.add(position)
        await self.db.commit()
        await self.db.refresh(position)
        return position
    
    async def get_user_positions(
        self,
        user_id: str,
        status: Optional[PositionStatus] = None,
        pool_address: Optional[str] = None,
        staked: Optional[bool] = None
    ) -> List[Position]:
        """Get user positions with optional filters."""
        stmt = select(Position).where(Position.user_id == user_id)
        
        if status:
            stmt = stmt.where(Position.status == status)
        if pool_address:
            stmt = stmt.where(Position.pool_address == pool_address)
        if staked is not None:
            stmt = stmt.where(Position.staked == staked)
        
        stmt = stmt.order_by(Position.entry_date.desc())
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def update_position_value(
        self,
        position_id: uuid.UUID,
        current_value_usdc: Decimal,
        unrealized_pnl_usdc: Optional[Decimal] = None,
        fees_earned_usdc: Optional[Decimal] = None,
        rewards_earned_usdc: Optional[Decimal] = None
    ) -> Optional[Position]:
        """Update position value and performance metrics."""
        stmt = select(Position).where(Position.position_id == position_id)
        result = await self.db.execute(stmt)
        position = result.scalar_one_or_none()
        
        if not position:
            return None
        
        position.current_value_usdc = current_value_usdc
        if unrealized_pnl_usdc is not None:
            position.unrealized_pnl_usdc = unrealized_pnl_usdc
        if fees_earned_usdc is not None:
            position.fees_earned_usdc = fees_earned_usdc
        if rewards_earned_usdc is not None:
            position.rewards_earned_usdc = rewards_earned_usdc
        
        position.last_updated = datetime.utcnow()
        
        await self.db.commit()
        await self.db.refresh(position)
        return position
    
    async def close_position(
        self,
        position_id: uuid.UUID,
        exit_tx_hash: str,
        realized_pnl_usdc: Decimal,
        final_value_usdc: Decimal
    ) -> Optional[Position]:
        """Close a position and record final metrics."""
        stmt = select(Position).where(Position.position_id == position_id)
        result = await self.db.execute(stmt)
        position = result.scalar_one_or_none()
        
        if not position:
            return None
        
        position.status = PositionStatus.CLOSED
        position.exit_tx_hash = exit_tx_hash
        position.exit_date = datetime.utcnow()
        position.realized_pnl_usdc = realized_pnl_usdc
        position.current_value_usdc = final_value_usdc
        position.unrealized_pnl_usdc = Decimal(0)
        
        # Calculate protocol fee if position was profitable
        total_profit = realized_pnl_usdc + position.fees_earned_usdc + position.rewards_earned_usdc
        if total_profit > 0:
            # Protocol fee is 5% of profit
            position.protocol_fee_amount = total_profit * Decimal('0.05')
            position.protocol_fee_collected = False
        
        await self.db.commit()
        await self.db.refresh(position)
        return position
    
    # Protocol fee methods removed - fees are now tracked directly on Position model
    # Use position.protocol_fee_amount, position.protocol_fee_collected fields instead
    
    async def calculate_user_performance(self, user_id: str) -> Dict[str, Any]:
        """Calculate comprehensive performance metrics for a user."""
        # Get all positions
        positions = await self.get_user_positions(user_id)
        
        # Calculate totals
        total_invested = sum(p.entry_amount_usdc for p in positions)
        total_current_value = sum(p.current_value_usdc or 0 for p in positions if p.status == PositionStatus.ACTIVE)
        total_realized_pnl = sum(p.realized_pnl_usdc for p in positions)
        total_unrealized_pnl = sum(p.unrealized_pnl_usdc for p in positions if p.status == PositionStatus.ACTIVE)
        total_fees_earned = sum(p.fees_earned_usdc for p in positions)
        total_rewards_earned = sum(p.rewards_earned_usdc for p in positions)
        
        # Get uncollected protocol fees from positions
        total_protocol_fees_pending = sum(
            p.protocol_fee_amount for p in positions 
            if p.protocol_fee_amount and not p.protocol_fee_collected
        )
        
        # Calculate overall PnL
        total_pnl = total_realized_pnl + total_unrealized_pnl + total_fees_earned + total_rewards_earned
        
        # Calculate APR if there are active positions
        active_positions = [p for p in positions if p.status == PositionStatus.ACTIVE]
        apr = Decimal(0)
        if active_positions and total_invested > 0:
            # Simple APR calculation (can be enhanced)
            avg_position_age_days = sum(
                (datetime.utcnow() - p.entry_date).days 
                for p in active_positions
            ) / len(active_positions)
            if avg_position_age_days > 0:
                apr = (total_pnl / total_invested) * (365 / avg_position_age_days) * 100
        
        return {
            "total_invested": float(total_invested),
            "total_current_value": float(total_current_value),
            "total_realized_pnl": float(total_realized_pnl),
            "total_unrealized_pnl": float(total_unrealized_pnl),
            "total_fees_earned": float(total_fees_earned),
            "total_rewards_earned": float(total_rewards_earned),
            "total_pnl": float(total_pnl),
            "total_protocol_fees_pending": float(total_protocol_fees_pending),
            "apr": float(apr),
            "active_positions": len(active_positions),
            "total_positions": len(positions)
        }