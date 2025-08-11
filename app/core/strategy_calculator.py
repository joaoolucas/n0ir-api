"""
Strategy calculator for quantitative scoring and position analysis.
"""
import math
from typing import Dict, Tuple, Optional, List
from datetime import datetime, timedelta


class StrategyCalculator:
    """
    Implements the quantitative scoring model and strategy calculations.
    """
    
    # Scoring weights for the composite model
    WEIGHTS = {
        'fee_efficiency': 0.30,
        'volume_consistency': 0.25,
        'liquidity_depth': 0.20,
        'correlation_benefit': 0.15,
        'execution_quality': 0.10
    }
    
    # Risk profile configurations
    RISK_PROFILES = {
        'conservative': {
            'max_position_size': 0.10,  # 10% of capital
            'min_tvl': 1_000_000,
            'min_volume_24h': 200_000,
            'max_volatility': 20,
            'range_multiplier': 2.5
        },
        'balanced': {
            'max_position_size': 0.20,  # 20% of capital
            'min_tvl': 500_000,
            'min_volume_24h': 100_000,
            'max_volatility': 40,
            'range_multiplier': 2.0
        },
        'aggressive': {
            'max_position_size': 0.30,  # 30% of capital
            'min_tvl': 250_000,
            'min_volume_24h': 50_000,
            'max_volatility': 60,
            'range_multiplier': 1.5
        }
    }
    
    def calculate_pool_score(self, pool_data: Dict) -> float:
        """
        Calculate composite score for a pool using the quantitative model.
        Score = w₁·F + w₂·V + w₃·L + w₄·C + w₅·E
        
        Args:
            pool_data: Pool information including TVL, volume, APR, etc.
            
        Returns:
            Score between 0-100
        """
        scores = {}
        
        # Fee Efficiency Score (F)
        apr = pool_data.get('apr', 0)
        fee_tier = pool_data.get('fee_tier', 0.003)  # 0.3% default
        scores['fee_efficiency'] = self._calculate_fee_efficiency_score(apr, fee_tier)
        
        # Volume Consistency Score (V)
        volume_24h = pool_data.get('volume_24h', 0)
        tvl = pool_data.get('tvl', 1)  # Avoid division by zero
        volume_tvl_ratio = volume_24h / tvl if tvl > 0 else 0
        scores['volume_consistency'] = self._calculate_volume_consistency_score(volume_tvl_ratio)
        
        # Liquidity Depth Score (L)
        scores['liquidity_depth'] = self._calculate_liquidity_depth_score(tvl)
        
        # Correlation Benefit Score (C)
        # Simplified - in production would analyze against existing portfolio
        scores['correlation_benefit'] = 50  # Neutral score without portfolio context
        
        # Execution Quality Score (E)
        tick_spacing = pool_data.get('tick_spacing', 60)
        scores['execution_quality'] = self._calculate_execution_quality_score(tick_spacing, tvl)
        
        # Calculate weighted composite score
        composite_score = sum(
            scores[component] * weight 
            for component, weight in self.WEIGHTS.items()
        )
        
        return min(100, max(0, composite_score))
    
    def _calculate_fee_efficiency_score(self, apr: float, fee_tier: float) -> float:
        """Calculate fee efficiency score based on APR and fee tier."""
        if apr <= 0:
            return 0
        
        # Target APR of 50% gets maximum score
        apr_score = min(100, (apr / 50) * 100)
        
        # Lower fee tiers are better for entry/exit
        fee_score = 100 * (1 - min(1, fee_tier / 0.01))  # 1% max fee
        
        return (apr_score * 0.7 + fee_score * 0.3)
    
    def _calculate_volume_consistency_score(self, volume_tvl_ratio: float) -> float:
        """Calculate volume consistency score."""
        # Optimal ratio around 0.5 (50% daily volume relative to TVL)
        if volume_tvl_ratio <= 0:
            return 0
        elif volume_tvl_ratio <= 0.1:
            return volume_tvl_ratio * 200  # Linear up to 20
        elif volume_tvl_ratio <= 0.5:
            return 20 + (volume_tvl_ratio - 0.1) * 200  # Linear 20-100
        elif volume_tvl_ratio <= 1.0:
            return 100 - (volume_tvl_ratio - 0.5) * 40  # Decline 100-80
        else:
            return max(0, 80 - (volume_tvl_ratio - 1.0) * 20)  # Further decline
    
    def _calculate_liquidity_depth_score(self, tvl: float) -> float:
        """Calculate liquidity depth score."""
        if tvl <= 0:
            return 0
        elif tvl < 100_000:
            return tvl / 100_000 * 20  # Up to 20 for small pools
        elif tvl < 500_000:
            return 20 + (tvl - 100_000) / 400_000 * 30  # 20-50
        elif tvl < 2_000_000:
            return 50 + (tvl - 500_000) / 1_500_000 * 30  # 50-80
        elif tvl < 10_000_000:
            return 80 + (tvl - 2_000_000) / 8_000_000 * 20  # 80-100
        else:
            return 100
    
    def _calculate_execution_quality_score(self, tick_spacing: int, tvl: float) -> float:
        """Calculate execution quality score based on tick spacing and liquidity."""
        # Lower tick spacing is better for precision
        tick_score = 100 * (1 - min(1, tick_spacing / 200))
        
        # Higher TVL means better execution
        tvl_score = self._calculate_liquidity_depth_score(tvl) * 0.5
        
        return (tick_score * 0.6 + tvl_score * 0.4)
    
    def calculate_optimal_range(
        self, 
        current_price: float, 
        volatility_24h: float,
        risk_profile: str = 'balanced'
    ) -> Tuple[int, int]:
        """
        Calculate optimal tick range for concentrated liquidity position.
        
        Args:
            current_price: Current pool price
            volatility_24h: 24-hour volatility percentage
            risk_profile: Risk profile for range calculation
            
        Returns:
            Tuple of (lower_tick, upper_tick)
        """
        profile = self.RISK_PROFILES[risk_profile]
        range_multiplier = profile['range_multiplier']
        
        # Calculate price range based on volatility
        # Using 2-sigma approach for range calculation
        price_range_percent = volatility_24h * range_multiplier / 100
        
        lower_price = current_price * (1 - price_range_percent)
        upper_price = current_price * (1 + price_range_percent)
        
        # Convert prices to ticks (simplified - assumes tick spacing of 60)
        # In production, this would use the actual pool's tick math
        lower_tick = self._price_to_tick(lower_price)
        upper_tick = self._price_to_tick(upper_price)
        
        # Ensure ticks are aligned to tick spacing
        tick_spacing = 60
        lower_tick = (lower_tick // tick_spacing) * tick_spacing
        upper_tick = ((upper_tick // tick_spacing) + 1) * tick_spacing
        
        return (lower_tick, upper_tick)
    
    def _price_to_tick(self, price: float) -> int:
        """Convert price to tick (simplified Uniswap V3 math)."""
        # This is a simplified version - actual implementation would use proper math
        # tick = log(sqrt(price)) / log(1.0001)
        if price <= 0:
            return 0
        return int(math.log(math.sqrt(price)) / math.log(1.0001))
    
    def _tick_to_price(self, tick: int) -> float:
        """Convert tick to price (simplified Uniswap V3 math)."""
        # price = (1.0001^tick)^2
        return (1.0001 ** tick) ** 2
    
    def calculate_position_size(
        self, 
        pool_stats: Dict,
        available_capital: float,
        risk_profile: str = 'balanced',
        existing_positions: List[Dict] = None
    ) -> Tuple[float, float]:
        """
        Calculate optimal position size using Modified Kelly Criterion.
        
        Args:
            pool_stats: Pool statistics including APR, volatility
            available_capital: Available USDC for investment
            risk_profile: Risk profile
            existing_positions: Existing positions for concentration check
            
        Returns:
            Tuple of (recommended_amount, max_amount)
        """
        profile = self.RISK_PROFILES[risk_profile]
        max_position_percent = profile['max_position_size']
        
        # Base position size from Kelly Criterion
        expected_return = pool_stats.get('apr', 0) / 100 / 365  # Daily return
        volatility = pool_stats.get('volatility_24h', 20) / 100
        
        if volatility > 0:
            kelly_fraction = expected_return / (volatility ** 2)
            # Apply safety factor (use 25% of Kelly for crypto)
            safe_kelly = kelly_fraction * 0.25
        else:
            safe_kelly = 0.1  # Default 10% if no volatility data
        
        # Calculate recommended amount
        recommended_amount = available_capital * min(safe_kelly, max_position_percent)
        
        # Check concentration limits if we have existing positions
        if existing_positions:
            total_invested = sum(p.get('invested_amount', 0) for p in existing_positions)
            total_portfolio = total_invested + available_capital
            
            # Don't exceed 25% in any single position
            max_single_position = total_portfolio * 0.25
            recommended_amount = min(recommended_amount, max_single_position - total_invested)
        
        # Ensure minimum position size of $1000
        if recommended_amount < 1000:
            recommended_amount = min(1000, available_capital * max_position_percent)
        
        max_amount = available_capital * max_position_percent
        
        return (recommended_amount, max_amount)
    
    def calculate_expected_returns(
        self,
        pool: Dict,
        position_size: float,
        time_horizon_days: int = 30
    ) -> Dict:
        """
        Calculate expected returns for a position.
        
        Args:
            pool: Pool data
            position_size: Position size in USDC
            time_horizon_days: Time horizon for calculation
            
        Returns:
            Dictionary with return metrics
        """
        apr = pool.get('apr', 0)
        daily_rate = apr / 365 / 100
        
        # Calculate expected returns
        expected_fees = position_size * daily_rate * time_horizon_days
        
        # Estimate rewards (simplified - assumes 30% of returns from rewards)
        expected_rewards = expected_fees * 0.3
        expected_trading_fees = expected_fees * 0.7
        
        # Estimate costs
        estimated_gas = 50  # $50 estimated gas for entry/exit
        volatility = pool.get('volatility_24h', 20)
        estimated_slippage = position_size * (volatility / 100) * 0.01  # Rough estimate
        
        net_returns = expected_fees - estimated_gas - estimated_slippage
        roi_percentage = (net_returns / position_size) * 100 if position_size > 0 else 0
        
        return {
            'expected_fees': expected_fees,
            'expected_trading_fees': expected_trading_fees,
            'expected_rewards': expected_rewards,
            'estimated_gas': estimated_gas,
            'estimated_slippage': estimated_slippage,
            'net_returns': net_returns,
            'roi_percentage': roi_percentage,
            'annualized_return': roi_percentage * (365 / time_horizon_days)
        }
    
    def calculate_risk_metrics(
        self,
        position: Dict,
        pool: Dict,
        portfolio_value: float
    ) -> Dict:
        """
        Calculate risk metrics for a position.
        
        Args:
            position: Position information
            pool: Pool data
            portfolio_value: Total portfolio value
            
        Returns:
            Dictionary with risk metrics
        """
        position_value = position.get('current_value', position.get('invested_amount', 0))
        volatility = pool.get('volatility_24h', 20) / 100
        
        # Calculate 1-day VaR at 95% confidence (1.65 sigma)
        position_var_1d = position_value * volatility * 1.65
        
        # Portfolio impact
        portfolio_impact = position_value / portfolio_value if portfolio_value > 0 else 1.0
        
        # Simplified correlation benefit (would need historical data in production)
        correlation_benefit = 0.1 * (1 - portfolio_impact)  # Diversification benefit
        
        return {
            'position_var_1d': position_var_1d,
            'portfolio_impact': portfolio_impact,
            'correlation_benefit': correlation_benefit,
            'volatility_24h': volatility * 100,
            'concentration_risk': portfolio_impact > 0.25
        }