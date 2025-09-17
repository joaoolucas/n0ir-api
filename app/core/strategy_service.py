"""
Main strategy service that orchestrates all strategy components.
"""
import asyncio
import math
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from app.core.logger import logger

from app.core.strategy_calculator import StrategyCalculator
from app.core.range_break_detector import RangeBreakDetector
from app.core.slippage_calculator import SlippageCalculator
from app.core.portfolio_analyzer import PortfolioAnalyzer
from app.core.pools_service import pools_service
from app.core.positions_service import positions_service
from app.core.cache import cache_manager
from app.core.effective_apr_calculator import EffectiveAPRCalculator
from app.schemas.strategy import (
    OpportunitiesRequest, OpportunitiesResponse, PoolOpportunity,
    MonitorPositionsRequest, MonitorPositionsResponse,
    RangeBreakRequest, RangeBreakResponse,
    WhipsawDetectionRequest, WhipsawDetectionResponse,
    RiskMetrics, SlippageInfo, RiskAnalysis, RangeParameters,
    PositionStatus, PortfolioMetrics, RangeStatus,
    ExecutionParams, AlternativeAction, RangeBreakMetrics,
    OptimalTiming, AlternativeStrategy, RebalanceRecommendation,
    PortfolioImprovement, SwitchRecommendation,
    AnalyzeRequest
)


# Whitelisted pools from specs/whitelist.md
WHITELISTED_POOLS = {
    "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59",  # WETH/USDC
    "0x4e962bb3889bf030368f56810a9c96b83cb3e778",  # cbBTC/USDC
}


