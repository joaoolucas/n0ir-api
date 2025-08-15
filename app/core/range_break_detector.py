"""
Range break detection and analysis for concentrated liquidity positions.
"""
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timedelta
from enum import Enum


class BreakSeverity(Enum):
    """Range break severity levels."""
    NONE = 0
    MILD = 1
    MODERATE = 2
    SEVERE = 3
    CRITICAL = 4


class RangeBreakDetector:
    """
    Detects and analyzes range breaks in concentrated liquidity positions.
    Implements the empirical observation that upward breaks tend to reverse.
    """
    
    # Severity thresholds
    SEVERITY_THRESHOLDS = {
        'mild': 0.4,      # 40% severity
        'moderate': 0.7,   # 70% severity
        'severe': 0.85,    # 85% severity
        'critical': 0.95   # 95% severity
    }
    
    # Reversal probabilities based on empirical data
    REVERSAL_PROBABILITIES = {
        'upward': {
            'mild': 0.50,
            'moderate': 0.65,
            'severe': 0.75,
            'critical': 0.85
        },
        'downward': {
            'mild': 0.30,
            'moderate': 0.40,
            'severe': 0.45,
            'critical': 0.50
        }
    }
    
    # Expected loss percentages if reversal occurs
    EXPECTED_REVERSAL_LOSSES = {
        'upward': {
            'mild': 5,
            'moderate': 8,
            'severe': 12,
            'critical': 15
        },
        'downward': {
            'mild': 3,
            'moderate': 5,
            'severe': 7,
            'critical': 10
        }
    }
    
    def detect_range_break(
        self,
        position: Dict,
        current_price: float,
        current_tick: Optional[int] = None
    ) -> Optional[Dict]:
        """
        Detect if a position has broken its range.
        
        Args:
            position: Position information with range data
            current_price: Current pool price
            current_tick: Current pool tick (optional)
            
        Returns:
            Range break information or None if in range
        """
        # Extract range information
        range_data = position.get('current_range', position.get('range', {}))
        
        # Get price bounds
        if 'lower_price' in range_data and 'upper_price' in range_data:
            lower_price = range_data['lower_price']
            upper_price = range_data['upper_price']
        elif 'lower_tick' in range_data and 'upper_tick' in range_data:
            # Convert ticks to prices if needed
            lower_price = self._tick_to_price(range_data['lower_tick'])
            upper_price = self._tick_to_price(range_data['upper_tick'])
        else:
            return None
        
        # Check if price is outside range
        if current_price < lower_price:
            break_type = 'downward'
            distance_from_range = (lower_price - current_price) / lower_price
            reference_price = lower_price
        elif current_price > upper_price:
            break_type = 'upward'
            distance_from_range = (current_price - upper_price) / upper_price
            reference_price = upper_price
        else:
            # Price is within range
            return None
        
        # Calculate severity
        severity = self._calculate_severity(distance_from_range, break_type)
        
        # Get severity level
        severity_level = self._get_severity_level(severity)
        
        return {
            'detected': True,
            'break_type': break_type,
            'current_price': current_price,
            'range_bounds': {
                'lower': lower_price,
                'upper': upper_price
            },
            'distance_from_range': distance_from_range * 100,  # As percentage
            'severity': severity,
            'severity_level': severity_level,
            'reference_price': reference_price,
            'timestamp': datetime.utcnow()
        }
    
    def _calculate_severity(self, distance_from_range: float, break_type: str) -> float:
        """
        Calculate break severity score (0-100).
        
        Args:
            distance_from_range: Proportional distance from range
            break_type: 'upward' or 'downward'
            
        Returns:
            Severity score 0-100
        """
        # Base severity from distance
        base_severity = min(100, distance_from_range * 100 * 2)  # 50% distance = 100 severity
        
        # Adjust for break type (upward breaks are more severe)
        if break_type == 'upward':
            severity_multiplier = 1.2  # 20% more severe
        else:
            severity_multiplier = 0.9  # 10% less severe
        
        return min(100, base_severity * severity_multiplier)
    
    def _get_severity_level(self, severity: float) -> str:
        """Get severity level from score."""
        if severity >= self.SEVERITY_THRESHOLDS['critical'] * 100:
            return 'critical'
        elif severity >= self.SEVERITY_THRESHOLDS['severe'] * 100:
            return 'severe'
        elif severity >= self.SEVERITY_THRESHOLDS['moderate'] * 100:
            return 'moderate'
        elif severity >= self.SEVERITY_THRESHOLDS['mild'] * 100:
            return 'mild'
        else:
            return 'negligible'
    
    def analyze_range_break_probability(
        self,
        pool_history: Dict,
        current_break: Dict
    ) -> Dict:
        """
        Analyze the probability of reversal for a range break.
        
        Args:
            pool_history: Historical pool data
            current_break: Current break information
            
        Returns:
            Analysis with reversal probability and expected loss
        """
        break_type = current_break['break_type']
        severity_level = current_break['severity_level']
        
        # Get base reversal probability from empirical data
        reversal_prob = self.REVERSAL_PROBABILITIES[break_type].get(
            severity_level, 
            0.5  # Default 50% if unknown
        )
        
        # Adjust based on pool volatility if available
        if 'volatility_24h' in pool_history:
            volatility = pool_history['volatility_24h']
            if volatility > 50:  # High volatility
                reversal_prob *= 1.1  # Increase reversal probability
            elif volatility < 10:  # Low volatility
                reversal_prob *= 0.9  # Decrease reversal probability
        
        # Cap probability at 0.95
        reversal_prob = min(0.95, reversal_prob)
        
        # Get expected loss if reversal occurs
        expected_loss = self.EXPECTED_REVERSAL_LOSSES[break_type].get(
            severity_level,
            10  # Default 10% loss
        )
        
        # Calculate risk-adjusted expected value
        expected_value = -reversal_prob * expected_loss
        
        return {
            'reversal_probability': reversal_prob,
            'expected_loss_if_reversal': expected_loss,
            'risk_adjusted_ev': expected_value,
            'confidence': self._calculate_confidence(pool_history),
            'recommendation': self._get_recommendation(
                break_type, 
                severity_level, 
                reversal_prob
            )
        }
    
    def _calculate_confidence(self, pool_history: Dict) -> float:
        """Calculate confidence in the analysis based on available data."""
        confidence = 0.5  # Base confidence
        
        # Increase confidence if we have good historical data
        if pool_history.get('data_points', 0) > 100:
            confidence += 0.2
        if pool_history.get('days_of_data', 0) > 7:
            confidence += 0.2
        if 'previous_breaks' in pool_history:
            confidence += 0.1
        
        return min(1.0, confidence)
    
    def _get_recommendation(
        self,
        break_type: str,
        severity_level: str,
        reversal_prob: float
    ) -> str:
        """Get action recommendation based on break analysis."""
        if break_type == 'upward':
            if severity_level in ['severe', 'critical']:
                return 'emergency_exit'
            elif severity_level == 'moderate' and reversal_prob > 0.7:
                return 'emergency_exit'
            elif reversal_prob > 0.7:
                return 'prepare_exit'
            else:
                return 'monitor_closely'
        else:  # downward
            if severity_level == 'critical':
                return 'consider_exit'
            elif severity_level == 'severe':
                return 'consider_rebalance'
            else:
                return 'monitor'
    
    def calculate_rebalance_decision(
        self,
        position: Dict,
        break_info: Dict,
        gas_price: float,
        slippage_estimate: float = 0.01
    ) -> Dict:
        """
        Calculate whether to rebalance or exit based on expected value.
        
        Args:
            position: Position information
            break_info: Range break information
            gas_price: Current gas price in USD
            slippage_estimate: Estimated slippage percentage
            
        Returns:
            Decision analysis with recommendation
        """
        invested_amount = position.get('invested_amount', 0)
        current_value = position.get('current_value', invested_amount)
        
        # Calculate costs
        rebalance_gas_cost = gas_price * 2  # Entry + exit
        exit_gas_cost = gas_price
        
        rebalance_slippage_cost = current_value * slippage_estimate * 2  # Round trip
        exit_slippage_cost = current_value * slippage_estimate
        
        # Get reversal analysis
        reversal_analysis = self.analyze_range_break_probability(
            {},  # Empty history for now
            break_info
        )
        
        # Calculate expected values
        reversal_prob = reversal_analysis['reversal_probability']
        expected_loss_pct = reversal_analysis['expected_loss_if_reversal']
        
        # EV of holding (do nothing)
        ev_hold = -reversal_prob * (current_value * expected_loss_pct / 100)
        
        # EV of exiting
        ev_exit = -exit_gas_cost - exit_slippage_cost
        
        # EV of rebalancing (assume 50% chance of success)
        rebalance_success_prob = 1 - reversal_prob
        ev_rebalance = (
            rebalance_success_prob * 0 -  # No loss if successful
            reversal_prob * (current_value * expected_loss_pct / 100) -
            rebalance_gas_cost - 
            rebalance_slippage_cost
        )
        
        # Determine best action
        if ev_exit > ev_hold and ev_exit > ev_rebalance:
            action = 'exit'
            expected_cost = exit_gas_cost + exit_slippage_cost
        elif ev_rebalance > ev_hold and ev_rebalance > ev_exit:
            action = 'rebalance'
            expected_cost = rebalance_gas_cost + rebalance_slippage_cost
        else:
            action = 'hold'
            expected_cost = 0
        
        return {
            'recommended_action': action,
            'expected_values': {
                'hold': ev_hold,
                'exit': ev_exit,
                'rebalance': ev_rebalance
            },
            'expected_cost': expected_cost,
            'break_severity': break_info['severity'],
            'reversal_probability': reversal_prob,
            'confidence': reversal_analysis['confidence']
        }
    
    def detect_whipsaw_pattern(
        self,
        break_history: List[Dict],
        time_window_hours: int = 24
    ) -> Dict:
        """
        Detect whipsaw patterns in range break history.
        
        Args:
            break_history: List of range break events
            time_window_hours: Time window to analyze
            
        Returns:
            Whipsaw detection results
        """
        if not break_history:
            return {
                'whipsaw_detected': False,
                'severity': 0,
                'pattern': 'none',
                'break_count': 0
            }
        
        # Filter events within time window
        cutoff_time = datetime.utcnow() - timedelta(hours=time_window_hours)
        recent_breaks = [
            b for b in break_history 
            if datetime.fromisoformat(b['timestamp']) > cutoff_time
        ]
        
        if len(recent_breaks) < 2:
            return {
                'whipsaw_detected': False,
                'severity': 0,
                'pattern': 'none',
                'break_count': len(recent_breaks)
            }
        
        # Count direction changes
        direction_changes = 0
        for i in range(1, len(recent_breaks)):
            if recent_breaks[i]['type'] != recent_breaks[i-1]['type']:
                direction_changes += 1
        
        # Calculate whipsaw severity
        break_frequency = len(recent_breaks) / (time_window_hours / 24)  # Breaks per day
        
        # Determine pattern
        if direction_changes >= 3 and break_frequency > 3:
            pattern = 'high_frequency_reversal'
            severity = min(100, direction_changes * 20 + break_frequency * 10)
        elif direction_changes >= 2 and break_frequency > 2:
            pattern = 'moderate_whipsaw'
            severity = min(80, direction_changes * 15 + break_frequency * 8)
        elif direction_changes >= 1:
            pattern = 'mild_oscillation'
            severity = min(60, direction_changes * 10 + break_frequency * 5)
        else:
            pattern = 'directional_break'
            severity = min(40, break_frequency * 10)
        
        whipsaw_detected = severity > 50
        
        return {
            'whipsaw_detected': whipsaw_detected,
            'severity': severity,
            'pattern': pattern,
            'break_count': len(recent_breaks),
            'direction_changes': direction_changes,
            'break_frequency': break_frequency,
            'recommended_action': self._get_whipsaw_recommendation(severity, pattern)
        }
    
    def _get_whipsaw_recommendation(self, severity: float, pattern: str) -> str:
        """Get recommendation for whipsaw pattern."""
        if severity > 80:
            return 'exit'
        elif severity > 60:
            return 'reduce_position'
        elif severity > 40:
            return 'widen_range'
        else:
            return 'monitor'
    
    def _tick_to_price(self, tick: int) -> float:
        """Convert tick to price (simplified)."""
        return 1.0001 ** tick
    
    def calculate_new_range_after_break(
        self,
        current_price: float,
        break_type: str,
        volatility: float,
        multiplier: float = 2.0
    ) -> Tuple[float, float]:
        """
        Calculate new range after a break.
        
        Args:
            current_price: Current pool price
            break_type: Type of break that occurred
            volatility: Current volatility
            multiplier: Range width multiplier
            
        Returns:
            Tuple of (lower_price, upper_price)
        """
        # Calculate base range
        range_width = volatility * multiplier / 100
        
        # Adjust for break type
        if break_type == 'upward':
            # Shift range up but keep it wider
            lower_price = current_price * (1 - range_width * 0.8)
            upper_price = current_price * (1 + range_width * 1.2)
        elif break_type == 'downward':
            # Shift range down but keep it wider
            lower_price = current_price * (1 - range_width * 1.2)
            upper_price = current_price * (1 + range_width * 0.8)
        else:
            # Symmetric range
            lower_price = current_price * (1 - range_width)
            upper_price = current_price * (1 + range_width)
        
        return (lower_price, upper_price)