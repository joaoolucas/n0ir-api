"""
Tests for the EffectiveAPR calculator
"""
import pytest
from app.core.effective_apr_calculator import EffectiveAPRCalculator


class TestEffectiveAPRCalculator:
    """Test suite for EffectiveAPRCalculator"""
    
    @pytest.fixture
    def calculator(self):
        """Create calculator instance for tests"""
        return EffectiveAPRCalculator()
    
    def test_formula_tick_spacing_below_100(self, calculator):
        """Test formula for tick spacing < 100 with penalty factor"""
        # Test case from formula.md: tick_spacing=50, range=2%, APR=1000%
        result = calculator.calculate_effective_apr(
            original_apr=1000,
            tick_spacing=50,
            total_range_percentage=0.02  # 2% range
        )
        # Expected: 1000 / ((0.02 * 100 * 2) + 1) = 1000 / 5 = 200
        assert abs(result - 200) < 0.1
        
        # Test with tick_spacing=10
        result = calculator.calculate_effective_apr(
            original_apr=1000,
            tick_spacing=10,
            total_range_percentage=0.02
        )
        # Expected: 1000 / ((0.02 * 100 * 10) + 1) = 1000 / 21 = 47.62
        assert abs(result - 47.62) < 0.1
        
        # Test with tick_spacing=1
        result = calculator.calculate_effective_apr(
            original_apr=1000,
            tick_spacing=1,
            total_range_percentage=0.02
        )
        # Expected: 1000 / ((0.02 * 100 * 100) + 1) = 1000 / 201 = 4.98
        assert abs(result - 4.98) < 0.1
    
    def test_formula_tick_spacing_100_and_above(self, calculator):
        """Test formula for tick spacing >= 100 without penalty factor"""
        # Test with tick_spacing=100
        result = calculator.calculate_effective_apr(
            original_apr=1000,
            tick_spacing=100,
            total_range_percentage=0.20  # 20% range
        )
        # Expected: 1000 / (0.20 * 100 * 1) = 1000 / 20 = 50
        assert abs(result - 50) < 0.1
        
        # Test with tick_spacing=200
        result = calculator.calculate_effective_apr(
            original_apr=1000,
            tick_spacing=200,
            total_range_percentage=0.20
        )
        # Expected: 1000 / (0.20 * 100 * 0.5) = 1000 / 10 = 100
        assert abs(result - 100) < 0.1
        
        # Test with tick_spacing=2000
        result = calculator.calculate_effective_apr(
            original_apr=1000,
            tick_spacing=2000,
            total_range_percentage=0.20
        )
        # Expected: 1000 / (0.20 * 100 * 0.05) = 1000 / 1 = 1000
        assert abs(result - 1000) < 0.1
    
    def test_edge_cases(self, calculator):
        """Test edge cases and error handling"""
        # Test with zero tick spacing (should return 0)
        result = calculator.calculate_effective_apr(
            original_apr=100,
            tick_spacing=0,
            total_range_percentage=0.1
        )
        assert result == 0.0
        
        # Test with negative APR (should return 0)
        result = calculator.calculate_effective_apr(
            original_apr=-100,
            tick_spacing=100,
            total_range_percentage=0.1
        )
        assert result == 0.0
        
        # Test with zero range (should return 0)
        result = calculator.calculate_effective_apr(
            original_apr=100,
            tick_spacing=100,
            total_range_percentage=0
        )
        assert result == 0.0
        
        # Test with very large range
        result = calculator.calculate_effective_apr(
            original_apr=100,
            tick_spacing=100,
            total_range_percentage=10  # 1000% range
        )
        # Should be very small but non-negative
        assert result >= 0
        assert result < 1
    
    def test_calculate_from_ticks(self, calculator):
        """Test calculation from tick values"""
        # Test with a reasonable range
        result = calculator.calculate_effective_apr_from_ticks(
            original_apr=500,
            tick_spacing=100,
            lower_tick=-1000,
            upper_tick=1000,
            current_tick=0
        )
        # Should return a reasonable value
        assert result > 0
        assert result <= 500
    
    def test_apr_efficiency(self, calculator):
        """Test APR efficiency calculation"""
        # Test 50% efficiency
        efficiency = calculator.calculate_apr_efficiency(
            original_apr=100,
            effective_apr=50
        )
        assert efficiency == 50.0
        
        # Test 100% efficiency (no loss)
        efficiency = calculator.calculate_apr_efficiency(
            original_apr=100,
            effective_apr=100
        )
        assert efficiency == 100.0
        
        # Test with zero original APR
        efficiency = calculator.calculate_apr_efficiency(
            original_apr=0,
            effective_apr=0
        )
        assert efficiency == 0.0
    
    def test_multiple_ranges(self, calculator):
        """Test calculation for multiple standard ranges"""
        results = calculator.calculate_multiple_ranges(
            original_apr=1000,
            tick_spacing=100
        )
        
        # Check that all standard ranges are calculated
        assert 'narrow' in results  # 5% range
        assert 'standard' in results  # 10% range
        assert 'wide' in results  # 20% range
        
        # Check that narrower ranges have higher effective APR
        assert results['narrow'] > results['standard']
        assert results['standard'] > results['wide']
        
        # All should be less than or equal to original
        assert results['narrow'] <= 1000
        assert results['standard'] <= 1000
        assert results['wide'] <= 1000
    
    def test_optimal_range_for_target_apr(self, calculator):
        """Test finding optimal range for target APR"""
        # Find range needed for 100% effective APR from 500% base
        range_width = calculator.calculate_optimal_range_for_target_apr(
            target_effective_apr=100,
            base_apr=500,
            tick_spacing=100
        )
        
        # Verify the range gives approximately the target APR
        actual_apr = calculator.calculate_effective_apr(
            original_apr=500,
            tick_spacing=100,
            total_range_percentage=range_width
        )
        assert abs(actual_apr - 100) < 1
    
    def test_risk_adjusted_apr(self, calculator):
        """Test risk-adjusted APR calculation"""
        # Test with moderate volatility and range
        risk_adjusted = calculator.calculate_risk_adjusted_apr(
            effective_apr=100,
            volatility=20,
            range_width=0.1,  # 10% range
            tick_spacing=100
        )
        
        # Should be less than effective APR due to risk
        assert risk_adjusted < 100
        assert risk_adjusted > 0
        
        # Higher volatility should reduce risk-adjusted APR more
        high_vol_adjusted = calculator.calculate_risk_adjusted_apr(
            effective_apr=100,
            volatility=50,
            range_width=0.1,
            tick_spacing=100
        )
        assert high_vol_adjusted < risk_adjusted
    
    def test_validate_and_calculate(self, calculator):
        """Test validation with error messages"""
        # Valid calculation
        apr, error = calculator.validate_and_calculate(
            original_apr=100,
            tick_spacing=100,
            total_range_percentage=0.1
        )
        assert apr > 0
        assert error is None
        
        # Invalid tick spacing
        apr, error = calculator.validate_and_calculate(
            original_apr=100,
            tick_spacing=0,
            total_range_percentage=0.1
        )
        assert apr == 0.0
        assert "Invalid tick spacing" in error
        
        # Invalid range (too wide)
        apr, error = calculator.validate_and_calculate(
            original_apr=100,
            tick_spacing=100,
            total_range_percentage=11  # >1000%
        )
        assert apr == 0.0
        assert "too wide" in error
        
        # Negative APR
        apr, error = calculator.validate_and_calculate(
            original_apr=-100,
            tick_spacing=100,
            total_range_percentage=0.1
        )
        assert apr == 0.0
        assert "cannot be negative" in error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])