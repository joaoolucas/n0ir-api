"""
Moonwell Strategy Service for delta-neutral strategies.
Generates strategy recommendations using Moonwell for hedging.
"""
from typing import Dict, Optional, List
from decimal import Decimal
from datetime import datetime
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.moonwell_service import moonwell_service
from app.core.blockchain_service import blockchain_service
from app.core.positions_service import positions_service
from app.core.pools_service import pools_service
from app.database.models import User
from app.schemas.users import (
    MoonwellStrategyResponse,
    CapitalInfo,
    StrategyAllocations,
    MoonwellAllocation,
    MoonwellCollateral,
    MoonwellBorrow,
    AerodromeLP,
    MonitoringInfo,
    RangeBreakMonitoring
)


class MoonwellStrategyService:
    """Service for generating Moonwell-based strategies."""

    async def generate_strategy(
        self,
        user_id: str,
        db: AsyncSession,
        pool_address: str = "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59"  # Default to WETH/USDC pool
    ) -> MoonwellStrategyResponse:
        """
        Generate Moonwell-based delta-neutral strategy for user.

        Args:
            user_id: User ID
            db: Database session

        Returns:
            Strategy response with allocations
        """
        try:
            # Get user and validate
            user = await self._get_user(user_id, db)
            if not user:
                raise ValueError(f"User {user_id} not found")

            if not user.cdp_wallet_address:
                raise ValueError(f"User {user_id} has no CDP wallet")

            # Get wallet balance
            balance = await blockchain_service.get_usdc_balance(user.cdp_wallet_address)
            logger.info(f"User {user_id} balance: ${balance:.2f}")

            # Get existing positions to check for range breaks
            positions = await positions_service.get_positions_by_owner(user.cdp_wallet_address)
            monitoring_info = None
            action = "open"

            # Check for range breaks in existing positions
            if positions:
                for position in positions:
                    if self._is_position_out_of_range(position):
                        monitoring_info = MonitoringInfo(
                            range_break=RangeBreakMonitoring(
                                trigger="price_outside_tick_bounds",
                                suggested_action="close_and_rebalance"
                            )
                        )
                        action = "rebalance"
                        logger.info(f"Position {position.nft_token_id} is out of range")
                        break

            # Get pool data for better calculations
            try:
                pool_data = await pools_service.get_pool(pool_address)
                # pool_data is a dict, not an object
                pool_metrics = {
                    'apr': pool_data.get('apr', 20),
                    'volume_24h': pool_data.get('volume_24h', 0),
                    'tvl_usd': pool_data.get('tvl_usd', 0),
                    'is_stable': pool_data.get('is_stable', False),
                    'symbol': pool_data.get('symbol', 'WETH-USDC'),
                    'current_tick': pool_data.get('current_tick', 0),
                    'tick_spacing': pool_data.get('tick_spacing', 100)
                }
                logger.info(f"Using pool {pool_metrics['symbol']} with APR {pool_metrics['apr']:.2f}%")
            except Exception as e:
                logger.warning(f"Could not fetch pool data for {pool_address}: {e}")
                pool_metrics = None

            # Get current ETH price from pool data or default
            weth_price = 4000  # Default
            if pool_metrics:
                # Calculate from pool price if available
                try:
                    # This would use the actual pool price calculation
                    # For now, use default
                    pass
                except:
                    pass

            # Generate allocations based on balance and pool metrics
            allocations_dict = moonwell_service.calculate_hedge_position(
                total_capital=float(balance),
                pool_address=pool_address,
                pool_metrics=pool_metrics,
                weth_price=weth_price
            )

            # Build response
            response = MoonwellStrategyResponse(
                user_id=user_id,
                strategy_type="delta_neutral",
                timestamp=datetime.utcnow().isoformat() + "Z",
                action=action,
                capital=CapitalInfo(
                    total_usd=Decimal(str(balance)),
                    base_asset="USDC"
                ),
                allocations=StrategyAllocations(
                    moonwell=MoonwellAllocation(
                        protocol="moonwell",
                        collateral=MoonwellCollateral(
                            market=allocations_dict["moonwell"]["collateral"]["market"],
                            amount_usdc=Decimal(str(allocations_dict["moonwell"]["collateral"]["amount_usdc"]))
                        ),
                        borrow=MoonwellBorrow(
                            market=allocations_dict["moonwell"]["borrow"]["market"],
                            amount_weth=Decimal(str(allocations_dict["moonwell"]["borrow"]["amount_weth"])),
                            amount_usd=Decimal(str(allocations_dict["moonwell"]["borrow"]["amount_usd"])),
                            post_borrow_action=allocations_dict["moonwell"]["borrow"]["post_borrow_action"]
                        )
                    ),
                    aerodrome_lp=AerodromeLP(
                        protocol="aerodrome",
                        pool=allocations_dict["aerodrome_lp"]["pool"],
                        amount_usdc=Decimal(str(allocations_dict["aerodrome_lp"]["amount_usdc"])),
                        range_percentage=allocations_dict["aerodrome_lp"]["range_percentage"],
                        pool_address=allocations_dict["aerodrome_lp"]["pool_address"],
                        effective_apr=Decimal(str(allocations_dict["aerodrome_lp"].get("effective_apr", 0)))
                    )
                ),
                monitoring=monitoring_info
            )

            logger.info(f"Generated {action} strategy for user {user_id}")
            return response

        except Exception as e:
            logger.error(f"Error generating strategy for user {user_id}: {e}")
            raise

    async def _get_user(self, user_id: str, db: AsyncSession) -> Optional[User]:
        """Get user from database."""
        result = await db.execute(
            select(User).where(
                (User.user_id == user_id) |
                (User.user_id == user_id.lower())
            )
        )
        return result.scalar_one_or_none()

    def _is_position_out_of_range(self, position) -> bool:
        """Check if position is out of range."""
        # Simplified check - in production, would check actual price vs ticks
        return getattr(position, 'in_range', True) is False


# Singleton instance
moonwell_strategy_service = MoonwellStrategyService()