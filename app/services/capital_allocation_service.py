"""Service for managing per-strategy capital allocation and tracking."""

from decimal import Decimal
from datetime import datetime
from typing import Optional, Tuple, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, text
from sqlalchemy.orm import attributes
from loguru import logger

from app.database.models import User
from app.schemas.capital import PositionEventRequest


class CapitalAllocationService:
    """Service for capital allocation tracking and enforcement."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def calculate_available_capital(
        self,
        user_id: str,
        strategy_code: str
    ) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
        """
        Calculate available capital for a strategy.

        Args:
            user_id: User wallet address
            strategy_code: Strategy short code (e.g., 'h3', 's1')

        Returns:
            Tuple of (allocated, deployed, available, wallet_balance)

        Raises:
            ValueError: If user not found or strategy not active
        """
        # Get user with active_strategies
        stmt = select(User).where(User.user_id == user_id).with_for_update()
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise ValueError(f"User {user_id} not found")

        if not user.active_strategies or strategy_code not in user.active_strategies:
            raise ValueError(f"Strategy {strategy_code} is not active for user {user_id}")

        strategy_info = user.active_strategies[strategy_code]

        # Extract capital allocation info
        allocated = Decimal(str(strategy_info.get('allocated_capital_usd', 0)))
        deployed = Decimal(str(strategy_info.get('deployed_capital_usd', 0)))
        available = allocated - deployed

        # Get wallet balance (stored in user.usdc_balance)
        wallet_balance = Decimal(str(user.usdc_balance or 0))

        logger.debug(
            f"Capital for {user_id}/{strategy_code}: "
            f"allocated={allocated}, deployed={deployed}, "
            f"available={available}, wallet={wallet_balance}"
        )

        return allocated, deployed, available, wallet_balance

    async def update_deployed_capital(
        self,
        user_id: str,
        strategy_code: str,
        delta: Decimal,
        tx_hash: str
    ) -> Tuple[Decimal, Decimal]:
        """
        Update deployed capital for a strategy.

        Args:
            user_id: User wallet address
            strategy_code: Strategy short code
            delta: Change in deployed capital (positive = increase, negative = decrease)
            tx_hash: Transaction hash for idempotency

        Returns:
            Tuple of (new_deployed, new_available)

        Raises:
            ValueError: If update would result in negative deployed capital
        """
        # Check for duplicate tx_hash (idempotency)
        check_dup = await self.db.execute(
            text("SELECT 1 FROM strategy_positions WHERE tx_hash = :tx_hash"),
            {"tx_hash": tx_hash}
        )
        if check_dup.scalar_one_or_none():
            logger.warning(f"Duplicate tx_hash {tx_hash}, skipping update (idempotent)")
            # Return current values without updating
            allocated, deployed, available, _ = await self.calculate_available_capital(user_id, strategy_code)
            return deployed, available

        # Get user with row lock
        stmt = select(User).where(User.user_id == user_id).with_for_update()
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise ValueError(f"User {user_id} not found")

        if not user.active_strategies or strategy_code not in user.active_strategies:
            raise ValueError(f"Strategy {strategy_code} is not active for user {user_id}")

        # Get current values
        strategy_info = user.active_strategies[strategy_code]
        allocated = Decimal(str(strategy_info.get('allocated_capital_usd', 0)))
        current_deployed = Decimal(str(strategy_info.get('deployed_capital_usd', 0)))

        # Calculate new deployed amount
        new_deployed = current_deployed + delta

        # Validate: deployed capital cannot go negative
        if new_deployed < 0:
            raise ValueError(
                f"Cannot decrease deployed capital below zero. "
                f"Current: {current_deployed}, delta: {delta}, would result in: {new_deployed}"
            )

        # Update deployed_capital_usd in active_strategies
        strategy_info['deployed_capital_usd'] = float(new_deployed)
        strategy_info['updated_at'] = datetime.utcnow().isoformat()

        # Mark JSONB field as modified for SQLAlchemy
        attributes.flag_modified(user, 'active_strategies')

        # Calculate new available
        new_available = allocated - new_deployed

        logger.info(
            f"Updated deployed capital for {user_id}/{strategy_code}: "
            f"{current_deployed} -> {new_deployed} (delta: {delta}), "
            f"available: {new_available}"
        )

        await self.db.commit()

        return new_deployed, new_available

    async def record_position_event(
        self,
        user_id: str,
        strategy_code: str,
        event: PositionEventRequest
    ) -> Tuple[Decimal, Decimal]:
        """
        Record a position lifecycle event and update deployed capital.

        Args:
            user_id: User wallet address
            strategy_code: Strategy short code
            event: Position event data

        Returns:
            Tuple of (new_deployed, new_available)

        Raises:
            ValueError: If event data is invalid or update fails
        """
        if event.type == "opened":
            if not event.capital_deployed_usd:
                raise ValueError("capital_deployed_usd required for 'opened' event")

            # Create strategy_positions record
            await self.db.execute(
                text("""
                    INSERT INTO strategy_positions (
                        user_id, strategy_code, token_id, capital_deployed_usd,
                        opened_at, tx_hash
                    ) VALUES (
                        :user_id, :strategy_code, :token_id, :capital_deployed_usd,
                        :opened_at, :tx_hash
                    )
                    ON CONFLICT (tx_hash) DO NOTHING
                """),
                {
                    "user_id": user_id,
                    "strategy_code": strategy_code,
                    "token_id": event.token_id,
                    "capital_deployed_usd": event.capital_deployed_usd,
                    "opened_at": event.timestamp,
                    "tx_hash": event.tx_hash
                }
            )

            # Increase deployed capital
            delta = event.capital_deployed_usd

        elif event.type == "closed":
            if not event.capital_returned_usd:
                raise ValueError("capital_returned_usd required for 'closed' event")

            # Get original deployed amount from strategy_positions
            result = await self.db.execute(
                text("""
                    SELECT capital_deployed_usd
                    FROM strategy_positions
                    WHERE token_id = :token_id AND user_id = :user_id
                """),
                {"token_id": event.token_id, "user_id": user_id}
            )
            row = result.first()

            if not row:
                logger.warning(
                    f"Position {event.token_id} not found in strategy_positions, "
                    f"using capital_returned_usd as fallback"
                )
                original_deployed = event.capital_returned_usd
            else:
                original_deployed = Decimal(str(row[0]))

            # Update strategy_positions record
            await self.db.execute(
                text("""
                    UPDATE strategy_positions
                    SET capital_returned_usd = :capital_returned,
                        closed_at = :closed_at,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE token_id = :token_id AND user_id = :user_id
                """),
                {
                    "token_id": event.token_id,
                    "user_id": user_id,
                    "capital_returned": event.capital_returned_usd,
                    "closed_at": event.timestamp
                }
            )

            # Decrease deployed capital by ORIGINAL amount (not returned amount)
            # This is critical: PnL should not affect allocation tracking
            delta = -original_deployed

        elif event.type == "rebalanced":
            if event.capital_change_usd is None:
                raise ValueError("capital_change_usd required for 'rebalanced' event")

            # Update strategy_positions record
            await self.db.execute(
                text("""
                    UPDATE strategy_positions
                    SET capital_deployed_usd = capital_deployed_usd + :delta,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE token_id = :token_id AND user_id = :user_id
                """),
                {
                    "token_id": event.token_id,
                    "user_id": user_id,
                    "delta": event.capital_change_usd
                }
            )

            delta = event.capital_change_usd

        else:
            raise ValueError(f"Invalid event type: {event.type}")

        # Update deployed capital in active_strategies
        new_deployed, new_available = await self.update_deployed_capital(
            user_id, strategy_code, delta, event.tx_hash
        )

        return new_deployed, new_available

    async def validate_allocation_change(
        self,
        user_id: str,
        strategy_code: str,
        new_allocation: Decimal
    ) -> None:
        """
        Validate that a new allocation is valid.

        Args:
            user_id: User wallet address
            strategy_code: Strategy short code
            new_allocation: New allocation amount

        Raises:
            ValueError: If allocation is invalid
        """
        if new_allocation <= 0:
            raise ValueError("Allocation must be positive")

        # Get current deployed capital
        _, deployed, _, _ = await self.calculate_available_capital(user_id, strategy_code)

        # Cannot reduce allocation below deployed capital
        if new_allocation < deployed:
            raise ValueError(
                f"Cannot set allocation to ${new_allocation} when ${deployed} "
                f"is already deployed. Close positions first."
            )

    async def update_allocation(
        self,
        user_id: str,
        strategy_code: str,
        new_allocation: Decimal
    ) -> Tuple[Decimal, Decimal, Decimal]:
        """
        Update allocated capital for a strategy.

        Args:
            user_id: User wallet address
            strategy_code: Strategy short code
            new_allocation: New allocation amount

        Returns:
            Tuple of (new_allocated, current_deployed, new_available)

        Raises:
            ValueError: If allocation is invalid
        """
        # Validate first
        await self.validate_allocation_change(user_id, strategy_code, new_allocation)

        # Get user with row lock
        stmt = select(User).where(User.user_id == user_id).with_for_update()
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise ValueError(f"User {user_id} not found")

        if not user.active_strategies or strategy_code not in user.active_strategies:
            raise ValueError(f"Strategy {strategy_code} is not active for user {user_id}")

        # Update allocation
        strategy_info = user.active_strategies[strategy_code]
        deployed = Decimal(str(strategy_info.get('deployed_capital_usd', 0)))

        strategy_info['allocated_capital_usd'] = float(new_allocation)
        strategy_info['updated_at'] = datetime.utcnow().isoformat()

        # Mark JSONB field as modified
        attributes.flag_modified(user, 'active_strategies')

        await self.db.commit()

        new_available = new_allocation - deployed

        logger.info(
            f"Updated allocation for {user_id}/{strategy_code}: "
            f"allocated={new_allocation}, deployed={deployed}, available={new_available}"
        )

        return new_allocation, deployed, new_available


# Singleton pattern for easy access
def get_capital_allocation_service(db: AsyncSession) -> CapitalAllocationService:
    """Get capital allocation service instance."""
    return CapitalAllocationService(db)