class StrategyService:
    """
    Main strategy service coordinating all strategy components.
    """
    
    def __init__(self):
        self.calculator = StrategyCalculator()
        self.range_detector = RangeBreakDetector()
        self.slippage_calc = SlippageCalculator()
        self.portfolio_analyzer = PortfolioAnalyzer()
        self.effective_apr_calc = EffectiveAPRCalculator()
        self.orchestrator = None  # Will be set after initialization to avoid circular import
        
        # Cache TTLs (in seconds)
        self.CACHE_TTL_OPPORTUNITIES = 300  # 5 minutes
        self.CACHE_TTL_ANALYSIS = 60       # 1 minute
        self.CACHE_TTL_MONITORING = 30     # 30 seconds
    
    def _calculate_price_from_sqrt_x96(self, sqrt_price_x96: str, token0_decimals: int = 18, token1_decimals: int = 18) -> float:
        """Calculate price from sqrtPriceX96.
        
        Returns the price of token0 in terms of token1.
        """
        try:
            sqrt_price_x96_int = int(sqrt_price_x96)
            if sqrt_price_x96_int == 0:
                return 1.0
            
            # Convert from X96 format
            sqrt_price = sqrt_price_x96_int / (2 ** 96)
            
            # Square to get the price
            price = sqrt_price ** 2
            
            # Adjust for decimals difference
            # Price is token1/token0, so we need to adjust decimals
            decimal_adjustment = 10 ** (token1_decimals - token0_decimals)
            adjusted_price = price * decimal_adjustment
            
            return adjusted_price
        except (ValueError, TypeError):
            return 1.0
    
    async def find_opportunities(
        self,
        request: OpportunitiesRequest
    ) -> OpportunitiesResponse:
        """
        Find and rank pool opportunities based on the quantitative scoring model.
        """
        # Strip whitespace from executor address to prevent validation errors
        request.executor_address = request.executor_address.strip()
        
        # Check cache
        import hashlib
        cache_key = f"strategy_opportunities:{hashlib.md5(str(request.dict()).encode()).hexdigest()}"
        cached = await cache_manager.get_custom(cache_key)
        if cached:
            return OpportunitiesResponse(**cached)
        
        # Fetch executor's current positions to exclude already invested pools
        # Use database positions for consistency with the rest of the API
        exclude_addresses = []
        total_position_value = 0
        all_positions = []
        
        try:
            from app.database.session import get_db
            from app.database.models import User, Position
            from app.services.user_service import UserService
            from sqlalchemy import select, or_
            
            async for session in get_db():
                # Get the user service instance
                user_service = UserService(session)
                
                # Get positions from database for the executor address
                db_positions = await user_service.get_user_positions(
                    request.executor_address, 
                    status='ACTIVE'  # Only active positions
                )
                
                # Also check if user has a CDP wallet and get those positions
                result = await session.execute(
                    select(User).where(
                        (User.user_id == request.executor_address) | 
                        (User.user_id == request.executor_address.lower())
                    )
                )
                user = result.scalar_one_or_none()
                
                if user and user.cdp_wallet_address:
                    logger.info(f"Checking CDP wallet {user.cdp_wallet_address} for positions in database")
                    # Get CDP wallet positions from database
                    cdp_positions = await user_service.get_user_positions(
                        user.cdp_wallet_address,
                        status='ACTIVE'
                    )
                    db_positions.extend(cdp_positions)
                
                # Convert database positions to exclude addresses
                for pos in db_positions:
                    if pos.pool_address:
                        exclude_addresses.append(pos.pool_address)
                        if pos.current_value_usdc and pos.current_value_usdc > 0:
                            total_position_value += float(pos.current_value_usdc)
                
                break  # Exit after first iteration
            
            # Make exclude_addresses unique
            exclude_addresses = list(set(exclude_addresses))
            
            logger.info(f"Executor has {len(db_positions)} positions (including CDP wallet) in {len(exclude_addresses)} unique pools, total value: ${total_position_value}")
        except Exception as e:
            logger.warning(f"Could not fetch executor positions: {e}")
            exclude_addresses = []
        
        # Calculate max_capital as available_capital + total position value
        max_capital = request.available_capital + total_position_value
        
        # Calculate optimal number of positions using new formula for Base L2
        # Average APR estimate for calculation (will vary by pool)
        avg_apr = 100  # 100% APR average estimate
        optimal_total_positions = self.calculator.calculate_optimal_position_count(
            max_capital, 
            avg_apr
        )
        
        # Adjust for already invested positions
        current_positions = len(exclude_addresses)
        max_new_positions = max(1, optimal_total_positions - current_positions)
        
        # Use balanced risk profile for all executors
        risk_profile = 'balanced'
        
        # Fetch whitelisted pools
        pools = await self._fetch_whitelisted_pools(exclude_addresses)
        
        # First pass: Calculate safety scores and allocation weights for all pools
        pool_candidates = []
        
        for pool in pools:
            # Skip if below minimum thresholds - pass available_capital for wallet-aware filtering
            if not self._meets_minimum_requirements(pool, risk_profile, request.available_capital):
                continue
            
            # Calculate safety score using the new simplified method
            safety_score = self.calculator.calculate_simple_safety_score(pool)
            
            # Skip very unsafe pools - more lenient for small wallets
            min_safety_score = 10 if request.available_capital < 100 else 20
            if safety_score < min_safety_score:
                continue
            
            # Calculate base score for compatibility
            base_score = self.calculator.calculate_pool_score(pool)
            
            # Calculate allocation weight (combines safety and APR)
            # Pass available_capital for wallet-size-aware weighting
            allocation_weight = self.calculator.calculate_allocation_weight(
                pool, 
                safety_score,
                request.available_capital
            )
            
            pool_candidates.append({
                'pool': pool,
                'safety_score': safety_score,
                'base_score': base_score,
                'allocation_weight': allocation_weight
            })
        
        # Sort by allocation weight (best opportunities first)
        pool_candidates.sort(key=lambda x: x['allocation_weight'], reverse=True)
        
        # Take only the top N candidates based on optimal position count
        # This ensures proper capital allocation to selected positions
        top_candidates = pool_candidates[:max_new_positions]
        
        # Calculate total weight ONLY for selected positions
        total_weight = sum(p['allocation_weight'] for p in top_candidates)
        
        # Target 85-100% capital utilization based on wallet size
        # Use TOTAL portfolio value to determine utilization rate
        # Someone with $100 available but $900 in positions should be treated as $1000 portfolio
        total_portfolio = max_capital  # This includes positions + available
        
        # For micro wallets, use 100% to ensure we can meet minimum position size
        if request.available_capital <= 100:
            target_utilization = 1.0  # Use 100% for micro wallets
        elif total_portfolio < 10_000:
            target_utilization = 0.95  # Use 95% for small portfolios
        elif total_portfolio < 25_000:
            target_utilization = 0.90  # Use 90% for medium portfolios
        else:
            target_utilization = 0.85  # Use 85% for larger portfolios
        allocatable_capital = request.available_capital * target_utilization
        
        # Second pass: Build opportunities with proper allocations
        opportunities = []
        allocated_so_far = 0
        
        for i, candidate in enumerate(top_candidates):
            pool = candidate['pool']
            safety_score = candidate['safety_score']
            base_score = candidate['base_score']
            allocation_weight = candidate['allocation_weight']
            
            # Calculate allocation for THIS position among selected positions
            if total_weight > 0:
                # Allocate based on weight among SELECTED positions only
                allocation_pct = allocation_weight / total_weight
            else:
                # Equal allocation if no weights
                allocation_pct = 1.0 / len(top_candidates) if top_candidates else 0
            
            # Calculate position size from allocatable capital
            base_amount = allocatable_capital * allocation_pct
            
            # For micro wallets with single position, ensure we use full available capital
            if request.available_capital <= 100 and len(top_candidates) == 1:
                base_amount = allocatable_capital  # Use full allocated capital
            
            # For micro wallets, skip complex position limiting to ensure we can deploy
            if request.available_capital <= 100:
                # Micro wallet: use the full base amount (which is already 100% of capital)
                max_amount = base_amount
            else:
                # Get dynamic position limit based on safety score
                # Use TOTAL portfolio value (positions + available) for sizing decisions
                total_portfolio_value = max_capital  # This includes positions + available
                max_position_pct = self.calculator.calculate_dynamic_position_limit(
                    safety_score, 
                    total_portfolio_value  # Use total portfolio, not just available
                )
                # But apply percentage only to available capital
                max_amount = request.available_capital * max_position_pct
                
                # Apply dynamic maximum but be more aggressive for small wallets
                # Small wallets need larger position sizes to be effective
                # Use total portfolio value for wallet size classification
                if total_portfolio_value < 5_000:
                    # Very small portfolio: allow up to 45% of available capital
                    aggressive_max = request.available_capital * 0.45
                    max_amount = max(max_amount, aggressive_max)
                elif total_portfolio_value < 10_000:
                    # Small portfolio: allow up to 40% of available capital
                    aggressive_max = request.available_capital * 0.40
                    max_amount = max(max_amount, aggressive_max)
                elif total_portfolio_value < 25_000:
                    # Medium portfolio: allow up to 35% of available capital
                    aggressive_max = request.available_capital * 0.35
                    max_amount = max(max_amount, aggressive_max)
            
            recommended_amount = min(base_amount, max_amount)
            
            # Ensure minimum position size
            apr = pool.get('apr', 100)
            min_position = self.calculator.calculate_minimum_position_size(apr)
            
            # Skip if we can't meet minimum
            if recommended_amount < min_position:
                continue
            
            recommended_amount = max(recommended_amount, min_position)
            
            # Track allocation
            allocated_so_far += recommended_amount
            
            # Calculate optimal range
            # Get current tick from pool data
            current_tick = pool.get('current_tick', 0)
            
            # Calculate price from sqrtPriceX96 if available
            if 'sqrt_price_x96' in pool:
                token0_decimals = pool.get('token0', {}).get('decimals', 18)
                token1_decimals = pool.get('token1', {}).get('decimals', 18)
                current_price = self._calculate_price_from_sqrt_x96(
                    pool['sqrt_price_x96'],
                    token0_decimals,
                    token1_decimals
                )
            else:
                current_price = pool.get('current_price', 1.0)
            
            tick_spacing = pool.get('tick_spacing', 100)  # Default to 100 if not provided
            is_stable = pool.get('is_stable', False)
            # Calculate volatility based on tick spacing instead of hardcoding
            volatility = self.calculator.calculate_volatility_from_tick_spacing(tick_spacing, is_stable)
            base_apr = pool.get('apr', 100)
            tvl = pool.get('tvl_usd', pool.get('tvl', 1_000_000))
            volume_24h = pool.get('volume_24h', 500_000)
            
            # Calculate range relative to current tick with enhanced parameters
            lower_tick, upper_tick = self.calculator.calculate_optimal_range_from_tick(
                current_tick,
                volatility,
                risk_profile,
                tick_spacing,
                base_apr,
                tvl,
                volume_24h
            )
            
            # Calculate slippage estimate
            slippage_breakdown = self.slippage_calc.calculate_slippage_breakdown(
                pool,
                recommended_amount,
                'enter'
            )
            
            # Calculate prices from ticks
            lower_price = self.calculator._tick_to_price(lower_tick)
            upper_price = self.calculator._tick_to_price(upper_tick)
            
            # Use tick-based price for consistency
            current_price_from_tick = self.calculator._tick_to_price(current_tick)
            
            # Calculate range percentages using tick-based prices for consistency
            if current_price_from_tick > 0:
                lower_percentage = ((current_price_from_tick - lower_price) / current_price_from_tick) * 100
                upper_percentage = ((upper_price - current_price_from_tick) / current_price_from_tick) * 100
                range_width_percentage = lower_percentage + upper_percentage
            else:
                lower_percentage = 0
                upper_percentage = 0
                range_width_percentage = 0
            
            # Calculate effective APR for the recommended range
            base_apr = pool.get('apr', 0) or 0  # Ensure base_apr is never None
            effective_apr = self.effective_apr_calc.calculate_effective_apr_from_ticks(
                base_apr,
                tick_spacing,
                lower_tick,
                upper_tick,
                current_tick
            )
            apr_efficiency = self.effective_apr_calc.calculate_apr_efficiency(base_apr, effective_apr)
            
            # Recalculate score using EFFECTIVE APR instead of base APR
            # This gives more accurate scoring
            pool_with_effective_apr = pool.copy()
            pool_with_effective_apr['apr'] = effective_apr  # Use effective APR for scoring
            
            # Recalculate pool score with effective APR
            effective_score = self.calculator.calculate_pool_score(pool_with_effective_apr)
            
            # Combine with safety score for final score
            # 60% effective score, 40% safety score
            final_score = (effective_score * 0.6) + (safety_score * 0.4)
            final_score = min(100, max(0, final_score))  # Cap at 0-100
            
            # Calculate expected returns using effective APR
            returns = self.calculator.calculate_expected_returns(
                pool,
                recommended_amount
            )
            
            opportunity = PoolOpportunity(
                pool_address=pool['address'],
                pair=f"{pool.get('token0', {}).get('symbol', 'TOKEN0')}/{pool.get('token1', {}).get('symbol', 'TOKEN1')}",
                score=final_score,
                expected_apr=returns['annualized_return'],
                effective_apr=effective_apr,
                apr_efficiency=apr_efficiency,
                recommended_amount=recommended_amount,
                recommended_range=RangeParameters(
                    lower_tick=lower_tick,
                    upper_tick=upper_tick,
                    lower_price=lower_price,
                    upper_price=upper_price,
                    range_percentage=range_width_percentage,
                    lower_percentage=lower_percentage,
                    upper_percentage=upper_percentage
                ),
                risk_metrics=RiskMetrics(
                    volatility_24h=volatility,
                    volume_tvl_ratio=pool.get('volume_24h', 0) / max(pool.get('tvl_usd', pool.get('tvl', 1)), 1),
                    slippage_estimate=slippage_breakdown['total_slippage']
                ),
                entry_conditions_met=self._check_entry_conditions(pool, final_score, effective_apr, request.available_capital)
            )
            
            opportunities.append(opportunity)
        
        
        # Already limited to max_new_positions in selection phase
        # Sort for display
        opportunities.sort(key=lambda x: x.score, reverse=True)
        
        # Calculate minimum position size for the average APR
        min_position_size = self.calculator.calculate_minimum_position_size(avg_apr)
        
        response = OpportunitiesResponse(
            opportunities=opportunities,
            optimal_position_count=optimal_total_positions,
            minimum_position_size=min_position_size
        )
        
        # Cache the response
        await cache_manager.set_custom(
            cache_key,
            response.dict(),
            ttl=self.CACHE_TTL_OPPORTUNITIES
        )
        
        return response
    
    async def _fetch_whitelisted_pools(
        self,
        exclude_addresses: List[str]
    ) -> List[Dict]:
        """Fetch data for whitelisted pools."""
        pools = []
        
        # Convert exclude list to set for faster lookup
        exclude_set = set(exclude_addresses)
        
        # Fetch each whitelisted pool
        for pool_address in WHITELISTED_POOLS:
            if pool_address in exclude_set:
                continue
            
            try:
                pool_data = await pools_service.get_pool(pool_address)
                if pool_data:
                    pools.append(pool_data)
            except Exception as e:
                logger.error(f"Error fetching pool {pool_address}: {e}")
                continue
        
        return pools
    
    def _meets_minimum_requirements(
        self,
        pool: Dict,
        risk_profile: str,
        available_capital: float = None
    ) -> bool:
        """Check if pool meets minimum requirements for risk profile.
        Now wallet-size aware - smaller wallets get access to more pools."""
        profile = self.calculator.RISK_PROFILES[risk_profile]
        
        tvl = pool.get('tvl_usd', 0)
        volume_24h = pool.get('volume_24h', 0)
        apr = pool.get('apr', 0)
        
        # Dynamic thresholds based on wallet size
        if available_capital and available_capital < 100:
            # Micro wallets ($10-100): Very lenient requirements
            min_tvl = 50_000      # vs 250k-1M normally
            min_volume = 10_000   # vs 50k-200k normally
            min_apr = 20          # vs 30-80 normally
        elif available_capital and available_capital < 1_000:
            # Small wallets ($100-1k): Lenient requirements  
            min_tvl = 100_000     # vs 250k-1M normally
            min_volume = 20_000   # vs 50k-200k normally
            min_apr = 25          # vs 30-80 normally
        elif available_capital and available_capital < 10_000:
            # Medium wallets ($1k-10k): Moderate requirements
            min_tvl = 200_000     # vs 250k-1M normally
            min_volume = 40_000   # vs 50k-200k normally
            min_apr = 30          # vs 30-80 normally
        else:
            # Large wallets ($10k+): Use profile defaults
            min_tvl = profile['min_tvl']
            min_volume = profile['min_volume_24h']
            
            # APR requirement based on TVL
            if tvl >= 5_000_000:  # $5M+ TVL - very safe pools
                min_apr = 30
            elif tvl >= 2_000_000:  # $2M+ TVL - safe pools
                min_apr = 40
            elif tvl >= 1_000_000:  # $1M+ TVL - moderate pools
                min_apr = 50
            else:
                min_apr = 80  # Smaller pools need higher APR
        
        return (
            tvl >= min_tvl and
            volume_24h >= min_volume and
            apr >= min_apr
        )
    
    def _check_entry_conditions(self, pool: Dict, score: float, effective_apr: float = None, available_capital: float = None) -> bool:
        """Check if entry conditions are met - wallet-size aware."""
        # Use effective APR if provided, otherwise fall back to base APR
        apr_to_check = effective_apr if effective_apr is not None else pool.get('apr', 0)
        
        # Dynamic thresholds based on wallet size
        if available_capital and available_capital < 100:
            # Micro wallets ($10-100): Very lenient conditions
            min_score = 20       # vs 45 normally
            min_tvl = 50_000     # vs 250k normally
            min_volume = 10_000  # vs 50k normally
            min_apr = 15         # vs 30 normally
        elif available_capital and available_capital < 1_000:
            # Small wallets ($100-1k): Lenient conditions
            min_score = 30       # vs 45 normally
            min_tvl = 100_000    # vs 250k normally
            min_volume = 20_000  # vs 50k normally
            min_apr = 20         # vs 30 normally
        elif available_capital and available_capital < 10_000:
            # Medium wallets ($1k-10k): Moderate conditions
            min_score = 40       # vs 45 normally
            min_tvl = 200_000    # vs 250k normally
            min_volume = 40_000  # vs 50k normally
            min_apr = 25         # vs 30 normally
        else:
            # Large wallets ($10k+): Standard conditions
            min_score = 45
            min_tvl = 250_000
            min_volume = 50_000
            min_apr = 30
        
        return (
            score >= min_score and
            pool.get('tvl_usd', 0) >= min_tvl and
            pool.get('volume_24h', 0) >= min_volume and
            apr_to_check >= min_apr
        )
    
    async def analyze_entry(
        self,
        request: AnalyzeRequest
    ) -> Dict[str, Any]:
        """
        Analyze a potential position entry with detailed risk assessment.
        """
        # Fetch pool data
        pool = await pools_service.get_pool(request.pool_address)
        if not pool:
            raise ValueError(f"Pool {request.pool_address} not found")
        
        # Check if pool is whitelisted (case-insensitive comparison)
        whitelisted_lower = {addr.lower() for addr in WHITELISTED_POOLS}
        if request.pool_address.lower() not in whitelisted_lower:
            warnings = ["Pool is not in the whitelist"]
        else:
            warnings = []
        
        # Calculate base pool score
        pool_score = self.calculator.calculate_pool_score(pool)
        
        # Calculate slippage
        slippage_breakdown = self.slippage_calc.calculate_slippage_breakdown(
            pool,
            request.amount_usdc,
            'enter'
        )
        
        slippage_info = SlippageInfo(
            estimated_percentage=slippage_breakdown['total_slippage'],
            max_acceptable=slippage_breakdown['max_recommended'],
            pair_volatility_class=slippage_breakdown['pair_classification']
        )
        
        # Calculate risk metrics
        risk_metrics = self.calculator.calculate_risk_metrics(
            {'invested_amount': request.amount_usdc},
            pool,
            request.amount_usdc * 5  # Assume 5x portfolio size
        )
        
        risk_analysis = RiskAnalysis(
            position_var_1d=risk_metrics['position_var_1d'],
            portfolio_impact=risk_metrics['portfolio_impact'],
            correlation_benefit=risk_metrics['correlation_benefit']
        )
        
        # Always calculate optimal range - this is our proposal to the executor
        # Get current tick from pool - ensure it's never None
        current_tick = pool.get('current_tick', 0) or 0
        
        # Calculate price from sqrtPriceX96 if available
        if 'sqrt_price_x96' in pool:
            token0_decimals = pool.get('token0', {}).get('decimals', 18)
            token1_decimals = pool.get('token1', {}).get('decimals', 18)
            current_price = self._calculate_price_from_sqrt_x96(
                pool['sqrt_price_x96'],
                token0_decimals,
                token1_decimals
            )
        else:
            current_price = pool.get('current_price', 1.0)
        
        tick_spacing = pool.get('tick_spacing', 100) or 100  # Default to 100 if None
        is_stable = pool.get('is_stable', False)
        # Calculate volatility based on tick spacing
        volatility = self.calculator.calculate_volatility_from_tick_spacing(tick_spacing, is_stable)
        base_apr = pool.get('apr', 100) or 100
        tvl = pool.get('tvl_usd', pool.get('tvl', 1_000_000)) or 1_000_000
        volume_24h = pool.get('volume_24h', 500_000) or 500_000
        
        # Calculate range relative to current tick with enhanced parameters
        lower_tick, upper_tick = self.calculator.calculate_optimal_range_from_tick(
            current_tick,
            volatility,
            'balanced',  # Use balanced risk profile for all
            tick_spacing,
            base_apr,
            tvl,
            volume_24h
        )
        
        # Calculate prices from ticks
        lower_price = self.calculator._tick_to_price(lower_tick)
        upper_price = self.calculator._tick_to_price(upper_tick)
        
        # Use tick-based price for consistency
        current_price_from_tick = self.calculator._tick_to_price(current_tick)
        
        # Calculate range percentages using tick-based prices for consistency
        if current_price_from_tick > 0:
            lower_percentage = ((current_price_from_tick - lower_price) / current_price_from_tick) * 100
            upper_percentage = ((upper_price - current_price_from_tick) / current_price_from_tick) * 100
            range_width_percentage = lower_percentage + upper_percentage
        else:
            lower_percentage = 0
            upper_percentage = 0
            range_width_percentage = 0
        
        optimal_range = RangeParameters(
            lower_tick=lower_tick,
            upper_tick=upper_tick,
            lower_price=lower_price,
            upper_price=upper_price,
            range_percentage=range_width_percentage,
            lower_percentage=lower_percentage,
            upper_percentage=upper_percentage
        )
        
        # Calculate effective APR for the optimal range
        base_apr = pool.get('apr', 0) or 0  # Ensure base_apr is never None
        effective_apr = self.effective_apr_calc.calculate_effective_apr_from_ticks(
            base_apr,
            tick_spacing,
            lower_tick,
            upper_tick,
            current_tick
        )
        apr_efficiency = self.effective_apr_calc.calculate_apr_efficiency(base_apr, effective_apr)
        
        # Calculate confidence score based on both pool score and effective APR
        # Weight the score to consider actual returns we'll get
        base_confidence = pool_score * 0.6  # 60% weight on pool fundamentals
        apr_confidence = min(100, (effective_apr / 100) * 40)  # 40% weight on effective APR
        confidence_score = min(100, base_confidence + apr_confidence)
        
        # Adjust confidence based on APR efficiency
        if apr_efficiency is not None:
            if apr_efficiency < 10:  # Less than 10% efficiency is very poor
                confidence_score *= 0.5
            elif apr_efficiency < 20:  # Less than 20% efficiency is poor
                confidence_score *= 0.75
        
        # Determine if should enter based on effective APR
        # Use effective APR for the entry decision since that's what we'll actually earn
        should_enter = (
            confidence_score >= 70 and
            slippage_breakdown['total_slippage'] <= 2.0 and
            request.pool_address.lower() in whitelisted_lower and
            effective_apr >= 50 and  # Minimum 50% effective APR for entry
            pool.get('tvl_usd', 0) >= 500_000 and
            pool.get('volume_24h', 0) >= 100_000
        )
        
        # Add warnings for risks
        if slippage_breakdown['total_slippage'] > 1.5:
            warnings.append(f"High slippage: {slippage_breakdown['total_slippage']:.2f}%")
        if risk_metrics['concentration_risk']:
            warnings.append("Position would create concentration risk")
        if effective_apr is not None and effective_apr < 10:
            efficiency_str = f"{apr_efficiency:.1f}" if apr_efficiency is not None else "N/A"
            warnings.append(f"Low effective APR: {effective_apr:.2f}% (efficiency: {efficiency_str}%)")
        
        return dict(
            should_enter=should_enter,
            confidence_score=confidence_score,
            slippage=slippage_info,
            risk_analysis=risk_analysis,
            optimal_range=optimal_range,
            effective_apr=effective_apr,
            apr_efficiency=apr_efficiency,
            warnings=warnings
        )
    
    async def monitor_positions(
        self,
        request: MonitorPositionsRequest
    ) -> MonitorPositionsResponse:
        """
        Monitor active positions and provide recommendations.
        """
        # Fetch positions for the user
        try:
            positions_data = await positions_service.get_positions_by_owner(request.user_address)
        except Exception as e:
            logger.error(f"Error fetching positions for {request.user_address}: {e}")
            positions_data = []
        
        position_statuses = []
        
        for position_data in positions_data:
            # Fetch current pool data
            pool = await pools_service.get_pool(position_data.pool_address)
            if not pool:
                continue
            
            # Check range status using tick-based comparison for accuracy
            current_tick = pool.get('current_tick')
            
            if current_tick is not None:
                # Use tick-based comparison like positions_service does
                in_range = position_data.tick_lower <= current_tick < position_data.tick_upper
                
                # Calculate range break severity if out of range
                if not in_range:
                    if current_tick < position_data.tick_lower:
                        # Below range
                        distance = (position_data.tick_lower - current_tick) / abs(position_data.tick_lower) if position_data.tick_lower != 0 else 0
                        range_break_severity = min(100, distance * 100 * 2)  # Scale to 0-100
                        price_position = 0  # Below range
                    else:
                        # Above range
                        distance = (current_tick - position_data.tick_upper) / abs(position_data.tick_upper) if position_data.tick_upper != 0 else 0
                        range_break_severity = min(100, distance * 100 * 2)  # Scale to 0-100
                        price_position = 1  # Above range
                    status = 'critical' if range_break_severity > 70 else 'out_of_range'
                else:
                    # In range
                    range_break_severity = 0
                    # Calculate position within range (0 = at lower bound, 1 = at upper bound)
                    range_width = position_data.tick_upper - position_data.tick_lower
                    if range_width > 0:
                        price_position = (current_tick - position_data.tick_lower) / range_width
                    else:
                        price_position = 0.5
                    status = 'in_range'
            else:
                # Fallback to position data if current_tick not available
                in_range = position_data.in_range
                price_position = 0.5
                range_break_severity = 0
                status = 'in_range' if in_range else 'out_of_range'
            
            # Calculate effective APR for this position
            base_apr = pool.get('apr', 0)
            effective_apr = base_apr  # Default to base APR
            
            if in_range and position_data.tick_spacing:
                # Calculate effective APR based on position's range
                try:
                    effective_apr = self.effective_apr_calc.calculate_effective_apr_from_ticks(
                        base_apr,
                        position_data.tick_spacing,
                        position_data.tick_lower,
                        position_data.tick_upper,
                        current_tick if current_tick is not None else 0
                    )
                except:
                    # Fallback to simplified calculation if the above fails
                    range_width = position_data.tick_upper - position_data.tick_lower
                    if range_width > 0:
                        # Approximate range percentage
                        range_percentage = range_width / 10000  # Rough approximation
                        effective_apr = self.effective_apr_calc.calculate_effective_apr(
                            base_apr,
                            position_data.tick_spacing,
                            range_percentage
                        )
            else:
                # Position out of range gets 0 effective APR
                effective_apr = 0
            
            # Calculate health score
            health_score = 100
            if not in_range:
                health_score -= range_break_severity * 0.5
            if effective_apr < 50:
                health_score -= 20
            health_score = max(0, health_score)
            
            # Determine recommended action
            # IMPORTANT: Check if position is unstaked first
            if hasattr(position_data, 'staked') and not position_data.staked:
                recommended_action = 'exit'
                action_details = {
                    'urgency': 'high', 
                    'reason': 'Position is unstaked - exit to avoid losing rewards',
                    'next_step': 'Use /api/v1/strategy/screen endpoint to find new opportunities'
                }
                health_score = 0  # Set health score to 0 for unstaked positions
            elif not in_range:
                # Out of range positions should be exited
                recommended_action = 'exit'
                action_details = {
                    'urgency': 'high', 
                    'reason': 'Position is out of range - exit and find new opportunities',
                    'next_step': 'Use /api/v1/strategy/screen endpoint to find better opportunities'
                }
            elif range_break_severity and range_break_severity > 85:
                recommended_action = 'exit'
                action_details = {
                    'urgency': 'high', 
                    'reason': 'Severe range break - exit and find new opportunities',
                    'next_step': 'Use /api/v1/strategy/screen endpoint to find better opportunities'
                }
            elif range_break_severity and range_break_severity > 70:
                recommended_action = 'rebalance'
                action_details = {'urgency': 'medium', 'reason': 'Range break detected - consider rebalancing'}
            elif health_score < 50:
                recommended_action = 'monitor'
                action_details = {'frequency': 'high', 'reason': 'Low health score - monitor closely'}
            else:
                recommended_action = 'hold'
                action_details = None
            
            position_status = PositionStatus(
                token_id=position_data.id,  # PositionInfo uses 'id' for token_id
                pool_address=position_data.pool_address,
                status=status,
                health_score=health_score,
                current_apr=effective_apr,  # Use effective APR instead of base APR
                accumulated_fees=position_data.unclaimed_fees_usd or 0,
                accumulated_rewards=0,  # Would calculate from position history
                range_status=RangeStatus(
                    in_range=in_range,
                    price_position=price_position,
                    range_break_severity=range_break_severity
                ),
                recommended_action=recommended_action,
                action_details=action_details
            )
            
            position_statuses.append(position_status)
        
        # Calculate portfolio metrics
        # Convert position data to expected format
        portfolio_positions = []
        for i, pos in enumerate(positions_data):
            # Get APR from corresponding position status if available
            current_apr = 0
            if i < len(position_statuses):
                current_apr = position_statuses[i].current_apr
            
            portfolio_positions.append({
                'current_value': pos.current_value_usd if pos.current_value_usd is not None else 0,
                'invested_amount': pos.current_value_usd if pos.current_value_usd is not None else 0,  # Approximation
                'volatility_24h': self.calculator.calculate_volatility_from_tick_spacing(
                    pos.tick_spacing or 100,
                    False  # is_stable not available in PositionInfo, default to False
                ),  # Calculate based on tick spacing
                'current_apr': current_apr
            })
        
        portfolio_analysis = self.portfolio_analyzer.calculate_portfolio_metrics(portfolio_positions)
        
        portfolio_metrics = PortfolioMetrics(
            total_value_usd=portfolio_analysis['total_value'],
            total_pnl_usd=portfolio_analysis['unrealized_pnl'],
            total_pnl_percentage=portfolio_analysis.get('unrealized_pnl_percentage', 0),
            active_positions=len(position_statuses),
            average_apr=portfolio_analysis['current_apr'],
            portfolio_volatility=portfolio_analysis.get('volatility', 0),
            diversification_score=portfolio_analysis.get('risk_score', 50)
        )
        
        # Generate alerts based on position statuses
        alerts = []
        recommended_actions = []
        
        for status in position_statuses:
            # Generate alerts for critical positions
            if status.status == 'critical':
                alerts.append({
                    'token_id': status.token_id,
                    'type': 'critical',
                    'message': f'Position {status.token_id} is critical - {status.action_details}'
                })
                if status.recommended_action:
                    recommended_actions.append(f"Token {status.token_id}: {status.recommended_action}")
            elif status.status == 'warning':
                alerts.append({
                    'token_id': status.token_id,
                    'type': 'warning',
                    'message': f'Position {status.token_id} needs attention - {status.action_details}'
                })
        
        # Create risk analysis matching the RiskAnalysis model fields
        risk_score = portfolio_analysis.get('risk_score', 50)
        risk_analysis = RiskAnalysis(
            overall_risk_score=100 - risk_score,  # Convert from portfolio health to risk
            concentration_risk=100 - risk_score if risk_score > 0 else 0,
            market_risk=min(30 + (len([a for a in alerts if a.get('type') == 'critical']) * 20), 100),
            liquidity_risk=20,  # Default moderate liquidity risk
            warnings=[f"Alert: {alert['message']}" for alert in alerts if alert.get('type') == 'warning')],
            recommendations=recommended_actions if recommended_actions else []
        )
        
        return MonitorPositionsResponse(
            positions=position_statuses,
            alerts=alerts,
            portfolio_metrics=portfolio_metrics,
            risk_analysis=risk_analysis,
            recommended_actions=recommended_actions
        )
    
    async def handle_range_break(
        self,
        request: RangeBreakRequest
    ) -> RangeBreakResponse:
        """
        Handle range break events with immediate action recommendations.
        """
        # Fetch position data
        try:
            position_data = await positions_service.get_position_by_id(request.token_id)
        except Exception as e:
            logger.error(f"Error fetching position {request.token_id}: {e}")
            raise ValueError(f"Position {request.token_id} not found")
        
        # Fetch pool data to get current price
        pool_address = position_data.pool_address if hasattr(position_data, 'pool_address') else position_data.get('pool_address', '') if isinstance(position_data, dict) else ''
        pool = await pools_service.get_pool(pool_address)
        if not pool:
            raise ValueError(f"Pool {pool_address} not found")
        
        # Calculate price from sqrtPriceX96 if available
        if 'sqrt_price_x96' in pool:
            token0_decimals = pool.get('token0', {}).get('decimals', 18)
            token1_decimals = pool.get('token1', {}).get('decimals', 18)
            current_price = self._calculate_price_from_sqrt_x96(
                pool['sqrt_price_x96'],
                token0_decimals,
                token1_decimals
            )
        else:
            current_price = pool.get('current_price', pool.get('token0_price', 1.0))
        
        # Calculate range boundaries from ticks
        tick_lower = position_data.tick_lower if hasattr(position_data, 'tick_lower') else position_data.get('tick_lower', 0) if isinstance(position_data, dict) else 0
        tick_upper = position_data.tick_upper if hasattr(position_data, 'tick_upper') else position_data.get('tick_upper', 0) if isinstance(position_data, dict) else 0
        
        # Simple tick to price conversion (simplified)
        lower_price = 1.0001 ** tick_lower
        upper_price = 1.0001 ** tick_upper
        
        # Determine break type
        if current_price > upper_price:
            break_type = 'upward'
            distance = (current_price - upper_price) / upper_price
        elif current_price < lower_price:
            break_type = 'downward'
            distance = (lower_price - current_price) / lower_price
        else:
            # Not actually broken
            break_type = None
            distance = 0
        
        # Create break info for analysis
        break_info = {
            'break_type': break_type if break_type else 'none',
            'severity': min(100, distance * 200) if break_type else 0,  # 50% distance = 100 severity
            'severity_level': '',
            'current_price': current_price
        }
        
        # Determine severity level
        severity = break_info.get('severity', 0)
        if severity >= 85:
            break_info['severity_level'] = 'critical'
        elif severity >= 70:
            break_info['severity_level'] = 'severe'
        elif severity >= 40:
            break_info['severity_level'] = 'moderate'
        else:
            break_info['severity_level'] = 'mild'
        
        # If no break, return monitor action
        if not break_type:
            return RangeBreakResponse(
                action='monitor',
                urgency='low',
                reasoning='Position is within range',
                execution_params=ExecutionParams(
                    exit_percentage=0,
                    max_slippage=0.5,
                    deadline=3600
                ),
                alternative_action=AlternativeAction(
                    type='hold',
                    expected_cost=0
                ),
                risk_metrics=RangeBreakMetrics(
                    reversal_probability=0,
                    expected_loss_if_reversal=0,
                    break_severity=0
                )
            )
        
        # Analyze range break probability
        reversal_analysis = self.range_detector.analyze_range_break_probability(
            {},  # Empty history for now
            break_info
        )
        
        # Get invested amount from position
        if hasattr(position_data, 'current_value_usd'):
            invested_amount = position_data.current_value_usd if position_data.current_value_usd is not None else 0
        elif isinstance(position_data, dict):
            invested_amount = position_data.get('total_value_usd', 0) or 0
        else:
            invested_amount = 0
        
        # Determine action based on break type and severity
        # Use consistent 50% threshold for both upward and downward breaks
        if break_info.get('severity', 0) >= 50:
            action = 'emergency_exit'
            urgency = 'high'
            if break_type == 'upward':
                reasoning = f"Upward break with {reversal_analysis['reversal_probability']*100:.0f}% reversal probability - exit and find new opportunities"
            else:
                reasoning = "Downward break exceeded 50% severity - exit and find new opportunities"
            exit_percentage = 100
            max_slippage = 2.0
        else:
            action = 'monitor'
            urgency = 'medium'
            if break_type == 'upward':
                reasoning = "Mild upward break - monitor closely"
            else:
                reasoning = "Mild downward break - monitor for opportunities"
            exit_percentage = 0
            max_slippage = 1.0
        
        execution_params = ExecutionParams(
            exit_percentage=exit_percentage,
            max_slippage=max_slippage,
            deadline=300 if urgency in ['critical', 'high'] else 600
        )
        
        # Calculate alternative action
        if action == 'emergency_exit':
            alternative = AlternativeAction(
                type='rebalance',
                expected_cost=50  # Estimated gas cost
            )
        else:
            alternative = AlternativeAction(
                type='hold',
                expected_cost=0
            )
        
        risk_metrics = RangeBreakMetrics(
            reversal_probability=reversal_analysis['reversal_probability'],
            expected_loss_if_reversal=reversal_analysis['expected_loss_if_reversal'],
            break_severity=break_info.get('severity', 0)
        )
        
        return RangeBreakResponse(
            action=action,
            urgency=urgency,
            reasoning=reasoning,
            execution_params=execution_params,
            alternative_action=alternative,
            risk_metrics=risk_metrics
        )
    
    async def analyze_exit(
        self,
        request: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze whether and how to exit a position.
        """
        # Fetch position data
        try:
            position_data = await positions_service.get_position_by_id(request.token_id)
        except Exception as e:
            logger.error(f"Error fetching position {request.token_id}: {e}")
            raise ValueError(f"Position {request.token_id} not found")
        
        # Check if position is unstaked - exit immediately without value calculations
        if hasattr(position_data, 'staked') and not position_data.staked:
            logger.info(f"Position {request.token_id} is unstaked - recommending immediate exit")
            return ExitAnalysisResponse(
                should_exit=True,
                exit_strategy='immediate',
                optimal_timing=OptimalTiming(
                    execute_now=True,
                    wait_minutes=0
                ),
                slippage_estimate=2.0,  # Conservative 2% for unstaked positions
                expected_proceeds=0,  # Unknown for unstaked positions
                roi_percentage=0,  # Return 0 instead of None to avoid type errors
                tax_implications=None
            )
        
        # Build position object from fetched data
        # Safely extract position values
        if hasattr(position_data, 'current_value_usd'):
            current_value = position_data.current_value_usd if position_data.current_value_usd is not None else 0
            invested_amount = position_data.current_value_usd if position_data.current_value_usd is not None else 0
            accumulated_fees = position_data.unclaimed_fees_usd if position_data.unclaimed_fees_usd is not None else 0
        elif isinstance(position_data, dict):
            current_value = position_data.get('total_value_usd', 0) or 0
            invested_amount = position_data.get('total_value_usd', 0) or 0
            accumulated_fees = position_data.get('uncollected_fees_usd', 0) or 0
        else:
            current_value = 0
            invested_amount = 0
            accumulated_fees = 0
            
        position = {
            'current_value': current_value,
            'invested_amount': invested_amount,  # Approximation
            'accumulated_fees': accumulated_fees,
            'accumulated_rewards': 0,  # Would need to track separately
            'entry_timestamp': datetime.utcnow()  # Would need to track separately
        }
        
        # Calculate ROI with None checks
        if position['invested_amount'] and position['invested_amount'] > 0:
            roi = ((position['current_value'] - position['invested_amount']) / 
                   position['invested_amount'] * 100)
            
            # Calculate total returns including fees and rewards
            total_returns = (position['current_value'] - position['invested_amount'] + 
                            position['accumulated_fees'] + position['accumulated_rewards'])
            roi_with_fees = (total_returns / position['invested_amount'] * 100)
        else:
            roi = 0
            roi_with_fees = 0
        
        # Determine exit strategy based on reason
        if request.exit_reason == 'range_break':
            should_exit = True
            exit_strategy = 'immediate'
            wait_minutes = 0
        elif request.exit_reason == 'stop_loss':
            should_exit = True
            exit_strategy = 'immediate'
            wait_minutes = 0
        elif request.exit_reason == 'take_profit':
            should_exit = roi_with_fees >= 20  # 20% profit target
            exit_strategy = 'graduated' if should_exit else 'wait'
            wait_minutes = 0 if should_exit else 60
        else:  # manual or rebalance
            should_exit = True
            exit_strategy = 'immediate'
            wait_minutes = 0
        
        # Estimate slippage for exit
        # We don't have pool data here, so use conservative estimate
        slippage_estimate = 1.0  # 1% conservative estimate
        
        # Calculate expected proceeds with None check
        if position['current_value'] and position['current_value'] > 0:
            expected_proceeds = position['current_value'] * (1 - slippage_estimate / 100)
        else:
            expected_proceeds = 0  # Unknown value
        
        return ExitAnalysisResponse(
            should_exit=should_exit,
            exit_strategy=exit_strategy,
            optimal_timing=OptimalTiming(
                execute_now=should_exit,
                wait_minutes=wait_minutes
            ),
            slippage_estimate=slippage_estimate,
            expected_proceeds=expected_proceeds,
            roi_percentage=roi_with_fees,
            tax_implications=None  # Not implemented
        )
    
    async def detect_whipsaw(
        self,
        request: WhipsawDetectionRequest
    ) -> WhipsawDetectionResponse:
        """
        Detect whipsaw patterns in position history.
        """
        # Fetch position data
        try:
            position_data = await positions_service.get_position_by_id(request.token_id)
        except Exception as e:
            logger.error(f"Error fetching position {request.token_id}: {e}")
            raise ValueError(f"Position {request.token_id} not found")
        
        # For now, create empty break history
        # In production, this would be tracked or calculated from historical data
        break_history = []
        
        # Detect whipsaw pattern
        whipsaw_result = self.range_detector.detect_whipsaw_pattern(break_history)
        
        # Map pattern to response format
        if whipsaw_result['pattern'] == 'high_frequency_reversal':
            pattern = 'high_frequency_reversal'
        elif whipsaw_result['pattern'] == 'directional_break':
            pattern = 'none'
        else:
            pattern = 'expanding_volatility'
        
        # Generate alternative strategies
        alternatives = []
        if whipsaw_result.get('whipsaw_detected', False):
            severity = whipsaw_result.get('severity', 0)
            if severity > 80:
                alternatives.append(AlternativeStrategy(
                    type='exit'
                ))
            elif severity > 60:
                alternatives.append(AlternativeStrategy(
                    type='reduce_position',
                    reduction_percentage=75
                ))
                alternatives.append(AlternativeStrategy(
                    type='widen_range',
                    new_range_multiplier=2.5
                ))
            else:
                alternatives.append(AlternativeStrategy(
                    type='widen_range',
                    new_range_multiplier=1.5
                ))
        
        # Map recommendation - check if recommended_action exists in result
        action_map = {
            'exit': 'exit',
            'reduce_position': 'reduce',
            'widen_range': 'widen_range',
            'monitor': 'monitor'
        }
        # Default to 'monitor' if no action in result
        raw_action = whipsaw_result.get('recommended_action', 'monitor')
        recommended_action = action_map.get(raw_action, 'monitor')
        
        return WhipsawDetectionResponse(
            whipsaw_detected=whipsaw_result.get('whipsaw_detected', False),
            severity=whipsaw_result.get('severity', 0),
            pattern=pattern,
            recommended_action=recommended_action,
            alternative_strategies=alternatives
        )
    
    async def analyze_position_switches(
        self,
        user_address: str,
        token_ids: List[int]
    ) -> Dict:
        """
        Analyze specific positions for potential switching opportunities.
        
        This method:
        1. Fetches user positions for given token_ids
        2. Retrieves candidate pools from whitelisted top performers
        3. Evaluates each position for switching opportunities
        4. Returns detailed switch recommendations
        
        Args:
            user_address: User wallet address
            token_ids: List of NFT token IDs to analyze
            
        Returns:
            Dictionary with switch recommendations and analysis
        """
        logger.info(f"Analyzing switch opportunities for {len(token_ids)} positions")
        
        calculator = StrategyCalculator()
        
        # Fetch actual position data
        positions_list = []
        for token_id in token_ids:
            try:
                # Try to fetch real position
                from app.core.positions_service import positions_service
                position = await positions_service.get_position_by_id(token_id)
                position_dict = position.dict() if hasattr(position, 'dict') else position
                
                # Map fields correctly
                if 'id' in position_dict:
                    position_dict['token_id'] = position_dict['id']
                if 'current_value_usd' in position_dict:
                    position_dict['current_value'] = position_dict['current_value_usd']
                
                positions_list.append(position_dict)
                logger.info(f"Fetched position {token_id} with value ${position_dict.get('current_value_usd', 0):.2f}")
            except Exception as e:
                logger.error(f"Failed to fetch position {token_id}: {e}")
                # Don't add to list if we can't fetch the position
        
        if not positions_list:
            return {
                'recommendations': [],
                'total_positions_analyzed': 0,
                'positions_recommended_for_switch': 0,
                'total_expected_apr_improvement': 0,
                'estimated_total_gas_cost': 0
            }
        
        # Fetch pool info for each position
        from app.core.pools_service import pools_service
        
        # Fetch pool info for all positions
        for position in positions_list:
            pool_address = position.get('pool_address')
            if pool_address:
                try:
                    pool_data = await pools_service.get_pool(pool_address, include_effective_apr=False)
                    # Add pool info to position
                    # Extract token symbols from nested objects
                    token0_symbol = 'UNKNOWN'
                    token1_symbol = 'UNKNOWN'
                    if isinstance(pool_data.get('token0'), dict):
                        token0_symbol = pool_data['token0'].get('symbol', 'UNKNOWN')
                    if isinstance(pool_data.get('token1'), dict):
                        token1_symbol = pool_data['token1'].get('symbol', 'UNKNOWN')
                    
                    position['pool_info'] = {
                        'symbol': pool_data.get('symbol', 'Unknown'),
                        'token0_symbol': token0_symbol,
                        'token1_symbol': token1_symbol,
                        'apr': pool_data.get('apr', pool_data.get('base_apr', 0)),
                        'base_apr': pool_data.get('base_apr', 0),
                        'tvl_usd': pool_data.get('tvl_usd', 0)
                    }
                    logger.info(f"Added pool info for position {position.get('token_id')}: {position['pool_info']['symbol']}")
                except Exception as e:
                    logger.warning(f"Failed to fetch pool info for position {position.get('token_id')}: {e}")
                    # Add default pool_info if fetch fails
                    position['pool_info'] = {
                        'symbol': 'Unknown',
                        'token0_symbol': 'UNKNOWN',
                        'token1_symbol': 'UNKNOWN',
                        'apr': 50,
                        'base_apr': 50,
                        'tvl_usd': 0
                    }
        
        # Calculate wallet size
        wallet_size = sum(p.get('current_value', 0) for p in positions_list)
        logger.info(f"Wallet size: ${wallet_size}")
        
        # Convert set to list for batch fetch
        whitelist_addresses = list(WHITELISTED_POOLS)
        
        # Fetch all whitelisted pools in batch with real APRs
        test_pools = []
        try:
            # Batch fetch all pools
            logger.info(f"Fetching {len(whitelist_addresses)} whitelisted pools")
            for pool_address in whitelist_addresses:
                try:
                    pool_data = await pools_service.get_pool(pool_address, include_effective_apr=False)
                    # Extract token symbols from nested objects
                    token0_symbol = 'UNKNOWN'
                    token1_symbol = 'UNKNOWN'
                    if isinstance(pool_data.get('token0'), dict):
                        token0_symbol = pool_data['token0'].get('symbol', 'UNKNOWN')
                    if isinstance(pool_data.get('token1'), dict):
                        token1_symbol = pool_data['token1'].get('symbol', 'UNKNOWN')
                    
                    test_pool = {
                        'address': pool_address,
                        'symbol': pool_data.get('symbol', 'Unknown'),
                        'token0_symbol': token0_symbol,
                        'token1_symbol': token1_symbol,
                        'fee': pool_data.get('fee', 0),
                        'tvl_usd': pool_data.get('tvl_usd', 0),
                        'volume_24h': pool_data.get('volume_24h', 0),
                        'apr': pool_data.get('apr', pool_data.get('base_apr', 0)),
                        'base_apr': pool_data.get('base_apr', 0),
                        'current_tick': pool_data.get('tick', 0)
                    }
                    test_pools.append(test_pool)
                    logger.info(f"Fetched pool {test_pool['symbol']} with APR {test_pool['apr']:.2f}%")
                except Exception as e:
                    logger.warning(f"Failed to fetch pool {pool_address}: {e}")
        except Exception as e:
            logger.error(f"Failed to fetch whitelisted pools: {e}")
        
        # Calculate switch recommendations
        recommendations = calculator.calculate_switch_recommendations(
            positions_list,
            test_pools,
            wallet_size
        )
        
        # Convert recommendations to response format
        switch_recommendations = []
        for rec in recommendations.get('recommendations', []):
            switch_rec = SwitchRecommendation(
                from_token_id=rec['from_token_id'],
                from_pool=rec['from_pool'],
                to_pool_address=rec['to_pool_address'],
                to_pool_name=rec['to_pool_name'],
                apr_improvement=rec['apr_improvement'],
                net_benefit_after_costs=rec['net_benefit_after_costs'],
                confidence=rec['confidence']
            )
            switch_recommendations.append(switch_rec)
        
        return {
            'recommendations': switch_recommendations,
            'total_positions_analyzed': recommendations.get('total_positions_analyzed', 0),
            'positions_recommended_for_switch': recommendations.get('positions_recommended_for_switch', 0),
            'total_expected_apr_improvement': recommendations.get('total_expected_apr_improvement', 0),
            'estimated_total_gas_cost': recommendations.get('estimated_total_gas_cost', 0)
        }

    async def rebalance_portfolio(
        self,
        request: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate portfolio rebalancing recommendations.
        Handles withdrawals by closing all positions and redeploying.
        """
        # Fetch user's positions
        try:
            positions_objects = await positions_service.get_positions_by_owner(request.user_address)
            # Convert PositionInfo objects to dictionaries with correct field mapping
            positions_list = []
            for pos in positions_objects:
                pos_dict = pos.dict()
                # Map fields for portfolio analyzer compatibility
                pos_dict['token_id'] = pos_dict.get('id')  # Map id to token_id
                pos_dict['current_value'] = pos_dict.get('current_value_usd', 0)
                pos_dict['invested_amount'] = pos_dict.get('current_value_usd', 0)  # Use current value as invested
                # Add dummy APR if not present (will be calculated by monitor service)
                pos_dict['current_apr'] = 100  # Default APR, should be fetched from pool data
                # Add position age (assume 30 days for now, should calculate from blockchain)
                pos_dict['position_age_days'] = 30  # Default age, should be calculated
                # Add safety score (default)
                pos_dict['safety_score'] = 50  # Default safety score
                positions_list.append(pos_dict)
        except Exception as e:
            logger.warning(f"Could not fetch positions for {request.user_address}: {e}")
            positions_list = []
        
        # Calculate total value in positions
        total_position_value = sum(pos.get('current_value', 0) or 0 for pos in positions_list)
        
        # Log for debugging
        logger.info(f"Portfolio analysis for {request.user_address}: "
                   f"positions_value=${total_position_value:.2f}, "
                   f"available_capital=${request.available_capital:.2f}")
        
        # Detect withdrawal: This logic is incorrect!
        # available_capital is ADDITIONAL money, not total wallet value
        # We should NOT trigger withdrawal based on this comparison
        # TODO: Fix or remove withdrawal detection logic
        is_withdrawal = False  # Disabled for now
        
        # Original flawed logic (kept for reference):
        # is_withdrawal = (
        #     total_position_value > 0 and 
        #     request.available_capital < total_position_value * 0.8
        # )
        
        recommendations = []
        
        if is_withdrawal:
            # Full rebalance: close all positions and redeploy
            logger.info(f"Withdrawal detected for {request.user_address}. Recommending full rebalance.")
            
            # Recommend closing all positions
            for pos in positions_list:
                recommendation = RebalanceRecommendation(
                    action='close',
                    token_id=pos.get('token_id'),  # Now using mapped token_id
                    pool_address=pos.get('pool_address'),
                    target_percentage=0,
                    suggested_amount=0,
                    reason='Withdrawal detected - closing all positions for redeployment'
                )
                recommendations.append(recommendation)
            
            # Calculate redeployment strategy for remaining capital
            if request.available_capital > 100:  # Minimum to redeploy
                redeployment = await self._calculate_redeployment_strategy(
                    request.available_capital,
                    request.user_address
                )
                
                for strategy in redeployment:
                    recommendation = RebalanceRecommendation(
                        action='open',
                        pool_address=strategy['pool_address'],
                        suggested_amount=strategy['amount'],
                        reason='Redeployment after withdrawal'
                    )
                    recommendations.append(recommendation)
        else:
            # Normal rebalancing (no withdrawal detected)
            # Check if new deposit (available capital > expected)
            is_deposit = request.available_capital > total_position_value * 0.1  # Has extra capital
            
            if is_deposit and len(positions_list) > 0:
                # Check if we should add new positions
                avg_apr = 100  # Estimate
                current_count = len(positions_list)
                total_capital = total_position_value + request.available_capital
                
                if self._should_add_position(current_count, total_capital, avg_apr):
                    # Recommend opening new positions with available capital
                    redeployment = await self._calculate_redeployment_strategy(
                        request.available_capital,
                        request.user_address
                    )
                    
                    for strategy in redeployment[:2]:  # Limit new positions
                        recommendation = RebalanceRecommendation(
                            action='open',
                            pool_address=strategy['pool_address'],
                            suggested_amount=strategy['amount'],
                            reason='New deposit - opening additional position'
                        )
                        recommendations.append(recommendation)
            else:
                # Standard rebalancing logic - focus on portfolio-level operations
                # No longer checking for switches here - that's handled by analyze_position_switches
                
                raw_recommendations = self.portfolio_analyzer.generate_rebalancing_recommendations(
                    positions_list,
                    request.available_capital,
                    'balanced',
                    candidate_pools=None  # No candidate pools for switching
                )
                
                for rec in raw_recommendations:
                    # Only handle portfolio-level actions (no switches)
                    if rec['action'] != 'switch':
                        recommendation = RebalanceRecommendation(
                            action=rec['action'],
                            token_id=rec.get('token_id'),
                            pool_address=rec.get('pool_address'),
                            target_percentage=rec.get('target_percentage'),
                            suggested_amount=rec.get('suggested_amount'),
                            reason=rec['reason']
                        )
                        recommendations.append(recommendation)
        
        # Calculate expected improvement
        current_metrics = self.portfolio_analyzer.calculate_portfolio_metrics(positions_list)
        
        # Estimate improvements
        apr_increase = 5.0 if len(recommendations) > 0 else 0
        risk_reduction = 10.0 if any(r.action in ['close', 'reduce'] for r in recommendations) else 0
        sharpe_improvement = 0.2 if len(recommendations) > 0 else 0
        
        improvement = PortfolioImprovement(
            apr_increase=apr_increase,
            risk_reduction=risk_reduction,
            sharpe_improvement=sharpe_improvement
        )
        
        return PortfolioRebalanceResponse(
            recommendations=recommendations,
            expected_portfolio_improvement=improvement,
            is_full_rebalance=is_withdrawal  # Add this field to schema
        )
    
    async def calculate_slippage(
        self,
        request: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculate dynamic slippage for a trade.
        """
        # Fetch pool data to get TVL, volatility, and pair info
        pool_data = await pools_service.get_pool(request.pool_address)
        if not pool_data:
            raise ValueError(f"Pool {request.pool_address} not found")
        
        # Create pool dict for slippage calculator
        pool = {
            'address': request.pool_address,
            'tvl': pool_data.get('tvl', 1_000_000),
            'volatility_24h': self.calculator.calculate_volatility_from_tick_spacing(
                pool_data.get('tick_spacing', 100),
                pool_data.get('is_stable', False)
            ),
            'token0_symbol': pool_data.get('token0_symbol', 'UNKNOWN'),
            'token1_symbol': pool_data.get('token1_symbol', 'UNKNOWN')
        }
        
        # Calculate slippage breakdown
        breakdown = self.slippage_calc.calculate_slippage_breakdown(
            pool,
            request.amount_usdc,
            request.action
        )
        
        return SlippageCalculationResponse(
            base_slippage=breakdown['base_slippage'],
            size_impact=breakdown['size_impact'],
            volatility_adjustment=breakdown['volatility_adjustment'],
            total_slippage=breakdown['total_slippage'],
            max_recommended=breakdown['max_recommended'],
            pair_classification=breakdown['pair_classification']
        )
    
    async def assess_risk(self, user_address: Optional[str] = None) -> Dict[str, Any]:
        """
        Get current portfolio risk assessment.
        """
        # Fetch positions if user_address provided
        if user_address:
            try:
                positions = await positions_service.get_positions_by_owner(user_address)
            except Exception as e:
                logger.warning(f"Could not fetch positions for {user_address}: {e}")
                positions = []
        else:
            positions = []
        
        # Calculate VaR
        var_metrics = self.portfolio_analyzer.calculate_portfolio_var(positions)
        portfolio_var = PortfolioVaR(
            var_1d_95=var_metrics.get('var_amount', 0),
            var_7d_95=var_metrics.get('var_amount', 0) * math.sqrt(7)
        )
        
        # Calculate concentration
        concentration_analysis = self.portfolio_analyzer.analyze_portfolio_concentration(positions)
        concentration_risk = ConcentrationRisk(
            highest_pool_percentage=concentration_analysis.get('highest_pool_percentage', 0),
            highest_token_percentage=concentration_analysis.get('highest_token_percentage', 0)
        )
        
        # Calculate range break risk
        range_break_var = var_metrics.get('range_break_var', 0)
        range_break_risk = RangeBreakRisk(
            positions_at_risk=0,
            potential_loss=range_break_var
        )
        
        # Calculate risk score
        risk_score = self.portfolio_analyzer.calculate_risk_score(positions)
        
        # Generate warnings
        warnings = []
        if concentration_risk.highest_pool_percentage and concentration_risk.highest_pool_percentage > 25:
            warnings.append("High concentration in single pool")
        if risk_score and risk_score > 70:
            warnings.append("Overall risk level is high")
        
        return RiskAssessmentResponse(
            portfolio_var=portfolio_var,
            concentration_risk=concentration_risk,
            range_break_risk=range_break_risk,
            warnings=warnings,
            risk_score=risk_score,
            recommended_actions=[]
        )
    
    async def get_performance_analytics(
        self,
        period: str = '24h',
        user_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get performance analytics for the strategy.
        """
        # For now, return example data
        # In production, would fetch actual performance data
        
        returns = ReturnMetrics(
            total_pnl=2500.0,
            roi_percentage=12.5,
            apr=48.2
        )
        
        fee_breakdown = FeeBreakdown(
            trading_fees=1800.0,
            rewards=1200.0,
            gas_costs=-400.0,
            slippage_costs=-100.0
        )
        
        risk_metrics = RiskPerformanceMetrics(
            sharpe_ratio=2.1,
            max_drawdown=-8.5,
            win_rate=0.75
        )
        
        execution_quality = ExecutionQuality(
            avg_slippage=0.65,
            successful_entries=15,
            successful_exits=12,
            range_breaks_handled=3
        )
        
        return PerformanceAnalyticsResponse(
            returns=returns,
            fee_breakdown=fee_breakdown,
            risk_metrics=risk_metrics,
            execution_quality=execution_quality
        )
    
    async def _calculate_redeployment_strategy(
        self,
        remaining_capital: float,
        executor_address: str
    ) -> List[Dict]:
        """
        Calculate new position deployment strategy after withdrawal.
        
        Args:
            remaining_capital: Capital remaining after withdrawal
            executor_address: Address of the executor
            
        Returns:
            List of recommended positions to open
        """
        # Use the find_opportunities logic but with remaining capital
        from app.schemas.strategy import OpportunitiesRequest
        
        request = OpportunitiesRequest(
            executor_address=executor_address,
            available_capital=remaining_capital,
            max_capital=remaining_capital
        )
        
        opportunities_response = await self.find_opportunities(request)
        
        # Convert opportunities to redeployment instructions
        redeployment_strategy = []
        for opp in opportunities_response.opportunities:
            redeployment_strategy.append({
                'pool_address': opp.pool_address,
                'amount': opp.recommended_amount,
                'lower_tick': opp.recommended_range.lower_tick,
                'upper_tick': opp.recommended_range.upper_tick,
                'action': 'open_position'
            })
        
        return redeployment_strategy
    
    def _should_add_position(
        self,
        current_count: int,
        available_capital: float,
        apr: float
    ) -> bool:
        """
        Determine if a new position should be added with deposit.
        
        Args:
            current_count: Current number of positions
            available_capital: Available capital for investment
            apr: Average APR of opportunities
            
        Returns:
            True if a new position should be added
        """
        optimal_count = self.calculator.calculate_optimal_position_count(
            available_capital,
            apr
        )
        
        return current_count < optimal_count
    
    async def comprehensive_analysis(
        self,
        executor_address: str,
        available_capital: float
    ) -> Dict[str, Any]:
        """
        Comprehensive analysis with orchestrator integration.
        Delegates to orchestrator if available, otherwise falls back to basic screening.
        """
        if self.orchestrator:
            # Use orchestrator for comprehensive analysis
            return await self.orchestrator.comprehensive_screen(
                executor_address=executor_address,
                available_capital=available_capital
            )
        else:
            # Fallback to basic screening
            from app.schemas.strategy import OpportunitiesRequest
            request = OpportunitiesRequest(
                executor_address=executor_address,
                available_capital=available_capital
            )
            response = await self.find_opportunities(request)
            
            # Return basic response matching expected structure
            return {
                'opportunities': response.opportunities,
                'optimal_position_count': response.optimal_position_count,
                'minimum_position_size': response.minimum_position_size,
                'timestamp': response.timestamp,
                'entry_analyses': [],
                'exit_recommendations': [],
                'switch_recommendations': [],
                'decision_matrix': None,
                'risk_alerts': []
            }


# Create singleton instance
strategy_service = StrategyService()