"""
Tests for the new dynamic allocation system.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta

from app.core.strategy_calculator import StrategyCalculator
from app.core.portfolio_analyzer import PortfolioAnalyzer
from app.core.strategy_service import StrategyService


class TestSafetyScoring:
    """Test safety score calculations."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.calculator = StrategyCalculator()
    
    def test_calculate_simple_safety_score_high_tvl(self):
        """Test safety score for high TVL pool."""
        pool_data = {
            'tvl_usd': 15_000_000,
            'volume_24h': 5_000_000,
            'token0': {'price_usd': 1800, 'symbol': 'ETH'},
            'token1': {'price_usd': 1, 'symbol': 'USDC'}
        }
        
        score = self.calculator.calculate_simple_safety_score(pool_data)
        
        # High TVL + good volume + stable pair = high score
        assert score >= 80
        assert score <= 100
    
    def test_calculate_simple_safety_score_low_tvl(self):
        """Test safety score for low TVL pool."""
        pool_data = {
            'tvl_usd': 100_000,
            'volume_24h': 10_000,
            'token0': {'price_usd': 0.0001, 'symbol': 'MEME'},
            'token1': {'price_usd': 1, 'symbol': 'USDC'}
        }
        
        score = self.calculator.calculate_simple_safety_score(pool_data)
        
        # Low TVL + low volume + meme token = low score
        assert score < 40
        assert score >= 0
    
    def test_calculate_simple_safety_score_stablecoin_pair(self):
        """Test safety score for stablecoin pair."""
        pool_data = {
            'tvl_usd': 2_000_000,
            'volume_24h': 800_000,
            'token0': {'price_usd': 1, 'symbol': 'USDC'},
            'token1': {'price_usd': 1, 'symbol': 'DAI'}
        }
        
        score = self.calculator.calculate_simple_safety_score(pool_data)
        
        # Stablecoin pairs get safety bonus
        assert score >= 70
    
    def test_calculate_simple_safety_score_medium_pool(self):
        """Test safety score for medium-sized pool."""
        pool_data = {
            'tvl_usd': 1_500_000,
            'volume_24h': 300_000,
            'token0': {'price_usd': 50, 'symbol': 'LINK'},
            'token1': {'price_usd': 1, 'symbol': 'USDC'}
        }
        
        score = self.calculator.calculate_simple_safety_score(pool_data)
        
        # Medium TVL + decent volume = moderate score
        assert 40 <= score <= 70


class TestDynamicPositionLimits:
    """Test dynamic position limit calculations."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.calculator = StrategyCalculator()
    
    def test_dynamic_position_limit_very_safe(self):
        """Test position limit for very safe pool."""
        limit = self.calculator.calculate_dynamic_position_limit(
            safety_score=85,
            wallet_size=50_000
        )
        
        # Very safe pool with medium wallet = 30% * 0.8 = 24%
        assert limit == pytest.approx(0.24, rel=0.01)
    
    def test_dynamic_position_limit_risky(self):
        """Test position limit for risky pool."""
        limit = self.calculator.calculate_dynamic_position_limit(
            safety_score=30,
            wallet_size=50_000
        )
        
        # Risky pool = 15% base * 0.8 = 12%
        assert limit == pytest.approx(0.12, rel=0.01)
    
    def test_dynamic_position_limit_small_wallet(self):
        """Test position limit for small wallet."""
        limit = self.calculator.calculate_dynamic_position_limit(
            safety_score=60,
            wallet_size=5_000
        )
        
        # Moderate safety + small wallet = 20% * 1.2 = 24%
        assert limit == pytest.approx(0.24, rel=0.01)
    
    def test_dynamic_position_limit_large_wallet(self):
        """Test position limit for large wallet."""
        limit = self.calculator.calculate_dynamic_position_limit(
            safety_score=75,
            wallet_size=150_000
        )
        
        # Safe pool + large wallet = 30% * 0.7 = 21%
        assert limit == pytest.approx(0.21, rel=0.01)


class TestAllocationWeights:
    """Test allocation weight calculations."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.calculator = StrategyCalculator()
    
    def test_allocation_weight_high_apr_high_safety(self):
        """Test allocation weight for high APR, high safety pool."""
        pool_data = {
            'effective_apr': 250,
            'tvl_usd': 10_000_000,
            'volume_24h': 3_000_000
        }
        safety_score = 85
        
        weight = self.calculator.calculate_allocation_weight(pool_data, safety_score)
        
        # High APR (100 score) + high safety (85) = high weight
        # (85 * 0.6) + (100 * 0.4) = 51 + 40 = 91
        assert weight == pytest.approx(91, rel=0.1)
    
    def test_allocation_weight_low_apr_high_safety(self):
        """Test allocation weight for low APR, high safety pool."""
        pool_data = {
            'effective_apr': 30,
            'tvl_usd': 10_000_000,
            'volume_24h': 3_000_000
        }
        safety_score = 85
        
        weight = self.calculator.calculate_allocation_weight(pool_data, safety_score)
        
        # Low APR (24 score) + high safety (85)
        # (85 * 0.6) + (24 * 0.4) = 51 + 9.6 = 60.6
        assert weight == pytest.approx(60.6, rel=0.1)
    
    def test_allocation_weight_high_apr_low_safety(self):
        """Test allocation weight for high APR, low safety pool."""
        pool_data = {
            'effective_apr': 200,
            'tvl_usd': 200_000,
            'volume_24h': 50_000
        }
        safety_score = 25
        
        weight = self.calculator.calculate_allocation_weight(pool_data, safety_score)
        
        # High APR (100) + low safety (25)
        # (25 * 0.6) + (100 * 0.4) = 15 + 40 = 55
        assert weight == pytest.approx(55, rel=0.1)


