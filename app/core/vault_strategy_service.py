"""
Vault Strategy Service for delta-neutral strategies.
Uses the new vault contract with Aave for hedging.
"""
from typing import Dict, Optional
from decimal import Decimal
from datetime import datetime
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.integrations.vault_contract import vault_contract
from app.core.blockchain_service import blockchain_service
from app.core.positions_service import positions_service
from app.core.pools_service import pools_service
from app.database.models import User
from app.schemas.users import (
    MoonwellStrategyResponse,
    CapitalInfo,
    StrategyAllocations,
    VaultAllocation,
    VaultHedgeSimulation,
    AerodromeLP,
    MonitoringInfo,
    RangeBreakMonitoring
)


class VaultStrategyService:
    """Service for generating vault-based strategies."""

    def calculate_ticks_from_range(
        self,
        current_tick: int,
        range_percentage: int,
        tick_spacing: int = 100
    ) -> tuple[int, int]:
        """Calculate tick bounds from range percentage."""
        # Range percentage is total range (e.g., 20 = ±10%)
        range_multiplier = range_percentage / 200  # Divide by 200 to get one-sided percentage

        # Calculate tick distance
        tick_distance = int(current_tick * range_multiplier)

        # Round to tick spacing
        tick_lower = ((current_tick - tick_distance) // tick_spacing) * tick_spacing
        tick_upper = ((current_tick + tick_distance) // tick_spacing) * tick_spacing

        return (tick_lower, tick_upper)

    async def generate_strategy(
        self,
        user_id: str,
        db: AsyncSession,
        pool_address: str = "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59"  # Default to WETH/USDC pool
    ) -> MoonwellStrategyResponse:
        """
        Generate vault-based delta-neutral strategy for user.

        Args:
            user_id: User ID
            db: Database session
            pool_address: Pool address

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

            # Get pool data
            try:
                pool_data = await pools_service.get_pool(pool_address)
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
                pool_metrics = {
                    'apr': 20,
                    'symbol': 'WETH-USDC',
                    'current_tick': 0,
                    'tick_spacing': 100
                }

            # Calculate suggested range based on pool metrics
            range_percentage = self._calculate_optimal_range(pool_metrics)

            # Calculate ticks
            tick_lower, tick_upper = self.calculate_ticks_from_range(
                pool_metrics['current_tick'],
                range_percentage,
                pool_metrics['tick_spacing']
            )

            # Find optimal strategy using vault contract
            try:
                optimal_strategy = vault_contract.find_optimal_strategy(
                    usdc_amount=float(balance),
                    pool_address=pool_address,
                    tick_lower=tick_lower,
                    tick_upper=tick_upper,
                    range_percentage=range_percentage
                )

                simulation = optimal_strategy['simulation']

                # Build vault allocation
                vault_allocation = VaultAllocation(
                    protocol="vault",
                    collateral_ratio_bps=optimal_strategy['collateral_ratio_bps'],
                    hedge_ratio=optimal_strategy['hedge_ratio'],
                    simulation=VaultHedgeSimulation(
                        hedge_asset=simulation['hedge_asset'],
                        collateral_amount=Decimal(str(simulation['collateral_amount'])),
                        borrow_amount_usd=Decimal(str(simulation['borrow_amount_usd'])),
                        borrow_amount_asset=Decimal(str(simulation['borrow_amount_asset'])),
                        total_lp_amount=Decimal(str(simulation['total_lp_amount'])),
                        asset_exposure_usd=Decimal(str(optimal_strategy['exposure_usd'])),
                        net_delta_usd=Decimal(str(optimal_strategy['net_delta_usd'])),
                        expected_health_factor=Decimal(str(simulation['expected_health_factor'])),
                        liquidation_price=Decimal(str(simulation['liquidation_price'])),
                        delta_neutral_score=Decimal(str(optimal_strategy['delta_neutral_score']))
                    )
                )

                # Calculate effective APR
                effective_apr = self._calculate_effective_apr(pool_metrics['apr'], range_percentage)

            except Exception as e:
                logger.error(f"Error finding optimal strategy: {e}")
                logger.warning("Vault contract simulations failed - using default strategy estimation")

                # Fallback to default strategy estimation
                collateral_amount = float(balance) * 0.6
                lp_amount = float(balance) * 0.4
                borrow_amount = collateral_amount * 0.45  # 45% LTV

                vault_allocation = VaultAllocation(
                    protocol="vault",
                    collateral_ratio_bps=6000,  # 60%
                    hedge_ratio=9500,  # 95%
                    simulation=VaultHedgeSimulation(
                        hedge_asset=settings.weth_address,
                        collateral_amount=Decimal(str(collateral_amount)),
                        borrow_amount_usd=Decimal(str(borrow_amount)),
                        borrow_amount_asset=Decimal(str(borrow_amount / 4000)),  # Assume $4000 WETH
                        total_lp_amount=Decimal(str(lp_amount + borrow_amount)),
                        asset_exposure_usd=Decimal(str((lp_amount + borrow_amount) * 0.5)),
                        net_delta_usd=Decimal(str(abs(borrow_amount - (lp_amount + borrow_amount) * 0.5))),
                        expected_health_factor=Decimal("2.0"),
                        liquidation_price=Decimal("2400"),  # 40% drop
                        delta_neutral_score=Decimal("0.95")
                    )
                )
                effective_apr = self._calculate_effective_apr(pool_metrics['apr'], range_percentage)

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
                    vault=vault_allocation,
                    aerodrome_lp=AerodromeLP(
                        protocol="aerodrome",
                        pool=pool_metrics['symbol'],
                        pool_address=pool_address,
                        amount_usdc=vault_allocation.simulation.total_lp_amount,
                        range_percentage=range_percentage,
                        effective_apr=Decimal(str(effective_apr))
                    )
                ),
                monitoring=monitoring_info
            )

            logger.info(f"Generated vault strategy for user {user_id}")
            logger.info(f"  Delta-neutral score: {vault_allocation.simulation.delta_neutral_score:.4f}")
            logger.info(f"  Health factor: {vault_allocation.simulation.expected_health_factor:.2f}")
            logger.info(f"  Net delta: ${vault_allocation.simulation.net_delta_usd:.2f}")

            return response

        except Exception as e:
            logger.error(f"Error generating strategy for user {user_id}: {e}")
            raise

    def _calculate_optimal_range(self, pool_metrics: Dict) -> int:
        """Calculate optimal range percentage based on pool metrics."""
        apr = pool_metrics.get('apr', 20)
        volume_24h = pool_metrics.get('volume_24h', 0)
        tvl = pool_metrics.get('tvl_usd', 0)
        is_stable = pool_metrics.get('is_stable', False)

        turnover = volume_24h / tvl if tvl > 0 else 0

        if is_stable:
            return 2  # ±1%

        if apr > 50 and turnover > 0.5:
            return 10  # ±5%
        elif apr > 20 or turnover > 0.2:
            return 20  # ±10%
        else:
            return 30  # ±15%

    def _calculate_effective_apr(self, base_apr: float, range_percentage: int) -> float:
        """Calculate effective APR based on range width."""
        if range_percentage <= 5:
            multiplier = 4.0
        elif range_percentage <= 10:
            multiplier = 2.5
        elif range_percentage <= 20:
            multiplier = 1.8
        elif range_percentage <= 30:
            multiplier = 1.4
        else:
            multiplier = 1.2

        return base_apr * multiplier

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
        return getattr(position, 'in_range', True) is False


# Singleton instance
vault_strategy_service = VaultStrategyService()
