"""
Main strategy service that orchestrates all strategy components.
"""
import asyncio
import math
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging

from app.core.strategy_calculator import StrategyCalculator
from app.core.range_break_detector import RangeBreakDetector
from app.core.slippage_calculator import SlippageCalculator
from app.core.portfolio_analyzer import PortfolioAnalyzer
from app.core.pools_service import pools_service
from app.core.positions_service import positions_service
from app.core.cache import cache_manager
from app.schemas.strategy import (
    OpportunitiesRequest, OpportunitiesResponse, PoolOpportunity,
    AnalyzeEntryRequest, AnalyzeEntryResponse,
    MonitorPositionsRequest, MonitorPositionsResponse,
    RangeBreakRequest, RangeBreakResponse,
    ExitAnalysisRequest, ExitAnalysisResponse,
    WhipsawDetectionRequest, WhipsawDetectionResponse,
    PortfolioRebalanceRequest, PortfolioRebalanceResponse,
    SlippageCalculationRequest, SlippageCalculationResponse,
    RiskAssessmentResponse, PerformanceAnalyticsResponse,
    RiskMetrics, SlippageInfo, RiskAnalysis, RangeParameters,
    PositionStatus, RangeStatus, PortfolioMetrics,
    ExecutionParams, AlternativeAction, RangeBreakMetrics,
    OptimalTiming, AlternativeStrategy, RebalanceRecommendation,
    PortfolioImprovement, PortfolioVaR, ConcentrationRisk,
    RangeBreakRisk, ReturnMetrics, FeeBreakdown,
    RiskPerformanceMetrics, ExecutionQuality
)

logger = logging.getLogger(__name__)