class TestPositionSizing:
    """Test position size calculations with dynamic limits."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.calculator = StrategyCalculator()
    
    def test_position_size_no_hard_cap(self):
        """Test that position sizing no longer has 25% hard cap."""
        pool_stats = {
            'tvl_usd': 15_000_000,
            'volume_24h': 5_000_000,
            'apr': 150,
            'effective_apr': 120,
            'token0': {'price_usd': 1800},
            'token1': {'price_usd': 1}
        }
        
        recommended, max_amount = self.calculator.calculate_position_size(
            pool_stats=pool_stats,
            available_capital=100_000,
            risk_profile='balanced'
        )
        
        # With very safe pool, max can be > 25%
        # Safety score should be high, allowing up to 40% * 0.7 = 28%
        assert max_amount > 25_000  # More than old 25% cap
        assert max_amount <= 40_000  # But not more than 40%
    
    def test_position_size_risky_pool_limited(self):
        """Test that risky pools get lower limits."""
        pool_stats = {
            'tvl_usd': 200_000,
            'volume_24h': 20_000,
            'apr': 300,
            'effective_apr': 150,
            'token0': {'price_usd': 0.001},
            'token1': {'price_usd': 1}
        }
        
        recommended, max_amount = self.calculator.calculate_position_size(
            pool_stats=pool_stats,
            available_capital=50_000,
            risk_profile='balanced'
        )
        
        # With risky pool, max should be limited
        assert max_amount <= 15_000  # 30% or less of capital
    
    def test_position_size_respects_minimum(self):
        """Test that position size respects minimum viable size."""
        pool_stats = {
            'tvl_usd': 1_000_000,
            'volume_24h': 200_000,
            'apr': 50,
            'effective_apr': 40
        }
        
        recommended, max_amount = self.calculator.calculate_position_size(
            pool_stats=pool_stats,
            available_capital=100,  # Very small capital
            risk_profile='balanced'
        )
        
        # Should return minimum position size
        min_size = self.calculator.calculate_minimum_position_size(50)
        assert recommended == min_size
        assert max_amount == min_size


class TestDynamicThresholds:
    """Test dynamic threshold calculations."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.analyzer = PortfolioAnalyzer()
    
    def test_dynamic_thresholds_safe_portfolio(self):
        """Test thresholds for safe portfolio."""
        positions = [
            {
                'pool_tvl': 10_000_000,
                'volume_24h': 3_000_000,
                'token0_price': 1800,
                'token1_price': 1
            },
            {
                'pool_tvl': 5_000_000,
                'volume_24h': 1_500_000,
                'token0_price': 50,
                'token1_price': 1
            }
        ]
        
        result = self.analyzer.get_dynamic_thresholds(
            positions=positions,
            wallet_size=50_000
        )
        
        # Safe portfolio should have relaxed thresholds
        assert result['thresholds']['max_pool_concentration'] > 0.25
        assert result['portfolio_safety_score'] >= 70
        assert result['wallet_size_category'] == 'large'
    
    def test_dynamic_thresholds_risky_portfolio(self):
        """Test thresholds for risky portfolio."""
        positions = [
            {
                'pool_tvl': 200_000,
                'volume_24h': 20_000,
                'token0_price': 0.0001,
                'token1_price': 1
            }
        ]
        
        result = self.analyzer.get_dynamic_thresholds(
            positions=positions,
            wallet_size=50_000
        )
        
        # Risky portfolio should have stricter thresholds
        assert result['thresholds']['max_pool_concentration'] < 0.25
        assert result['portfolio_safety_score'] < 50
    
    def test_dynamic_thresholds_wallet_size_adjustment(self):
        """Test thresholds adjust based on wallet size."""
        positions = []
        
        # Small wallet
        small_result = self.analyzer.get_dynamic_thresholds(
            positions=positions,
            wallet_size=5_000
        )
        
        # Large wallet
        large_result = self.analyzer.get_dynamic_thresholds(
            positions=positions,
            wallet_size=150_000
        )
        
        # Large wallets should have stricter concentration limits
        assert large_result['thresholds']['max_pool_concentration'] < \
               small_result['thresholds']['max_pool_concentration']
        
        assert small_result['wallet_size_category'] == 'small'
        assert large_result['wallet_size_category'] == 'whale'
    
    def test_dynamic_thresholds_market_conditions(self):
        """Test thresholds adjust based on market conditions."""
        positions = []
        
        # High volatility market
        high_vol_result = self.analyzer.get_dynamic_thresholds(
            positions=positions,
            wallet_size=50_000,
            market_conditions={'market_volatility': 90}
        )
        
        # Low volatility market
        low_vol_result = self.analyzer.get_dynamic_thresholds(
            positions=positions,
            wallet_size=50_000,
            market_conditions={'market_volatility': 15}
        )
        
        # High volatility should have stricter VaR limits
        assert high_vol_result['thresholds']['max_var_1d'] < \
               low_vol_result['thresholds']['max_var_1d']


