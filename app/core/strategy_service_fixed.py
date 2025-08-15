"""Fixed version of analyze_position_switches that works."""
from typing import Dict, List
from app.core.logger import logger
from app.core.strategy_calculator import StrategyCalculator
from app.schemas.strategy_v2 import SwitchRecommendation

async def analyze_position_switches_working(
    user_address: str,
    token_ids: List[int],
    strategy_service
) -> Dict:
    """
    Working version of switch analysis.
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
    
    # Calculate wallet size
    wallet_size = sum(p.get('current_value', 0) for p in positions_list)
    logger.info(f"Wallet size: ${wallet_size}")
    
    # Fetch real pool data from the whitelist using batch endpoint
    from app.core.pools_service import pools_service
    
    # Import whitelisted pools from main strategy service
    from app.core.strategy_service import WHITELISTED_POOLS
    
    # Convert set to list for batch fetch
    whitelist_addresses = list(WHITELISTED_POOLS)
    
    # Fetch all whitelisted pools in batch with real APRs
    test_pools = []
    try:
        # Use the batch fetch method to get all pools at once
        batch_pools = await pools_service.get_pools_batch(whitelist_addresses)
        
        for pool_data in batch_pools:
            if pool_data:
                # Use the real APR from pool data (base_apr is the pool's actual APR)
                apr = pool_data.get('apr', pool_data.get('base_apr', 0))
                test_pools.append({
                    'address': pool_data.get('address', ''),
                    'symbol': pool_data.get('symbol', 'Unknown'),
                    'apr': apr,  # Real APR from chain
                    'tvl_usd': pool_data.get('tvl_usd', 0),
                    'volume_24h': pool_data.get('volume_24h', 0)
                })
                logger.info(f"Fetched pool {pool_data.get('symbol')} with real APR: {apr}%")
    except Exception as e:
        logger.error(f"Failed to fetch batch pool data: {e}")
        # Try individual fetches as fallback
        for pool_address in whitelist_addresses[:5]:  # Limit to first 5 for performance
            try:
                pool_data = await pools_service.get_pool(pool_address)
                if pool_data:
                    apr = pool_data.get('apr', pool_data.get('base_apr', 0))
                    test_pools.append({
                        'address': pool_address,
                        'symbol': pool_data.get('symbol', 'Unknown'),
                        'apr': apr,
                        'tvl_usd': pool_data.get('tvl_usd', 0),
                        'volume_24h': pool_data.get('volume_24h', 0)
                    })
                    logger.info(f"Fetched pool {pool_data.get('symbol')} with real APR: {apr}%")
            except Exception as e2:
                logger.error(f"Failed to fetch pool data for {pool_address}: {e2}")
    
    if not test_pools:
        logger.warning("No pools fetched from whitelist")
        return {
            'recommendations': [],
            'total_positions_analyzed': len(positions_list),
            'positions_recommended_for_switch': 0,
            'total_expected_apr_improvement': 0,
            'estimated_total_gas_cost': 0
        }
    
    # Calculate allocation weights for candidate pools
    candidate_pools = []
    for pool in test_pools:
        safety_score = calculator.calculate_simple_safety_score(pool)
        allocation_weight = calculator.calculate_allocation_weight(
            pool,
            safety_score,
            wallet_size
        )
        
        candidate_pools.append({
            'address': pool['address'],
            'apr': pool['apr'],
            'safety_score': safety_score,
            'allocation_weight': allocation_weight,
            'tvl': pool['tvl_usd'],
            'volume_24h': pool['volume_24h'],
            'pair': pool['symbol']
        })
    
    # Sort by allocation weight
    candidate_pools.sort(key=lambda x: x['allocation_weight'], reverse=True)
    
    logger.info(f"Top candidate: {candidate_pools[0]['pair']} with weight {candidate_pools[0]['allocation_weight']:.1f}")
    
    # Analyze each position
    recommendations = []
    
    # Import cooldown manager
    from app.core.cooldown_manager import cooldown_manager
    
    for position in positions_list:
        current_pool = position.get('pool_address', '').lower()
        position_id = position.get('token_id', position.get('id'))
        
        # Check if position is in cooldown
        cooldown_info = await cooldown_manager.check_cooldown(
            user_address=user_address,
            pool_address=current_pool
        )
        
        if cooldown_info:
            logger.info(f"Position {position_id} is in cooldown for pool {current_pool} - skipping switch recommendation")
            continue
        
        # Get BASE APR from pool data (not effective APR which is user-specific)
        current_apr = 0
        if current_pool:
            try:
                from app.core.pools_service import pools_service
                pool_data = await pools_service.get_pool(current_pool)
                # Use base APR, not effective APR
                current_apr = pool_data.get('apr', pool_data.get('base_apr', 50))
                logger.info(f"Fetched current pool BASE APR: {current_apr}% for {current_pool}")
            except Exception as e:
                logger.warning(f"Could not fetch APR for current pool {current_pool}: {e}")
                # Try to get from position data as fallback
                pool_info = position.get('pool_info', {})
                current_apr = pool_info.get('apr', pool_info.get('base_apr', 50))
        
        logger.info(f"Position {position_id} current BASE APR: {current_apr}%")
        
        # Track if we found any valid switch
        found_switch = False
        
        # Find best switch
        for candidate in candidate_pools[:3]:  # Check top 3
            candidate_pool = candidate['address'].lower()
            
            # CRITICAL: Skip if it's the same pool
            if current_pool == candidate_pool:
                logger.info(f"Skipping same pool: {candidate['pair']} for position {position_id}")
                continue
            
            # Calculate actual APR improvement
            apr_difference = candidate['apr'] - current_apr
            apr_improvement = (apr_difference / current_apr) if current_apr > 0 else (apr_difference / 100)
            
            # Only recommend if there's a meaningful improvement
            min_improvement_threshold = 0.2 if wallet_size < 1000 else 0.5  # 20% for small, 50% for larger wallets
            
            # Skip if candidate APR is lower or improvement is too small
            if apr_difference <= 0:
                logger.info(f"Skipping {candidate['pair']} - APR ({candidate['apr']}%) not better than current ({current_apr}%)")
                continue
            
            if apr_improvement > min_improvement_threshold:
                recommendation = SwitchRecommendation(
                    token_id=position_id,
                    current_pool_address=position['pool_address'],
                    current_apr=current_apr,
                    current_value=position.get('current_value', 500),
                    target_pool_address=candidate['address'],
                    target_pool_symbol=candidate['pair'],
                    target_apr=candidate['apr'],
                    target_safety_score=candidate['safety_score'],
                    target_allocation_weight=candidate['allocation_weight'],
                    should_switch=True,
                    reason=f"Switch from {current_apr:.0f}% to {candidate['apr']:.0f}% APR ({apr_improvement*100:.0f}% improvement)",
                    expected_benefit=apr_difference,
                    breakeven_days=2.0,  # Rough estimate
                    estimated_gas_cost=100.0
                )
                recommendations.append(recommendation)
                found_switch = True
                break  # Only one recommendation per position
        
        if not found_switch:
            logger.info(f"No valid switch found for position {position_id} - already in optimal pool or no better alternatives")
    
    total_apr_improvement = sum(r.expected_benefit for r in recommendations)
    total_gas_cost = sum(r.estimated_gas_cost for r in recommendations)
    
    # Calculate portfolio summary
    from app.schemas.strategy_v2 import PortfolioSummary
    
    total_value = sum(p.get('current_value_usd', p.get('current_value', 0)) for p in positions_list)
    total_pnl = sum(p.get('pnl_usd', 0) for p in positions_list)
    total_emissions = sum(p.get('emissions_value_usd', 0) for p in positions_list)
    
    # Calculate weighted APR
    weighted_apr = 0
    for p in positions_list:
        value = p.get('current_value_usd', p.get('current_value', 0))
        apr = p.get('current_apr', 50)  # Default APR
        if total_value > 0:
            weighted_apr += (value / total_value) * apr
    
    # Calculate concentration risk
    token_values = {}
    for p in positions_list:
        pool_info = p.get('pool_info', {})
        token0 = pool_info.get('token0_symbol', 'UNKNOWN')
        token1 = pool_info.get('token1_symbol', 'UNKNOWN')
        value = p.get('current_value_usd', p.get('current_value', 0))
        
        # Simplified: assume 50/50 split
        token_values[token0] = token_values.get(token0, 0) + value * 0.5
        token_values[token1] = token_values.get(token1, 0) + value * 0.5
    
    concentration_risk = {}
    if total_value > 0:
        concentration_risk = {token: (value / total_value) * 100 
                            for token, value in token_values.items()}
    
    # Identify top and under performers
    sorted_positions = sorted(positions_list, 
                            key=lambda x: x.get('pnl_percentage', 0), 
                            reverse=True)
    
    top_performers = []
    for p in sorted_positions[:3]:
        top_performers.append({
            'token_id': p.get('token_id', p.get('id')),
            'pool': p.get('pool_info', {}).get('symbol', 'Unknown'),
            'pnl_percentage': p.get('pnl_percentage', 0),
            'value_usd': p.get('current_value_usd', p.get('current_value', 0))
        })
    
    underperformers = []
    for p in sorted_positions[-3:] if len(sorted_positions) > 3 else []:
        underperformers.append({
            'token_id': p.get('token_id', p.get('id')),
            'pool': p.get('pool_info', {}).get('symbol', 'Unknown'),
            'pnl_percentage': p.get('pnl_percentage', 0),
            'value_usd': p.get('current_value_usd', p.get('current_value', 0))
        })
    
    # Calculate risk score (simplified)
    risk_score = 50.0  # Base score
    # Increase risk if highly concentrated
    max_concentration = max(concentration_risk.values()) if concentration_risk else 0
    if max_concentration > 40:
        risk_score += (max_concentration - 40) * 0.5
    # Decrease risk for diversification
    if len(positions_list) > 5:
        risk_score -= 10
    risk_score = max(0, min(100, risk_score))
    
    portfolio_summary = PortfolioSummary(
        total_value_usd=total_value,
        total_positions=len(positions_list),
        total_pnl_usd=total_pnl,
        total_pnl_percentage=(total_pnl / total_value * 100) if total_value > 0 else 0,
        weighted_apr=weighted_apr,
        total_emissions_value_usd=total_emissions,
        risk_score=risk_score,
        concentration_risk=concentration_risk,
        top_performers=top_performers,
        underperformers=underperformers
    )
    
    return {
        'portfolio_summary': portfolio_summary,
        'recommendations': recommendations,
        'total_positions_analyzed': len(positions_list),
        'positions_recommended_for_switch': len(recommendations),
        'total_expected_apr_improvement': total_apr_improvement,
        'estimated_total_gas_cost': total_gas_cost
    }