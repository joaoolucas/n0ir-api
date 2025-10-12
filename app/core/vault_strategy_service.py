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
    VaultStrategyResponse,
    DeprecatedCapitalInfo as CapitalInfo,
    ContractParameters,
    PositionParams,
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
        pool_address: str = "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59",  # Default to WETH/USDC pool
        strategy_config: Optional['StrategyConfig'] = None  # Optional strategy configuration
    ) -> VaultStrategyResponse:
        """
        Generate vault-based strategy for user with optional strategy configuration.

        Args:
            user_id: User ID
            db: Database session
            pool_address: Pool address
            strategy_config: Optional StrategyConfig for multi-strategy support

        Returns:
            Strategy response with allocations
        """
        try:
            logger.info(f"[POOL-DEBUG] generate_strategy called with pool_address={pool_address}, strategy_type={strategy_config.strategy_type.value if strategy_config else 'None'}")
            # Get user and validate
            user = await self._get_user(user_id, db)
            if not user:
                raise ValueError(f"User {user_id} not found")

            if not user.cdp_wallet_address:
                raise ValueError(f"User {user_id} has no CDP wallet")

            # Get wallet balance
            balance = await blockchain_service.get_usdc_balance(user.cdp_wallet_address)

            # Minimum amount required to enter a position
            MIN_POSITION_AMOUNT = Decimal("40")
            DUAL_POSITION_THRESHOLD = Decimal("1000")
            WETH_USDC_POOL = "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59"
            USDC_CBBTC_POOL = "0x4e962BB3889Bf030368F56810A9c96B83CB3E778"

            # Get active positions count and pools
            active_positions, position_pools = await self._get_active_positions_info(user_id, db)
            position_count = len(active_positions)

            logger.info(f"User {user_id} has {position_count} active positions in pools: {position_pools}")

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

            # STRATEGY LOGIC BASED ON POSITION COUNT

            # Case: 0 active positions
            if position_count == 0:
                if balance <= 0:
                    logger.warning(f"User {user_id} has no positions and insufficient balance: ${balance:.2f}")
                    return await self._generate_no_action_strategy(
                        user_id=user_id,
                        balance=balance,
                        pool_address=pool_address,
                        reason=f"No active positions. Deposit USDC to start earning.",
                        db=db
                    )

                if balance < MIN_POSITION_AMOUNT:
                    logger.warning(f"User {user_id} balance ${balance:.2f} below minimum ${MIN_POSITION_AMOUNT}")
                    return await self._generate_no_action_strategy(
                        user_id=user_id,
                        balance=balance,
                        pool_address=pool_address,
                        reason=f"Insufficient balance for new position. Minimum: {MIN_POSITION_AMOUNT} USDC, Current: {balance:.2f} USDC",
                        db=db
                    )

                # Check if user selected a blueprint strategy (50/50 dual positions)
                is_blueprint = strategy_config and "blueprint" in strategy_config.strategy_type.value

                if is_blueprint:
                    # Blueprint strategies always do 50/50 split with same $40 minimum
                    logger.info(f"User {user_id} selected blueprint strategy with ${balance:.2f} - opening dual positions")
                    return await self._generate_dual_position_strategy(
                        user_id=user_id,
                        balance=balance,
                        strategy_config=strategy_config
                    )

                # Non-blueprint strategies: balance-based logic
                if balance >= DUAL_POSITION_THRESHOLD:
                    logger.info(f"User {user_id} balance ${balance:.2f} >= ${DUAL_POSITION_THRESHOLD} - recommending dual positions")
                    return await self._generate_dual_position_strategy(
                        user_id=user_id,
                        balance=balance,
                        strategy_config=strategy_config
                    )

                # Single position for balance between $40-$999
                logger.info(f"User {user_id} opening single position with ${balance:.2f}")
                return await self._generate_single_position_strategy(
                    user_id=user_id,
                    balance=balance,
                    pool_address=pool_address,
                    db=db,
                    strategy_config=strategy_config
                )

            # Case: 1 active position
            elif position_count == 1:
                if balance >= MIN_POSITION_AMOUNT:
                    # Open second position using the pool_address from strategy_config
                    # This supports multi-strategy system (h1, h2, n1-n6, s1, s2)
                    existing_pool = position_pools[0]
                    logger.info(f"User {user_id} has 1 position in {existing_pool}, opening second in {pool_address}")
                    return await self._generate_single_position_strategy(
                        user_id=user_id,
                        balance=balance,
                        pool_address=pool_address,  # Use the pool from strategy_config, not hardcoded logic
                        db=db,
                        strategy_config=strategy_config
                    )
                else:
                    logger.info(f"User {user_id} has 1 position but insufficient balance for second: ${balance:.2f}")
                    return await self._generate_no_action_strategy(
                        user_id=user_id,
                        balance=balance,
                        pool_address=pool_address,
                        reason=f"Insufficient balance for second position. Minimum: {MIN_POSITION_AMOUNT} USDC, Current: {balance:.2f} USDC",
                        db=db
                    )

            # Case: 2 active positions
            elif position_count == 2:
                # Check if both positions are in different pools
                if len(set(p.lower() for p in position_pools)) == 1:
                    # Both positions in same pool - violation!
                    logger.error(f"User {user_id} has 2 positions in same pool {position_pools[0]} - must close one")
                    violation_alerts = [
                        PositionAlert(
                            position_id=pos.nft_token_id,
                            pool_address=pos.pool_address,
                            reason="duplicate_pool_violation",
                            suggested_action="close",
                            current_in_range=True,
                            current_neutral_ratio=None
                        )
                        for pos in active_positions
                    ]
                    monitoring_info = MonitoringInfo(alerts=violation_alerts)
                    return await self._generate_monitoring_only_strategy(
                        user_id=user_id,
                        balance=balance,
                        pool_address=pool_address,
                        monitoring_info=monitoring_info
                    )

                # Check if we should rebalance with new capital
                if balance >= MIN_POSITION_AMOUNT:
                    logger.info(f"User {user_id} has 2 positions + ${balance:.2f} available - recommending rebalance")
                    rebalance_alerts = [
                        PositionAlert(
                            position_id=pos.nft_token_id,
                            pool_address=pos.pool_address,
                            reason="rebalance_with_new_capital",
                            suggested_action="close",
                            current_in_range=True,
                            current_neutral_ratio=None
                        )
                        for pos in active_positions
                    ]
                    monitoring_info = MonitoringInfo(alerts=rebalance_alerts)
                    return await self._generate_monitoring_only_strategy(
                        user_id=user_id,
                        balance=balance,
                        pool_address=pool_address,
                        monitoring_info=monitoring_info
                    )
                else:
                    # Max positions reached, capital fully deployed
                    logger.info(f"User {user_id} has 2 positions, capital fully deployed")
                    return await self._generate_no_action_strategy(
                        user_id=user_id,
                        balance=balance,
                        pool_address=pool_address,
                        reason=f"Maximum positions reached (2/2). Capital efficiently deployed.",
                        db=db
                    )

            # Case: More than 2 positions (shouldn't happen, but handle it)
            else:
                logger.error(f"User {user_id} has {position_count} positions - exceeds maximum of 2")
                excess_alerts = [
                    PositionAlert(
                        position_id=pos.nft_token_id,
                        pool_address=pos.pool_address,
                        reason="exceeds_max_positions",
                        suggested_action="close",
                        current_in_range=True,
                        current_neutral_ratio=None
                    )
                    for pos in active_positions[2:]  # Alert for positions beyond first 2
                ]
                monitoring_info = MonitoringInfo(alerts=excess_alerts)
                return await self._generate_monitoring_only_strategy(
                    user_id=user_id,
                    balance=balance,
                    pool_address=pool_address,
                    monitoring_info=monitoring_info
                )


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

    async def _get_active_positions_info(self, user_id: str, db: AsyncSession) -> tuple:
        """
        Get active positions and their pool addresses.

        Returns:
            Tuple of (active_positions_list, pool_addresses_list)
        """
        from app.services.user_service import UserService

        try:
            service = UserService(db)
            positions = await service.get_user_positions(user_id=user_id, status='ACTIVE')

            if not positions:
                return ([], [])

            pool_addresses = [pos.pool_address for pos in positions if pos.pool_address]

            return (positions, pool_addresses)

        except Exception as e:
            logger.error(f"Error getting active positions info for user {user_id}: {e}")
            return ([], [])

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
    ) -> VaultStrategyResponse:
        """
        Generate a monitoring-only strategy response when positions need attention.
        This returns alerts without requiring minimum balance.
        """
        # Extract position IDs from alerts
        positions_to_close = [alert.position_id for alert in monitoring_info.alerts]

        # Create contract params with positions to close
        deadline = int(datetime.utcnow().timestamp()) + 900
        contract_params = ContractParameters(
            deadline=deadline,
            positions_to_close=positions_to_close
        )

        return VaultStrategyResponse(
            user_id=user_id,
            strategy_type="delta_neutral",
            timestamp=datetime.utcnow().isoformat(),
            action="close",  # User should close problematic positions
            capital=CapitalInfo(total_usd=Decimal(str(balance))),
            contract_params=contract_params,
            monitoring=monitoring_info,
            performance=None
        )

    async def _generate_no_action_strategy(
        self,
        user_id: str,
        balance: float,
        pool_address: str,
        reason: str,
        db: AsyncSession
    ) -> VaultStrategyResponse:
        """
        Generate a no_action strategy response when balance is insufficient.
        Returns performance data instead of contract params.
        """
        logger.info(f"Generating no_action strategy for {user_id}: {reason}")

        # Get performance data from user service
        from app.services.user_service import UserService

        try:
            service = UserService(db)
            perf_data = await service.calculate_user_performance(user_id)

            performance = PerformanceData(
                apr=perf_data.get('apr'),
                wallet_balance=Decimal(str(perf_data.get('wallet_balance', balance))),
                positions_value=Decimal(str(perf_data.get('positions_value', 0))),
                total_balance=Decimal(str(perf_data.get('total_balance', balance))),
                active_positions=perf_data.get('active_positions', 0),
                realized_pnl_usdc=Decimal(str(perf_data.get('realized_pnl_usdc', 0))),
                realized_pnl_pct=perf_data.get('realized_pnl_pct'),
                pnl_usdc=Decimal(str(perf_data.get('pnl_usdc', 0))),
                pnl_pct=perf_data.get('pnl_pct')
            )
        except Exception as e:
            logger.error(f"Error fetching performance data for {user_id}: {e}")
            # Fallback to basic data
            performance = PerformanceData(
                apr=None,
                wallet_balance=Decimal(str(balance)),
                positions_value=Decimal(0),
                total_balance=Decimal(str(balance)),
                active_positions=0,
                realized_pnl_usdc=Decimal(0),
                realized_pnl_pct=None,
                pnl_usdc=Decimal(0),
                pnl_pct=None
            )

        return VaultStrategyResponse(
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

    async def _generate_single_position_strategy(
        self,
        user_id: str,
        balance: float,
        pool_address: str,
        db: AsyncSession,
        strategy_config: Optional['StrategyConfig'] = None
    ) -> VaultStrategyResponse:
        """
        Generate single position strategy.

        Args:
            user_id: User ID
            balance: Available USDC balance
            pool_address: Pool address to open position in
            db: Database session

        Returns:
            Strategy response for single position
        """
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

        # Check if this strategy should use hedging
        should_hedge = True
        if strategy_config:
            # Non-hedged strategies: no Aave borrowing
            # Stable strategies: no need for hedging (already stable)
            should_hedge = strategy_config.hedged and not strategy_config.is_stable
            logger.info(f"Strategy config: hedged={strategy_config.hedged}, stable={strategy_config.is_stable}, should_hedge={should_hedge}")

        # Find optimal strategy using vault contract (only if hedging)
        if should_hedge:
            try:
                optimal_strategy = vault_contract.find_optimal_strategy(
                    usdc_amount=float(balance),
                    pool_address=pool_address,
                    range_percentage=range_percentage
                )
            except Exception as e:
                logger.error(f"Error finding optimal strategy: {e}")
                logger.warning("Vault contract simulations failed - using default hedging strategy")
                optimal_strategy = {
                    'hedge_ratio': 9500,
                    'collateral_ratio_bps': 6500,
                    'simulation': None
                }
        else:
            # Non-hedged or stable: no Aave borrowing
            logger.info(f"Skipping hedge optimization - using direct LP strategy")
            optimal_strategy = {
                'hedge_ratio': 0,  # No hedging
                'collateral_ratio_bps': 0,  # No Aave collateral
                'simulation': None
            }

        # Calculate deadline (15 minutes from now)
        deadline = int(datetime.utcnow().timestamp()) + 900

        # Get strategy-specific slippage
        slippage_bps = strategy_config.slippage_bps if strategy_config else 50

        # Build contract parameters
        contract_params = ContractParameters(
            pool=pool_address,
            range_percentage=range_percentage,
            deadline=deadline,
            usdc_amount=Decimal(str(balance)),
            slippage_bps=slippage_bps,
            hedge_ratio=optimal_strategy['hedge_ratio'],
            collateral_ratio_bps=optimal_strategy['collateral_ratio_bps']
        )

        logger.info(f"Generated single position strategy for {user_id}: pool={pool_address}, amount=${balance}, hedge_ratio={optimal_strategy['hedge_ratio']}, collateral_ratio={optimal_strategy['collateral_ratio_bps']}")

        # Build response
        return VaultStrategyResponse(
            user_id=user_id,
            strategy_type="delta_neutral",
            timestamp=datetime.utcnow().isoformat(),
            action="open",
            capital=CapitalInfo(
                total_usd=Decimal(str(balance)),
                base_asset="USDC"
            ),
            contract_params=contract_params,
            monitoring=None,
            performance=None
        )

    async def _generate_dual_position_strategy(
        self,
        user_id: str,
        balance: float,
        strategy_config: Optional['StrategyConfig'] = None
    ) -> VaultStrategyResponse:
        """
        Generate dual position strategy for balances >= $1000.
        Fixed allocation: WETH/USDC 70%, USDC/cbBTC 30%
        """
        # Pool addresses
        WETH_USDC_POOL = "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59"
        USDC_CBBTC_POOL = "0x4e962BB3889Bf030368F56810A9c96B83CB3E778"

        # Use strategy config allocation split if provided, otherwise default 70/30
        if strategy_config:
            # Get allocations from strategy config (should be 50/50 for blueprint)
            weth_allocation_pct = strategy_config.allocation_split.get(WETH_USDC_POOL, 0.5)
            cbbtc_allocation_pct = strategy_config.allocation_split.get(USDC_CBBTC_POOL, 0.5)
        else:
            # Default allocation: WETH/USDC gets 70%, USDC/cbBTC gets 30%
            weth_allocation_pct = 0.7
            cbbtc_allocation_pct = 0.3

        # Calculate allocations
        total_balance = Decimal(str(balance))
        weth_allocation = total_balance * Decimal(str(weth_allocation_pct))
        cbbtc_allocation = total_balance * Decimal(str(cbbtc_allocation_pct))

        logger.info(f"Dual position allocation: WETH/USDC {weth_allocation_pct*100}% (${weth_allocation}), USDC/cbBTC {cbbtc_allocation_pct*100}% (${cbbtc_allocation})")

        # Build position params (order by allocation percentage - highest first)
        positions_data = [
            ("WETH/USDC", WETH_USDC_POOL, weth_allocation_pct, weth_allocation),
            ("USDC/cbBTC", USDC_CBBTC_POOL, cbbtc_allocation_pct, cbbtc_allocation)
        ]
        positions_data.sort(key=lambda x: x[2], reverse=True)  # Sort by allocation % descending

        deadline = int(datetime.utcnow().timestamp()) + 900
        range_percentage = 10

        # Check if this strategy should use hedging
        should_hedge = True
        if strategy_config:
            should_hedge = strategy_config.hedged and not strategy_config.is_stable
            logger.info(f"Strategy config: hedged={strategy_config.hedged}, stable={strategy_config.is_stable}, should_hedge={should_hedge}")

        # Calculate optimal strategy for position 1 (only if hedging)
        if should_hedge:
            try:
                optimal_strategy_1 = vault_contract.find_optimal_strategy(
                    usdc_amount=float(positions_data[0][3]),
                    pool_address=positions_data[0][1],
                    range_percentage=range_percentage
                )
                hedge_ratio_1 = optimal_strategy_1['hedge_ratio']
                collateral_ratio_1 = optimal_strategy_1['collateral_ratio_bps']
                logger.info(f"Position 1 optimal ratios: hedge={hedge_ratio_1}, collateral={collateral_ratio_1}")
            except Exception as e:
                logger.warning(f"Failed to find optimal strategy for position 1: {e}, using defaults")
                hedge_ratio_1 = 9500
                collateral_ratio_1 = 6500
        else:
            logger.info(f"Skipping hedge optimization for position 1 - using direct LP strategy")
            hedge_ratio_1 = 0
            collateral_ratio_1 = 0

        # Calculate optimal strategy for position 2 (only if hedging)
        if should_hedge:
            try:
                optimal_strategy_2 = vault_contract.find_optimal_strategy(
                    usdc_amount=float(positions_data[1][3]),
                    pool_address=positions_data[1][1],
                    range_percentage=range_percentage
                )
                hedge_ratio_2 = optimal_strategy_2['hedge_ratio']
                collateral_ratio_2 = optimal_strategy_2['collateral_ratio_bps']
                logger.info(f"Position 2 optimal ratios: hedge={hedge_ratio_2}, collateral={collateral_ratio_2}")
            except Exception as e:
                logger.warning(f"Failed to find optimal strategy for position 2: {e}, using defaults")
                hedge_ratio_2 = 9500
                collateral_ratio_2 = 6500
        else:
            logger.info(f"Skipping hedge optimization for position 2 - using direct LP strategy")
            hedge_ratio_2 = 0
            collateral_ratio_2 = 0

        # Get strategy-specific slippage
        slippage_bps = strategy_config.slippage_bps if strategy_config else 50

        # Create position params with optimal ratios
        position_1 = PositionParams(
            pool=positions_data[0][1],
            pool_name=positions_data[0][0],
            usdc_amount=positions_data[0][3],
            range_percentage=range_percentage,
            deadline=deadline,
            slippage_bps=slippage_bps,
            hedge_ratio=hedge_ratio_1,
            collateral_ratio_bps=collateral_ratio_1
        )

        position_2 = PositionParams(
            pool=positions_data[1][1],
            pool_name=positions_data[1][0],
            usdc_amount=positions_data[1][3],
            range_percentage=range_percentage,
            deadline=deadline,
            slippage_bps=slippage_bps,
            hedge_ratio=hedge_ratio_2,
            collateral_ratio_bps=collateral_ratio_2
        )

        contract_params = ContractParameters(
            position_1=position_1,
            position_2=position_2
        )

        return VaultStrategyResponse(
            user_id=user_id,
            strategy_type="delta_neutral",
            timestamp=datetime.utcnow().isoformat(),
            action="open_dual",
            capital=CapitalInfo(total_usd=total_balance),
            contract_params=contract_params,
            monitoring=None,
            performance=None
        )


# Singleton instance
vault_strategy_service = VaultStrategyService()