# Whitelisted pools from specs/whitelist.md
WHITELISTED_POOLS = {
    "0x3f53f1Fd5b7723DDf38D93a584D280B9b94C3111",  # ZORA/USDC
    "0x363d1607b8DA83d6B6EA76D017CeEcf1316BB08A",  # cbBTC/cbDOGE
    "0xFd4F716cb3c493aFDDd40C67d3f42426aEb2d902",  # WETH/uLINK
    "0x56b92E5B391DbFb8b8028AC95A4b97f52ffEB416",  # WETH/KAITO
    "0xe077DdFb9E9d9403A8eC42D3023D17e8417ee399",  # GIZA/USDC
    "0x68a5aEA4DE3D938a755D85d1868Fe79A9C7B6ae1",  # WETH/DEGEN
    "0x22A52bB644f855ebD5ca2edB643FF70222D70C31",  # WETH/AIXBT
    "0x4e829F8A5213c42535AB84AA40BD4aDCCE9cBa02",  # WETH/BRETT
    "0x3f0296BF652e19bca772EC3dF08b32732F93014A",  # VIRTUAL/WETH
    "0xb2cc224c1c9feE385f8ad6a55b4d94E92359DC59",  # WETH/USDC
    "0x93617b2909a7c207E4180dE0E667ea80c9BdfE9e",  # oUSDT/WETH
    "0xcb1F3E1A6BB8A0e2D97bDC9d48DB093B2C0095f9",  # USDC/rETH
    "0x72bE417AFB0aBEa66913141C605D313BB389b59C",  # WETH/LINK
    "0x4796eda5A091B8Ca92EFA7d7Ee6f4De113A626FE",  # LsETH/cbBTC
    "0x98eCc8425cc4C3f30dD4EF02360B05698008a8fc",  # USDC/LsETH
    "0x8782d97C8b25B4d17dBFbaa03f25dC18e51e909D",  # cbADA/cbBTC
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
        
        # Cache TTLs (in seconds)
        self.CACHE_TTL_OPPORTUNITIES = 300  # 5 minutes
        self.CACHE_TTL_ANALYSIS = 60       # 1 minute
        self.CACHE_TTL_MONITORING = 30     # 30 seconds
    
    async def find_opportunities(
        self,
        request: OpportunitiesRequest
    ) -> OpportunitiesResponse:
        """
        Find and rank pool opportunities based on the quantitative scoring model.
        """
        # Check cache
        import hashlib
        cache_key = f"strategy_opportunities:{hashlib.md5(str(request.dict()).encode()).hexdigest()}"
        cached = await cache_manager.get_custom(cache_key)
        if cached:
            return OpportunitiesResponse(**cached)
        
        # Fetch whitelisted pools
        pools = await self._fetch_whitelisted_pools(request.exclude_addresses)
        
        # Score and rank pools
        opportunities = []
        for pool in pools:
            # Skip if below minimum thresholds
            if not self._meets_minimum_requirements(pool, request.risk_profile):
                continue
            
            # Calculate score
            score = self.calculator.calculate_pool_score(pool)
            
            # Skip low-scoring pools
            if score < 50:
                continue
            
            # Calculate position sizing
            recommended_amount, max_amount = self.calculator.calculate_position_size(
                pool,
                request.available_capital,
                request.risk_profile
            )
            
            # Calculate optimal range
            current_price = pool.get('current_price', 1.0)
            volatility = pool.get('volatility_24h', 20)
            lower_tick, upper_tick = self.calculator.calculate_optimal_range(
                current_price,
                volatility,
                request.risk_profile
            )
            
            # Calculate slippage estimate
            slippage_breakdown = self.slippage_calc.calculate_slippage_breakdown(
                pool,
                recommended_amount,
                'enter'
            )
            
            # Calculate expected returns
            returns = self.calculator.calculate_expected_returns(
                pool,
                recommended_amount
            )
            
            opportunity = PoolOpportunity(
                pool_address=pool['address'],
                pair=f"{pool.get('token0_symbol', 'TOKEN0')}/{pool.get('token1_symbol', 'TOKEN1')}",
                score=score,
                expected_apr=returns['annualized_return'],
                recommended_amount=recommended_amount,
                recommended_range=RangeParameters(
                    lower_tick=lower_tick,
                    upper_tick=upper_tick
                ),
                risk_metrics=RiskMetrics(
                    volatility_24h=volatility,
                    volume_tvl_ratio=pool.get('volume_24h', 0) / max(pool.get('tvl', 1), 1),
                    slippage_estimate=slippage_breakdown['total_slippage']
                ),
                entry_conditions_met=self._check_entry_conditions(pool, score)
            )
            
            opportunities.append(opportunity)
        
        # Sort by score descending
        opportunities.sort(key=lambda x: x.score, reverse=True)
        
        # Limit to max positions
        opportunities = opportunities[:request.max_positions]
        
        response = OpportunitiesResponse(opportunities=opportunities)
        
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
        risk_profile: str
    ) -> bool:
        """Check if pool meets minimum requirements for risk profile."""
        profile = self.calculator.RISK_PROFILES[risk_profile]
        
        tvl = pool.get('tvl', 0)
        volume_24h = pool.get('volume_24h', 0)
        apr = pool.get('apr', 0)
        
        return (
            tvl >= profile['min_tvl'] and
            volume_24h >= profile['min_volume_24h'] and
            apr >= 80  # Minimum 80% APR from strategy specs
        )
    
    def _check_entry_conditions(self, pool: Dict, score: float) -> bool:
        """Check if entry conditions are met."""
        return (
            score >= 60 and
            pool.get('tvl', 0) >= 500_000 and
            pool.get('volume_24h', 0) >= 100_000 and
            pool.get('apr', 0) >= 80
        )
    
    async def analyze_entry(
        self,
        request: AnalyzeEntryRequest
    ) -> AnalyzeEntryResponse:
        """
        Analyze a potential position entry with detailed risk assessment.
        """
        # Fetch pool data
        pool = await pools_service.get_pool(request.pool_address)
        if not pool:
            raise ValueError(f"Pool {request.pool_address} not found")
        
        # Check if pool is whitelisted
        if request.pool_address not in WHITELISTED_POOLS:
            warnings = ["Pool is not in the whitelist"]
        else:
            warnings = []
        
        # Calculate confidence score
        pool_score = self.calculator.calculate_pool_score(pool)
        confidence_score = min(100, pool_score * 1.2)  # Boost for entry analysis
        
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
        
        # Calculate optimal range if not provided
        if request.proposed_range:
            optimal_range = request.proposed_range
        else:
            current_price = pool.get('current_price', 1.0)
            volatility = pool.get('volatility_24h', 20)
            lower_tick, upper_tick = self.calculator.calculate_optimal_range(
                current_price,
                volatility,
                'balanced'
            )
            optimal_range = RangeParameters(
                lower_tick=lower_tick,
                upper_tick=upper_tick
            )
        
        # Determine if should enter
        should_enter = (
            confidence_score >= 70 and
            slippage_breakdown['total_slippage'] <= 2.0 and
            request.pool_address in WHITELISTED_POOLS and
            self._check_entry_conditions(pool, pool_score)
        )
        
        # Add warnings for risks
        if slippage_breakdown['total_slippage'] > 1.5:
            warnings.append(f"High slippage: {slippage_breakdown['total_slippage']:.2f}%")
        if risk_metrics['concentration_risk']:
            warnings.append("Position would create concentration risk")
        
        return AnalyzeEntryResponse(
            should_enter=should_enter,
            confidence_score=confidence_score,
            slippage=slippage_info,
            risk_analysis=risk_analysis,
            optimal_range=optimal_range,
            warnings=warnings
        )
    
    async def monitor_positions(
        self,
        request: MonitorPositionsRequest
    ) -> MonitorPositionsResponse:
        """
        Monitor active positions and provide recommendations.
        """
        position_statuses = []
        
        for position_info in request.positions:
            # Fetch current pool data
            pool = await pools_service.get_pool(position_info.pool_address)
            if not pool:
                continue
            
            # Check range status
            current_price = pool.get('current_price', position_info.entry_price)
            range_break = self.range_detector.detect_range_break(
                position_info.dict(),
                current_price
            )
            
            if range_break:
                in_range = False
                price_position = 0 if range_break['break_type'] == 'downward' else 1
                range_break_severity = range_break['severity']
                status = 'critical' if range_break_severity > 70 else 'out_of_range'
            else:
                in_range = True
                # Calculate position within range
                lower_price = position_info.current_range.lower_price or 0
                upper_price = position_info.current_range.upper_price or float('inf')
                price_range = upper_price - lower_price
                price_position = (current_price - lower_price) / price_range if price_range > 0 else 0.5
                range_break_severity = 0
                status = 'in_range'
            
            # Calculate health score
            health_score = 100
            if not in_range:
                health_score -= range_break_severity * 0.5
            if pool.get('apr', 0) < 50:
                health_score -= 20
            health_score = max(0, health_score)
            
            # Determine recommended action
            if range_break_severity > 85:
                recommended_action = 'exit'
                action_details = {'urgency': 'high', 'reason': 'Severe range break'}
            elif range_break_severity > 70:
                recommended_action = 'rebalance'
                action_details = {'urgency': 'medium', 'reason': 'Range break detected'}
            elif health_score < 50:
                recommended_action = 'monitor'
                action_details = {'frequency': 'high', 'reason': 'Low health score'}
            else:
                recommended_action = 'hold'
                action_details = None
            
            position_status = PositionStatus(
                token_id=position_info.token_id,
                pool_address=position_info.pool_address,
                status=status,
                health_score=health_score,
                current_apr=pool.get('apr', 0),
                accumulated_fees=0,  # Would calculate from position history
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
        positions_data = [p.dict() for p in request.positions]
        portfolio_analysis = self.portfolio_analyzer.calculate_portfolio_metrics(positions_data)
        
        portfolio_metrics = PortfolioMetrics(
            total_value=portfolio_analysis['total_value'],
            unrealized_pnl=portfolio_analysis['unrealized_pnl'],
            current_apr=portfolio_analysis['current_apr'],
            risk_score=portfolio_analysis['risk_score']
        )
        
        return MonitorPositionsResponse(
            positions=position_statuses,
            portfolio_metrics=portfolio_metrics
        )
    
    async def handle_range_break(
        self,
        request: RangeBreakRequest
    ) -> RangeBreakResponse:
        """
        Handle range break events with immediate action recommendations.
        """
        position = request.position
        
        # Create break info for analysis
        break_info = {
            'break_type': position.break_type,
            'severity': 0,  # Will be calculated
            'severity_level': '',
            'current_price': position.current_price
        }
        
        # Calculate severity
        lower_price = position.range['lower_price']
        upper_price = position.range['upper_price']
        
        if position.break_type == 'upward':
            distance = (position.current_price - upper_price) / upper_price
        else:
            distance = (lower_price - position.current_price) / lower_price
        
        break_info['severity'] = min(100, distance * 200)  # 50% distance = 100 severity
        
        # Determine severity level
        if break_info['severity'] >= 85:
            break_info['severity_level'] = 'critical'
        elif break_info['severity'] >= 70:
            break_info['severity_level'] = 'severe'
        elif break_info['severity'] >= 40:
            break_info['severity_level'] = 'moderate'
        else:
            break_info['severity_level'] = 'mild'
        
        # Analyze range break probability
        reversal_analysis = self.range_detector.analyze_range_break_probability(
            {},  # Empty history for now
            break_info
        )
        
        # Determine action based on break type and severity
        if position.break_type == 'upward':
            if break_info['severity'] >= 70:
                action = 'emergency_exit'
                urgency = 'critical'
                reasoning = f"Upward break with {reversal_analysis['reversal_probability']*100:.0f}% reversal probability"
                exit_percentage = 100
                max_slippage = 2.0
            elif break_info['severity'] >= 40:
                action = 'partial_exit'
                urgency = 'high'
                reasoning = "Moderate upward break - reduce exposure"
                exit_percentage = 75
                max_slippage = 1.5
            else:
                action = 'monitor'
                urgency = 'medium'
                reasoning = "Mild upward break - monitor closely"
                exit_percentage = 0
                max_slippage = 1.0
        else:  # downward
            if break_info['severity'] >= 85:
                action = 'rebalance'
                urgency = 'high'
                reasoning = "Severe downward break - consider rebalancing"
                exit_percentage = 0
                max_slippage = 1.0
            else:
                action = 'monitor'
                urgency = 'low'
                reasoning = "Downward break - monitor for opportunities"
                exit_percentage = 0
                max_slippage = 0.5
        
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
            break_severity=break_info['severity']
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
        request: ExitAnalysisRequest
    ) -> ExitAnalysisResponse:
        """
        Analyze whether and how to exit a position.
        """
        position = request.position
        
        # Calculate ROI
        roi = ((position.current_value - position.invested_amount) / 
               position.invested_amount * 100) if position.invested_amount > 0 else 0
        
        # Calculate total returns including fees and rewards
        total_returns = (position.current_value - position.invested_amount + 
                        position.accumulated_fees + position.accumulated_rewards)
        roi_with_fees = (total_returns / position.invested_amount * 100) if position.invested_amount > 0 else 0
        
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
        
        # Calculate expected proceeds
        expected_proceeds = position.current_value * (1 - slippage_estimate / 100)
        
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
        position = request.position
        
        # Convert range break history to expected format
        break_history = [
            {
                'timestamp': event.timestamp.isoformat(),
                'type': event.type
            }
            for event in position.range_break_history
        ]
        
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
        if whipsaw_result['whipsaw_detected']:
            if whipsaw_result['severity'] > 80:
                alternatives.append(AlternativeStrategy(
                    type='exit'
                ))
            elif whipsaw_result['severity'] > 60:
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
        
        # Map recommendation
        action_map = {
            'exit': 'exit',
            'reduce_position': 'reduce',
            'widen_range': 'widen_range',
            'monitor': 'monitor'
        }
        recommended_action = action_map.get(
            whipsaw_result['recommended_action'],
            'monitor'
        )
        
        return WhipsawDetectionResponse(
            whipsaw_detected=whipsaw_result['whipsaw_detected'],
            severity=whipsaw_result['severity'],
            pattern=pattern,
            recommended_action=recommended_action,
            alternative_strategies=alternatives
        )
    
    async def rebalance_portfolio(
        self,
        request: PortfolioRebalanceRequest
    ) -> PortfolioRebalanceResponse:
        """
        Generate portfolio rebalancing recommendations.
        """
        # Convert positions to expected format
        positions_data = [p.dict() for p in request.positions]
        
        # Generate recommendations
        raw_recommendations = self.portfolio_analyzer.generate_rebalancing_recommendations(
            positions_data,
            request.available_capital,
            request.risk_tolerance
        )
        
        # Convert to response format
        recommendations = []
        for rec in raw_recommendations:
            recommendation = RebalanceRecommendation(
                action=rec['action'],
                token_id=rec.get('token_id'),
                pool_address=rec.get('pool_address'),
                target_percentage=rec.get('target_percentage'),
                suggested_amount=rec.get('suggested_amount'),
                reason=rec['reason']
            )
            recommendations.append(recommendation)
        
        # Calculate expected improvement (simplified)
        current_metrics = self.portfolio_analyzer.calculate_portfolio_metrics(positions_data)
        
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
            expected_portfolio_improvement=improvement
        )
    
    async def calculate_slippage(
        self,
        request: SlippageCalculationRequest
    ) -> SlippageCalculationResponse:
        """
        Calculate dynamic slippage for a trade.
        """
        # Create pool dict for slippage calculator
        pool = {
            'address': request.pool_address,
            'tvl': request.current_tvl,
            'volatility_24h': request.volatility_24h
        }
        
        # Parse pair to get tokens
        if '/' in request.pair:
            token0, token1 = request.pair.split('/')
            pool['token0_symbol'] = token0
            pool['token1_symbol'] = token1
        else:
            pool['token0_symbol'] = 'UNKNOWN'
            pool['token1_symbol'] = 'UNKNOWN'
        
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
    
    async def assess_risk(self) -> RiskAssessmentResponse:
        """
        Get current portfolio risk assessment.
        """
        # For now, return example data
        # In production, would fetch actual positions
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
            highest_pool_percentage=concentration_analysis['highest_pool_percentage'],
            highest_token_percentage=concentration_analysis['highest_token_percentage']
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
        if concentration_risk.highest_pool_percentage > 25:
            warnings.append("High concentration in single pool")
        if risk_score > 70:
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
        executor_address: Optional[str] = None
    ) -> PerformanceAnalyticsResponse:
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


# Create singleton instance
strategy_service = StrategyService()