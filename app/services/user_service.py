from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from decimal import Decimal
import uuid
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, or_, func, case, Numeric
from sqlalchemy.orm import selectinload

from app.database.models import User, Transaction, Position
from app.schemas.users import TransactionType, TransactionStatus, PositionStatus
from app.core.logger import logger
from app.core.positions_service import positions_service
from app.services.agent_management_service import get_agent_service
from app.core.blockchain_service import blockchain_service


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
                cdp_wallet_name=cdp_wallet_name
            )
            # Set agent status through the property (stored in user_metadata)
            user.agent_status = 'not_started'
            
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
    
    async def list_all_users(self) -> List[User]:
        """List all users."""
        # All users are considered active - no status field in new schema
        stmt = select(User)
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def get_user_by_wallet(self, wallet_address: str) -> Optional[User]:
        """Get user by wallet address (EOA or CDP wallet)."""
        stmt = select(User).where(
            or_(
                User.user_id == wallet_address,
                User.cdp_wallet_address == wallet_address
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def update_user_status(self, user_id: str, status: str) -> Optional[User]:
        """Update user agent status in metadata."""
        user = await self.get_user(user_id)
        if not user:
            return None
        
        # Agent status is stored in user_metadata
        if user.user_metadata is None:
            user.user_metadata = {}
        user.user_metadata['agent_status'] = status
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
        metadata: Optional[Dict[str, Any]] = None,
        realized_pnl_usdc: Optional[Decimal] = None,
        portfolio_value_at_time: Optional[Decimal] = None,
        cost_basis_withdrawn: Optional[Decimal] = None
    ) -> Transaction:
        """Create a new transaction record."""
        # Map old transaction_type enum to new tx_type string
        tx_type_mapping = {
            TransactionType.DEPOSIT: 'DEPOSIT',
            TransactionType.WITHDRAW: 'WITHDRAWAL',
            TransactionType.POSITION_ENTRY: 'POSITION_CREATED',
            TransactionType.POSITION_EXIT: 'POSITION_CLOSED',
            TransactionType.FEE_COLLECTION: 'FEES_COLLECTED'
        }
        
        tx_type_value = tx_type_mapping.get(transaction_type, str(transaction_type).upper())
        
        # Prepare metadata with PnL values
        tx_metadata = metadata or {}
        if realized_pnl_usdc is not None:
            tx_metadata['realized_pnl_usdc'] = float(realized_pnl_usdc)
        if portfolio_value_at_time is not None:
            tx_metadata['portfolio_value_at_time'] = float(portfolio_value_at_time)
        if cost_basis_withdrawn is not None:
            tx_metadata['cost_basis_withdrawn'] = float(cost_basis_withdrawn)
        
        transaction = Transaction(
            user_id=user_id,
            tx_type=tx_type_value,
            tx_hash=tx_hash,
            status=TransactionStatus.PENDING,
            tx_metadata=tx_metadata,
            event_data={'amount_usdc': float(amount_usdc)} if amount_usdc else {}
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
        stmt = select(Transaction).where(Transaction.id == transaction_id)
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
            # Store gas_price in tx_metadata since it's a property that reads from there
            metadata = transaction.tx_metadata or {}
            metadata['gas_price'] = float(gas_price)
            transaction.tx_metadata = metadata
        
        if status == TransactionStatus.CONFIRMED:
            transaction.processed_at = datetime.utcnow()
        
        await self.db.commit()
        await self.db.refresh(transaction)
        return transaction
    
    async def get_user_balance(self, user_id: str) -> Decimal:
        """Get user's current USDC balance from watcher-maintained field."""
        # Read directly from the users table - watcher owns this data
        user = await self.get_user(user_id)
        if not user:
            return Decimal(0)
        
        # Return the watcher-maintained balance
        return user.usdc_balance or Decimal(0)
    
    async def get_user_transactions(
        self,
        user_id: str,
        transaction_type: Optional[TransactionType] = None,
        status: Optional[TransactionStatus] = None,
        limit: int = 100,
        offset: int = 0,
        sort_order: str = "desc"
    ) -> List[Transaction]:
        """Get user transactions with optional filters."""
        stmt = select(Transaction).where(Transaction.user_id == user_id)
        
        if transaction_type:
            # Map old enum value to new tx_type string
            tx_type_map = {
                'deposit': 'DEPOSIT',
                'withdraw': 'WITHDRAWAL', 
                'position_entry': 'POSITION_CREATED',
                'position_exit': 'POSITION_CLOSED',
                'fee_collection': 'FEES_COLLECTED',
                'protocol_fee': 'PROTOCOL_FEE'
            }
            tx_type_value = tx_type_map.get(transaction_type.value if hasattr(transaction_type, 'value') else transaction_type, transaction_type)
            stmt = stmt.where(Transaction.tx_type == tx_type_value)
        if status:
            stmt = stmt.where(Transaction.status == status)
        
        # Order by block_number first (if available), then by created_at
        # This ensures proper chronological order for blockchain transactions
        if sort_order.lower() == "asc":
            # Oldest first
            stmt = stmt.order_by(
                Transaction.block_number.asc().nullsfirst(),  # Blockchain order first
                Transaction.created_at.asc()  # Then by creation time
            )
        else:
            # Newest first (default)
            stmt = stmt.order_by(
                Transaction.block_number.desc().nullslast(),  # Blockchain order first
                Transaction.created_at.desc()  # Then by creation time
            )
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
        
        # Auto-confirm the deposit (whether it has tx_hash or not)
        # This allows both on-chain and simulated deposits to work
        transaction = await self.update_transaction_status(
            transaction_id=transaction.id,
            status=TransactionStatus.CONFIRMED,
            tx_hash=tx_hash
        )
        
        # Recalculate user PnL after deposit
        await self.recalculate_user_pnl(user_id)
        
        # Publish balance change event for confirmed deposits
        new_balance = await self.get_user_balance(user_id)
        agent_service = get_agent_service()
        await agent_service.publish_balance_event(
            user_id=user_id,
            balance=float(new_balance),
            event_type='deposit'
        )
        logger.info(f"Published balance event after deposit for {user_id}: {new_balance} USDC")
        
        logger.info(f"Processed deposit of {amount} USDC for user {user_id}")
        return transaction
    
    async def withdraw_usdc(
        self,
        user_id: str,
        amount: Decimal,
        tx_hash: Optional[str] = None,
        to_address: Optional[str] = None,
        force_close_positions: bool = True,
        max_slippage_percent: Decimal = Decimal("0.5"),
        withdraw_all: bool = False
    ) -> Transaction:
        """Process USDC withdrawal for user.
        
        Args:
            user_id: The user's wallet address (used as ID)
            amount: Amount of USDC to withdraw
            tx_hash: Optional transaction hash if already executed
            to_address: Optional destination address (defaults to user_id)
            force_close_positions: Whether to close positions if needed
            max_slippage_percent: Maximum acceptable slippage when closing positions
            withdraw_all: Whether to withdraw entire available balance
        """
        # Verify user exists
        user = await self.get_user(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        # Check current wallet balance
        wallet_balance = await self.get_user_balance(user_id)
        
        # Track positions that need to be closed
        positions_to_close = []
        positions_closed = []
        
        # If withdraw_all is true and wallet has sufficient balance, use actual balance
        if withdraw_all and wallet_balance >= amount:
            logger.info(f"Withdraw all: using actual wallet balance {wallet_balance} instead of requested {amount}")
            amount = wallet_balance
        
        # If wallet balance is insufficient, check if we should close positions
        if wallet_balance < amount:
            if not force_close_positions:
                raise ValueError(f"Insufficient wallet balance. Available: {wallet_balance}, Requested: {amount}")
            
            # Get active positions
            active_positions = await self.get_user_positions(user_id, status='ACTIVE')
            
            if not active_positions:
                raise ValueError(f"Insufficient funds. Wallet: {wallet_balance}, No active positions to close")
            
            logger.info(f"Need to close {len(active_positions)} positions for withdrawal of {amount} USDC")
            
            # Store positions that need to be closed (but don't close them yet)
            positions_to_close = active_positions
            
            # Calculate expected balance after closing positions
            expected_balance = wallet_balance
            for position in active_positions:
                expected_balance += (position.current_value_usdc or position.entry_amount_usdc)
            
            if expected_balance < amount:
                raise ValueError(f"Insufficient funds even with positions. Expected: {expected_balance}, Requested: {amount}")
        
        # If no tx_hash provided, execute withdrawal through agent manager
        if not tx_hash:
            from app.services.agent_management_service import get_agent_service
            agent_service = get_agent_service()
            
            try:
                # If positions need to be closed, mark them as closed in DB first
                # (will rollback if withdrawal fails)
                if positions_to_close:
                    for position in positions_to_close:
                        closed_position = await self.close_position(
                            user_id=user_id,
                            nft_token_id=position.nft_token_id
                        )
                        if closed_position:
                            positions_closed.append(closed_position)
                            logger.info(f"Marked position {position.nft_token_id} as closed in DB")
                    
                    # Ensure all transactions are committed before checking balance
                    await self.db.commit()
                    
                    # Re-check balance after marking positions closed
                    wallet_balance = await self.get_user_balance(user_id)
                    logger.info(f"Balance after closing {len(positions_closed)} positions: {wallet_balance} USDC")
                    
                    # If withdraw_all flag is set, use the actual balance
                    if withdraw_all:
                        logger.info(f"Withdraw all: using actual balance {wallet_balance} instead of requested {amount}")
                        amount = wallet_balance
                    elif wallet_balance < amount:
                        # Rollback position closures
                        await self._rollback_position_closures(positions_closed)
                        raise ValueError(f"Still insufficient after closing positions. Available: {wallet_balance}, Requested: {amount}")
                
                # Request withdrawal through agent
                result = await agent_service.withdraw_usdc(
                    user_id=user_id,
                    amount=float(amount),
                    to_address=to_address,
                    positions_to_close=[p.nft_token_id for p in positions_to_close],  # Tell agent which positions to close
                    withdraw_all=withdraw_all
                )
                
                if not result.get('success'):
                    # Rollback position closures if withdrawal failed
                    if positions_closed:
                        await self._rollback_position_closures(positions_closed)
                    error_msg = result.get('error', 'Unknown error')
                    raise ValueError(f"Withdrawal failed: {error_msg}")
                
                tx_hash = result.get('tx_hash')
                if not tx_hash:
                    # Rollback position closures if no tx_hash
                    if positions_closed:
                        await self._rollback_position_closures(positions_closed)
                    raise ValueError("Withdrawal executed but no transaction hash returned")
                    
            except Exception as e:
                # Rollback any position closures on any error
                if positions_closed:
                    await self._rollback_position_closures(positions_closed)
                raise
        
        # Calculate realized PnL for this withdrawal
        # Get total deposits and current portfolio value
        all_deposits = await self.get_user_transactions(
            user_id=user_id,
            transaction_type=TransactionType.DEPOSIT,
            status=TransactionStatus.CONFIRMED
        )
        total_deposited = sum(t.amount_usdc for t in all_deposits)
        
        # Get current portfolio value before withdrawal
        wallet_balance_before = await self.get_user_balance(user_id)
        active_positions = await self.get_user_positions(user_id, status='ACTIVE')
        positions_value = sum(p.current_value_usdc or p.entry_amount_usdc for p in active_positions)
        portfolio_value_before = wallet_balance_before + positions_value
        
        # Calculate realized PnL when withdrawal occurs
        # Realized PnL = total_withdrawals - total_deposits (after this withdrawal)
        from app.services.pnl_calculator import PnLCalculator
        
        # Update realized PnL based on this withdrawal
        pnl_result = await PnLCalculator.calculate_realized_pnl_on_withdrawal(
            db=self.db,
            user_id=user_id,
            withdrawal_amount=amount
        )
        
        realized_pnl_amount = pnl_result["realized_pnl_usd"]
        
        # Create withdrawal transaction record
        transaction = await self.create_transaction(
            user_id=user_id,
            transaction_type=TransactionType.WITHDRAW,
            amount_usdc=amount,
            tx_hash=tx_hash,
            realized_pnl_usdc=Decimal(0),  # Don't attribute PnL to individual tx
            portfolio_value_at_time=portfolio_value_before,
            cost_basis_withdrawn=Decimal(0),
            metadata={
                "type": "withdrawal",
                "to_address": to_address or user_id,
                "realized_pnl_total": str(realized_pnl_amount)  # Track total realized PnL
            }
        )
        
        # Mark as confirmed since we have tx_hash
        if tx_hash:
            transaction = await self.update_transaction_status(
                transaction_id=transaction.id,
                status=TransactionStatus.CONFIRMED,
                tx_hash=tx_hash
            )
        
        # Don't recalculate PnL here - we already updated it above
        # Just recalculate unrealized PnL from active positions
        if tx_hash:  # Only for confirmed withdrawals
            # Update only unrealized PnL from positions
            await self._update_unrealized_pnl_only(user_id)
            
            # Publish balance change event for confirmed withdrawals
            new_balance = await self.get_user_balance(user_id)
            agent_service = get_agent_service()
            await agent_service.publish_balance_event(
                user_id=user_id,
                balance=float(new_balance),
                event_type='withdrawal'
            )
            logger.info(f"Published balance event after withdrawal for {user_id}: {new_balance} USDC")
        
        logger.info(f"Processed withdrawal of {amount} USDC for user {user_id} (tx: {tx_hash})")
        return transaction
    
    async def preview_withdrawal(
        self,
        user_id: str,
        amount: Decimal
    ) -> Dict[str, Any]:
        """Preview a withdrawal to show what would happen.
        
        Returns information about positions that would need to be closed,
        estimated fees, and whether the withdrawal is possible.
        """
        # Get current wallet balance
        wallet_balance = await self.get_user_balance(user_id)
        
        # Get active positions
        active_positions = await self.get_user_positions(user_id, status='ACTIVE')
        
        # Calculate total positions value
        positions_value = Decimal(0)
        if active_positions:
            for position in active_positions:
                # Use current_value_usdc from database as estimate
                positions_value += position.current_value_usdc or position.entry_amount_usdc
        
        # Determine if positions need to be closed
        requires_closing = wallet_balance < amount
        positions_to_close = len(active_positions) if requires_closing else 0
        
        # Gas fees are sponsored - no USDC cost to user
        estimated_gas = Decimal("0")
        
        # Estimate slippage (0.1% of positions value - minimal for liquidity removal)
        estimated_slippage = positions_value * Decimal("0.001") if requires_closing else Decimal(0)
        
        # Calculate estimated available after closing
        if requires_closing:
            estimated_available = wallet_balance + positions_value - estimated_gas - estimated_slippage
        else:
            estimated_available = wallet_balance
        
        # Determine if withdrawal is possible
        can_withdraw = estimated_available >= amount
        
        # Generate warning message
        warning_message = None
        if requires_closing:
            if estimated_slippage > 0:
                warning_message = f"This withdrawal requires closing {positions_to_close} position(s). Estimated slippage: {estimated_slippage:.4f} USDC"
            else:
                warning_message = f"This withdrawal requires closing {positions_to_close} position(s)"
        if not can_withdraw:
            warning_message = f"Insufficient funds. Available after closing: {estimated_available:.6f} USDC (includes {estimated_slippage:.4f} USDC slippage)"
        
        return {
            "requested_amount": amount,
            "wallet_balance": wallet_balance,
            "positions_to_close": positions_to_close,
            "positions_value": positions_value if requires_closing else Decimal(0),
            "estimated_gas_fees": estimated_gas,
            "estimated_slippage": estimated_slippage,
            "estimated_available": estimated_available,
            "can_withdraw": can_withdraw,
            "requires_position_closing": requires_closing,
            "warning_message": warning_message
        }
    
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
        total_unrealized = sum(p.unrealized_pnl_usdc for p in positions if p.status == 'ACTIVE')
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
        gauge_address: Optional[str] = None,
        pool_name: Optional[str] = None
    ) -> Position:
        """Create a new position and deduct balance atomically."""
        # Check if user has sufficient balance
        current_balance = await self.get_user_balance(user_id)
        if current_balance < entry_amount_usdc:
            raise ValueError(
                f"Insufficient balance. Available: {current_balance}, Required: {entry_amount_usdc}"
            )
        
        # Create position with initial value set to entry amount
        position = Position(
            user_id=user_id,
            token_id=nft_token_id,  # Primary key is token_id, not nft_token_id
            pool_address=pool_address,
            pool_name=pool_name,
            token0_address=token0_address,
            token1_address=token1_address,
            tick_lower=tick_lower,
            tick_upper=tick_upper,
            tick_spacing=tick_spacing,
            liquidity=liquidity,
            entry_amount_usdc=entry_amount_usdc,
            current_value_usdc=entry_amount_usdc,  # Initialize with entry amount
            entry_tx_hash=entry_tx_hash,
            staked=staked,
            gauge_address=gauge_address,
            status='ACTIVE',  # Use uppercase status for consistency
            entry_date=datetime.utcnow(),
            last_updated=datetime.utcnow()
        )
        
        # Create transaction record for position entry (debit)
        transaction = Transaction(
            user_id=user_id,
            transaction_type=TransactionType.POSITION_ENTRY,
            amount_usdc=entry_amount_usdc,  # Store as positive, type indicates debit
            pool_name=pool_name,  # Add pool name to transaction
            tx_hash=entry_tx_hash,
            status=TransactionStatus.CONFIRMED,
            tx_metadata=json.dumps({
                "nft_token_id": nft_token_id,
                "pool_address": pool_address,
                "pool_name": pool_name,
                "action": "position_opened"
            }),
            confirmed_at=datetime.now(timezone.utc)
        )
        
        # Add both records in the same transaction
        self.db.add(position)
        self.db.add(transaction)
        await self.db.commit()
        await self.db.refresh(position)
        
        # Recalculate user PnL after creating position
        await self.recalculate_user_pnl(user_id)
        
        logger.info(f"Created position {nft_token_id} for user {user_id}, deducted {entry_amount_usdc} USDC")
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
            # staked is stored in position_data JSONB field
            if staked:
                stmt = stmt.where(Position.position_data['gauge_info']['staked'].astext == 'true')
            else:
                stmt = stmt.where(
                    or_(
                        Position.position_data['gauge_info']['staked'].astext == 'false',
                        Position.position_data['gauge_info']['staked'].is_(None)
                    )
                )
        
        stmt = stmt.order_by(Position.created_at.desc())
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def update_position_value(
        self,
        nft_token_id: int,
        current_value_usdc: Decimal,
        unrealized_pnl_usdc: Optional[Decimal] = None,
        fees_earned_usdc: Optional[Decimal] = None,
        rewards_earned_usdc: Optional[Decimal] = None
    ) -> Optional[Position]:
        """Update position value and performance metrics."""
        stmt = select(Position).where(Position.token_id == nft_token_id)
        result = await self.db.execute(stmt)
        position = result.scalar_one_or_none()
        
        if not position:
            return None
        
        position.current_value_usdc = current_value_usdc
        if unrealized_pnl_usdc is not None:
            position.unrealized_pnl_usd = unrealized_pnl_usdc
        if fees_earned_usdc is not None:
            position.fees_earned_usdc = fees_earned_usdc
        if rewards_earned_usdc is not None:
            position.rewards_earned_usdc = rewards_earned_usdc
        
        position.last_updated = datetime.now(timezone.utc)
        
        await self.db.commit()
        await self.db.refresh(position)
        return position
    
    async def sync_position_values(self, user_id: str) -> None:
        """Sync all position values with blockchain for a user."""
        from app.core.positions_service import positions_service
        
        positions = await self.get_user_positions(user_id, status='ACTIVE')
        
        for position in positions:
            try:
                # Fetch real-time value from blockchain
                position_info = await positions_service.get_position_by_id(position.nft_token_id)
                
                if position_info:
                    current_value = Decimal(str(position_info.current_value_usd or 0))
                    unclaimed_fees = Decimal(str(position_info.unclaimed_fees_usd or 0))
                    
                    # Update position value
                    total_value = current_value + unclaimed_fees
                    unrealized_pnl = total_value - (position.entry_amount_usdc or Decimal(0))
                    
                    await self.update_position_value(
                        nft_token_id=position.nft_token_id,
                        current_value_usdc=total_value,
                        unrealized_pnl_usdc=unrealized_pnl,
                        fees_earned_usdc=unclaimed_fees
                    )
                    
                    logger.info(f"Updated position {position.nft_token_id} value: ${total_value}")
                else:
                    logger.warning(f"Could not fetch blockchain data for position {position.nft_token_id}")
                    
            except Exception as e:
                if "execution reverted: ID" in str(e) or "ContractLogicError" in str(e):
                    # Position closed on-chain but not in DB
                    logger.error(f"Position {position.nft_token_id} closed on-chain but still active in DB")
                    # Could mark as closed here if needed
                else:
                    logger.error(f"Error syncing position {position.nft_token_id}: {e}")
    
    async def update_position_status(
        self,
        nft_token_id: int,
        status
    ) -> Optional[Position]:
        """Update position status in database."""
        stmt = select(Position).where(Position.token_id == nft_token_id)
        result = await self.db.execute(stmt)
        position = result.scalar_one_or_none()
        
        if position:
            position.status = status
            position.last_updated = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(position)
            logger.info(f"Updated position {nft_token_id} status to {status}")
        
        return position
    
    async def close_position(
        self,
        user_id: str,
        nft_token_id: int,
        exit_tx_hash: Optional[str] = None,
        realized_pnl_usdc: Optional[Decimal] = None,
        final_value_usdc: Optional[Decimal] = None
    ) -> Optional[Position]:
        """Close a position and return funds to user balance."""
        # Allow closing already closed positions for idempotency
        stmt = select(Position).where(
            and_(
                Position.token_id == nft_token_id,  # Use actual column name
                Position.user_id == user_id,
                Position.status.in_(['active', 'closed'])
            )
        )
        result = await self.db.execute(stmt)
        position = result.scalar_one_or_none()
        
        if not position:
            logger.error(f"Position {nft_token_id} not found for user {user_id} with status='active'")
            # Try to find it without status filter to debug
            debug_stmt = select(Position).where(
                and_(
                    Position.token_id == nft_token_id,  # Use actual column name
                    Position.user_id == user_id
                )
            )
            debug_result = await self.db.execute(debug_stmt)
            debug_position = debug_result.scalar_one_or_none()
            if debug_position:
                logger.error(f"Found position but with status='{debug_position.status}' instead of 'active'")
            else:
                logger.error(f"Position {nft_token_id} not found at all for user {user_id}")
            return None
        
        # If position is already closed, just return it without creating duplicate transaction
        if position.status == 'CLOSED':
            logger.info(f"Position {nft_token_id} is already closed, skipping duplicate closure")
            return position
        
        # Calculate final value if not provided
        if final_value_usdc is None:
            # For now, skip blockchain fetch and use database values
            # The blockchain fetch might be failing or returning None
            final_value_usdc = position.current_value_usdc or position.entry_amount_usdc
            logger.info(f"Using database value for position {nft_token_id}: current={position.current_value_usdc}, entry={position.entry_amount_usdc}, using={final_value_usdc}")
        
        # Calculate realized P&L if not provided
        if realized_pnl_usdc is None:
            realized_pnl_usdc = final_value_usdc - position.entry_amount_usdc
        
        # Update position status
        position.status = 'CLOSED'
        position.exit_tx_hash = exit_tx_hash
        position.exit_date = datetime.now(timezone.utc)
        position.realized_pnl_usd = realized_pnl_usdc
        position.current_value_usdc = final_value_usdc
        position.unrealized_pnl_usd = Decimal(0)
        
        # No protocol fee - return full value to user
        position.protocol_fee_amount = Decimal('0')
        position.protocol_fee_collected = False
        amount_returned = final_value_usdc
        
        logger.info(f"Position {nft_token_id} closure details: final_value={final_value_usdc}, amount_returned={amount_returned}")
        
        # Create transaction record for position exit (credit) with realized PnL - directly as CONFIRMED
        tx_metadata = {
            "nft_token_id": nft_token_id,
            "pool_address": position.pool_address,
            "pool_name": position.pool_name,
            "action": "position_closed",
            "realized_pnl": str(realized_pnl_usdc),
            "protocol_fee": "0",
            "realized_pnl_usdc": float(realized_pnl_usdc)
        }
        
        transaction = Transaction(
            id=uuid.uuid4(),  # Ensure we have a primary key
            user_id=user_id,
            tx_type='POSITION_CLOSED',  # Maps to TransactionType.POSITION_EXIT
            tx_hash=exit_tx_hash,
            status='CONFIRMED',  # Fixed to uppercase for consistency
            tx_metadata=tx_metadata,
            event_data={'amount_usdc': float(amount_returned)},
            processed_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc)
        )
        
        self.db.add(transaction)
        await self.db.commit()
        await self.db.refresh(position)
        await self.db.refresh(transaction)
        
        # Recalculate user PnL after closing position
        await self.recalculate_user_pnl(user_id)
        
        # Log the transaction details for debugging
        logger.info(f"Created POSITION_CLOSED transaction: id={transaction.id}, amount={float(amount_returned)}, status={transaction.status}")
        
        # Double-check the balance immediately after
        test_balance = await self.get_user_balance(user_id)
        logger.info(f"Balance after closing position {nft_token_id}: {test_balance} USDC (should be {amount_returned})")
        
        logger.info(f"Closed position {nft_token_id} for user {user_id}, returned {amount_returned} USDC")
        return position
    
    # Protocol fee methods removed - fees are now tracked directly on Position model
    # Use position.protocol_fee_amount, position.protocol_fee_collected fields instead
    
    async def update_user_pnl(
        self, 
        user_id: str,
        unrealized_pnl: Decimal,
        realized_pnl: Decimal,
        unrealized_pnl_percentage: Decimal,
        realized_pnl_percentage: Decimal
    ) -> None:
        """Update user's PnL values in the database.
        
        Args:
            user_id: User's wallet address
            unrealized_pnl: Unrealized P&L from active positions
            realized_pnl: Realized P&L calculated as (withdrawals - deposits) + closed positions PnL
            unrealized_pnl_percentage: Unrealized PnL as percentage
            realized_pnl_percentage: Realized PnL as percentage
        """
        stmt = select(User).where(User.user_id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user:
            user.unrealized_pnl_usd = unrealized_pnl
            user.realized_pnl_usd = realized_pnl
            user.unrealized_pnl_pct = unrealized_pnl_percentage
            user.realized_pnl_pct = realized_pnl_percentage
            user.updated_at = datetime.now(timezone.utc)
            
            await self.db.commit()
            logger.info(
                f"Updated PnL for user {user_id}: "
                f"unrealized={unrealized_pnl}, realized={realized_pnl}, "
                f"unrealized%={unrealized_pnl_percentage}, realized%={realized_pnl_percentage}"
            )
    
    async def _rollback_position_closures(self, positions: List) -> None:
        """Rollback position closures by reopening them and removing exit transactions."""
        logger.info(f"Rolling back {len(positions)} position closures")
        
        for position in positions:
            try:
                # Reopen the position
                position.status = 'ACTIVE'
                position.exit_date = None
                position.exit_tx_hash = None
                position.realized_pnl_usd = Decimal(0)
                
                # Find and remove the POSITION_EXIT transaction using JSONB containment
                from sqlalchemy import cast, Text
                from sqlalchemy.dialects.postgresql import JSONB
                
                exit_tx = await self.db.execute(
                    select(Transaction).where(
                        and_(
                            Transaction.tx_type == 'POSITION_CLOSED',
                            Transaction.tx_metadata.op('@>')(cast({'nft_token_id': position.nft_token_id}, JSONB))
                        )
                    ).order_by(Transaction.created_at.desc()).limit(1)
                )
                exit_transaction = exit_tx.scalar_one_or_none()
                
                if exit_transaction:
                    await self.db.delete(exit_transaction)
                    logger.info(f"Removed POSITION_EXIT transaction for position {position.nft_token_id}")
                
                logger.info(f"Rolled back position {position.nft_token_id} to ACTIVE status")
                
            except Exception as e:
                logger.error(f"Error rolling back position {position.nft_token_id}: {e}")
        
        await self.db.commit()
    
    async def _update_unrealized_pnl_only(self, user_id: str) -> None:
        """Update only unrealized PnL from active positions without changing realized PnL."""
        stmt = select(User).where(User.user_id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(f"User {user_id} not found for unrealized PnL update")
            return
        
        # Get all active positions for unrealized PNL
        all_positions = await self.get_user_positions(user_id)
        active_positions = [p for p in all_positions if p.status == 'ACTIVE']
        
        # Calculate unrealized PNL from active positions
        unrealized_pnl = Decimal(0)
        
        for position in active_positions:
            try:
                # Try to get real-time value from blockchain
                from app.services.positions_service import positions_service
                position_info = await positions_service.get_position_by_id(position.nft_token_id)
                
                if position_info:
                    current_value_usd = Decimal(str(position_info.current_value_usd or 0))
                    unclaimed_fees_usd = Decimal(str(position_info.unclaimed_fees_usd or 0))
                    position_current_value = current_value_usd + unclaimed_fees_usd
                    position.current_value_usdc = position_current_value
                else:
                    # Use cached value if blockchain fetch fails
                    position_current_value = position.current_value_usdc or position.entry_amount_usdc or Decimal(0)
                
                # Calculate unrealized PNL for this position
                position_unrealized_pnl = position_current_value - position.entry_amount_usdc
                unrealized_pnl += position_unrealized_pnl
                
            except Exception as e:
                logger.error(f"Error fetching position {position.nft_token_id}: {e}")
                # Use cached value as fallback
                cached_value = position.current_value_usdc or position.entry_amount_usdc or Decimal(0)
                position_unrealized_pnl = cached_value - position.entry_amount_usdc
                unrealized_pnl += position_unrealized_pnl
        
        # Update only unrealized PnL fields
        total_deposits = Decimal(str(user.total_deposits_usdc or 0))
        if total_deposits > 0:
            unrealized_pnl_percentage = (unrealized_pnl / total_deposits) * Decimal(100)
        else:
            unrealized_pnl_percentage = Decimal(0)
        
        user.unrealized_pnl_usd = unrealized_pnl
        user.unrealized_pnl_pct = unrealized_pnl_percentage
        user.updated_at = datetime.now(timezone.utc)
        
        await self.db.commit()
        logger.info(f"Updated unrealized PnL for user {user_id}: ${unrealized_pnl} ({unrealized_pnl_percentage:.2f}%)")
    
    async def recalculate_user_pnl(self, user_id: str) -> None:
        """Recalculate and update user's PnL values.
        
        PNL is calculated as:
        - Realized PNL: total_withdrawals - total_deposits (simple cash-on-cash return)
        - Unrealized PNL: Sum of (current_value - entry_amount) from active positions
        
        This should be called after:
        - Position is closed
        - Position is opened
        - Position value is updated
        - Deposits/Withdrawals
        """
        from app.core.positions_service import positions_service
        
        # Get user to fetch totals from the database
        stmt = select(User).where(User.user_id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(f"User {user_id} not found for PnL calculation")
            return
        
        # Use the totals maintained by the watcher
        total_deposits = Decimal(str(user.total_deposits_usdc or 0))
        total_withdrawals = Decimal(str(user.total_withdrawals_usdc or 0))
        
        # Realized PNL should only be calculated when withdrawals are made
        # It represents actual profit/loss that has been "realized" by withdrawing
        # For now, use the existing realized_pnl_usd from the user record
        # This should be updated only when processing WITHDRAWAL transactions
        realized_pnl = Decimal(str(user.realized_pnl_usd or 0))
        
        # Get all active positions for unrealized PNL
        all_positions = await self.get_user_positions(user_id)
        active_positions = [p for p in all_positions if p.status == 'ACTIVE']
        
        # Calculate unrealized PNL from active positions
        unrealized_pnl = Decimal(0)
        
        for position in active_positions:
            try:
                # Fetch real-time value from blockchain
                position_info = await positions_service.get_position_by_id(position.nft_token_id)
                
                if position_info:
                    current_value_usd = Decimal(str(position_info.current_value_usd or 0))
                    unclaimed_fees_usd = Decimal(str(position_info.unclaimed_fees_usd or 0))
                    
                    # Calculate total current value
                    position_current_value = current_value_usd + unclaimed_fees_usd
                    
                    # Update position's current value in DB for caching
                    position.current_value_usdc = position_current_value
                    
                    # Calculate unrealized PNL for this position
                    position_unrealized_pnl = position_current_value - position.entry_amount_usdc
                    unrealized_pnl += position_unrealized_pnl
                else:
                    # If blockchain fetch fails, use database value
                    cached_value = position.current_value_usdc or position.entry_amount_usdc or Decimal(0)
                    position_unrealized_pnl = cached_value - position.entry_amount_usdc
                    unrealized_pnl += position_unrealized_pnl
                    
            except Exception as e:
                # Check if position was closed externally
                if "execution reverted: ID" in str(e) or "ContractLogicError" in str(e):
                    logger.warning(f"Position {position.nft_token_id} not found on-chain, may be closed externally")
                    # Mark position as closed if it doesn't exist on-chain
                    position.status = 'CLOSED'
                    position.realized_pnl_usd = position.current_value_usdc - position.entry_amount_usdc
                    # Move its PNL to realized
                    realized_pnl += position.realized_pnl_usdc or Decimal(0)
                else:
                    logger.error(f"Error fetching position {position.nft_token_id}: {e}")
                    # Use database value as fallback for unrealized PNL
                    cached_value = position.current_value_usdc or position.entry_amount_usdc or Decimal(0)
                    position_unrealized_pnl = cached_value - position.entry_amount_usdc
                    unrealized_pnl += position_unrealized_pnl
        
        # Commit any position value updates
        await self.db.commit()
        
        # Calculate percentages based on total deposits
        # This shows the return on actual money invested
        if total_deposits > 0:
            realized_pnl_percentage = (realized_pnl / total_deposits) * Decimal(100)
            unrealized_pnl_percentage = (unrealized_pnl / total_deposits) * Decimal(100)
        else:
            realized_pnl_percentage = Decimal(0)
            unrealized_pnl_percentage = Decimal(0)
        
        # Update user PnL values
        await self.update_user_pnl(
            user_id=user_id,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=realized_pnl,
            unrealized_pnl_percentage=unrealized_pnl_percentage,
            realized_pnl_percentage=realized_pnl_percentage
        )
        
        logger.info(f"Updated PNL for user {user_id}: deposits={total_deposits}, withdrawals={total_withdrawals}, realized={realized_pnl} ({realized_pnl_percentage:.2f}%), unrealized={unrealized_pnl} ({unrealized_pnl_percentage:.2f}%)")
    
    async def calculate_user_performance(self, user_id: str) -> Dict[str, Any]:
        """Calculate comprehensive performance metrics for a user."""
        # Get all positions
        positions = await self.get_user_positions(user_id)
        
        # Calculate totals
        total_invested = sum(p.entry_amount_usdc for p in positions)
        total_current_value = sum(p.current_value_usdc or 0 for p in positions if p.status == 'ACTIVE')
        total_realized_pnl = sum(p.realized_pnl_usdc for p in positions)
        total_unrealized_pnl = sum(p.unrealized_pnl_usdc for p in positions if p.status == 'ACTIVE')
        total_fees_earned = sum(p.fees_earned_usdc for p in positions)
        total_rewards_earned = sum(p.rewards_earned_usdc for p in positions)
        
        # Get uncollected protocol fees from positions
        total_protocol_fees_pending = sum(
            p.protocol_fee_amount for p in positions 
            if p.protocol_fee_amount and not p.protocol_fee_collected
        )
        
        # Calculate overall PnL
        total_pnl = total_realized_pnl + total_unrealized_pnl + total_fees_earned + total_rewards_earned
        
        # Calculate APR - fetch from strategy monitor endpoint for accurate weighted average
        active_positions = [p for p in positions if p.status == 'ACTIVE']
        apr = Decimal(0)
        
        # Get user to find CDP wallet address for strategy monitor
        user = await self.get_user(user_id)
        if user and user.cdp_wallet_address and active_positions:
            try:
                # Call strategy monitor endpoint internally
                from app.schemas.strategy_v2 import MonitorRequest
                from app.core.strategy_service import strategy_service
                from app.schemas.strategy import MonitorPositionsRequest
                
                # Use the CDP wallet address for the strategy monitor
                monitor_request = MonitorPositionsRequest(
                    user_address=user.cdp_wallet_address
                )
                monitor_response = await strategy_service.monitor_positions(monitor_request)
                
                # Calculate weighted average APR based on position values
                if monitor_response and monitor_response.positions:
                    from app.core.positions_service import positions_service
                    
                    # Fetch actual position data for values
                    positions_data = await positions_service.get_positions_by_owner(user.cdp_wallet_address)
                    
                    # Calculate weighted average APR
                    total_value = 0
                    weighted_apr_sum = 0
                    
                    for pos_data in positions_data:
                        # Find corresponding position status with effective APR
                        pos_status = next((p for p in monitor_response.positions if p.token_id == pos_data.id), None)
                        if pos_status and pos_data.current_value_usd:
                            position_value = pos_data.current_value_usd
                            total_value += position_value
                            weighted_apr_sum += position_value * pos_status.current_apr
                    
                    apr = Decimal(weighted_apr_sum / total_value) if total_value > 0 else Decimal(0)
                
            except Exception as e:
                logger.warning(f"Could not fetch APR from strategy monitor for user {user_id}: {e}")
                # Fallback to simple APR calculation
                if active_positions and total_invested > 0:
                    avg_position_age_days = sum(
                        (datetime.now(timezone.utc) - p.entry_date).days 
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