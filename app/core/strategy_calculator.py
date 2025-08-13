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
    
    # Base L2 Gas Costs (in USDC)
    BASE_GAS_COSTS = {
        'open_position': 0.25,
        'close_position': 0.25,
        'total_lifecycle': 0.50
    }
    
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
        tvl = pool_data.get('tvl_usd', pool_data.get('tvl', 1))  # Support both field names
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
        
        # Use more reasonable APR targets for scoring
        # 100% APR = score 60, 200% = 80, 500% = 100
        if apr >= 500:
            apr_score = 100
        elif apr >= 200:
            apr_score = 80 + (apr - 200) / 300 * 20
        elif apr >= 100:
            apr_score = 60 + (apr - 100) / 100 * 20
        elif apr >= 50:
            apr_score = 40 + (apr - 50) / 50 * 20
        else:
            apr_score = apr / 50 * 40
        
        # Lower fee tiers are better for entry/exit
        fee_score = 100 * (1 - min(1, fee_tier / 0.01))  # 1% max fee
        
        return (apr_score * 0.7 + fee_score * 0.3)
    
    def _calculate_volume_consistency_score(self, volume_tvl_ratio: float) -> float:
        """Calculate volume consistency score - more forgiving for high volume."""
        # High volume is generally good for liquidity and price discovery
        if volume_tvl_ratio <= 0:
            return 0
        elif volume_tvl_ratio <= 0.1:
            return volume_tvl_ratio * 300  # Up to 30 (was 20)
        elif volume_tvl_ratio <= 0.5:
            return 30 + (volume_tvl_ratio - 0.1) * 125  # 30-80 (was 20-100)
        elif volume_tvl_ratio <= 1.0:
            return 80 + (volume_tvl_ratio - 0.5) * 20  # 80-90 (was 100-80)
        elif volume_tvl_ratio <= 5.0:
            return 90 - (volume_tvl_ratio - 1.0) * 5  # 90-70 gradual decline
        else:
            return max(50, 70 - (volume_tvl_ratio - 5.0) * 2)  # Floor at 50
    
    def _calculate_liquidity_depth_score(self, tvl: float) -> float:
        """Calculate liquidity depth score - more generous for smaller pools."""
        if tvl <= 0:
            return 0
        elif tvl < 100_000:
            return tvl / 100_000 * 30  # Up to 30 for small pools (was 20)
        elif tvl < 500_000:
            return 30 + (tvl - 100_000) / 400_000 * 20  # 30-50 (was 20-50)
        elif tvl < 1_000_000:
            return 50 + (tvl - 500_000) / 500_000 * 15  # 50-65
        elif tvl < 2_000_000:
            return 65 + (tvl - 1_000_000) / 1_000_000 * 15  # 65-80
        elif tvl < 5_000_000:
            return 80 + (tvl - 2_000_000) / 3_000_000 * 15  # 80-95
        else:
            return 95 + min(5, (tvl - 5_000_000) / 5_000_000 * 5)  # 95-100
    
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
        risk_profile: str = 'balanced',
        tick_spacing: int = 100
    ) -> Tuple[int, int]:
        """
        Calculate optimal tick range for concentrated liquidity position.
        
        Args:
            current_price: Current pool price
            volatility_24h: 24-hour volatility percentage
            risk_profile: Risk profile for range calculation
            tick_spacing: Pool's tick spacing (1, 10, 50, 100, 200, 2000)
            
        Returns:
            Tuple of (lower_tick, upper_tick)
        """
        profile = self.RISK_PROFILES[risk_profile]
        range_multiplier = profile['range_multiplier']
        
        # Calculate minimum range based on tick spacing
        # Minimum range = tick_spacing / 100
        # E.g., tick_spacing 200 = 2% minimum range (1% each side)
        min_range_percent_each_side = tick_spacing / 100 / 2
        
        # Calculate desired price range based on volatility
        # Using 2-sigma approach for range calculation
        desired_range_percent = volatility_24h * range_multiplier / 100
        
        # Ensure range is at least the minimum allowed by tick spacing
        price_range_percent = max(desired_range_percent, min_range_percent_each_side)
        
        lower_price = current_price * (1 - price_range_percent)
        upper_price = current_price * (1 + price_range_percent)
        
        # Convert prices to ticks
        lower_tick = self._price_to_tick(lower_price)
        upper_tick = self._price_to_tick(upper_price)
        
        # Ensure ticks are aligned to tick spacing
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
        """Convert tick to price (Uniswap V3 math)."""
        # price = 1.0001^tick
        return 1.0001 ** tick
    
    def calculate_optimal_range_from_tick(
        self,
        current_tick: int,
        volatility_24h: float,
        risk_profile: str = 'balanced',
        tick_spacing: int = 100,
        base_apr: float = 100,
        tvl: float = 1_000_000,
        volume_24h: float = 500_000
    ) -> Tuple[int, int]:
        """
        Advanced optimal tick range calculation using quantitative optimization.
        
        This implementation maximizes risk-adjusted returns by balancing:
        - Effective APR (concentration benefit)
        - Range break probability (rebalancing cost)
        - Market depth (execution quality)
        - Volatility regime (risk management)
        
        Args:
            current_tick: Current pool tick
            volatility_24h: 24-hour volatility percentage
            risk_profile: Risk profile for range calculation
            tick_spacing: Pool's tick spacing
            base_apr: Base APR of the pool
            tvl: Total value locked in USD
            volume_24h: 24-hour trading volume in USD
            
        Returns:
            Tuple of (lower_tick, upper_tick)
        """
        # Convert volatility to daily standard deviation
        # Annual vol / sqrt(365) = daily vol
        daily_vol = volatility_24h / 100 / math.sqrt(365)
        
        # Step 1: Calculate base range using 2-sigma confidence for 7-day horizon
        # This gives ~95% probability of staying in range for 7 days
        time_horizon_days = 7
        base_range = 2 * daily_vol * math.sqrt(time_horizon_days)
        
        # Step 2: Apply tick spacing constraints
        # Minimum range must be at least 2x tick spacing to avoid too frequent rebalancing
        min_ticks = max(20, tick_spacing * 2)
        min_range = (1.0001 ** min_ticks - 1) * 2
        base_range = max(base_range, min_range)
        
        # Step 3: Market depth adjustment
        # Deeper markets can support tighter ranges
        depth_factor = self._calculate_market_depth_factor(tvl, volume_24h)
        adjusted_range = base_range * depth_factor
        
        # Step 4: Calculate maximum efficient range
        # Beyond this point, effective APR becomes too low (<10% efficiency)
        max_efficient_range = self._calculate_max_efficient_range(base_apr, tick_spacing)
        
        # Step 5: Apply risk profile adjustment
        risk_multipliers = {
            'conservative': 1.3,   # 30% wider range for safety
            'balanced': 1.0,       # Optimal range
            'aggressive': 0.8      # 20% tighter range for higher APR
        }
        profile_multiplier = risk_multipliers.get(risk_profile, 1.0)
        profile_range = adjusted_range * profile_multiplier
        
        # Step 6: Apply intelligent capping
        # Never exceed 20% total range for capital efficiency
        # Never go below 2% to prevent excessive rebalancing
        # Never exceed max efficient range
        final_range = min(max(profile_range, 0.02), min(0.20, max_efficient_range))
        
        # Step 7: Apply special adjustments for extreme volatility
        if volatility_24h > 100:  # Extremely volatile (memecoins, etc)
            # Force wider range for safety, but still cap at 20%
            final_range = min(0.20, max(final_range, 0.15))
        elif volatility_24h < 5:  # Very stable pairs
            # Can use tighter range, but ensure minimum
            final_range = max(0.02, min(final_range, 0.05))
        
        # Step 8: Convert to ticks
        range_each_side = final_range / 2
        current_price = 1.0001 ** current_tick
        
        lower_price = current_price * (1 - range_each_side)
        upper_price = current_price * (1 + range_each_side)
        
        # Convert prices back to ticks
        lower_tick = int(math.log(lower_price) / math.log(1.0001))
        upper_tick = int(math.log(upper_price) / math.log(1.0001))
        
        # Align to tick spacing
        lower_tick = (lower_tick // tick_spacing) * tick_spacing
        upper_tick = ((upper_tick // tick_spacing) + 1) * tick_spacing
        
        return (lower_tick, upper_tick)
    
    def _calculate_market_depth_factor(self, tvl: float, volume_24h: float) -> float:
        """
        Calculate market depth adjustment factor.
        Deeper markets with higher liquidity can support tighter ranges.
        
        Args:
            tvl: Total value locked in USD
            volume_24h: 24-hour trading volume in USD
            
        Returns:
            Depth factor (0.7-1.5, lower = tighter range allowed)
        """
        # Base depth factor based on TVL
        if tvl >= 10_000_000:  # $10M+ TVL - very deep market
            depth_factor = 0.8
        elif tvl >= 5_000_000:  # $5M+ TVL - deep market
            depth_factor = 0.9
        elif tvl >= 1_000_000:  # $1M+ TVL - normal market
            depth_factor = 1.0
        elif tvl >= 500_000:  # $500k+ TVL - shallow market
            depth_factor = 1.2
        else:  # <$500k TVL - very shallow market
            depth_factor = 1.5
        
        # Adjust based on volume/TVL ratio (market activity)
        volume_tvl_ratio = volume_24h / tvl if tvl > 0 else 0
        
        if volume_tvl_ratio > 1.0:  # Very high activity
            # High volume indicates active trading, can use tighter range
            depth_factor *= 0.9
        elif volume_tvl_ratio > 0.5:  # Normal activity
            # No adjustment needed
            pass
        elif volume_tvl_ratio > 0.1:  # Low activity
            # Lower volume means less price discovery, need wider range
            depth_factor *= 1.1
        else:  # Very low activity
            # Almost no trading, need much wider range
            depth_factor *= 1.3
        
        # Clamp to reasonable bounds
        return max(0.7, min(1.5, depth_factor))
    
    def _calculate_max_efficient_range(self, base_apr: float, tick_spacing: int) -> float:
        """
        Calculate maximum range where effective APR stays above 10% of base APR.
        Beyond this range, capital efficiency becomes too poor.
        
        Args:
            base_apr: Base APR of the pool
            tick_spacing: Pool's tick spacing
            
        Returns:
            Maximum efficient range as decimal (e.g., 0.2 for 20%)
        """
        # We want: effective_apr >= 0.1 * base_apr
        # Using the formula from effective_apr_calculator
        
        multiplier = 100 / tick_spacing
        target_efficiency = 0.10  # We want at least 10% efficiency
        
        if tick_spacing < 100:
            # Formula: effective = base / ((range * multiplier * 100) + 1)
            # We want: 0.1 * base = base / ((range * multiplier * 100) + 1)
            # Solving: range = (10 - 1) / (multiplier * 100)
            max_range = 9 / (multiplier * 100)
        else:
            # Formula: effective = base / (range * multiplier * 100)
            # We want: 0.1 * base = base / (range * multiplier * 100)
            # Solving: range = 10 / (multiplier * 100)
            max_range = 10 / (multiplier * 100)
        
        # Apply reasonable bounds
        # Never exceed 30% range even if formula allows it
        # Never less than 5% to ensure some flexibility
        return max(0.05, min(0.30, max_range))
    
    def calculate_simple_safety_score(self, pool_data: Dict) -> float:
        """
        Calculate simple safety score using only existing data.
        Score = TVL_score * 0.4 + Volume_score * 0.3 + Token_price_score * 0.3
        
        Returns score 0-100, where 100 is safest.
        """
        # TVL Score (0-100): Log scale, $10M+ gets 100
        tvl = pool_data.get('tvl_usd', pool_data.get('tvl', 0))
        if tvl >= 10_000_000:
            tvl_score = 100
        elif tvl >= 5_000_000:
            tvl_score = 90
        elif tvl >= 2_000_000:
            tvl_score = 75
        elif tvl >= 1_000_000:
            tvl_score = 60
        elif tvl >= 500_000:
            tvl_score = 45
        elif tvl >= 250_000:
            tvl_score = 30
        else:
            tvl_score = max(0, (tvl / 250_000) * 30)
        
        # Volume Score (0-100): Based on volume/TVL ratio
        volume_24h = pool_data.get('volume_24h', 0)
        volume_tvl_ratio = volume_24h / tvl if tvl > 0 else 0
        
        if volume_tvl_ratio >= 0.5:  # 50%+ daily volume = very healthy
            volume_score = 100
        elif volume_tvl_ratio >= 0.3:
            volume_score = 85
        elif volume_tvl_ratio >= 0.15:
            volume_score = 70
        elif volume_tvl_ratio >= 0.05:
            volume_score = 50
        else:
            volume_score = max(0, (volume_tvl_ratio / 0.05) * 50)
        
        # Token Price Score (0-100): Use prices as market cap proxy
        # Higher priced tokens often = more established
        token0_price = pool_data.get('token0', {}).get('price_usd', 0)
        token1_price = pool_data.get('token1', {}).get('price_usd', 0)
        
        # Check for stablecoins (price near $1)
        token0_symbol = pool_data.get('token0', {}).get('symbol', '').upper()
        token1_symbol = pool_data.get('token1', {}).get('symbol', '').upper()
        
        stablecoins = {'USDC', 'USDT', 'DAI', 'EURC', 'FRAX', 'BUSD'}
        has_stable = token0_symbol in stablecoins or token1_symbol in stablecoins
        
        if has_stable:
            # Stablecoin pairs get bonus safety score
            token_score = 80
        else:
            # For non-stable pairs, use average price as proxy
            avg_price = (token0_price + token1_price) / 2 if (token0_price + token1_price) > 0 else 0
            
            if avg_price >= 1000:  # High value tokens (ETH, BTC level)
                token_score = 90
            elif avg_price >= 100:
                token_score = 75
            elif avg_price >= 10:
                token_score = 60
            elif avg_price >= 1:
                token_score = 45
            else:
                token_score = max(20, avg_price * 45)  # Min 20 for any token
        
        # Calculate weighted safety score
        safety_score = (tvl_score * 0.4) + (volume_score * 0.3) + (token_score * 0.3)
        
        return min(100, max(0, safety_score))
    
    def calculate_dynamic_position_limit(self, safety_score: float, wallet_size: float) -> float:
        """
        Calculate dynamic position limit based on safety and wallet size.
        More aggressive limits for smaller wallets to ensure proper allocation.
        
        Returns: Maximum position size as percentage (0.1 = 10%)
        """
        # MORE AGGRESSIVE base limits by safety tier
        if safety_score >= 80:  # Very safe
            base_limit = 0.50  # 50% max (was 40%)
        elif safety_score >= 65:  # Safe
            base_limit = 0.40  # 40% max (was 30%)
        elif safety_score >= 50:  # Moderate
            base_limit = 0.35  # 35% max (was 20%)
        elif safety_score >= 35:  # Risky
            base_limit = 0.25  # 25% max (was 15%)
        else:  # Very risky
            base_limit = 0.15  # 15% max (was 10%)
        
        # Adjust for wallet size - MORE AGGRESSIVE for small wallets
        if wallet_size >= 100_000:
            # Large wallets: reduce limits for diversification
            wallet_multiplier = 0.6  # More diversification needed
        elif wallet_size >= 50_000:
            wallet_multiplier = 0.7
        elif wallet_size >= 25_000:
            wallet_multiplier = 0.8
        elif wallet_size >= 10_000:
            wallet_multiplier = 1.0  # No adjustment
        elif wallet_size >= 5_000:
            # $5k-10k wallets: allow concentration for efficiency
            wallet_multiplier = 1.3  # 30% boost
        else:
            # <$5k wallets: heavy concentration is optimal
            wallet_multiplier = 1.5  # 50% boost
        
        return base_limit * wallet_multiplier
    
    def calculate_allocation_weight(self, pool_data: Dict, safety_score: float) -> float:
        """
        Calculate allocation weight balancing safety and APR.
        More balanced approach to include safer pools.
        
        Returns: Allocation weight (higher = more allocation)
        """
        # Get effective APR (already calculated)
        apr = pool_data.get('effective_apr', pool_data.get('apr', 0))
        
        # APR Score (0-100): More generous scoring for moderate APRs
        if apr >= 200:
            apr_score = 100
        elif apr >= 150:
            apr_score = 90  # Was 85
        elif apr >= 100:
            apr_score = 80  # Was 70
        elif apr >= 75:
            apr_score = 70  # Was 55
        elif apr >= 50:
            apr_score = 60  # Was 40 - big boost for 50%+ APR
        elif apr >= 30:
            apr_score = 45  # New tier for lower APR pools
        else:
            apr_score = max(0, (apr / 30) * 45)  # More generous base
        
        # For high safety pools, give more weight to safety
        # This helps USDC/WETH type pools compete
        if safety_score >= 80:
            # Very safe pools: 70% safety, 30% APR
            allocation_weight = (safety_score * 0.7) + (apr_score * 0.3)
        elif safety_score >= 65:
            # Safe pools: balanced 50/50
            allocation_weight = (safety_score * 0.5) + (apr_score * 0.5)
        else:
            # Riskier pools: favor APR more (40% safety, 60% APR)
            allocation_weight = (safety_score * 0.4) + (apr_score * 0.6)
        
        return allocation_weight
    
    def calculate_range_break_probability(
        self,
        range_width: float,
        daily_volatility: float,
        time_horizon_days: int = 7
    ) -> float:
        """
        Calculate probability of price breaking out of range within time horizon.
        Uses normal distribution assumption for price movements.
        
        Args:
            range_width: Total range width as decimal (e.g., 0.1 for 10%)
            daily_volatility: Daily volatility as decimal
            time_horizon_days: Number of days to consider
            
        Returns:
            Probability of range break (0-1)
        """
        import math
        
        # Calculate standard deviation over time horizon
        # Volatility scales with square root of time
        period_volatility = daily_volatility * math.sqrt(time_horizon_days)
        
        # Range is split equally above and below
        half_range = range_width / 2
        
        # Calculate z-score: how many standard deviations to reach range boundary
        if period_volatility > 0:
            z_score = half_range / period_volatility
            
            # Use normal CDF approximation
            # P(break) = 2 * P(Z > z_score) = 2 * (1 - Φ(z_score))
            # Using approximation: Φ(z) ≈ 0.5 + 0.5 * erf(z/√2)
            # For simplicity, using a polynomial approximation
            
            # Approximate normal CDF
            def norm_cdf(z):
                # Approximation accurate to ~0.01
                t = 1 / (1 + 0.2316419 * abs(z))
                d = 0.3989423 * math.exp(-z * z / 2)
                prob = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))))
                if z > 0:
                    return 1 - prob
                else:
                    return prob
            
            # Probability of staying within range
            prob_in_range = norm_cdf(z_score) - norm_cdf(-z_score)
            
            # Probability of breaking out
            prob_break = 1 - prob_in_range
            
            return min(1.0, max(0.0, prob_break))
        else:
            # No volatility means no break
            return 0.0
    
    def calculate_optimal_position_count(self, total_capital: float, apr: float) -> int:
        """
        Calculate optimal number of positions for individual agent.
        More aggressive position counts for better capital utilization.
        
        Args:
            total_capital: Total available capital in USDC
            apr: Expected average APR as percentage (e.g., 100 for 100%)
            
        Returns:
            Optimal number of positions
        """
        # Optimized for Base L2's low gas costs - can have more positions
        if total_capital < 100:
            return 1  # Single position for very small amounts
        elif total_capital < 1000:
            return 1  # Still single position under $1k
        elif total_capital < 3000:
            return 2  # 2 positions for $1k-3k
        elif total_capital < 5000:
            return 3  # 3 positions for $3k-5k (key change)
        elif total_capital < 10000:
            return 4  # 4 positions for $5k-10k (was 3)
        elif total_capital < 25000:
            return 5  # 5 positions for $10k-25k (was 4)
        elif total_capital < 50000:
            return 6  # 6 positions for $25k-50k (was 5)
        else:
            # $50k+ gets maximum 8 positions (was 7)
            return 8
    
    def calculate_minimum_position_size(self, apr: float) -> float:
        """
        Calculate minimum viable position size based on APR and gas costs.
        
        Args:
            apr: Expected APR as percentage (e.g., 100 for 100%)
            
        Returns:
            Minimum position size in USDC
        """
        # Convert APR to decimal
        apr_decimal = apr / 100 if apr > 1 else apr
        
        # With Base L2's ultra-low gas ($0.50 total), we can allow smaller positions
        # At 100% APR, $10 generates $10/year, covering gas in ~18 days
        # At 200% APR, $10 generates $20/year, covering gas in ~9 days
        
        # Formula: Position should cover gas costs within 30 days
        # gas_based_minimum = (gas_cost × 12) / apr_decimal
        # This ensures position covers gas in 1 month
        gas_based_minimum = (self.BASE_GAS_COSTS['total_lifecycle'] * 12) / apr_decimal if apr_decimal > 0 else 100
        
        # Absolute minimum of $10 for Base L2
        return max(10, gas_based_minimum)
    
    def calculate_position_size(
        self, 
        pool_stats: Dict,
        available_capital: float,
        risk_profile: str = 'balanced',
        existing_positions: List[Dict] = None
    ) -> Tuple[float, float]:
        """
        Calculate optimal position size with dynamic limits based on pool safety.
        
        Args:
            pool_stats: Pool statistics including APR, volatility
            available_capital: Available USDC for investment
            risk_profile: Risk profile
            existing_positions: Existing positions (for individual agent)
            
        Returns:
            Tuple of (recommended_amount, max_amount)
        """
        # Calculate safety score for this pool
        safety_score = self.calculate_simple_safety_score(pool_stats)
        
        # Get dynamic position limit based on safety and wallet size
        max_position_pct = self.calculate_dynamic_position_limit(safety_score, available_capital)
        
        # Calculate allocation weight (combination of safety and APR)
        allocation_weight = self.calculate_allocation_weight(pool_stats, safety_score)
        
        # Get APR for minimum position calculation
        apr = pool_stats.get('apr', 100)  # Default 100% APR
        
        # Calculate optimal number of positions for this capital level
        optimal_position_count = self.calculate_optimal_position_count(available_capital, apr)
        
        # Base allocation from weight (this will be normalized by service layer)
        # For now, use a simple approach based on allocation weight
        base_allocation = available_capital * (allocation_weight / 100) / optimal_position_count
        
        # Apply dynamic maximum based on safety score
        max_amount = available_capital * max_position_pct
        
        # Get minimum position size based on APR
        min_position = self.calculate_minimum_position_size(apr)
        
        # Calculate recommended amount
        recommended_amount = min(base_allocation, max_amount)
        recommended_amount = max(recommended_amount, min_position)
        
        # If we can't meet minimum with available capital, adjust
        if recommended_amount > available_capital:
            return (min_position, min_position)
        
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
        
        # Estimate costs using Base L2 gas costs
        estimated_gas = self.BASE_GAS_COSTS['total_lifecycle']  # $0.50 for entry/exit
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