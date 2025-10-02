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
from app.core.config import settings
from app.database.models import User
from app.schemas.users import (
    MoonwellStrategyResponse,
    CapitalInfo,
    ContractParameters,
    VaultHedgeSimulation,
    AerodromeLP,
    MonitoringInfo,
    PositionAlert
)


class VaultStrategyService:
    """Service for generating vault-based strategies."""

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

            # Minimum amount required to enter a position
            MIN_POSITION_AMOUNT = Decimal("40")

            # Check if balance is sufficient
            if balance <= 0:
                logger.warning(f"User {user_id} has insufficient balance: ${balance:.2f}")
                raise ValueError(f"Insufficient USDC balance. Please deposit USDC to your CDP wallet first.")

            if balance < MIN_POSITION_AMOUNT:
                logger.warning(f"User {user_id} balance ${balance:.2f} below minimum ${MIN_POSITION_AMOUNT}")
                raise ValueError(f"Minimum position size is {MIN_POSITION_AMOUNT} USDC. Current balance: {balance:.2f} USDC")

            # Check active positions for monitoring alerts
            monitoring_info = await self._check_positions_monitoring(user_id, db)
            action = "open"

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

            # Find optimal strategy using vault contract
            try:
                optimal_strategy = vault_contract.find_optimal_strategy(
                    usdc_amount=float(balance),
                    pool_address=pool_address,
                    range_percentage=range_percentage
                )

                sim = optimal_strategy['simulation']

                # Calculate deadline (15 minutes from now)
                deadline = int(datetime.utcnow().timestamp()) + 900

                # Build contract parameters
                contract_params = ContractParameters(
                    pool=pool_address,
                    range_percentage=range_percentage,
                    deadline=deadline,
                    usdc_amount=Decimal(str(balance)),
                    slippage_bps=50,  # 0.5% slippage
                    hedge_ratio=optimal_strategy['hedge_ratio'],
                    collateral_ratio_bps=optimal_strategy['collateral_ratio_bps']
                )

                # Build simulation results
                simulation = VaultHedgeSimulation(
                    hedge_asset=sim['hedge_asset'],
                    collateral_amount=Decimal(str(sim['collateral_amount'])),
                    borrow_amount_usd=Decimal(str(sim['borrow_amount_usd'])),
                    borrow_amount_asset=Decimal(str(sim['borrow_amount_asset'])),
                    total_lp_amount=Decimal(str(sim['total_lp_amount'])),
                    asset_exposure_usd=Decimal(str(optimal_strategy['exposure_usd'])),
                    net_delta_usd=Decimal(str(optimal_strategy['net_delta_usd'])),
                    expected_health_factor=Decimal(str(sim['expected_health_factor'])),
                    liquidation_price=Decimal(str(sim['liquidation_price'])),
                    delta_neutral_score=Decimal(str(optimal_strategy['delta_neutral_score']))
                )

                effective_apr = self._calculate_effective_apr(pool_metrics['apr'], range_percentage)

            except Exception as e:
                logger.error(f"Error finding optimal strategy: {e}")
                logger.warning("Vault contract simulations failed - using default strategy estimation")

                # Fallback parameters
                collateral_amount = float(balance) * 0.65
                borrow_amount = collateral_amount * 0.45
                lp_amount = collateral_amount + borrow_amount

                deadline = int(datetime.utcnow().timestamp()) + 900

                contract_params = ContractParameters(
                    pool=pool_address,
                    range_percentage=range_percentage,
                    deadline=deadline,
                    usdc_amount=Decimal(str(balance)),
                    slippage_bps=50,
                    hedge_ratio=9500,
                    collateral_ratio_bps=6500
                )

                simulation = VaultHedgeSimulation(
                    hedge_asset=settings.weth_address,
                    collateral_amount=Decimal(str(collateral_amount)),
                    borrow_amount_usd=Decimal(str(borrow_amount)),
                    borrow_amount_asset=Decimal(str(borrow_amount / 4000)),
                    total_lp_amount=Decimal(str(lp_amount)),
                    asset_exposure_usd=Decimal(str(lp_amount * 0.5)),
                    net_delta_usd=Decimal(str(abs(borrow_amount - lp_amount * 0.5))),
                    expected_health_factor=Decimal("2.0"),
                    liquidation_price=Decimal("2400"),
                    delta_neutral_score=Decimal("0.95")
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
                contract_params=contract_params,
                simulation=simulation,
                aerodrome_pool=AerodromeLP(
                    protocol="aerodrome",
                    pool=pool_metrics['symbol'],
                    pool_address=pool_address,
                    amount_usdc=simulation.total_lp_amount,
                    range_percentage=range_percentage,
                    effective_apr=Decimal(str(effective_apr))
                ),
                monitoring=monitoring_info
            )

            logger.info(f"Generated vault strategy for user {user_id}")
            logger.info(f"  Delta-neutral score: {simulation.delta_neutral_score:.4f}")
            logger.info(f"  Health factor: {simulation.expected_health_factor:.2f}")
            logger.info(f"  Net delta: ${simulation.net_delta_usd:.2f}")

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

    async def _check_positions_monitoring(self, user_id: str, db: AsyncSession) -> Optional[MonitoringInfo]:
        """
        Check active positions for monitoring alerts.

        Rules:
        - Hedged positions: Check neutral_ratio (0.8-1.2) and in_range
        - Non-hedged positions: Only check in_range

        Returns:
            MonitoringInfo with list of alerts, or None if no alerts
        """
        from app.services.user_service import UserService

        try:
            # Get active positions using the positions endpoint logic
            service = UserService(db)
            positions = await service.get_user_positions(user_id=user_id, status='ACTIVE')

            if not positions:
                return None

            alerts = []
            NEUTRAL_RATIO_MIN = Decimal("0.8")
            NEUTRAL_RATIO_MAX = Decimal("1.2")

            # Enrich positions with full data
            from app.api.v1.endpoints.info import enrich_position_with_pool_data

            for position in positions:
                try:
                    enriched = await enrich_position_with_pool_data(position, db)

                    in_range = enriched.get('in_range', True)
                    neutral_ratio = enriched.get('neutral_ratio')
                    is_hedged = enriched.get('hedge', {}).get('is_hedged', False) if enriched.get('hedge') else False
                    pool_address = enriched.get('pool_address', '')
                    position_id = enriched.get('nft_token_id')

                    # Check rules
                    reasons = []

                    # Rule 1: in_range must be True (for all positions)
                    if not in_range:
                        reasons.append('out_of_range')

                    # Rule 2: neutral_ratio must be 0.8-1.2 (only for hedged positions)
                    if is_hedged and neutral_ratio is not None:
                        if neutral_ratio < NEUTRAL_RATIO_MIN or neutral_ratio > NEUTRAL_RATIO_MAX:
                            reasons.append('neutral_ratio_breach')

                    # Create alert if any rule violated
                    if reasons:
                        alert = PositionAlert(
                            position_id=position_id,
                            pool_address=pool_address,
                            reason=', '.join(reasons),
                            suggested_action="close",
                            current_in_range=in_range,
                            current_neutral_ratio=Decimal(str(neutral_ratio)) if neutral_ratio is not None else None,
                            threshold_min=NEUTRAL_RATIO_MIN if is_hedged else None,
                            threshold_max=NEUTRAL_RATIO_MAX if is_hedged else None
                        )
                        alerts.append(alert)
                        logger.warning(f"Position {position_id} alert: {reasons}, neutral_ratio={neutral_ratio}, in_range={in_range}")

                except Exception as e:
                    logger.error(f"Error checking position {position.nft_token_id} for monitoring: {e}")
                    continue

            if alerts:
                return MonitoringInfo(alerts=alerts)

            return None

        except Exception as e:
            logger.error(f"Error checking positions monitoring for user {user_id}: {e}")
            return None


# Singleton instance
vault_strategy_service = VaultStrategyService()
