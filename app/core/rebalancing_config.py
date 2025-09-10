"""
Rebalancing configuration to prevent unnecessary portfolio churn.
These thresholds ensure that rebalancing only occurs when meaningful improvements are possible.
"""
from typing import Dict, Any
from pydantic import BaseModel, Field


class RebalancingThresholds(BaseModel):
    """
    Configurable thresholds for smart rebalancing decisions.
    Prevents unnecessary transactions and gas waste.
    """
    
    # Entry Thresholds
    min_confidence_for_entry: float = Field(
        default=75.0,
        ge=0, le=100,
        description="Minimum confidence score (0-100) required to enter a new position"
    )
    
    min_apr_for_entry: float = Field(
        default=80.0,  # Increased based on quant analysis
        ge=0,
        description="Minimum expected APR (%) for small positions (<$2000)"
    )
    
    min_allocation_size: float = Field(
        default=50.0,  # Increased to ensure proper-sized positions
        ge=50,
        description="Minimum position size in USDC for new positions when portfolio exists"
    )
    
    # Switch/Rebalancing Thresholds
    min_apr_improvement_for_switch: float = Field(
        default=35.0,  # Increased from 20% based on true switching costs
        ge=0,
        description="Minimum APR improvement (%) required to switch positions"
    )
    
    min_net_benefit_for_switch: float = Field(
        default=500.0,  # Increased to account for all costs
        ge=0,
        description="Minimum net benefit in USDC (after gas) to justify a switch"
    )
    
    min_confidence_for_switch: float = Field(
        default=70.0,
        ge=0, le=100,
        description="Minimum confidence score for switch recommendations"
    )
    
    # Exit Thresholds
    critical_loss_threshold: float = Field(
        default=-20.0,
        le=0,
        description="Loss percentage that triggers immediate exit"
    )
    
    underperformance_threshold: float = Field(
        default=0.5,
        ge=0, le=1,
        description="Exit if APR drops below this fraction of entry APR"
    )
    
    # Gas Cost Management
    max_gas_cost_ratio: float = Field(
        default=0.02,
        ge=0, le=0.1,
        description="Maximum gas cost as percentage of position value"
    )
    
    estimated_gas_per_action: float = Field(
        default=50.0,
        ge=0,
        description="Estimated gas cost in USDC per transaction"
    )
    
    # Portfolio Constraints
    max_positions: int = Field(
        default=10,
        ge=1, le=20,
        description="Maximum number of concurrent positions"
    )
    
    min_positions: int = Field(
        default=3,
        ge=1, le=10,
        description="Minimum positions for diversification"
    )
    
    reserve_capital_ratio: float = Field(
        default=0.1,
        ge=0, le=0.5,
        description="Percentage of capital to keep as reserve"
    )
    
    # Timing Constraints
    min_hours_between_switches: int = Field(
        default=24,
        ge=1,
        description="Minimum hours between switching the same position"
    )
    
    min_hours_between_rebalances: int = Field(
        default=6,
        ge=1,
        description="Minimum hours between portfolio rebalances"
    )


