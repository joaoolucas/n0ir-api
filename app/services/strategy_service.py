"""Service for managing user strategies."""

from typing import List, Optional
from decimal import Decimal
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import joinedload
from loguru import logger

from app.database.models import UserStrategy, User, Position, StrategyType, StrategyStatus
from app.schemas.strategy import (
    StrategyTypeEnum,
    StrategyStatusEnum,
    StrategyResponse,
    StrategyListResponse,
    StrategyWithPositionsResponse,
    PositionSummary,
    StrategyPerformance
)


class StrategyService:
    """Service for managing user strategies."""

    def __init__(self, db: AsyncSession):
        """
        Initialize strategy service.

        Args:
            db: Database session
        """
        self.db = db

    async def create_strategy(
        self,
        user_id: str,
        strategy_type: StrategyTypeEnum,
        capital_usdc: Decimal
    ) -> UserStrategy:
        """
        Create a new strategy for a user.

        Args:
            user_id: User wallet address
            strategy_type: Type of strategy to create
            capital_usdc: Initial capital allocation

        Returns:
            Created UserStrategy instance

        Raises:
            ValueError: If user not found or capital is invalid
        """
        # Verify user exists
        user = await self._get_user(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        if capital_usdc <= 0:
            raise ValueError("Capital must be greater than 0")

        # Create strategy
        strategy = UserStrategy(
            user_id=user_id.lower(),
            strategy_type=StrategyType[strategy_type.name],
            status=StrategyStatus.ACTIVE,
            capital_allocated_usdc=capital_usdc
        )

        self.db.add(strategy)
        await self.db.commit()
        await self.db.refresh(strategy)

        logger.info(
            f"Created {strategy_type.value} strategy for user {user_id} "
            f"with ${capital_usdc} capital (ID: {strategy.strategy_id})"
        )

        return strategy

    async def get_user_strategies(
        self,
        user_id: str,
        status: Optional[StrategyStatusEnum] = None
    ) -> List[UserStrategy]:
        """
        Get all strategies for a user.

        Args:
            user_id: User wallet address
            status: Optional status filter

        Returns:
            List of UserStrategy instances
        """
        query = select(UserStrategy).where(
            UserStrategy.user_id == user_id.lower()
        )

        if status:
            query = query.where(UserStrategy.status == StrategyStatus[status.name])

        query = query.order_by(UserStrategy.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_strategy_by_id(
        self,
        strategy_id: UUID,
        load_positions: bool = False
    ) -> Optional[UserStrategy]:
        """
        Get strategy by ID.

        Args:
            strategy_id: Strategy UUID
            load_positions: Whether to eagerly load positions

        Returns:
            UserStrategy instance or None if not found
        """
        query = select(UserStrategy).where(
            UserStrategy.strategy_id == strategy_id
        )

        if load_positions:
            query = query.options(joinedload(UserStrategy.positions))

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def update_strategy_status(
        self,
        strategy_id: UUID,
        status: StrategyStatusEnum
    ) -> UserStrategy:
        """
        Update strategy status.

        Args:
            strategy_id: Strategy UUID
            status: New status

        Returns:
            Updated UserStrategy instance

        Raises:
            ValueError: If strategy not found
        """
        strategy = await self.get_strategy_by_id(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")

        strategy.status = StrategyStatus[status.name]
        await self.db.commit()
        await self.db.refresh(strategy)

        logger.info(f"Updated strategy {strategy_id} status to {status.value}")

        return strategy

    async def update_strategy_capital(
        self,
        strategy_id: UUID,
        capital_usdc: Decimal
    ) -> UserStrategy:
        """
        Update strategy capital allocation.

        Args:
            strategy_id: Strategy UUID
            capital_usdc: New capital allocation

        Returns:
            Updated UserStrategy instance

        Raises:
            ValueError: If strategy not found or capital is invalid
        """
        strategy = await self.get_strategy_by_id(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")

        if capital_usdc <= 0:
            raise ValueError("Capital must be greater than 0")

        old_capital = strategy.capital_allocated_usdc
        strategy.capital_allocated_usdc = capital_usdc
        await self.db.commit()
        await self.db.refresh(strategy)

        logger.info(
            f"Updated strategy {strategy_id} capital from "
            f"${old_capital} to ${capital_usdc}"
        )

        return strategy

    async def get_strategy_positions(
        self,
        strategy_id: UUID,
        active_only: bool = False
    ) -> List[Position]:
        """
        Get all positions for a strategy.

        Args:
            strategy_id: Strategy UUID
            active_only: If True, only return active positions

        Returns:
            List of Position instances
        """
        query = select(Position).where(
            Position.strategy_id == strategy_id
        )

        if active_only:
            query = query.where(Position.status == "ACTIVE")

        query = query.order_by(Position.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_strategy_performance(
        self,
        strategy_id: UUID
    ) -> StrategyPerformance:
        """
        Calculate performance metrics for a strategy.

        Args:
            strategy_id: Strategy UUID

        Returns:
            StrategyPerformance instance with metrics
        """
        # Get all positions for this strategy
        positions = await self.get_strategy_positions(strategy_id)

        # Calculate metrics
        total_positions = len(positions)
        active_positions = len([p for p in positions if p.status == "ACTIVE"])

        total_deployed = sum(p.entry_amount_usdc for p in positions)
        current_value = sum(p.current_value_usdc or Decimal(0) for p in positions if p.status == "ACTIVE")
        unrealized_pnl = sum(p.unrealized_pnl_usdc for p in positions if p.status == "ACTIVE")
        realized_pnl = sum(p.realized_pnl_usdc for p in positions)

        total_pnl = realized_pnl + unrealized_pnl

        # Calculate percentages
        unrealized_pnl_pct = None
        if current_value > 0:
            unrealized_pnl_pct = (unrealized_pnl / current_value) * 100

        realized_pnl_pct = None
        total_pnl_pct = None
        if total_deployed > 0:
            realized_pnl_pct = (realized_pnl / total_deployed) * 100
            total_pnl_pct = (total_pnl / total_deployed) * 100

        return StrategyPerformance(
            total_positions=total_positions,
            active_positions=active_positions,
            total_deployed_usdc=total_deployed,
            current_value_usdc=current_value,
            unrealized_pnl_usdc=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            realized_pnl_usdc=realized_pnl,
            realized_pnl_pct=realized_pnl_pct,
            total_pnl_usdc=total_pnl,
            total_pnl_pct=total_pnl_pct
        )

    async def get_strategy_details(
        self,
        strategy_id: UUID
    ) -> Optional[StrategyWithPositionsResponse]:
        """
        Get detailed strategy information with positions and performance.

        Args:
            strategy_id: Strategy UUID

        Returns:
            StrategyWithPositionsResponse or None if not found
        """
        strategy = await self.get_strategy_by_id(strategy_id, load_positions=True)
        if not strategy:
            return None

        # Get positions
        positions = await self.get_strategy_positions(strategy_id)
        position_summaries = [
            PositionSummary(
                token_id=p.token_id,
                pool_address=p.pool_address,
                pool_name=p.pool_name,
                status=p.status,
                entry_amount_usdc=p.entry_amount_usdc,
                current_value_usdc=p.current_value_usdc,
                unrealized_pnl_usdc=p.unrealized_pnl_usdc
            )
            for p in positions
        ]

        # Get performance
        performance = await self.get_strategy_performance(strategy_id)

        return StrategyWithPositionsResponse(
            strategy_id=strategy.strategy_id,
            user_id=strategy.user_id,
            strategy_type=StrategyTypeEnum(strategy.strategy_type.value),
            status=StrategyStatusEnum(strategy.status.value),
            capital_allocated_usdc=strategy.capital_allocated_usdc,
            created_at=strategy.created_at,
            updated_at=strategy.updated_at,
            positions=position_summaries,
            performance=performance
        )

    async def delete_strategy(
        self,
        strategy_id: UUID
    ) -> bool:
        """
        Delete a strategy (closes it permanently).

        Args:
            strategy_id: Strategy UUID

        Returns:
            True if deleted, False if not found

        Raises:
            ValueError: If strategy has active positions
        """
        strategy = await self.get_strategy_by_id(strategy_id)
        if not strategy:
            return False

        # Check for active positions
        active_positions = await self.get_strategy_positions(strategy_id, active_only=True)
        if active_positions:
            raise ValueError(
                f"Cannot delete strategy with {len(active_positions)} active positions. "
                "Close all positions first."
            )

        # Set status to closed instead of deleting
        strategy.status = StrategyStatus.CLOSED
        await self.db.commit()

        logger.info(f"Closed strategy {strategy_id}")

        return True

    async def _get_user(self, user_id: str) -> Optional[User]:
        """Get user from database."""
        result = await self.db.execute(
            select(User).where(
                (User.user_id == user_id) |
                (User.user_id == user_id.lower())
            )
        )
        return result.scalar_one_or_none()
