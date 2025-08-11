"""
Dynamic slippage calculator for different pair types and market conditions.
"""
from typing import Dict, Tuple, Optional
import math


class SlippageCalculator:
    """
    Calculates dynamic slippage based on pair characteristics, volatility, and position size.
    """
    
    # Slippage profiles for different pair types
    SLIPPAGE_PROFILES = {
        'stable': {
            'base': 0.001,  # 0.1%
            'max': 0.003,    # 0.3%
            'volatility_multiplier': 0.5,
            'size_impact_factor': 0.2
        },
        'semi-volatile': {
            'base': 0.005,  # 0.5%
            'max': 0.010,   # 1.0%
            'volatility_multiplier': 1.0,
            'size_impact_factor': 0.4
        },
        'volatile': {
            'base': 0.020,  # 2.0%
            'max': 0.050,   # 5.0%
            'volatility_multiplier': 1.5,
            'size_impact_factor': 0.6
        },
        'memecoin': {
            'base': 0.030,  # 3.0%
            'max': 0.100,   # 10.0%
            'volatility_multiplier': 2.0,
            'size_impact_factor': 0.8
        }
    }
    
    # Token classifications
    STABLE_TOKENS = {
        'USDC', 'USDT', 'DAI', 'FRAX', 'LUSD', 'USDbC', 'BUSD', 'TUSD'
    }
    
    SEMI_VOLATILE_TOKENS = {
        'WETH', 'ETH', 'WBTC', 'BTC', 'stETH', 'cbETH', 'rETH', 'MATIC', 'BNB'
    }
    
    VOLATILE_TOKENS = {
        'AERO', 'OP', 'ARB', 'UNI', 'LINK', 'AVAX', 'SOL', 'ADA', 'DOT'
    }
    
    # Known memecoins - everything else with high volatility is treated as memecoin
    KNOWN_MEMECOINS = {
        'DOGE', 'SHIB', 'PEPE', 'FLOKI', 'MEME', 'BONK', 'WIF', 'BRETT'
    }
    
    def classify_pair(self, token0: str, token1: str) -> str:
        """
        Classify a token pair into volatility categories.
        
        Args:
            token0: First token symbol
            token1: Second token symbol
            
        Returns:
            Pair classification: 'stable', 'semi-volatile', 'volatile', or 'memecoin'
        """
        # Normalize token symbols
        token0 = token0.upper()
        token1 = token1.upper()
        
        tokens = {token0, token1}
        
        # Both tokens are stables = stable pair
        if tokens.issubset(self.STABLE_TOKENS):
            return 'stable'
        
        # One stable + one semi-volatile = semi-volatile
        if (tokens & self.STABLE_TOKENS) and (tokens & self.SEMI_VOLATILE_TOKENS):
            return 'semi-volatile'
        
        # Check for known memecoins
        if tokens & self.KNOWN_MEMECOINS:
            return 'memecoin'
        
        # One stable + one volatile/unknown = volatile
        if tokens & self.STABLE_TOKENS:
            return 'volatile'
        
        # Both semi-volatile = semi-volatile
        if tokens.issubset(self.SEMI_VOLATILE_TOKENS):
            return 'semi-volatile'
        
        # One semi-volatile + one volatile/unknown = volatile
        if tokens & self.SEMI_VOLATILE_TOKENS:
            return 'volatile'
        
        # Both volatile or unknown = memecoin (highest risk)
        return 'memecoin'
    
    def calculate_dynamic_slippage(
        self,
        pool: Dict,
        position_size: float,
        action: str = 'enter'
    ) -> float:
        """
        Calculate dynamic slippage for a specific trade.
        
        Args:
            pool: Pool information including TVL, volatility, pair info
            position_size: Size of the position in USDC
            action: 'enter' or 'exit'
            
        Returns:
            Total slippage as a decimal (e.g., 0.01 for 1%)
        """
        # Get pair classification
        token0 = pool.get('token0_symbol', 'UNKNOWN')
        token1 = pool.get('token1_symbol', 'UNKNOWN')
        pair_class = self.classify_pair(token0, token1)
        
        # Get slippage profile
        profile = self.SLIPPAGE_PROFILES[pair_class]
        
        # Base slippage
        base_slippage = profile['base']
        
        # Adjust for volatility
        volatility_24h = pool.get('volatility_24h', 20)  # Default 20% if not provided
        volatility_adjustment = self._calculate_volatility_adjustment(
            volatility_24h,
            profile['volatility_multiplier']
        )
        
        # Adjust for position size impact
        tvl = pool.get('tvl', 1_000_000)  # Default 1M if not provided
        size_impact = self._calculate_size_impact(
            position_size,
            tvl,
            profile['size_impact_factor']
        )
        
        # Adjust for action (exits typically have higher slippage)
        action_multiplier = 1.2 if action == 'exit' else 1.0
        
        # Calculate total slippage
        total_slippage = (base_slippage + volatility_adjustment + size_impact) * action_multiplier
        
        # Cap at maximum for the profile
        total_slippage = min(total_slippage, profile['max'])
        
        return total_slippage
    
    def _calculate_volatility_adjustment(
        self,
        volatility: float,
        multiplier: float
    ) -> float:
        """
        Calculate slippage adjustment based on volatility.
        
        Args:
            volatility: 24-hour volatility percentage
            multiplier: Volatility multiplier from profile
            
        Returns:
            Volatility adjustment to add to base slippage
        """
        # Convert volatility to decimal and apply multiplier
        volatility_decimal = volatility / 100
        
        # Non-linear adjustment: higher volatility has increasing impact
        adjustment = (volatility_decimal ** 1.5) * multiplier * 0.01
        
        return adjustment
    
    def _calculate_size_impact(
        self,
        position_size: float,
        tvl: float,
        impact_factor: float
    ) -> float:
        """
        Calculate slippage impact from position size relative to TVL.
        
        Args:
            position_size: Position size in USDC
            tvl: Total value locked in pool
            impact_factor: Size impact factor from profile
            
        Returns:
            Size impact adjustment to add to base slippage
        """
        if tvl <= 0:
            return 0.05  # 5% penalty for zero TVL
        
        # Calculate position as percentage of TVL
        size_percentage = position_size / tvl
        
        # Non-linear impact: square root for smaller positions, squared for larger
        if size_percentage < 0.01:  # Less than 1% of TVL
            impact = math.sqrt(size_percentage) * impact_factor * 0.1
        elif size_percentage < 0.05:  # 1-5% of TVL
            impact = size_percentage * impact_factor
        else:  # More than 5% of TVL
            impact = (size_percentage ** 2) * impact_factor * 2
        
        return impact
    
    def calculate_slippage_breakdown(
        self,
        pool: Dict,
        position_size: float,
        action: str = 'enter'
    ) -> Dict:
        """
        Calculate detailed slippage breakdown for transparency.
        
        Args:
            pool: Pool information
            position_size: Position size in USDC
            action: 'enter' or 'exit'
            
        Returns:
            Detailed breakdown of slippage components
        """
        # Get pair classification
        token0 = pool.get('token0_symbol', 'UNKNOWN')
        token1 = pool.get('token1_symbol', 'UNKNOWN')
        pair_class = self.classify_pair(token0, token1)
        
        # Get profile
        profile = self.SLIPPAGE_PROFILES[pair_class]
        
        # Calculate components
        base_slippage = profile['base']
        
        volatility_24h = pool.get('volatility_24h', 20)
        volatility_adjustment = self._calculate_volatility_adjustment(
            volatility_24h,
            profile['volatility_multiplier']
        )
        
        tvl = pool.get('tvl', 1_000_000)
        size_impact = self._calculate_size_impact(
            position_size,
            tvl,
            profile['size_impact_factor']
        )
        
        action_multiplier = 1.2 if action == 'exit' else 1.0
        
        # Total before capping
        raw_total = (base_slippage + volatility_adjustment + size_impact) * action_multiplier
        
        # Final total after capping
        total_slippage = min(raw_total, profile['max'])
        
        return {
            'base_slippage': base_slippage * 100,  # As percentage
            'volatility_adjustment': volatility_adjustment * 100,
            'size_impact': size_impact * 100,
            'action_multiplier': action_multiplier,
            'total_slippage': total_slippage * 100,
            'max_recommended': profile['max'] * 100,
            'pair_classification': pair_class,
            'was_capped': raw_total > profile['max'],
            'slippage_in_usdc': position_size * total_slippage
        }
    
    def get_max_position_size(
        self,
        pool: Dict,
        max_slippage_tolerance: float = 0.02
    ) -> float:
        """
        Calculate maximum position size given slippage tolerance.
        
        Args:
            pool: Pool information
            max_slippage_tolerance: Maximum acceptable slippage (e.g., 0.02 for 2%)
            
        Returns:
            Maximum position size in USDC
        """
        tvl = pool.get('tvl', 1_000_000)
        
        # Get pair classification
        token0 = pool.get('token0_symbol', 'UNKNOWN')
        token1 = pool.get('token1_symbol', 'UNKNOWN')
        pair_class = self.classify_pair(token0, token1)
        
        profile = self.SLIPPAGE_PROFILES[pair_class]
        
        # Work backwards from slippage tolerance
        # Simplified calculation - assumes linear relationship
        available_slippage = max_slippage_tolerance - profile['base']
        
        if available_slippage <= 0:
            return 0  # Can't trade within tolerance
        
        # Estimate max size as percentage of TVL
        # This is simplified - in production would use iterative calculation
        max_size_percentage = math.sqrt(available_slippage / profile['size_impact_factor'])
        
        max_position = tvl * min(max_size_percentage, 0.1)  # Cap at 10% of TVL
        
        return max_position
    
    def estimate_execution_cost(
        self,
        position_size: float,
        slippage: float,
        gas_price_usd: float = 25
    ) -> Dict:
        """
        Estimate total execution cost including slippage and gas.
        
        Args:
            position_size: Position size in USDC
            slippage: Slippage as decimal
            gas_price_usd: Estimated gas cost in USD
            
        Returns:
            Execution cost breakdown
        """
        slippage_cost = position_size * slippage
        total_cost = slippage_cost + gas_price_usd
        cost_percentage = (total_cost / position_size * 100) if position_size > 0 else 0
        
        return {
            'slippage_cost': slippage_cost,
            'gas_cost': gas_price_usd,
            'total_cost': total_cost,
            'cost_percentage': cost_percentage,
            'break_even_days': self._calculate_break_even_days(total_cost, position_size)
        }
    
    def _calculate_break_even_days(
        self,
        total_cost: float,
        position_size: float,
        apr: float = 40
    ) -> float:
        """
        Calculate days to break even on execution costs.
        
        Args:
            total_cost: Total execution cost
            position_size: Position size
            apr: Expected APR (default 40%)
            
        Returns:
            Days to break even
        """
        if position_size <= 0 or apr <= 0:
            return float('inf')
        
        daily_return = position_size * (apr / 100 / 365)
        
        if daily_return <= 0:
            return float('inf')
        
        return total_cost / daily_return