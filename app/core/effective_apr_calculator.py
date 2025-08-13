"""
Effective APR calculator for concentrated liquidity positions.
Based on Aerodrome's tick spacing APR formula from specs/formula.md
"""
import math
from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class EffectiveAPRCalculator:
    """
    Calculates effective APR based on concentrated liquidity range and tick spacing.
    
    Formula:
    multiplier = 100 / tick_spacing
    if tick_spacing < 100:
        effective_APR = original_APR / ((total_range × multiplier) + 1)
    else:
        effective_APR = original_APR / (total_range × multiplier)
    """
    
    # Standard range widths for common strategies
    STANDARD_RANGE_WIDTHS = {
        'narrow': 0.05,    # 5% total range - aggressive strategy
        'standard': 0.10,  # 10% total range - balanced strategy
        'wide': 0.20       # 20% total range - conservative strategy
    }
    
    def calculate_effective_apr(
        self,
        original_apr: float,
        tick_spacing: int,
        total_range_percentage: float
    ) -> float:
        """
        Calculate effective APR using the Aerodrome formula.
        
        Args:
            original_apr: Original pool APR (e.g., 150 for 150%)
            tick_spacing: Pool's tick spacing (1, 10, 50, 100, 200, 2000)
            total_range_percentage: Total range width as decimal (0.1 for 10%)
            
        Returns:
            Effective APR after range adjustment
        """
        try:
            # Validation
            if tick_spacing <= 0:
                logger.warning(f"Invalid tick spacing: {tick_spacing}")
                return 0.0
            
            if total_range_percentage <= 0:
                logger.warning(f"Invalid range percentage: {total_range_percentage}")
                return 0.0
            
            if original_apr < 0:
                logger.warning(f"Negative APR: {original_apr}")
                return 0.0
            
            # Calculate multiplier
            multiplier = 100 / tick_spacing
            
            # Apply formula based on tick spacing threshold
            if tick_spacing < 100:
                # Apply penalty factor for tight tick spacings
                divisor = (total_range_percentage * 100 * multiplier) + 1
            else:
                # No penalty factor for wider tick spacings
                divisor = total_range_percentage * 100 * multiplier
            
            if divisor == 0:
                return original_apr
            
            effective_apr = original_apr / divisor
            
            # Sanity check - effective APR shouldn't exceed original
            # (it shouldn't mathematically, but ensure safety)
            effective_apr = min(effective_apr, original_apr)
            
            return max(0, effective_apr)  # Ensure non-negative
            
        except Exception as e:
            logger.error(f"Error calculating effective APR: {e}")
            return 0.0
    
    def calculate_effective_apr_from_ticks(
        self,
        original_apr: float,
        tick_spacing: int,
        lower_tick: int,
        upper_tick: int,
        current_tick: int
    ) -> float:
        """
        Calculate effective APR from tick range.
        
        Args:
            original_apr: Original pool APR
            tick_spacing: Pool's tick spacing
            lower_tick: Lower tick of the range
            upper_tick: Upper tick of the range
            current_tick: Current pool tick
            
        Returns:
            Effective APR for the specified tick range
        """
        try:
            # Convert ticks to prices using Uniswap V3 formula
            lower_price = 1.0001 ** lower_tick
            upper_price = 1.0001 ** upper_tick
            current_price = 1.0001 ** current_tick
            
            if current_price <= 0:
                return 0.0
            
            # Calculate range as percentage of current price
            # Use the wider calculation to account for both sides
            lower_range = abs(current_price - lower_price) / current_price
            upper_range = abs(upper_price - current_price) / current_price
            total_range_percentage = lower_range + upper_range
            
            return self.calculate_effective_apr(
                original_apr,
                tick_spacing,
                total_range_percentage
            )
            
        except Exception as e:
            logger.error(f"Error calculating effective APR from ticks: {e}")
            return 0.0
    
    def calculate_apr_efficiency(
        self,
        original_apr: float,
        effective_apr: float
    ) -> float:
        """
        Calculate what percentage of original APR is captured.
        
        Args:
            original_apr: Original pool APR
            effective_apr: Effective APR after range adjustment
            
        Returns:
            Efficiency percentage (0-100)
        """
        if original_apr <= 0:
            return 0.0
        
        efficiency = (effective_apr / original_apr) * 100
        return min(100.0, max(0.0, efficiency))  # Cap between 0-100%
    
    def calculate_multiple_ranges(
        self,
        original_apr: float,
        tick_spacing: int
    ) -> Dict[str, float]:
        """
        Calculate effective APR for standard range widths.
        
        Args:
            original_apr: Original pool APR
            tick_spacing: Pool's tick spacing
            
        Returns:
            Dictionary mapping range type to effective APR
        """
        results = {}
        
        for range_type, range_width in self.STANDARD_RANGE_WIDTHS.items():
            results[range_type] = self.calculate_effective_apr(
                original_apr,
                tick_spacing,
                range_width
            )
        
        return results
    
    def calculate_optimal_range_for_target_apr(
        self,
        target_effective_apr: float,
        base_apr: float,
        tick_spacing: int
    ) -> float:
        """
        Calculate the range width needed to achieve a target effective APR.
        
        Args:
            target_effective_apr: Desired effective APR
            base_apr: Original pool APR
            tick_spacing: Pool's tick spacing
            
        Returns:
            Required range width as decimal (e.g., 0.1 for 10%)
        """
        try:
            if target_effective_apr <= 0 or base_apr <= 0:
                return 0.0
            
            if target_effective_apr >= base_apr:
                # Can't achieve higher than base APR
                return 0.01  # Return minimum range
            
            multiplier = 100 / tick_spacing
            
            if tick_spacing < 100:
                # Solve: target = base / ((range × multiplier × 100) + 1)
                # range = (base / target - 1) / (multiplier × 100)
                range_width = (base_apr / target_effective_apr - 1) / (multiplier * 100)
            else:
                # Solve: target = base / (range × multiplier × 100)
                # range = base / (target × multiplier × 100)
                range_width = base_apr / (target_effective_apr * multiplier * 100)
            
            # Cap between reasonable bounds (2% - 100%)
            return max(0.02, min(1.0, range_width))
            
        except Exception as e:
            logger.error(f"Error calculating optimal range: {e}")
            return 0.1  # Default to 10% range
    
    def calculate_risk_adjusted_apr(
        self,
        effective_apr: float,
        volatility: float,
        range_width: float,
        tick_spacing: int
    ) -> float:
        """
        Calculate risk-adjusted APR considering volatility and range break probability.
        
        Args:
            effective_apr: Effective APR after range adjustment
            volatility: 24h volatility percentage
            range_width: Total range width as decimal
            tick_spacing: Pool's tick spacing
            
        Returns:
            Risk-adjusted APR
        """
        try:
            # Calculate leverage factor based on concentration
            multiplier = 100 / tick_spacing
            leverage_factor = 1 + (multiplier / 10)  # Simplified leverage approximation
            
            # Adjust for risk using simplified Sharpe-like calculation
            # Higher volatility and tighter ranges increase risk
            risk_factor = volatility * leverage_factor / (range_width * 100)
            
            # Risk-adjusted APR (simplified model)
            # Penalize APR based on risk level
            risk_adjusted = effective_apr / (1 + risk_factor)
            
            return max(0, risk_adjusted)
            
        except Exception as e:
            logger.error(f"Error calculating risk-adjusted APR: {e}")
            return effective_apr
    
    def validate_and_calculate(
        self,
        original_apr: float,
        tick_spacing: int,
        total_range_percentage: float
    ) -> Tuple[float, Optional[str]]:
        """
        Safe calculation with validation and error messages.
        
        Args:
            original_apr: Original pool APR
            tick_spacing: Pool's tick spacing
            total_range_percentage: Total range width as decimal
            
        Returns:
            Tuple of (effective_apr, error_message)
        """
        # Validation checks
        if tick_spacing <= 0:
            return (0.0, "Invalid tick spacing: must be positive")
        
        if total_range_percentage <= 0:
            return (0.0, "Invalid range: must be positive")
        
        if total_range_percentage > 10:
            return (0.0, "Invalid range: too wide (>1000%)")
        
        if original_apr < 0:
            return (0.0, "Invalid APR: cannot be negative")
        
        # Calculate effective APR
        effective_apr = self.calculate_effective_apr(
            original_apr,
            tick_spacing,
            total_range_percentage
        )
        
        # Sanity checks
        if effective_apr > original_apr:
            return (original_apr, "Warning: Capped at original APR")
        
        if effective_apr == 0 and original_apr > 0:
            return (0.0, "Warning: Effective APR rounds to zero")
        
        return (effective_apr, None)