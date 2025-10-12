from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import uuid
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, or_, func, case, Numeric
from sqlalchemy.orm import selectinload

from app.database.models import User, Transaction, Position
# WalletTransaction removed - using transactions table instead
from app.schemas.users import TransactionType, TransactionStatus, PositionStatus, TimePeriod
from app.core.logger import logger
from app.core.positions_service import positions_service
from app.services.agent_management_service import get_agent_service
from app.core.blockchain_service import blockchain_service
from app.core.config import settings


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
                cdp_wallet_address=cdp_wallet_address
            )
            # Set agent status and wallet name through user_metadata
            user.agent_status = 'not_started'
            if cdp_wallet_name:
                if not user.user_metadata:
                    user.user_metadata = {}
                user.user_metadata['cdp_wallet_name'] = cdp_wallet_name
            
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

            # Get amount from event_data (amount_usdc column is deprecated)
            amt = Decimal(str(tx.event_data.get('amount_usdc', 0)))

            # The event_data doesn't have from_address/to_address fields
            # For deposits and withdrawals categorized by wallet_transaction_service,
            # we can trust the tx_type since it's already validated
            if tx.tx_type == 'DEPOSIT':
                deposits += amt
            elif tx.tx_type in ['WITHDRAWAL', 'WITHDRAW']:
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
        
        now = datetime.now(timezone.utc)
        transaction = Transaction(
            user_id=user_id,
            tx_type=tx_type_value,
            tx_hash=tx_hash,
            status=TransactionStatus.PENDING,
            tx_metadata=tx_metadata,
            event_data={'amount_usdc': float(amount_usdc)} if amount_usdc else {},
            block_timestamp=now,  # Set block_timestamp for proper ordering
            created_at=now
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
        """Get user transactions with optional filters, including CDP wallet transactions."""
        # First get transactions from the main Transaction table
        stmt = select(Transaction).where(Transaction.user_id == user_id)

        # Filter out deprecated transaction types (STAKING, SWAP, FEE_TRANSFER)
        stmt = stmt.where(Transaction.tx_type.not_in(['STAKING', 'SWAP', 'FEE_TRANSFER']))

        if transaction_type:
            # Use the enum value directly - it should match the database
            tx_type_value = transaction_type.value if hasattr(transaction_type, 'value') else str(transaction_type)
            stmt = stmt.where(Transaction.tx_type == tx_type_value)
        if status:
            stmt = stmt.where(Transaction.status == status)

        # Order by block_timestamp for true chronological ordering
        # Use COALESCE to handle nulls (though all should have block_timestamp)
        if sort_order.lower() == "asc":
            # Oldest first
            stmt = stmt.order_by(
                func.coalesce(Transaction.block_timestamp, Transaction.created_at).asc()
            )
        else:
            # Newest first (default)
            stmt = stmt.order_by(
                func.coalesce(Transaction.block_timestamp, Transaction.created_at).desc()
            )

        # Execute regular transactions query
        result = await self.db.execute(stmt)
        transactions = list(result.scalars().all())

        # Note: CDP wallet transactions are now stored directly in the transactions table
        # with appropriate tx_type instead of a separate WalletTransaction table

        # Apply limit and offset to results
        return transactions[offset:offset + limit]
    
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
        withdraw_all: bool = False
    ) -> Transaction:
        """Process USDC withdrawal for user.

        Withdrawals always:
        - Go to the user_id address (no destination_address parameter)
        - Force close positions if needed (hardcoded to True)
        - Use 0.1% max slippage (hardcoded)
        - Execute through agent manager (no manual tx_hash)

        Args:
            user_id: The user's wallet address (used as both ID and destination)
            amount: Amount of USDC to withdraw
            withdraw_all: Whether to withdraw entire available balance
        """
        # Hardcoded parameters
        FORCE_CLOSE_POSITIONS = True
        MAX_SLIPPAGE_PERCENT = Decimal("0.1")
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
        
        # If wallet balance is insufficient, always try to close positions (force_close_positions is always True)
        if wallet_balance < amount:
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
            
            # Skip validation if withdraw_all is True - we want to withdraw everything
            if not withdraw_all and expected_balance < amount:
                raise ValueError(f"Insufficient funds even with positions. Expected: {expected_balance}, Requested: {amount}")
        
        # Always execute withdrawal through agent manager
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

            # Request withdrawal through agent (destination is always user_id)
            result = await agent_service.withdraw_usdc(
                user_id=user_id,
                amount=float(amount),
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
        now = datetime.now(timezone.utc)
        transaction = Transaction(
            id=uuid.uuid4(),
            user_id=user_id,
            tx_type='WITHDRAW',  # Changed from WITHDRAWAL to match schema
            tx_hash=tx_hash,
            status='CONFIRMED',  # Always CONFIRMED since we wait for tx_hash from agent
            event_data={
                'amount_usdc': float(amount),
                'to_address': user_id  # Always withdraw to user's own address
            },
            block_timestamp=now,  # Set block_timestamp for proper ordering
            created_at=now
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
            fee_msg = " A 5% protocol fee applies to AERO rewards."
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
            logger.warning(
                "Recorded balance below entry amount for user {} (available={}, required={}); "
                "proceeding because on-chain balance is authoritative.",
                user_id,
                current_balance,
                entry_amount_usdc,
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
            entry_date=datetime.utcnow()
        )
        
        # Create transaction record for position entry (debit)
        now = datetime.now(timezone.utc)
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
            block_timestamp=now,  # Set block_timestamp for proper ordering
            confirmed_at=now
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

        # updated_at will be set automatically by SQLAlchemy onupdate

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
            # updated_at will be set automatically by SQLAlchemy onupdate
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
        
        now = datetime.now(timezone.utc)
        transaction = Transaction(
            id=uuid.uuid4(),  # Ensure we have a primary key
            user_id=user_id,
            tx_type='POSITION_CLOSED',  # Direct string since we're not using the enum here
            tx_hash=exit_tx_hash,
            status='CONFIRMED',  # Fixed to uppercase for consistency
            tx_metadata=tx_metadata,
            event_data={'amount_usdc': float(amount_returned)},
            block_timestamp=now,  # Set block_timestamp for proper ordering
            processed_at=now,
            created_at=now
        )
        
        self.db.add(transaction)
        await self.db.commit()
        await self.db.refresh(position)
        await self.db.refresh(transaction)
        
        # Recalculate user PnL after closing position
        await self.recalculate_user_pnl(user_id)
        
        # Log the transaction details for debugging
        logger.info(f"Created POSITION_CLOSED transaction: id={transaction.id}, amount={float(amount_returned)}, status={transaction.status}")

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

        Uses the SimplePeriodPnLCalculator for proper period-based calculations that:
        - Considers all positions active during the period (not just opened/closed)
        - Uses average invested capital as the denominator for percentages
        - Provides meaningful metrics that avoid impossible percentage values

        Args:
            user_id: User identifier
            period: Time period to calculate PnL for (24h, 7d, 30d, all)

        Returns:
            Dictionary with PnL values for the period
        """
        from app.services.period_pnl_calculator import SimplePeriodPnLCalculator

        # Use the new period PNL calculator for proper calculations
        calculator = SimplePeriodPnLCalculator(self.db)
        pnl_result = await calculator.calculate_period_pnl(user_id, period)

        # Map the results to maintain backwards compatibility with existing API
        # The new calculator provides more accurate calculations that avoid impossible percentages
        return {
            "realized_pnl_usdc": pnl_result.get("realized_pnl_usdc", Decimal(0)),
            "unrealized_pnl_usdc": pnl_result.get("unrealized_pnl_usdc", Decimal(0)),
            "fees_earned_usdc": pnl_result.get("fees_earned_usdc", Decimal(0)),
            "rewards_earned_usdc": pnl_result.get("rewards_earned_usdc", Decimal(0)),
            "total_pnl_usdc": pnl_result.get("total_pnl_usdc", Decimal(0)),
            "total_pnl_percentage": pnl_result.get("total_pnl_percentage", Decimal(0)),
            "net_deposits": pnl_result.get("net_deposits", Decimal(0)),
            "average_invested": pnl_result.get("average_invested", Decimal(0)),
            # Additional fields for API compatibility
            "realized_pnl_percentage": Decimal(0),  # Will be calculated in the endpoint
            "unrealized_pnl_percentage": Decimal(0),  # Will be calculated in the endpoint
            "unrealized_pnl_pct": Decimal(0),  # Will be calculated in the endpoint
            "protocol_fees_pending_usdc": Decimal(0),
            "net_pnl_usdc": pnl_result.get("total_pnl_usdc", Decimal(0)),
            "active_positions_count": 0  # Will be calculated separately if needed
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
                # Strategy monitoring removed - using direct position data instead
                from app.core.positions_service import positions_service

                # Fetch actual position data for values
                positions_data = await positions_service.get_positions_by_owner(user.cdp_wallet_address)

                # Calculate weighted average APR directly from pool data
                total_value = 0
                weighted_apr_sum = 0

                from app.core.pools_service import pools_service
                for pos_data in positions_data:
                    if pos_data.current_value_usd and hasattr(pos_data, 'pool_address'):
                        try:
                            pool_info = await pools_service.get_pool_info(pos_data.pool_address)
                            if pool_info:
                                position_value = pos_data.current_value_usd
                                pool_apr = pool_info.get('apr_7d', 0)
                                total_value += position_value
                                weighted_apr_sum += position_value * pool_apr
                        except:
                            pass

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

    async def sync_blockchain_data(self, user_id: str) -> Dict[str, Any]:
        """Sync user's blockchain data (transactions and positions) with database.

        This should be called by all endpoints to ensure DB is up-to-date with onchain state.

        Uses smart rate limiting: skips sync if user was synced within the last 15 seconds.

        Args:
            user_id: User identifier

        Returns:
            Dict with sync results (transactions_synced, positions_created, etc.)
        """
        from app.core.cache import cache_manager

        # Check if we should skip sync due to rate limiting
        if await cache_manager.should_skip_sync(user_id):
            # Return cached result if available
            cached_result = await cache_manager.get_cached_sync_result(user_id)
            if cached_result:
                logger.debug(f"Skipping sync for {user_id} - synced {cached_result.get('seconds_ago', '?')}s ago")
                return cached_result

            # If no cached result, return minimal success result
            logger.debug(f"Skipping sync for {user_id} - recently synced")
            return {
                "transactions_synced": 0,
                "positions_created": 0,
                "positions_updated": 0,
                "success": True,
                "skipped": True
            }

        sync_result = {
            "transactions_synced": 0,
            "positions_created": 0,
            "positions_updated": 0,
            "success": False
        }

        try:
            # Get user with CDP wallet
            user = await self.get_user(user_id)
            if not user or not user.cdp_wallet_address:
                logger.warning(f"User {user_id} has no CDP wallet for sync")
                return sync_result

            # Only sync if CDP API key is configured
            if not settings.cdp_client_api_key:
                logger.debug("CDP API key not configured, skipping blockchain sync")
                return sync_result

            # Import here to avoid circular dependency
            from app.services.wallet_transaction_service import WalletTransactionService

            # Sync transactions from blockchain
            wallet_service = WalletTransactionService(self.db)

            # Fetch and sync transactions
            tx_result = await wallet_service.fetch_and_sync_transactions(
                user_id=user_id,
                cdp_wallet_address=user.cdp_wallet_address,
                limit=100  # Sync last 100 transactions
            )

            sync_result["transactions_synced"] = tx_result.get("transactions_synced", 0)

            # Ensure positions exist for all POSITION_CREATED transactions
            positions_result = await wallet_service.ensure_positions_for_transactions(user_id)
            sync_result["positions_created"] = positions_result.get("positions_created", 0) if positions_result else 0

            # Update position values from blockchain
            positions = await self.get_user_positions(user_id, status=PositionStatus.ACTIVE)
            positions_updated = 0

            for position in positions:
                try:
                    # Get current value from blockchain
                    position_info = await positions_service.get_position_by_id(position.token_id)

                    if position_info and position_info.current_value_usd:
                        await self.update_position_value(
                            nft_token_id=position.token_id,
                            current_value_usdc=Decimal(str(position_info.current_value_usd)),
                            unrealized_pnl_usdc=Decimal("0"),  # Not available in PositionInfo
                            fees_earned_usdc=Decimal(str(position_info.unclaimed_fees_usd or 0)),
                            rewards_earned_usdc=Decimal("0")  # Rewards are in AERO, not USD
                        )
                        positions_updated += 1
                except Exception as e:
                    logger.warning(f"Failed to update position {position.token_id}: {e}")

            sync_result["positions_updated"] = positions_updated
            sync_result["success"] = True

            # Recalculate deployed capital from active positions
            await self._recalculate_deployed_capital(user_id)

            # Mark sync as completed and cache the result
            await cache_manager.mark_sync_completed(user_id)
            await cache_manager.cache_sync_result(user_id, sync_result)

            logger.info(f"Blockchain sync for {user_id}: {sync_result}")

        except Exception as e:
            logger.error(f"Error syncing blockchain data for {user_id}: {e}")
            sync_result["error"] = str(e)

        return sync_result

    async def _recalculate_deployed_capital(self, user_id: str) -> None:
        """
        Recalculate deployed_capital_usd for each active strategy based on actual positions.

        This is called after blockchain sync to ensure capital tracking stays accurate.
        It infers which strategy owns each position based on pool address.

        Args:
            user_id: User wallet address
        """
        from app.schemas.strategy import infer_strategy_from_pool
        from sqlalchemy.orm import attributes

        try:
            # Get user with active strategies
            user = await self.get_user(user_id)
            if not user or not user.active_strategies:
                return

            # Get all active positions
            active_positions = await self.get_user_positions(user_id, status=PositionStatus.ACTIVE)

            # Calculate deployed capital per strategy
            deployed_by_strategy = {}

            for position in active_positions:
                # Use stored strategy_type if available, otherwise infer from pool
                strategy_code = position.strategy_type

                if not strategy_code:
                    # Fallback: infer strategy from pool address
                    strategy_code = infer_strategy_from_pool(
                        position.pool_address,
                        user.active_strategies
                    )

                    # Store inferred strategy_type for future syncs
                    if strategy_code:
                        position.strategy_type = strategy_code
                        logger.info(
                            f"Inferred and stored strategy_type={strategy_code} for position {position.token_id}"
                        )

                if strategy_code and strategy_code in user.active_strategies:
                    # Use entry_amount_usdc as the deployed capital for this position
                    deployed_amount = position.entry_amount_usdc or Decimal(0)
                    deployed_by_strategy[strategy_code] = deployed_by_strategy.get(strategy_code, Decimal(0)) + deployed_amount

            # Update deployed_capital_usd for each active strategy
            for strategy_code, strategy_info in user.active_strategies.items():
                new_deployed = float(deployed_by_strategy.get(strategy_code, Decimal(0)))
                old_deployed = strategy_info.get('deployed_capital_usd', 0.0)

                if new_deployed != old_deployed:
                    strategy_info['deployed_capital_usd'] = new_deployed
                    strategy_info['updated_at'] = datetime.utcnow().isoformat()
                    logger.info(
                        f"Recalculated deployed capital for {user_id}/{strategy_code}: "
                        f"{old_deployed} -> {new_deployed}"
                    )

            # Mark JSONB field as modified
            attributes.flag_modified(user, 'active_strategies')
            await self.db.commit()

        except Exception as e:
            logger.error(f"Error recalculating deployed capital for {user_id}: {e}")