class TestIntegration:
    """Integration tests for the allocation system."""
    
    @patch('app.core.strategy_service.StrategyService._get_pool_data')
    @patch('app.core.strategy_service.StrategyService._get_executor_positions')
    async def test_find_opportunities_with_safety_scoring(self, mock_positions, mock_pool_data):
        """Test that find_opportunities uses safety scoring correctly."""
        service = StrategyService()
        
        # Mock pool data
        mock_pool_data.return_value = [
            {
                'address': '0xaaa',
                'pair': 'ETH/USDC',
                'tvl_usd': 10_000_000,
                'volume_24h': 3_000_000,
                'apr': 150,
                'effective_apr': 120,
                'fee_tier': 0.003,
                'tick_spacing': 100,
                'current_tick': 1000,
                'volatility_24h': 30,
                'token0': {'symbol': 'ETH', 'price_usd': 1800},
                'token1': {'symbol': 'USDC', 'price_usd': 1}
            },
            {
                'address': '0xbbb',
                'pair': 'MEME/USDC',
                'tvl_usd': 100_000,
                'volume_24h': 50_000,
                'apr': 500,
                'effective_apr': 200,
                'fee_tier': 0.01,
                'tick_spacing': 200,
                'current_tick': -5000,
                'volatility_24h': 150,
                'token0': {'symbol': 'MEME', 'price_usd': 0.0001},
                'token1': {'symbol': 'USDC', 'price_usd': 1}
            }
        ]
        
        mock_positions.return_value = []
        
        # Call find_opportunities
        opportunities = await service.find_opportunities(
            executor_address='0x123',
            available_capital=50_000,
            risk_profile='balanced'
        )
        
        # Should prioritize safe pool despite lower APR
        assert len(opportunities) > 0
        
        # ETH/USDC should rank higher due to safety
        eth_pool = next((o for o in opportunities if 'ETH' in o['pair']), None)
        meme_pool = next((o for o in opportunities if 'MEME' in o['pair']), None)
        
        if eth_pool and meme_pool:
            # ETH pool should get higher allocation despite lower APR
            assert eth_pool['recommended_amount'] > meme_pool['recommended_amount']
    
    def test_position_count_recommendations(self):
        """Test optimal position count calculations."""
        calculator = StrategyCalculator()
        
        # Small wallet
        count_5k = calculator.calculate_optimal_position_count(5_000, 100)
        assert count_5k == 2
        
        # Medium wallet
        count_25k = calculator.calculate_optimal_position_count(25_000, 100)
        assert count_25k == 4
        
        # Large wallet
        count_100k = calculator.calculate_optimal_position_count(100_000, 100)
        assert count_100k == 7
        
        # Very large wallet
        count_500k = calculator.calculate_optimal_position_count(500_000, 100)
        assert count_500k == 7  # Capped at 7


class TestEdgeCases:
    """Test edge cases in the allocation system."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.calculator = StrategyCalculator()
        self.analyzer = PortfolioAnalyzer()
    
    def test_zero_tvl_pool(self):
        """Test safety score with zero TVL."""
        pool_data = {
            'tvl_usd': 0,
            'volume_24h': 0,
            'token0': {'price_usd': 1},
            'token1': {'price_usd': 1}
        }
        
        score = self.calculator.calculate_simple_safety_score(pool_data)
        assert score == 0
    
    def test_negative_apr(self):
        """Test allocation weight with negative APR."""
        pool_data = {
            'effective_apr': -10,
            'tvl_usd': 1_000_000,
            'volume_24h': 100_000
        }
        
        weight = self.calculator.calculate_allocation_weight(pool_data, 50)
        assert weight >= 0  # Should handle gracefully
    
    def test_extreme_wallet_sizes(self):
        """Test with extreme wallet sizes."""
        # Tiny wallet
        tiny_limit = self.calculator.calculate_dynamic_position_limit(50, 100)
        assert tiny_limit > 0
        
        # Huge wallet
        huge_limit = self.calculator.calculate_dynamic_position_limit(80, 10_000_000)
        assert huge_limit > 0
        assert huge_limit < 1  # Still a percentage
    
    def test_empty_portfolio_thresholds(self):
        """Test thresholds with empty portfolio."""
        result = self.analyzer.get_dynamic_thresholds(
            positions=[],
            wallet_size=50_000
        )
        
        # Should use neutral safety score (50)
        assert result['portfolio_safety_score'] == 50
        assert 'thresholds' in result
        assert result['recommended_position_count'] > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])