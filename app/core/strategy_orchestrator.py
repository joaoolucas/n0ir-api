"""
Strategy Orchestrator for comprehensive portfolio analysis.
Coordinates parallel execution of multiple analyses for optimal decision making.
"""
import asyncio
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime
import time

from app.core.logger import logger
from app.core.cache import cache_manager
from app.core.positions_service import positions_service
from app.core.pools_service import pools_service
from app.core.rebalancing_config import RebalancingStrategy, RebalancingThresholds
from app.schemas.strategy import (
    AnalyzeEntryRequest,
    ExitAnalysisRequest,
    OpportunitiesRequest
)
# Schema imports will be handled in the endpoint to avoid circular imports


class StrategyOrchestrator:
    """
    Orchestrates comprehensive strategy analysis with parallel execution
    and intelligent caching.
    """
    
    # Cache TTLs
    USER_CONTEXT_TTL = 10  # 10 seconds for user-specific data
    ANALYSIS_TTL = 5       # 5 seconds for analysis results
    
    def __init__(self, strategy_service, rebalancing_strategy: RebalancingStrategy = None):
        """Initialize orchestrator with strategy service and rebalancing strategy."""
        self.strategy_service = strategy_service
        self.cache_manager = cache_manager
        self.positions_service = positions_service
        self.pools_service = pools_service
        self.rebalancing_strategy = rebalancing_strategy or RebalancingStrategy()
    
    async def comprehensive_screen(
        self,
        executor_address: str,
        available_capital: float
    ) -> Dict[str, Any]:
        """
        Main entry point for enhanced screening with full analysis.
        
        Args:
            executor_address: User's wallet address
            available_capital: Available USDC for investment
            
        Returns:
            Comprehensive screening response with all analyses
        """
        start_time = time.time()
        
        # Check cache first
        cache_key = self._build_cache_key(executor_address, available_capital)
        cached_result = await self.cache_manager.get_custom(cache_key)
        if cached_result:
            logger.info(f"Cache hit for comprehensive screen: {executor_address}")
            cached_result['cache_hit'] = True
            return cached_result
        
        try:
            # Fetch user context in parallel
            user_context = await self._fetch_user_context(executor_address, available_capital)
            
            # Get screening opportunities (existing logic)
            opportunities = await self._get_base_opportunities(executor_address, available_capital)
            
            # No longer filtering by cooldowns
            valid_opportunities = opportunities
            
            # Run parallel analyses
            analyses = await self._run_parallel_analyses(
                user_context,
                valid_opportunities,
                available_capital
            )
            
            # Build decision matrix
            decision_matrix = self._build_decision_matrix(
                analyses,
                available_capital,
                len(user_context['positions'])
            )
            
            # Detect risk alerts
            risk_alerts = self._detect_risk_alerts(
                user_context,
                analyses,
                available_capital
            )
            
            # Convert opportunities to dicts if they're objects
            opportunities_as_dicts = []
            for opp in valid_opportunities:
                if hasattr(opp, 'dict'):
                    opportunities_as_dicts.append(opp.dict())
                else:
                    opportunities_as_dicts.append(opp)
            
            # Build comprehensive response
            response = {
                'user_context': {
                    'executor_address': executor_address,
                    'available_capital': available_capital,
                    'positions_value': user_context['positions_value'],
                    'total_portfolio_value': available_capital + user_context['positions_value'],
                    'active_positions': len(user_context['positions'])
                },
                'opportunities': opportunities_as_dicts,
                'entry_analyses': analyses['entries'],
                'exit_recommendations': analyses['exits'],
                'switch_recommendations': analyses['switches'],
                'decision_matrix': decision_matrix,
                'risk_alerts': risk_alerts,
                'analysis_timestamp': datetime.utcnow().isoformat(),
                'cache_hit': False,
                'analysis_time_ms': int((time.time() - start_time) * 1000)
            }
            
            # Cache the result
            await self.cache_manager.set_custom(
                cache_key,
                response,
                ttl=self.ANALYSIS_TTL
            )
            
            logger.info(
                f"Comprehensive screen completed for {executor_address} "
                f"in {response['analysis_time_ms']}ms"
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Error in comprehensive screen: {e}")
            raise
    
    async def _fetch_user_context(
        self,
        executor_address: str,
        available_capital: float
    ) -> Dict[str, Any]:
        """
        Fetch all user data in parallel.
        
        Returns dict with positions and calculated values.
        """
        tasks = [
            self.positions_service.get_positions_by_owner(executor_address)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle positions
        positions = []
        positions_value = 0
        if not isinstance(results[0], Exception):
            positions = results[0]
            positions_value = sum(
                p.current_value_usd for p in positions 
                if p.current_value_usd
            )
        else:
            logger.warning(f"Failed to fetch positions: {results[0]}")
        
        
        return {
            'positions': positions,
            'positions_value': positions_value
        }
    
    async def _get_base_opportunities(
        self,
        executor_address: str,
        available_capital: float
    ) -> List[Dict]:
        """Get base opportunities using existing strategy service."""
        request = OpportunitiesRequest(
            executor_address=executor_address,
            available_capital=available_capital
        )
        response = await self.strategy_service.find_opportunities(request)
        return response.opportunities
    
    
    async def _run_parallel_analyses(
        self,
        user_context: Dict,
        opportunities: List[Dict],
        available_capital: float
    ) -> Dict[str, List]:
        """
        Run all analyses in parallel with error isolation.
        
        Returns dict with entries, exits, and switches lists.
        """
        # Limit opportunities for performance
        top_opportunities = opportunities[:10]
        
        # Create analysis tasks
        entry_tasks = [
            self._analyze_entry(opp, available_capital)
            for opp in top_opportunities
        ]
        
        exit_tasks = [
            self._analyze_exit(pos)
            for pos in user_context['positions']
        ]
        
        # For switches, analyze all positions together
        switch_task = self._analyze_switches(
            user_context['positions'],
            top_opportunities
        )
        
        # Execute all tasks in parallel
        all_tasks = entry_tasks + exit_tasks + [switch_task]
        results = await asyncio.gather(*all_tasks, return_exceptions=True)
        
        # Separate results
        entries = []
        exits = []
        switches = []
        
        # Process entry results
        for i, result in enumerate(results[:len(entry_tasks)]):
            if not isinstance(result, Exception) and result:
                entries.append(result)
            elif isinstance(result, Exception):
                logger.warning(f"Entry analysis failed: {result}")
        
        # Process exit results
        exit_start = len(entry_tasks)
        exit_end = exit_start + len(exit_tasks)
        for i, result in enumerate(results[exit_start:exit_end]):
            if not isinstance(result, Exception) and result:
                exits.append(result)
            elif isinstance(result, Exception):
                logger.warning(f"Exit analysis failed: {result}")
        
        # Process switch result
        if len(results) > exit_end:
            switch_result = results[-1]
            if not isinstance(switch_result, Exception) and switch_result:
                switches = switch_result
            elif isinstance(switch_result, Exception):
                logger.warning(f"Switch analysis failed: {switch_result}")
        
        return {
            'entries': entries,
            'exits': exits,
            'switches': switches
        }
    
    async def _analyze_entry(
        self,
        opportunity: Any,
        available_capital: float
    ) -> Optional[Dict]:
        """Analyze entry opportunity for a single pool."""
        try:
            # Handle both dict and object types
            if hasattr(opportunity, 'pool_address'):
                # It's a PoolOpportunity object
                pool_address = opportunity.pool_address
                pool_name = getattr(opportunity, 'pool_name', 'Unknown')
                recommended_allocation = getattr(opportunity, 'recommended_allocation', available_capital * 0.25)
                safety_score = getattr(opportunity, 'safety_score', 0)
            else:
                # It's a dict
                pool_address = opportunity['pool_address']
                pool_name = opportunity.get('pool_name', 'Unknown')
                recommended_allocation = opportunity.get('recommended_allocation', available_capital * 0.25)
                safety_score = opportunity.get('safety_score', 0)
            
            # Use recommended allocation or calculate based on available capital
            amount = min(recommended_allocation, available_capital)
            
            request = AnalyzeEntryRequest(
                pool_address=pool_address,
                amount_usdc=amount
            )
            
            response = await self.strategy_service.analyze_entry(request)
            
            if response.should_enter:
                return {
                    'pool_address': pool_address,
                    'pool_name': pool_name,
                    'confidence_score': response.confidence_score,
                    'optimal_allocation': amount,
                    'expected_apr': response.effective_apr,
                    'risk_metrics': {
                        'safety_score': safety_score,
                        'slippage': response.slippage.dict() if hasattr(response.slippage, 'dict') else response.slippage,
                        'warnings': response.warnings
                    },
                    'optimal_range': response.optimal_range.dict() if hasattr(response.optimal_range, 'dict') else response.optimal_range
                }
            return None
            
        except Exception as e:
            logger.error(f"Error analyzing entry for pool: {e}")
            return None
    
    async def _analyze_exit(self, position: Any) -> Optional[Dict]:
        """Analyze exit opportunity for a single position."""
        try:
            # Check if position is out of range or underperforming
            exit_reason = "performance"  # Default reason
            
            if hasattr(position, 'in_range') and not position.in_range:
                exit_reason = "range_break"
            
            request = ExitAnalysisRequest(
                token_id=position.id,
                exit_reason=exit_reason
            )
            
            response = await self.strategy_service.analyze_exit(request)
            
            if response.should_exit:
                return {
                    'token_id': position.id,
                    'pool_address': position.pool_address,
                    'urgency': response.exit_strategy.get('urgency', 'low'),
                    'reason': exit_reason,
                    'expected_proceeds': response.expected_proceeds,
                    'roi_percentage': response.roi_percentage,
                    'slippage_estimate': response.slippage_estimate
                }
            return None
            
        except Exception as e:
            logger.error(f"Error analyzing exit for position {position.id}: {e}")
            return None
    
    async def _analyze_switches(
        self,
        positions: List[Any],
        opportunities: List[Dict]
    ) -> List[Dict]:
        """Analyze potential position switches."""
        try:
            if not positions or not opportunities:
                return []
            
            # Get token IDs from positions
            token_ids = [p.id for p in positions]
            
            # Call switch analysis
            result = await self.strategy_service.analyze_position_switches(
                user_address=positions[0].owner if positions else "",
                token_ids=token_ids
            )
            
            # Format switch recommendations
            switches = []
            for rec in result.get('recommendations', []):
                switches.append({
                    'from_token_id': rec['token_id'],
                    'from_pool': rec['current_pool'],
                    'to_pool_address': rec['recommended_pool'],
                    'to_pool_name': rec.get('recommended_pool_name', 'Unknown'),
                    'apr_improvement': rec.get('apr_improvement', 0),
                    'net_benefit_after_costs': rec.get('net_benefit', 0),
                    'confidence': rec.get('confidence', 0)
                })
            
            return switches[:5]  # Limit to top 5 switches
            
        except Exception as e:
            logger.error(f"Error analyzing switches: {e}")
            return []
    
    def _build_decision_matrix(
        self,
        analyses: Dict[str, List],
        available_capital: float,
        active_positions: int
    ) -> Dict:
        """Build decision matrix from analyses with smart rebalancing thresholds."""
        immediate_actions = []
        scheduled_actions = []
        
        # REBALANCING THRESHOLDS - Prevent unnecessary churn
        MIN_CONFIDENCE_FOR_ENTRY = 75  # Only enter if confidence > 75%
        MIN_APR_IMPROVEMENT_FOR_SWITCH = 35  # Switch only if APR improves by 35%+ (updated from quant analysis)
        MIN_NET_BENEFIT_FOR_SWITCH = 500  # Switch only if net benefit > $500
        MIN_ALLOCATION_SIZE = 10  # Minimum position size $10 for testing
        MAX_GAS_COST_RATIO = 0.05  # Gas can be up to 5% for small test positions
        
        # Priority 1: Urgent exits (always execute these)
        for exit in analyses['exits']:
            if exit['urgency'] in ['critical', 'high']:
                immediate_actions.append({
                    'type': 'exit',
                    'token_id': exit['token_id'],
                    'priority': 1 if exit['urgency'] == 'critical' else 2,
                    'reason': exit['reason']
                })
        
        # Priority 2: High confidence entries (using rebalancing strategy)
        rejected_count = {'low_confidence': 0, 'low_apr': 0, 'gas_cost': 0, 'small_size': 0}
        
        for entry in sorted(analyses['entries'], 
                          key=lambda x: x['confidence_score'], 
                          reverse=True)[:5]:  # Check top 5
            
            # Use rebalancing strategy to determine if we should enter
            should_enter, reason = self.rebalancing_strategy.should_enter_position(
                confidence=entry['confidence_score'],
                expected_apr=entry['expected_apr'],
                allocation=entry['optimal_allocation'],
                available_capital=available_capital
            )
            
            if should_enter:
                immediate_actions.append({
                    'type': 'entry',
                    'pool': entry['pool_address'],
                    'priority': 3,
                    'allocation': entry['optimal_allocation'],
                    'confidence': entry['confidence_score'],
                    'expected_apr': entry['expected_apr'],
                    'reason': reason
                })
            else:
                # Track why entries were rejected
                if 'Confidence' in reason:
                    rejected_count['low_confidence'] += 1
                elif 'APR' in reason:
                    rejected_count['low_apr'] += 1
                elif 'Gas' in reason:
                    rejected_count['gas_cost'] += 1
                elif 'Allocation' in reason:
                    rejected_count['small_size'] += 1
                logger.debug(f"Entry rejected: {reason}")
        
        # Priority 3: Beneficial switches (with strict thresholds)
        for switch in analyses['switches']:
            # Apply multiple thresholds to prevent marginal switches
            if (switch['apr_improvement'] >= MIN_APR_IMPROVEMENT_FOR_SWITCH and
                switch['net_benefit_after_costs'] > MIN_NET_BENEFIT_FOR_SWITCH and
                switch.get('confidence', 0) > 70):
                
                scheduled_actions.append({
                    'type': 'switch',
                    'schedule': 'tomorrow',
                    'from_token': switch['from_token_id'],
                    'to_pool': switch['to_pool_address'],
                    'apr_improvement': switch['apr_improvement'],
                    'expected_benefit': switch['net_benefit_after_costs']
                })
        
        # Calculate optimal capital allocation
        optimal_positions = min(
            max(3, int((available_capital / 1000) ** 0.5)),  # Square root rule
            10  # Max positions
        )
        
        allocation_per_position = available_capital / optimal_positions if optimal_positions > 0 else 0
        
        return {
            'immediate_actions': sorted(immediate_actions, key=lambda x: x['priority']),
            'scheduled_actions': scheduled_actions,
            'capital_allocation': {
                'recommended_positions': optimal_positions,
                'allocation_per_position': round(allocation_per_position, 2),
                'active_positions': active_positions
            }
        }
    
    def _detect_risk_alerts(
        self,
        user_context: Dict,
        analyses: Dict,
        available_capital: float
    ) -> List[Dict]:
        """Detect and generate risk alerts."""
        alerts = []
        
        # Check portfolio concentration
        if user_context['positions']:
            total_value = user_context['positions_value'] + available_capital
            if user_context['positions_value'] / total_value > 0.95:
                alerts.append({
                    'type': 'concentration',
                    'message': 'Over 95% of capital is deployed',
                    'severity': 'medium'
                })
        
        # Check for multiple urgent exits
        urgent_exits = [e for e in analyses['exits'] if e['urgency'] in ['critical', 'high']]
        if len(urgent_exits) > 2:
            alerts.append({
                'type': 'portfolio_health',
                'message': f'{len(urgent_exits)} positions require urgent attention',
                'severity': 'high'
            })
        
        # Check if too many positions
        if len(user_context['positions']) > 15:
            alerts.append({
                'type': 'over_diversification',
                'message': 'Portfolio has too many positions, consider consolidation',
                'severity': 'medium'
            })
        
        # Check if capital is too fragmented
        if available_capital > 0 and len(analyses['entries']) > 0:
            min_position = 10  # $10 minimum position size for testing
            if available_capital / len(analyses['entries']) < min_position:
                alerts.append({
                    'type': 'capital_fragmentation',
                    'message': 'Available capital too small for optimal diversification',
                    'severity': 'low'
                })
        
        return alerts
    
    def _build_cache_key(self, executor_address: str, available_capital: float) -> str:
        """Build cache key for user screening."""
        return f"screen:comprehensive:{executor_address.lower()}:{available_capital}"