class RebalancingStrategy:
    """
    Strategy implementation using configurable thresholds.
    """
    
    def __init__(self, thresholds: RebalancingThresholds = None):
        self.thresholds = thresholds or RebalancingThresholds()
    
    def should_enter_position(
        self,
        confidence: float,
        expected_apr: float,
        allocation: float,
        available_capital: float,
        nav: float = 0,
        has_existing_positions: bool = False
    ) -> tuple[bool, str]:
        """
        Determine if a new position should be entered.
        Uses dynamic APR thresholds and NAV-based benefit requirements.
        
        Args:
            confidence: Confidence score (0-100)
            expected_apr: Expected APR percentage
            allocation: Proposed allocation amount
            available_capital: Available capital for investment
            nav: Net Asset Value (positions + available capital)
            has_existing_positions: Whether user has existing positions
            
        Returns:
            (should_enter, reason)
        """
        # Check confidence threshold
        if confidence < self.thresholds.min_confidence_for_entry:
            return False, f"Confidence {confidence:.1f}% below threshold {self.thresholds.min_confidence_for_entry}%"
        
        # If user has existing positions, apply stricter criteria
        if has_existing_positions:
            # Minimum position size for adding to existing portfolio
            min_position_size = max(50.0, min(100.0, nav * 0.05))  # 5% of NAV, capped between $50-$100
            
            if allocation < min_position_size:
                return False, f"Allocation ${allocation:.0f} below minimum ${min_position_size:.0f} for portfolio addition"
            
            # Calculate minimum benefit requirement: max($20, 10 bps of NAV)
            min_benefit = max(20.0, nav * 0.001)  # 10 bps = 0.1% = 0.001
            
            # Estimate annual benefit from this position
            # Annual benefit = allocation * (APR/100)
            estimated_annual_benefit = allocation * (expected_apr / 100)
            # Pro-rate to 30 days for near-term benefit
            estimated_30d_benefit = estimated_annual_benefit * (30 / 365)
            
            if estimated_30d_benefit < min_benefit:
                return False, f"Expected benefit ${estimated_30d_benefit:.2f} below minimum ${min_benefit:.2f} (10bps NAV or $20)"
            
            # APR uplift requirement (must beat 35% threshold)
            if expected_apr < 35:
                return False, f"APR {expected_apr:.1f}% below 35% uplift threshold for portfolio addition"
        
        # Dynamic APR threshold based on position size
        # For Base L2 with $0.50 gas costs
        if allocation < 50:
            min_apr = 500  # Very small positions need very high APR
        elif allocation < 100:
            min_apr = 200  # Small positions need high APR to justify gas
        elif allocation < 500:
            min_apr = 100  # Medium-small positions
        elif allocation < 2000:
            min_apr = 80   # Medium positions
        elif allocation < 5000:
            min_apr = 60   # Large positions
        else:
            min_apr = 50   # Very large positions can accept lower APR
        
        # Check dynamic APR threshold
        if expected_apr < min_apr:
            return False, f"APR {expected_apr:.1f}% below threshold {min_apr}% for ${allocation:.0f} position"
        
        # Check allocation size
        if allocation < self.thresholds.min_allocation_size:
            return False, f"Allocation ${allocation:.0f} below minimum ${self.thresholds.min_allocation_size}"
        
        # Check gas cost efficiency
        gas_ratio = self.thresholds.estimated_gas_per_action / allocation
        if gas_ratio > self.thresholds.max_gas_cost_ratio:
            return False, f"Gas cost {gas_ratio:.1%} exceeds maximum {self.thresholds.max_gas_cost_ratio:.1%}"
        
        # Check if we have enough capital
        if allocation > available_capital:
            return False, f"Insufficient capital: need ${allocation:.0f}, have ${available_capital:.0f}"
        
        return True, "All entry criteria met"
    
    def should_switch_position(
        self,
        current_apr: float,
        new_apr: float,
        switch_benefit: float,
        position_value: float,
        confidence: float = 100
    ) -> tuple[bool, str]:
        """
        Determine if a position should be switched.
        
        Returns:
            (should_switch, reason)
        """
        apr_improvement = new_apr - current_apr
        
        # Check APR improvement threshold
        if apr_improvement < self.thresholds.min_apr_improvement_for_switch:
            return False, f"APR improvement {apr_improvement:.1f}% below threshold {self.thresholds.min_apr_improvement_for_switch}%"
        
        # Check net benefit threshold
        if switch_benefit < self.thresholds.min_net_benefit_for_switch:
            return False, f"Net benefit ${switch_benefit:.0f} below threshold ${self.thresholds.min_net_benefit_for_switch}"
        
        # Check confidence
        if confidence < self.thresholds.min_confidence_for_switch:
            return False, f"Confidence {confidence:.1f}% below threshold {self.thresholds.min_confidence_for_switch}%"
        
        # Check if gas cost is worth it
        gas_ratio = (self.thresholds.estimated_gas_per_action * 2) / position_value  # Exit + Enter
        if gas_ratio > self.thresholds.max_gas_cost_ratio:
            return False, f"Gas cost {gas_ratio:.1%} exceeds maximum {self.thresholds.max_gas_cost_ratio:.1%}"
        
        return True, f"Switch justified: +{apr_improvement:.1f}% APR, ${switch_benefit:.0f} benefit"
    
    def should_exit_position(
        self,
        entry_apr: float,
        current_apr: float,
        pnl_percentage: float,
        in_range: bool
    ) -> tuple[bool, str, str]:
        """
        Determine if a position should be exited.
        
        Returns:
            (should_exit, urgency, reason)
        """
        # Critical loss - immediate exit
        if pnl_percentage < self.thresholds.critical_loss_threshold:
            return True, "critical", f"Critical loss: {pnl_percentage:.1f}%"
        
        # Out of range with significant underperformance
        if not in_range and current_apr < entry_apr * self.thresholds.underperformance_threshold:
            return True, "high", f"Out of range with poor APR: {current_apr:.1f}%"
        
        # Severe underperformance even if in range
        if current_apr < entry_apr * 0.25:  # Less than 25% of original APR
            return True, "medium", f"Severe underperformance: {current_apr:.1f}% vs {entry_apr:.1f}% entry"
        
        return False, "low", "Position performing acceptably"
    
    def get_rebalancing_summary(self, actions: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a summary explaining why actions were or weren't taken.
        """
        return {
            "thresholds_applied": {
                "min_confidence": self.thresholds.min_confidence_for_entry,
                "min_apr": self.thresholds.min_apr_for_entry,
                "min_switch_benefit": self.thresholds.min_net_benefit_for_switch,
                "gas_threshold": self.thresholds.max_gas_cost_ratio
            },
            "actions_filtered": {
                "total_opportunities": len(actions.get('all_opportunities', [])),
                "passed_thresholds": len(actions.get('immediate_actions', [])),
                "rejected_low_confidence": actions.get('rejected_low_confidence', 0),
                "rejected_low_apr": actions.get('rejected_low_apr', 0),
                "rejected_gas_cost": actions.get('rejected_gas_cost', 0)
            },
            "recommendation": self._get_recommendation(actions)
        }
    
    def _get_recommendation(self, actions: Dict[str, Any]) -> str:
        """Generate human-readable recommendation."""
        immediate = actions.get('immediate_actions', [])
        
        if not immediate:
            return "No actions recommended - all opportunities below thresholds"
        elif len(immediate) == 1:
            return f"Execute 1 high-confidence action"
        else:
            return f"Execute {len(immediate)} high-confidence actions"


# Default instance with conservative thresholds
default_rebalancing_strategy = RebalancingStrategy()