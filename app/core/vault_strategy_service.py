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
    PositionAlert,
    RecommendedPosition,
    PerformanceData
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

            # Check active positions for monitoring alerts FIRST
            monitoring_info = await self._check_positions_monitoring(user_id, db)

            # If there are monitoring alerts, return them regardless of balance
            # User needs to close problematic positions
            if monitoring_info and monitoring_info.alerts:
                logger.warning(f"User {user_id} has {len(monitoring_info.alerts)} position alerts - returning monitoring-only strategy")
                return await self._generate_monitoring_only_strategy(
                    user_id=user_id,
                    balance=balance,
                    pool_address=pool_address,
                    monitoring_info=monitoring_info
                )

            # No alerts - check if balance is sufficient for opening new position
            if balance <= 0:
                logger.warning(f"User {user_id} has insufficient balance: ${balance:.2f}")
                raise ValueError(f"Insufficient USDC balance. Please deposit USDC to your CDP wallet first.")

            if balance < MIN_POSITION_AMOUNT:
                logger.warning(f"User {user_id} balance ${balance:.2f} below minimum ${MIN_POSITION_AMOUNT} - returning no_action strategy")
                return await self._generate_no_action_strategy(
                    user_id=user_id,
                    balance=balance,
                    pool_address=pool_address,
                    reason=f"Insufficient balance for new position. Minimum: {MIN_POSITION_AMOUNT} USDC, Current: {balance:.2f} USDC",
                    db=db
                )

            # No alerts and sufficient balance - determine strategy type
            DUAL_POSITION_THRESHOLD = Decimal("2000")

            # Check if balance qualifies for dual position strategy
            if balance > DUAL_POSITION_THRESHOLD:
                logger.info(f"User {user_id} balance ${balance:.2f} > ${DUAL_POSITION_THRESHOLD} - recommending dual positions")
                return await self._generate_dual_position_strategy(
                    user_id=user_id,
                    balance=balance
                )

            # Single position strategy for balance <= $2000
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

                if not optimal_strategy or 'simulation' not in optimal_strategy:
                    raise ValueError("Invalid optimal strategy returned from vault contract")

                sim = optimal_strategy['simulation']

                if not sim:
                    raise ValueError("Simulation data is None")

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

    async def _generate_monitoring_only_strategy(
        self,
        user_id: str,
        balance: float,
        pool_address: str,
        monitoring_info: MonitoringInfo
    ) -> MoonwellStrategyResponse:
        """
        Generate a monitoring-only strategy response when positions need attention.
        This returns alerts without requiring minimum balance.
        """
        # Get basic pool data for context
        try:
            pool_data = await pools_service.get_pool(pool_address)
            pool_symbol = pool_data.get('symbol', 'WETH-USDC')
        except:
            pool_symbol = 'WETH-USDC'

        # Create minimal contract params (won't be used, but required by schema)
        deadline = int(datetime.utcnow().timestamp()) + 900
        contract_params = ContractParameters(
            pool=pool_address,
            range_percentage=10,  # Default
            deadline=deadline,
            usdc_amount=Decimal(str(balance)),
            slippage_bps=50,
            hedge_ratio=9500,
            collateral_ratio_bps=6500
        )

        # Create minimal simulation (won't be used)
        simulation = VaultHedgeSimulation(
            hedge_asset="WETH",
            collateral_amount=Decimal(0),
            borrow_amount_usd=Decimal(0),
            borrow_amount_asset=Decimal(0),
            total_lp_amount=Decimal(0),
            asset_exposure_usd=Decimal(0),
            net_delta_usd=Decimal(0),
            expected_health_factor=Decimal(0),
            liquidation_price=Decimal(0),
            delta_neutral_score=Decimal(0)
        )

        # Create minimal aerodrome pool info
        aerodrome_pool = AerodromeLP(
            pool=pool_symbol,
            pool_address=pool_address,
            amount_usdc=Decimal(0),
            range_percentage=10,
            effective_apr=None
        )

        return MoonwellStrategyResponse(
            user_id=user_id,
            strategy_type="delta_neutral",
            timestamp=datetime.utcnow().isoformat(),
            action="close",  # User should close problematic positions
            capital=CapitalInfo(total_usd=Decimal(str(balance))),
            contract_params=contract_params,
            simulation=simulation,
            aerodrome_pool=aerodrome_pool,
            monitoring=monitoring_info
        )

    async def _generate_no_action_strategy(
        self,
        user_id: str,
        balance: float,
        pool_address: str,
        reason: str,
        db: AsyncSession
    ) -> MoonwellStrategyResponse:
        """
        Generate a no_action strategy response when balance is insufficient.
        Returns performance data instead of contract params.
        """
        logger.info(f"Generating no_action strategy for {user_id}: {reason}")

        # Get positions for performance calculation
        from app.services.user_service import UserService

        user_service = UserService(db)
        user_positions = await user_service.get_user_positions(user_id)

        # Calculate active positions value
        active_positions = [p for p in user_positions if p.status == 'ACTIVE']
        positions_value = Decimal(0)
        total_apr = Decimal(0)
        apr_count = 0

        for position in active_positions:
            if position.entry_amount_usdc:
                positions_value += Decimal(str(position.entry_amount_usdc))
            # Get APR if available
            if hasattr(position, 'apr') and position.apr:
                total_apr += Decimal(str(position.apr))
                apr_count += 1

        # Calculate average APR
        avg_apr = (total_apr / apr_count) if apr_count > 0 else None

        # Calculate PnL
        closed_positions = [p for p in user_positions if p.status == 'CLOSED']
        realized_pnl = sum(Decimal(str(p.realized_pnl_usdc)) for p in closed_positions if p.realized_pnl_usdc) or Decimal(0)

        # Unrealized PnL (simplified - would need blockchain data for accuracy)
        unrealized_pnl = Decimal(0)

        total_pnl = realized_pnl + unrealized_pnl
        total_balance = Decimal(str(balance)) + positions_value

        # Calculate PnL percentages
        total_invested = sum(Decimal(str(p.entry_amount_usdc)) for p in user_positions if p.entry_amount_usdc) or Decimal(1)
        realized_pnl_pct = (realized_pnl / total_invested * 100) if total_invested > 0 else None
        pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else None

        performance = PerformanceData(
            apr=avg_apr,
            wallet_balance=Decimal(str(balance)),
            positions_value=positions_value,
            total_balance=total_balance,
            active_positions=len(active_positions),
            realized_pnl_usdc=realized_pnl,
            realized_pnl_pct=realized_pnl_pct,
            pnl_usdc=total_pnl,
            pnl_pct=pnl_pct
        )

        return MoonwellStrategyResponse(
            user_id=user_id,
            strategy_type="delta_neutral",
            timestamp=datetime.utcnow().isoformat(),
            action="no_action",  # Insufficient balance for action
            capital=CapitalInfo(total_usd=Decimal(str(balance))),
            contract_params=None,
            simulation=None,
            aerodrome_pool=None,
            monitoring=None,
            performance=performance
        )

    async def _generate_dual_position_strategy(
        self,
        user_id: str,
        balance: float
    ) -> MoonwellStrategyResponse:
        """
        Generate dual position strategy for balances > $2000.
        70% WETH/USDC + 30% USDC/cbBTC
        """
        # Pool addresses
        WETH_USDC_POOL = "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59"
        CBBTC_USDC_POOL = "0x9b2d25297db97d5c8a4e1e65dfb6e5a4c42e5c07"  # TODO: Verify this address

        # Allocation percentages
        WETH_ALLOCATION_PCT = 70
        CBBTC_ALLOCATION_PCT = 30

        # Calculate allocations
        total_balance = Decimal(str(balance))
        weth_allocation = total_balance * Decimal(str(WETH_ALLOCATION_PCT)) / Decimal("100")
        cbbtc_allocation = total_balance * Decimal(str(CBBTC_ALLOCATION_PCT)) / Decimal("100")

        logger.info(f"Dual position strategy: ${weth_allocation:.2f} WETH/USDC + ${cbbtc_allocation:.2f} USDC/cbBTC")

        # Build recommended positions
        recommended_positions = [
            RecommendedPosition(
                pool_name="WETH/USDC",
                pool_address=WETH_USDC_POOL,
                allocation_percentage=WETH_ALLOCATION_PCT,
                allocation_usdc=weth_allocation
            ),
            RecommendedPosition(
                pool_name="USDC/cbBTC",
                pool_address=CBBTC_USDC_POOL,
                allocation_percentage=CBBTC_ALLOCATION_PCT,
                allocation_usdc=cbbtc_allocation
            )
        ]

        # Get pool data for the primary (WETH) pool
        try:
            pool_data = await pools_service.get_pool(WETH_USDC_POOL)
            pool_symbol = pool_data.get('symbol', 'WETH/USDC')
        except:
            pool_symbol = 'WETH/USDC'

        # Create contract params for first position (WETH/USDC with 70%)
        deadline = int(datetime.utcnow().timestamp()) + 900
        contract_params = ContractParameters(
            pool=WETH_USDC_POOL,
            range_percentage=10,
            deadline=deadline,
            usdc_amount=weth_allocation,
            slippage_bps=50,
            hedge_ratio=9500,
            collateral_ratio_bps=6500
        )

        # Create minimal simulation (user will call strategy for each position separately)
        simulation = VaultHedgeSimulation(
            hedge_asset="WETH",
            collateral_amount=Decimal(0),
            borrow_amount_usd=Decimal(0),
            borrow_amount_asset=Decimal(0),
            total_lp_amount=Decimal(0),
            asset_exposure_usd=Decimal(0),
            net_delta_usd=Decimal(0),
            expected_health_factor=Decimal(0),
            liquidation_price=Decimal(0),
            delta_neutral_score=Decimal(0)
        )

        # Create aerodrome pool info
        aerodrome_pool = AerodromeLP(
            pool=pool_symbol,
            pool_address=WETH_USDC_POOL,
            amount_usdc=weth_allocation,
            range_percentage=10,
            effective_apr=None
        )

        return MoonwellStrategyResponse(
            user_id=user_id,
            strategy_type="delta_neutral",
            timestamp=datetime.utcnow().isoformat(),
            action="open_dual",
            capital=CapitalInfo(total_usd=total_balance),
            contract_params=contract_params,
            simulation=simulation,
            aerodrome_pool=aerodrome_pool,
            monitoring=None,
            recommended_positions=recommended_positions
        )


# Singleton instance
vault_strategy_service = VaultStrategyService()
