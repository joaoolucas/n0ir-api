"""Service for managing user trading strategies using relational user_strategies table."""

from decimal import Decimal
from datetime import datetime
from typing import Optional, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update
from sqlalchemy.orm import attributes
from loguru import logger

from app.database.models import User, UserStrategy
from app.schemas.strategy import StrategyTypeEnum, STRATEGY_SHORT_CODES


# Reverse mapping: short code -> full type
CODE_TO_STRATEGY_TYPE = {v: k for k, v in {
    "hedged_weth_only": "h1",
    "hedged_cbbtc_only": "h2",
    "nonhedged_weth_only": "n1",
    "nonhedged_cbbtc_only": "n2",
    "nonhedged_cbltc_cbbtc": "n3",
    "nonhedged_cbada_cbbtc": "n4",
    "nonhedged_cbxrp_cbbtc": "n5",
    "nonhedged_cbdoge_cbbtc": "n6",
    "stable_usdc_eurc": "s1",
    "stable_usdc_msusd": "s2",
}.items()}


class StrategyService:
    """Service for CRUD operations on user strategies."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_strategies(self, user_id: str) -> List[UserStrategy]:
        """
        Get all active strategies for a user.

        Args:
            user_id: User wallet address

        Returns:
            List of active UserStrategy objects
        """
        stmt = select(UserStrategy).where(
            and_(
                UserStrategy.user_id == user_id,
                UserStrategy.status == 'active'
            )
        )
        result = await self.db.execute(stmt)
        strategies = result.scalars().all()

        logger.debug(f"Found {len(strategies)} active strategies for user {user_id}")
        return list(strategies)

    async def get_active_strategies_dict(self, user_id: str) -> Dict[str, dict]:
        """
        Get active strategies as dictionary matching JSONB format.

        Args:
            user_id: User wallet address

        Returns:
            Dict mapping strategy code (e.g., 's1') to strategy info dict
        """
        strategies = await self.get_active_strategies(user_id)
        return {s.strategy_code: s.to_dict() for s in strategies}

    async def get_strategy_by_code(
        self,
        user_id: str,
        strategy_code: str,
        lock_for_update: bool = False
    ) -> Optional[UserStrategy]:
        """
        Get a specific strategy by its short code.

        Args:
            user_id: User wallet address
            strategy_code: Strategy short code (e.g., 's1', 'h1')
            lock_for_update: If True, use SELECT FOR UPDATE for row locking

        Returns:
            UserStrategy object or None if not found
        """
        # Convert short code to full type
        strategy_type = CODE_TO_STRATEGY_TYPE.get(strategy_code)
        if not strategy_type:
            logger.warning(f"Unknown strategy code: {strategy_code}")
            return None

        stmt = select(UserStrategy).where(
            and_(
                UserStrategy.user_id == user_id,
                UserStrategy.strategy_type == strategy_type
            )
        )

        if lock_for_update:
            stmt = stmt.with_for_update()

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def activate_strategy(
        self,
        user_id: str,
        strategy_type: str,
        allocated_capital_usd: Decimal
    ) -> UserStrategy:
        """
        Activate a new strategy for a user.

        Args:
            user_id: User wallet address
            strategy_type: Full strategy type name (e.g., 'stable_usdc_eurc')
            allocated_capital_usd: Maximum capital to allocate

        Returns:
            Created UserStrategy object

        Raises:
            ValueError: If strategy already exists
        """
        # Check if strategy already exists
        existing = await self.get_strategy_by_code(
            user_id,
            self._get_strategy_code(strategy_type)
        )
        if existing and existing.status == 'active':
            raise ValueError(f"Strategy {strategy_type} is already active for user {user_id}")

        # Reactivate if it was closed
        if existing and existing.status in ('closed', 'paused'):
            existing.status = 'active'
            existing.allocated_capital_usd = allocated_capital_usd
            existing.deployed_capital_usd = Decimal(0)
            existing.updated_at = datetime.utcnow()
            await self.db.flush()
            logger.info(f"Reactivated strategy {strategy_type} for user {user_id}")
            return existing

        # Create new strategy
        strategy = UserStrategy(
            user_id=user_id,
            strategy_type=strategy_type,
            status='active',
            allocated_capital_usd=allocated_capital_usd,
            deployed_capital_usd=Decimal(0)
        )

        self.db.add(strategy)
        await self.db.flush()

        logger.info(
            f"Activated strategy {strategy_type} for user {user_id} "
            f"with allocated capital {allocated_capital_usd}"
        )

        return strategy

    async def deactivate_strategy(
        self,
        user_id: str,
        strategy_code: str
    ) -> bool:
        """
        Deactivate a strategy by setting status to 'closed'.

        This uses proper row-level locking to prevent race conditions.

        Args:
            user_id: User wallet address
            strategy_code: Strategy short code (e.g., 's1')

        Returns:
            True if deactivated, False if strategy not found

        Raises:
            ValueError: If strategy not found or already closed
        """
        # Get strategy with row lock
        strategy = await self.get_strategy_by_code(
            user_id,
            strategy_code,
            lock_for_update=True
        )

        if not strategy:
            raise ValueError(f"Strategy {strategy_code} not found for user {user_id}")

        if strategy.status == 'closed':
            raise ValueError(f"Strategy {strategy_code} is already closed")

        # Update status to closed
        strategy.status = 'closed'
        strategy.updated_at = datetime.utcnow()

        # Reset capital allocations
        strategy.allocated_capital_usd = Decimal(0)
        strategy.deployed_capital_usd = Decimal(0)

        await self.db.flush()

        logger.info(f"Deactivated strategy {strategy_code} for user {user_id}")

        return True

    async def update_deployed_capital(
        self,
        user_id: str,
        strategy_code: str,
        new_deployed: Decimal
    ) -> UserStrategy:
        """
        Update deployed capital for a strategy.

        Args:
            user_id: User wallet address
            strategy_code: Strategy short code
            new_deployed: New deployed capital amount

        Returns:
            Updated UserStrategy object

        Raises:
            ValueError: If strategy not found or deployed > allocated
        """
        # Get strategy with row lock
        strategy = await self.get_strategy_by_code(
            user_id,
            strategy_code,
            lock_for_update=True
        )

        if not strategy:
            raise ValueError(f"Strategy {strategy_code} not found for user {user_id}")

        if new_deployed > strategy.allocated_capital_usd:
            raise ValueError(
                f"Deployed capital {new_deployed} exceeds allocated {strategy.allocated_capital_usd}"
            )

        strategy.deployed_capital_usd = new_deployed
        strategy.updated_at = datetime.utcnow()

        await self.db.flush()

        logger.debug(
            f"Updated deployed capital for {user_id}/{strategy_code}: {new_deployed}"
        )

        return strategy

    async def sync_to_jsonb(self, user_id: str) -> dict:
        """
        Sync user_strategies table to user.active_strategies JSONB.

        This is used during the migration period for backward compatibility.

        Args:
            user_id: User wallet address

        Returns:
            Dict suitable for user.active_strategies JSONB column
        """
        strategies_dict = await self.get_active_strategies_dict(user_id)

        # Update user's JSONB column
        stmt = select(User).where(User.user_id == user_id).with_for_update()
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if user:
            user.active_strategies = strategies_dict
            attributes.flag_modified(user, 'active_strategies')
            await self.db.flush()

        return strategies_dict

    def _get_strategy_code(self, strategy_type: str) -> str:
        """Convert strategy type to short code."""
        mapping = {
            "hedged_weth_only": "h1",
            "hedged_cbbtc_only": "h2",
            "nonhedged_weth_only": "n1",
            "nonhedged_cbbtc_only": "n2",
            "nonhedged_cbltc_cbbtc": "n3",
            "nonhedged_cbada_cbbtc": "n4",
            "nonhedged_cbxrp_cbbtc": "n5",
            "nonhedged_cbdoge_cbbtc": "n6",
            "stable_usdc_eurc": "s1",
            "stable_usdc_msusd": "s2",
        }
        return mapping.get(strategy_type, strategy_type)
