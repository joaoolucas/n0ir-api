from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import uuid
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, or_, func, case, Numeric
from sqlalchemy.orm import selectinload

from app.database.models import User, Transaction, Position
from app.schemas.users import TransactionType, TransactionStatus, PositionStatus, TimePeriod
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
            
            # Check if CDP wallet address is already registered (unless it's None or a pending placeholder)
            if cdp_wallet_address and not cdp_wallet_address.startswith("pending_"):
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

    async def get_deposit_withdrawal_totals(self, user_id: str) -> tuple[Decimal, Decimal]:
        """Compute total deposits and withdrawals from confirmed transactions.

        Only counts REAL user deposits/withdrawals:
        - Deposits: from user wallet to CDP wallet
        - Withdrawals: from CDP wallet to user wallet
        Returns (total_deposits, total_withdrawals) as Decimals.
        """
        stmt = select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.status == 'CONFIRMED',
            Transaction.tx_type.in_(['DEPOSIT', 'WITHDRAWAL', 'WITHDRAW'])
        )
        result = await self.db.execute(stmt)
        txs = result.scalars().all()

        # Get user's CDP wallet address
        user = await self.get_user(user_id)
        if not user or not user.cdp_wallet_address:
            return Decimal(0), Decimal(0)
        
        cdp_wallet = user.cdp_wallet_address.lower()
        user_wallet = user_id.lower()

        deposits = Decimal(0)
        withdrawals = Decimal(0)
        for tx in txs:
            if not tx.event_data:
                continue
                
            amt = Decimal(str(tx.amount_usdc or 0))
            from_addr = tx.event_data.get('from_address', '').lower()
            to_addr = tx.event_data.get('to_address', '').lower()
            
            if tx.tx_type == 'DEPOSIT':
                # Only count if from user wallet to CDP wallet
                if from_addr == user_wallet and to_addr == cdp_wallet:
                    deposits += amt
            elif tx.tx_type in ['WITHDRAWAL', 'WITHDRAW']:
                # Only count if from CDP wallet to user wallet
                if from_addr == cdp_wallet and to_addr == user_wallet:
                    withdrawals += amt

        return deposits, withdrawals
    
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
        
        # Only update if current wallet is None or a pending placeholder
        if user.cdp_wallet_address is None or (user.cdp_wallet_address and user.cdp_wallet_address.startswith("pending_")):
            logger.info(f"Updating wallet for user {user_id}: {user.cdp_wallet_address} -> {wallet_address}")
            user.cdp_wallet_address = wallet_address
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
        # Use the transaction type value directly (already uppercase in enum)
        tx_type_value = transaction_type.value if hasattr(transaction_type, 'value') else str(transaction_type)
        
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
    
    async def check_and_update_deposit_flag(self, user_id: str) -> bool:
        """Check if user has net deposits of 50 USDC and update flag if needed.
        
        Returns:
            True if user has net deposits >= 50 USDC, False otherwise
        """
        user = await self.get_user(user_id)
        if not user:
            return False
        
        # Calculate net deposits (deposits minus withdrawals)
        total_deposits = Decimal(str(user.total_deposits_usdc or 0))
        total_withdrawals = Decimal(str(user.total_withdrawals_usdc or 0))
        net_deposits = total_deposits - total_withdrawals
        
        # Update flag based on net deposits
        should_have_flag = net_deposits >= Decimal('50')
        
        if should_have_flag != user.has_deposited_50_usdc:
            user.has_deposited_50_usdc = should_have_flag
            await self.db.commit()
            logger.info(
                f"User {user_id} 50+ USDC flag {'granted' if should_have_flag else 'revoked'}: "
                f"net deposits = {net_deposits} USDC (deposits: {total_deposits}, withdrawals: {total_withdrawals})"
            )
        
        return should_have_flag
    
    async def get_user_balance(self, user_id: str) -> Decimal:
        """Get user's current USDC balance from database."""
        # Check and update deposit flag
        await self.check_and_update_deposit_flag(user_id)
        
        # Get the balance from the user record which should be kept in sync by the watcher
        stmt = select(User).where(User.user_id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return Decimal(0)
        
        # Return the stored balance which should be maintained by the watcher
        # The watcher updates this balance whenever transactions occur
        return Decimal(str(user.usdc_balance or 0))
    
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
            # Use the enum value directly - it should match the database
            tx_type_value = transaction_type.value if hasattr(transaction_type, 'value') else str(transaction_type)
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
        has_deposited_50 = await self.check_and_update_deposit_flag(user_id)
        agent_service = get_agent_service()
        await agent_service.publish_balance_event(
            user_id=user_id,
            balance=float(new_balance),
            event_type='deposit',
            has_deposited_50_usdc=has_deposited_50
        )
        logger.info(f"Published balance event after deposit for {user_id}: {new_balance} USDC (50+ deposited: {has_deposited_50})")
        
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
                # DO NOT mark positions as closed in DB - let the agent handle it on-chain
                # The watcher will detect POSITION_CLOSED events and update the DB
                
                # If withdraw_all and positions need to be closed, calculate expected total
                if withdraw_all and positions_to_close:
                    # Calculate expected balance after positions are closed (including AERO rewards)
                    expected_total = wallet_balance
                    for position in positions_to_close:
                        expected_total += (position.current_value_usdc or position.entry_amount_usdc)
                    
                    # Note: AERO rewards will be handled by the agent when closing positions
                    logger.info(f"Withdraw all: expecting ~{expected_total} USDC after closing {len(positions_to_close)} positions")
                    # Use a high amount to ensure everything is withdrawn
                    amount = expected_total * Decimal("1.1")  # Add 10% buffer to ensure all funds are withdrawn
                
                # Request withdrawal through agent (it will close positions on-chain if needed)
                result = await agent_service.withdraw_usdc(
                    user_id=user_id,
                    amount=float(amount),
                    to_address=to_address,
                    positions_to_close=[int(p.nft_token_id) for p in positions_to_close if p.nft_token_id],  # Ensure NFT IDs are integers
                    withdraw_all=withdraw_all
                )
                
                if not result.get('success'):
                    error_msg = result.get('error', 'Unknown error')
                    raise ValueError(f"Withdrawal failed: {error_msg}")
                
                tx_hash = result.get('tx_hash')
                if not tx_hash:
                    raise ValueError("Withdrawal executed but no transaction hash returned")
                    
            except Exception as e:
                raise
        
        # Don't create transaction in database - let the watcher handle it
        # The watcher will detect the WITHDRAWAL event on-chain and create the transaction
        # This prevents duplicate transactions
        
        # Return a temporary transaction object for API response only (not saved to DB)
        from app.database.models import Transaction
        from datetime import datetime, timezone
        import uuid
        
        # Create a mock transaction for the API response
        transaction = Transaction(
            id=uuid.uuid4(),
            user_id=user_id,
            tx_type='WITHDRAWAL',
            tx_hash=tx_hash,
            status='PENDING' if not tx_hash else 'CONFIRMED',
            event_data={
                'amount_usdc': float(amount),
                'to_address': to_address or user_id
            },
            created_at=datetime.now(timezone.utc)
        )
        
        # Check and update deposit flag after withdrawal
        await self.check_and_update_deposit_flag(user_id)
        
        logger.info(f"Withdrawal request processed for {amount} USDC from user {user_id} - watcher will create transaction record")
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
        
        # Calculate total positions value (excluding AERO rewards which are handled separately)
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
        # Note: AERO rewards are not included here as they require separate claiming
        # and conversion, which is uncertain and handled separately
        if requires_closing:
            estimated_available = wallet_balance + positions_value - estimated_slippage
        else:
            estimated_available = wallet_balance
        
        # Determine if withdrawal is possible
        can_withdraw = estimated_available >= amount
        
        # Generate warning message
        warning_message = None
        if requires_closing:
            # Simple protocol fee message without specific AERO amounts
            fee_msg = " A 2% protocol fee (0.0081 USDC) applies to AERO rewards."
            if estimated_slippage > 0:
                warning_message = f"This withdrawal requires closing {positions_to_close} position(s). Estimated slippage: {estimated_slippage:.4f} USDC.{fee_msg}"
            else:
                warning_message = f"This withdrawal requires closing {positions_to_close} position(s).{fee_msg}"
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
            transaction_type=TransactionType.POSITION_CREATED,
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
                Position.status.in_(['ACTIVE', 'CLOSED'])  # Use uppercase status values
            )
        )
        result = await self.db.execute(stmt)
        position = result.scalar_one_or_none()
        
        if not position:
            logger.error(f"Position {nft_token_id} not found for user {user_id} with status='ACTIVE' or 'CLOSED'")
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
                logger.error(f"Found position but with status='{debug_position.status}' instead of 'ACTIVE' or 'CLOSED'")
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
        # Calculate actual PnL: final value minus entry amount
        # The realized_pnl_usdc parameter might contain the final value, not the PnL
        actual_pnl = final_value_usdc - position.entry_amount_usdc
        position.realized_pnl_usd = actual_pnl
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
            tx_type='POSITION_CLOSED',  # Direct string since we're not using the enum here
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
        """Update only unrealized PnL using MTM portfolio minus net deposits minus realized."""
        stmt = select(User).where(User.user_id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            logger.error(f"User {user_id} not found for unrealized PnL update")
            return

        # Get active positions
        all_positions = await self.get_user_positions(user_id)
        active_positions = [p for p in all_positions if p.status == 'ACTIVE']

        # Wallet balance
        wallet_balance = await self.get_user_balance(user_id)

        # Build MTM portfolio
        total_portfolio_value_mtm = Decimal(str(wallet_balance))

        from app.core.positions_service import positions_service
        for position in active_positions:
            try:
                position_info = await positions_service.get_position_by_id(position.nft_token_id)
                if position_info:
                    current_value_usd = Decimal(str(position_info.current_value_usd or 0))
                    unclaimed_fees_usd = Decimal(str(position_info.unclaimed_fees_usd or 0))
                    position_current_value = current_value_usd + unclaimed_fees_usd
                    position.current_value_usdc = position_current_value
                else:
                    position_current_value = position.current_value_usdc or position.entry_amount_usdc or Decimal(0)
                total_portfolio_value_mtm += position_current_value
            except Exception as e:
                logger.error(f"Error fetching position {position.nft_token_id}: {e}")
                cached_value = position.current_value_usdc or position.entry_amount_usdc or Decimal(0)
                total_portfolio_value_mtm += cached_value

            # cost basis not used here

        await self.db.commit()

        # Net deposits
        deposits_sum, withdrawals_sum = await self.get_deposit_withdrawal_totals(user_id)
        net_deposits = deposits_sum - withdrawals_sum

        realized_so_far = Decimal(str(user.realized_pnl_usd or 0))
        unrealized_pnl = total_portfolio_value_mtm - net_deposits - realized_so_far

        # Percentage based on net deposits
        if net_deposits > 0:
            unrealized_pnl_percentage = (unrealized_pnl / net_deposits) * Decimal(100)
        else:
            unrealized_pnl_percentage = Decimal(0)

        user.unrealized_pnl_usd = unrealized_pnl
        user.unrealized_pnl_pct = unrealized_pnl_percentage
        user.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        logger.info(
            f"Updated unrealized PnL for user {user_id}: ${unrealized_pnl} (mtm) ({unrealized_pnl_percentage:.2f}%)"
        )
    
    async def recalculate_user_pnl(self, user_id: str) -> None:
        """Recalculate and update user's PnL values.
        
        PNL is calculated as:
        - Realized PNL: Sum of PnL from all CLOSED positions
        - Unrealized PNL: Sum of PnL from all ACTIVE positions
        
        This should be called after:
        - Position is closed
        - Position is opened
        - Position value is updated
        - Deposits/Withdrawals
        """
        from app.core.positions_service import positions_service
        from sqlalchemy import select, and_, or_
        from app.database.models import Transaction
        
        # Get user to fetch totals from the database
        stmt = select(User).where(User.user_id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(f"User {user_id} not found for PnL calculation")
            return
        
        # Get deposits and withdrawals for percentage calculations
        total_deposits, total_withdrawals = await self.get_deposit_withdrawal_totals(user_id)
        
        # Get all positions
        all_positions = await self.get_user_positions(user_id)
        active_positions = [p for p in all_positions if p.status == 'ACTIVE']
        closed_positions = [p for p in all_positions if p.status == 'CLOSED']
        
        # =================================================================
        # REALIZED PNL: Sum of PnL from all CLOSED positions
        # =================================================================
        realized_pnl = Decimal(0)
        for position in closed_positions:
            # For closed positions, calculate PnL as exit value - entry value
            exit_value = position.current_value_usdc or Decimal(0)
            entry_value = position.entry_amount_usdc or Decimal(0)
            position_pnl = exit_value - entry_value
            realized_pnl += position_pnl
            logger.debug(f"Closed position {position.nft_token_id}: entry={entry_value}, exit={exit_value}, pnl={position_pnl}")
        
        # =================================================================
        # UNREALIZED PNL: Sum of PnL from all ACTIVE positions  
        # =================================================================
        total_unrealized_pnl = Decimal(0)
        
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
                    
                    # Calculate unrealized PnL for this position
                    entry_value = position.entry_amount_usdc or Decimal(0)
                    position_unrealized_pnl = position_current_value - entry_value
                    total_unrealized_pnl += position_unrealized_pnl
                    
                    logger.debug(f"Active position {position.nft_token_id}: entry={entry_value}, current={position_current_value}, unrealized_pnl={position_unrealized_pnl}")
                else:
                    # Use cached values if blockchain fetch fails
                    cached_value = position.current_value_usdc or position.entry_amount_usdc or Decimal(0)
                    entry_value = position.entry_amount_usdc or Decimal(0)
                    position_unrealized_pnl = cached_value - entry_value
                    total_unrealized_pnl += position_unrealized_pnl
                    
            except Exception as e:
                logger.error(f"Error fetching position {position.nft_token_id}: {e}")
                # Use database values as fallback
                cached_value = position.current_value_usdc or position.entry_amount_usdc or Decimal(0)
                entry_value = position.entry_amount_usdc or Decimal(0)
                position_unrealized_pnl = cached_value - entry_value
                total_unrealized_pnl += position_unrealized_pnl
        
        # Commit any position value updates
        await self.db.commit()
        
        # Calculate net deposits (deposits - withdrawals) for percentage calculations
        net_deposits = total_deposits - total_withdrawals

        logger.info(
            f"PNL for {user_id}: "
            f"realized={realized_pnl:.2f} (from {len(closed_positions)} closed positions), "
            f"unrealized={total_unrealized_pnl:.2f} (from {len(active_positions)} active positions)"
        )
        
        # Calculate percentage returns
        # For realized: based on total deposits if we have deposits
        realized_pnl_percentage = Decimal(0)
        if total_deposits > 0:
            realized_pnl_percentage = (realized_pnl / total_deposits) * 100
        
        # For unrealized: based on net deposits (deposits - withdrawals) if positive
        unrealized_pnl_percentage = Decimal(0)
        if net_deposits > 0:
            unrealized_pnl_percentage = (total_unrealized_pnl / net_deposits) * 100
        
        # Update user PnL values
        await self.update_user_pnl(
            user_id=user_id,
            unrealized_pnl=total_unrealized_pnl,
            realized_pnl=realized_pnl,
            unrealized_pnl_percentage=unrealized_pnl_percentage,
            realized_pnl_percentage=realized_pnl_percentage
        )
        
        logger.info(f"Updated PNL for user {user_id}: realized={realized_pnl:.2f} ({realized_pnl_percentage:.2f}%), unrealized={total_unrealized_pnl:.2f} ({unrealized_pnl_percentage:.2f}%)")
    
    async def recalculate_user_pnl_for_period(self, user_id: str, period: TimePeriod = TimePeriod.ALL_TIME) -> Dict[str, Decimal]:
        """Recalculate and return user's PnL values for a specific time period.
        
        PNL is calculated as:
        - Realized PNL: Sum of PnL from positions CLOSED within the period
        - Unrealized PNL: Sum of PnL from positions CREATED within the period and still ACTIVE
        
        Args:
            user_id: User identifier
            period: Time period to calculate PnL for (24h, 7d, 30d, all)
        
        Returns:
            Dictionary with PnL values for the period
        """
        from app.core.positions_service import positions_service
        from sqlalchemy import select, and_, or_
        from app.database.models import Transaction
        
        # Get user
        stmt = select(User).where(User.user_id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(f"User {user_id} not found for PnL calculation")
            return {}
        
        # Calculate time boundary based on period
        now = datetime.now(timezone.utc)
        if period == TimePeriod.DAY_1:
            time_boundary = now - timedelta(days=1)
        elif period == TimePeriod.DAY_7:
            time_boundary = now - timedelta(days=7)
        elif period == TimePeriod.DAY_30:
            time_boundary = now - timedelta(days=30)
        else:  # ALL_TIME
            time_boundary = None
        
        # Get all positions
        all_positions = await self.get_user_positions(user_id)
        
        # Filter positions based on period
        if time_boundary:
            # For closed positions: include if closed within the period
            closed_positions = [
                p for p in all_positions 
                if p.status == 'CLOSED' and p.closed_at and p.closed_at >= time_boundary
            ]
            
            # For active positions: include if created within the period
            active_positions = [
                p for p in all_positions 
                if p.status == 'ACTIVE' and p.created_at and p.created_at >= time_boundary
            ]
        else:
            # All time - include all positions
            closed_positions = [p for p in all_positions if p.status == 'CLOSED']
            active_positions = [p for p in all_positions if p.status == 'ACTIVE']
        
        # Get deposits and withdrawals for the period for percentage calculations
        total_deposits = Decimal(0)
        total_withdrawals = Decimal(0)
        
        if time_boundary:
            # Get deposits for the period
            deposit_stmt = select(Transaction).where(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.tx_type == 'DEPOSIT',
                    Transaction.status == 'CONFIRMED',
                    Transaction.created_at >= time_boundary
                )
            )
            deposit_result = await self.db.execute(deposit_stmt)
            deposits = deposit_result.scalars().all()
            total_deposits = sum(Decimal(str(t.amount_usdc)) for t in deposits)
            
            # Get withdrawals for the period
            withdrawal_stmt = select(Transaction).where(
                and_(
                    Transaction.user_id == user_id,
                    or_(Transaction.tx_type == 'WITHDRAWAL', Transaction.tx_type == 'WITHDRAW'),
                    Transaction.status == 'CONFIRMED',
                    Transaction.created_at >= time_boundary
                )
            )
            withdrawal_result = await self.db.execute(withdrawal_stmt)
            withdrawals = withdrawal_result.scalars().all()
            total_withdrawals = sum(Decimal(str(t.amount_usdc)) for t in withdrawals)
        else:
            # All time - get all deposits and withdrawals
            total_deposits, total_withdrawals = await self.get_deposit_withdrawal_totals(user_id)
        
        # =================================================================
        # REALIZED PNL: Sum of PnL from positions CLOSED within the period
        # =================================================================
        realized_pnl = Decimal(0)
        for position in closed_positions:
            # For closed positions, calculate PnL as exit value - entry value
            exit_value = position.current_value_usdc or Decimal(0)
            entry_value = position.entry_amount_usdc or Decimal(0)
            position_pnl = exit_value - entry_value
            realized_pnl += position_pnl
            logger.debug(f"Closed position {position.nft_token_id} (period {period}): entry={entry_value}, exit={exit_value}, pnl={position_pnl}")
        
        # =================================================================
        # UNREALIZED PNL: Sum of PnL from positions CREATED within period and still ACTIVE
        # =================================================================
        total_unrealized_pnl = Decimal(0)
        
        for position in active_positions:
            try:
                # Fetch real-time value from blockchain
                position_info = await positions_service.get_position_by_id(position.nft_token_id)
                
                if position_info:
                    current_value_usd = Decimal(str(position_info.current_value_usd or 0))
                    unclaimed_fees_usd = Decimal(str(position_info.unclaimed_fees_usd or 0))
                    
                    # Calculate total current value
                    position_current_value = current_value_usd + unclaimed_fees_usd
                    
                    # Calculate unrealized PnL for this position
                    entry_value = position.entry_amount_usdc or Decimal(0)
                    position_unrealized_pnl = position_current_value - entry_value
                    total_unrealized_pnl += position_unrealized_pnl
                    
                    logger.debug(f"Active position {position.nft_token_id} (period {period}): entry={entry_value}, current={position_current_value}, unrealized_pnl={position_unrealized_pnl}")
                else:
                    # Use cached values if blockchain fetch fails
                    cached_value = position.current_value_usdc or position.entry_amount_usdc or Decimal(0)
                    entry_value = position.entry_amount_usdc or Decimal(0)
                    position_unrealized_pnl = cached_value - entry_value
                    total_unrealized_pnl += position_unrealized_pnl
                    
            except Exception as e:
                logger.error(f"Error fetching position {position.nft_token_id}: {e}")
                # Use database values as fallback
                cached_value = position.current_value_usdc or position.entry_amount_usdc or Decimal(0)
                entry_value = position.entry_amount_usdc or Decimal(0)
                position_unrealized_pnl = cached_value - entry_value
                total_unrealized_pnl += position_unrealized_pnl
        
        # Calculate net deposits for percentage calculations
        net_deposits = total_deposits - total_withdrawals
        
        # Calculate percentage returns
        realized_pnl_percentage = Decimal(0)
        if total_deposits > 0:
            realized_pnl_percentage = (realized_pnl / total_deposits) * 100
        
        unrealized_pnl_percentage = Decimal(0)
        if net_deposits > 0:
            unrealized_pnl_percentage = (total_unrealized_pnl / net_deposits) * 100
        
        # Calculate total fees and rewards from filtered positions
        all_filtered_positions = closed_positions + active_positions
        total_fees_earned = sum(p.fees_earned_usdc or Decimal(0) for p in all_filtered_positions)
        total_rewards_earned = sum(p.rewards_earned_usdc or Decimal(0) for p in all_filtered_positions)
        
        # Get protocol fees pending from filtered positions
        protocol_fees_pending = sum(
            p.protocol_fee_amount for p in all_filtered_positions 
            if p.protocol_fee_amount and not p.protocol_fee_collected
        )
        
        # Calculate total PnL (realized + unrealized)
        total_pnl = realized_pnl + total_unrealized_pnl
        
        # Net PnL after protocol fees
        net_pnl = total_pnl - protocol_fees_pending
        
        logger.info(
            f"PNL for {user_id} (period {period}): "
            f"realized={realized_pnl:.2f} ({realized_pnl_percentage:.2f}%), "
            f"unrealized={total_unrealized_pnl:.2f} ({unrealized_pnl_percentage:.2f}%)"
        )
        
        return {
            "realized_pnl_usdc": realized_pnl,
            "unrealized_pnl_usdc": total_unrealized_pnl,
            "unrealized_pnl_percentage": unrealized_pnl_percentage,
            "unrealized_pnl_pct": unrealized_pnl_percentage,  # Alias
            "realized_pnl_percentage": realized_pnl_percentage,
            "fees_earned_usdc": total_fees_earned,
            "rewards_earned_usdc": total_rewards_earned,
            "total_pnl_usdc": total_pnl,
            "protocol_fees_pending_usdc": protocol_fees_pending,
            "net_pnl_usdc": net_pnl,
            "period": period,
            "active_positions_count": len(active_positions),
            "closed_positions_count": len(closed_positions)
        }
    
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
