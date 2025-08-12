"""
Portfolio-level risk and performance analysis for DeFi positions.
"""
import math
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from collections import defaultdict


class PortfolioAnalyzer:
    """
    Analyzes portfolio-level metrics including VaR, concentration risk, and performance.
    """
    
    # Risk thresholds
    RISK_THRESHOLDS = {
        'max_pool_concentration': 0.25,      # 25% max in single pool
        'max_token_concentration': 0.40,     # 40% max in single token
        'max_var_1d': 0.05,                 # 5% 1-day VaR
        'max_var_7d': 0.10,                 # 10% 7-day VaR
        'min_sharpe_ratio': 1.5,            # Minimum acceptable Sharpe
        'max_correlation': 0.7               # Max correlation between positions
    }
    
    # Risk score weights
    RISK_WEIGHTS = {
        'var': 0.35,
        'concentration': 0.30,
        'range_break': 0.20,
        'volatility': 0.15
    }
    
    def calculate_portfolio_var(
        self,
        positions: List[Dict],
        confidence: float = 0.95,
        time_horizon_days: int = 1
    ) -> Dict:
        """
        Calculate portfolio Value at Risk.
        
        Args:
            positions: List of position dictionaries
            confidence: Confidence level (e.g., 0.95 for 95%)
            time_horizon_days: Time horizon in days
            
        Returns:
            VaR metrics dictionary
        """
        if not positions:
            return {
                'var_amount': 0,
                'var_percentage': 0,
                'confidence': confidence,
                'time_horizon_days': time_horizon_days
            }
        
        # Calculate total portfolio value
        total_value = sum(p.get('current_value', p.get('invested_amount', 0)) 
                         for p in positions)
        
        if total_value <= 0:
            return {
                'var_amount': 0,
                'var_percentage': 0,
                'confidence': confidence,
                'time_horizon_days': time_horizon_days
            }
        
        # Get z-score for confidence level
        z_score = self._get_z_score(confidence)
        
        # Calculate individual position VaRs
        position_vars = []
        for position in positions:
            pos_value = position.get('current_value', position.get('invested_amount', 0))
            volatility = position.get('volatility_24h', 20) / 100  # Convert to decimal
            
            # Scale volatility to time horizon
            scaled_volatility = volatility * math.sqrt(time_horizon_days)
            
            # Calculate position VaR
            pos_var = pos_value * scaled_volatility * z_score
            position_vars.append(pos_var)
        
        # Simple portfolio VaR (assumes no correlation)
        # In production, would use correlation matrix
        portfolio_var = math.sqrt(sum(v**2 for v in position_vars))
        
        # Calculate range break specific VaR
        range_break_var = self.calculate_range_break_specific_var(positions)
        
        # Total VaR includes range break risk
        total_var = math.sqrt(portfolio_var**2 + range_break_var**2)
        
        return {
            'var_amount': total_var,
            'var_percentage': (total_var / total_value) * 100,
            'portfolio_var': portfolio_var,
            'range_break_var': range_break_var,
            'confidence': confidence,
            'time_horizon_days': time_horizon_days,
            'total_portfolio_value': total_value
        }
    
    def _get_z_score(self, confidence: float) -> float:
        """Get z-score for confidence level."""
        z_scores = {
            0.90: 1.28,
            0.95: 1.65,
            0.99: 2.33
        }
        return z_scores.get(confidence, 1.65)
    
    def calculate_range_break_specific_var(
        self,
        positions: List[Dict],
        reversal_probability: float = 0.70
    ) -> float:
        """
        Calculate VaR specific to range break risks.
        
        Args:
            positions: List of positions
            reversal_probability: Probability of reversal after upward break
            
        Returns:
            Range break specific VaR
        """
        range_break_risk = 0
        
        for position in positions:
            pos_value = position.get('current_value', position.get('invested_amount', 0))
            
            # Check if position is near range boundary
            range_status = position.get('range_status', {})
            price_position = range_status.get('price_position', 0.5)  # 0-1 within range
            
            # Risk increases as price approaches boundaries
            if price_position < 0.2 or price_position > 0.8:
                # Near boundary - higher risk
                boundary_risk = pos_value * 0.12 * reversal_probability  # 12% potential loss
                range_break_risk += boundary_risk
            elif price_position < 0.3 or price_position > 0.7:
                # Moderate distance from boundary
                boundary_risk = pos_value * 0.08 * reversal_probability * 0.5
                range_break_risk += boundary_risk
        
        return range_break_risk
    
    def analyze_portfolio_concentration(self, positions: List[Dict]) -> Dict:
        """
        Analyze concentration risk in the portfolio.
        
        Args:
            positions: List of positions
            
        Returns:
            Concentration analysis
        """
        if not positions:
            return {
                'pool_concentration': {},
                'token_concentration': {},
                'highest_pool_percentage': 0,
                'highest_token_percentage': 0,
                'concentration_score': 100,  # Perfect score for empty portfolio
                'warnings': []
            }
        
        # Calculate total portfolio value
        total_value = sum(p.get('current_value', p.get('invested_amount', 0)) 
                         for p in positions)
        
        if total_value <= 0:
            return {
                'pool_concentration': {},
                'token_concentration': {},
                'highest_pool_percentage': 0,
                'highest_token_percentage': 0,
                'concentration_score': 0,
                'warnings': ['Portfolio has zero value']
            }
        
        # Pool concentration
        pool_values = defaultdict(float)
        for position in positions:
            pool_address = position.get('pool_address', 'unknown')
            pos_value = position.get('current_value', position.get('invested_amount', 0))
            pool_values[pool_address] += pos_value
        
        pool_concentration = {
            pool: (value / total_value) * 100 
            for pool, value in pool_values.items()
        }
        
        # Token concentration
        token_values = defaultdict(float)
        for position in positions:
            # Extract tokens from pair (simplified)
            pair = position.get('pair', '')
            if '/' in pair:
                token0, token1 = pair.split('/')
                pos_value = position.get('current_value', position.get('invested_amount', 0))
                # Assume 50/50 split for simplicity
                token_values[token0] += pos_value * 0.5
                token_values[token1] += pos_value * 0.5
        
        token_concentration = {
            token: (value / total_value) * 100 
            for token, value in token_values.items()
        }
        
        # Find highest concentrations
        highest_pool_pct = max(pool_concentration.values()) if pool_concentration else 0
        highest_token_pct = max(token_concentration.values()) if token_concentration else 0
        
        # Calculate concentration score (100 is best, 0 is worst)
        pool_penalty = max(0, highest_pool_pct - self.RISK_THRESHOLDS['max_pool_concentration'] * 100)
        token_penalty = max(0, highest_token_pct - self.RISK_THRESHOLDS['max_token_concentration'] * 100)
        concentration_score = max(0, 100 - pool_penalty - token_penalty)
        
        # Generate warnings
        warnings = []
        if highest_pool_pct > self.RISK_THRESHOLDS['max_pool_concentration'] * 100:
            warnings.append(f"Pool concentration too high: {highest_pool_pct:.1f}%")
        if highest_token_pct > self.RISK_THRESHOLDS['max_token_concentration'] * 100:
            warnings.append(f"Token concentration too high: {highest_token_pct:.1f}%")
        
        return {
            'pool_concentration': pool_concentration,
            'token_concentration': token_concentration,
            'highest_pool_percentage': highest_pool_pct,
            'highest_token_percentage': highest_token_pct,
            'concentration_score': concentration_score,
            'warnings': warnings
        }
    
    def calculate_sharpe_ratio(
        self,
        returns: List[float],
        risk_free_rate: float = 0.05
    ) -> float:
        """
        Calculate Sharpe ratio for returns series.
        
        Args:
            returns: List of periodic returns
            risk_free_rate: Annual risk-free rate
            
        Returns:
            Sharpe ratio
        """
        if not returns or len(returns) < 2:
            return 0
        
        # Calculate average return
        avg_return = sum(returns) / len(returns)
        
        # Calculate standard deviation
        variance = sum((r - avg_return) ** 2 for r in returns) / (len(returns) - 1)
        std_dev = math.sqrt(variance)
        
        if std_dev == 0:
            return 0
        
        # Annualize if needed (assuming daily returns)
        periods_per_year = 365
        annualized_return = avg_return * periods_per_year
        annualized_std = std_dev * math.sqrt(periods_per_year)
        
        # Calculate Sharpe ratio
        sharpe = (annualized_return - risk_free_rate) / annualized_std
        
        return sharpe
    
    def calculate_portfolio_metrics(
        self,
        positions: List[Dict],
        historical_returns: Optional[List[float]] = None
    ) -> Dict:
        """
        Calculate comprehensive portfolio metrics.
        
        Args:
            positions: List of positions
            historical_returns: Optional historical returns data
            
        Returns:
            Portfolio metrics
        """
        # Calculate total values
        total_value = sum(p.get('current_value', p.get('invested_amount', 0)) 
                         for p in positions)
        total_invested = sum(p.get('invested_amount', 0) for p in positions)
        
        # Calculate PnL
        unrealized_pnl = total_value - total_invested
        pnl_percentage = (unrealized_pnl / total_invested * 100) if total_invested > 0 else 0
        
        # Calculate weighted APR
        weighted_apr = 0
        for position in positions:
            pos_value = position.get('current_value', position.get('invested_amount', 0))
            apr = position.get('current_apr', 0)
            if total_value > 0:
                weight = pos_value / total_value
                weighted_apr += apr * weight
        
        # Calculate risk score
        risk_score = self.calculate_risk_score(positions)
        
        # Calculate Sharpe if we have historical data
        sharpe_ratio = 0
        if historical_returns:
            sharpe_ratio = self.calculate_sharpe_ratio(historical_returns)
        
        return {
            'total_value': total_value,
            'total_invested': total_invested,
            'unrealized_pnl': unrealized_pnl,
            'pnl_percentage': pnl_percentage,
            'current_apr': weighted_apr,
            'risk_score': risk_score,
            'sharpe_ratio': sharpe_ratio,
            'position_count': len(positions)
        }
    
    def calculate_risk_score(self, positions: List[Dict]) -> float:
        """
        Calculate overall portfolio risk score (0-100, lower is better).
        
        Args:
            positions: List of positions
            
        Returns:
            Risk score
        """
        if not positions:
            return 0
        
        scores = {}
        
        # VaR component
        var_metrics = self.calculate_portfolio_var(positions)
        var_pct = var_metrics['var_percentage']
        scores['var'] = min(100, (var_pct / self.RISK_THRESHOLDS['max_var_1d']) * 100)
        
        # Concentration component
        concentration = self.analyze_portfolio_concentration(positions)
        scores['concentration'] = 100 - concentration['concentration_score']
        
        # Range break component
        range_break_var = var_metrics.get('range_break_var', 0)
        total_value = var_metrics.get('total_portfolio_value', 1)
        range_break_pct = (range_break_var / total_value * 100) if total_value > 0 else 0
        scores['range_break'] = min(100, range_break_pct * 10)  # Scale up for sensitivity
        
        # Volatility component
        avg_volatility = sum(p.get('volatility_24h', 20) for p in positions) / len(positions)
        scores['volatility'] = min(100, avg_volatility * 2)  # Scale for 0-100
        
        # Calculate weighted risk score
        risk_score = sum(scores[component] * weight 
                        for component, weight in self.RISK_WEIGHTS.items())
        
        return min(100, max(0, risk_score))
    
    def generate_rebalancing_recommendations(
        self,
        positions: List[Dict],
        available_capital: float,
        risk_tolerance: str = 'balanced'
    ) -> List[Dict]:
        """
        Generate portfolio rebalancing recommendations.
        
        Args:
            positions: Current positions
            available_capital: Available capital for new positions
            risk_tolerance: Risk tolerance level
            
        Returns:
            List of rebalancing recommendations
        """
        recommendations = []
        
        # Analyze current portfolio
        concentration = self.analyze_portfolio_concentration(positions)
        metrics = self.calculate_portfolio_metrics(positions)
        
        # Check for overconcentration
        for pool_address, pct in concentration['pool_concentration'].items():
            if pct > self.RISK_THRESHOLDS['max_pool_concentration'] * 100:
                # Find the position
                for position in positions:
                    if position.get('pool_address') == pool_address:
                        recommendations.append({
                            'action': 'reduce',
                            'token_id': position.get('token_id'),
                            'pool_address': pool_address,
                            'target_percentage': 50,  # Reduce by half
                            'reason': f'Overconcentration: {pct:.1f}% of portfolio'
                        })
                        break
        
        # Check for underperforming positions
        avg_apr = metrics['current_apr']
        for position in positions:
            pos_apr = position.get('current_apr', 0)
            if pos_apr < avg_apr * 0.5:  # Less than half of average
                recommendations.append({
                    'action': 'close',
                    'token_id': position.get('token_id'),
                    'pool_address': position.get('pool_address'),
                    'reason': f'Underperforming: {pos_apr:.1f}% APR vs {avg_apr:.1f}% average'
                })
        
        # Check for positions with high range break risk
        for position in positions:
            range_status = position.get('range_status', {})
            if range_status.get('range_break_severity', 0) > 70:
                recommendations.append({
                    'action': 'rebalance',
                    'token_id': position.get('token_id'),
                    'pool_address': position.get('pool_address'),
                    'reason': 'High range break risk'
                })
        
        # Suggest new positions if capital available and not overconcentrated
        if available_capital > 1000 and len(positions) < 10:
            recommendations.append({
                'action': 'open',
                'suggested_amount': min(available_capital * 0.2, 5000),
                'reason': 'Diversification opportunity'
            })
        
        return recommendations
    
    def calculate_correlation_matrix(self, positions: List[Dict]) -> Dict:
        """
        Calculate correlation matrix for positions (simplified).
        
        Args:
            positions: List of positions
            
        Returns:
            Correlation analysis
        """
        # Simplified correlation based on token overlap
        correlations = {}
        
        for i, pos1 in enumerate(positions):
            for j, pos2 in enumerate(positions):
                if i >= j:
                    continue
                
                # Extract tokens
                pair1 = pos1.get('pair', '').split('/')
                pair2 = pos2.get('pair', '').split('/')
                
                # Calculate correlation based on token overlap
                common_tokens = set(pair1) & set(pair2)
                if len(common_tokens) == 2:
                    correlation = 1.0  # Same pair
                elif len(common_tokens) == 1:
                    correlation = 0.5  # One token in common
                else:
                    correlation = 0.0  # No tokens in common
                
                key = f"{pos1.get('pool_address', i)}_{pos2.get('pool_address', j)}"
                correlations[key] = correlation
        
        # Calculate average correlation
        avg_correlation = sum(correlations.values()) / len(correlations) if correlations else 0
        
        return {
            'correlation_matrix': correlations,
            'average_correlation': avg_correlation,
            'high_correlation_warning': avg_correlation > self.RISK_THRESHOLDS['max_correlation']
        }
    
    def get_dynamic_thresholds(
        self,
        positions: List[Dict],
        wallet_size: float,
        market_conditions: Optional[Dict] = None
    ) -> Dict:
        """
        Calculate dynamic risk thresholds based on portfolio safety and market conditions.
        
        These thresholds adapt based on:
        - Portfolio safety score
        - Wallet size (larger wallets need stricter thresholds)
        - Current market conditions
        - Portfolio composition
        
        Args:
            positions: Current positions
            wallet_size: Total wallet value in USD
            market_conditions: Optional market condition data
            
        Returns:
            Dynamic risk thresholds dictionary
        """
        # Import calculator for safety scores
        from app.core.strategy_calculator import StrategyCalculator
        calculator = StrategyCalculator()
        
        # Calculate average safety score of current positions
        avg_safety_score = 0
        if positions:
            safety_scores = []
            for position in positions:
                # Build pool data from position for safety calculation
                pool_data = {
                    'tvl_usd': position.get('pool_tvl', position.get('tvl', 1_000_000)),
                    'volume_24h': position.get('volume_24h', 100_000),
                    'token0': {'price_usd': position.get('token0_price', 1)},
                    'token1': {'price_usd': position.get('token1_price', 1)}
                }
                safety_scores.append(calculator.calculate_simple_safety_score(pool_data))
            avg_safety_score = sum(safety_scores) / len(safety_scores)
        else:
            # No positions = neutral safety
            avg_safety_score = 50
        
        # Base thresholds (copy from class defaults)
        thresholds = self.RISK_THRESHOLDS.copy()
        
        # Adjust based on portfolio safety
        if avg_safety_score >= 70:  # Very safe portfolio
            # Can tolerate slightly higher concentration
            thresholds['max_pool_concentration'] = 0.30  # 30% (from 25%)
            thresholds['max_token_concentration'] = 0.45  # 45% (from 40%)
            thresholds['max_var_1d'] = 0.06  # 6% (from 5%)
            thresholds['max_var_7d'] = 0.12  # 12% (from 10%)
        elif avg_safety_score >= 50:  # Moderate safety
            # Keep defaults
            pass
        else:  # Low safety portfolio
            # Need stricter thresholds
            thresholds['max_pool_concentration'] = 0.20  # 20% (from 25%)
            thresholds['max_token_concentration'] = 0.35  # 35% (from 40%)
            thresholds['max_var_1d'] = 0.04  # 4% (from 5%)
            thresholds['max_var_7d'] = 0.08  # 8% (from 10%)
        
        # Adjust based on wallet size
        if wallet_size >= 100_000:  # Large wallet
            # Stricter concentration limits for diversification
            thresholds['max_pool_concentration'] *= 0.8
            thresholds['max_token_concentration'] *= 0.85
            thresholds['min_sharpe_ratio'] = 2.0  # Higher Sharpe requirement
        elif wallet_size >= 50_000:  # Medium-large wallet
            thresholds['max_pool_concentration'] *= 0.9
            thresholds['max_token_concentration'] *= 0.95
            thresholds['min_sharpe_ratio'] = 1.75
        elif wallet_size >= 25_000:  # Medium wallet
            # Keep defaults
            pass
        elif wallet_size >= 10_000:  # Small-medium wallet
            # Can concentrate a bit more
            thresholds['max_pool_concentration'] *= 1.1
            thresholds['max_token_concentration'] *= 1.05
            thresholds['min_sharpe_ratio'] = 1.25
        else:  # Small wallet (<$10k)
            # Can concentrate more due to limited capital
            thresholds['max_pool_concentration'] = min(0.40, thresholds['max_pool_concentration'] * 1.2)
            thresholds['max_token_concentration'] = min(0.50, thresholds['max_token_concentration'] * 1.1)
            thresholds['min_sharpe_ratio'] = 1.0
        
        # Adjust based on market conditions if provided
        if market_conditions:
            market_volatility = market_conditions.get('market_volatility', 50)
            
            if market_volatility > 80:  # High volatility market
                # Stricter VaR limits
                thresholds['max_var_1d'] *= 0.8
                thresholds['max_var_7d'] *= 0.8
                thresholds['max_correlation'] = 0.6  # Lower correlation limit
            elif market_volatility > 60:  # Moderate-high volatility
                thresholds['max_var_1d'] *= 0.9
                thresholds['max_var_7d'] *= 0.9
            elif market_volatility < 20:  # Very low volatility
                # Can be slightly more aggressive
                thresholds['max_var_1d'] *= 1.2
                thresholds['max_var_7d'] *= 1.2
                thresholds['max_correlation'] = 0.8  # Higher correlation acceptable
        
        # Calculate position count recommendations
        optimal_positions = self._calculate_optimal_position_count(wallet_size, avg_safety_score)
        
        return {
            'thresholds': thresholds,
            'portfolio_safety_score': avg_safety_score,
            'wallet_size_category': self._get_wallet_size_category(wallet_size),
            'recommended_position_count': optimal_positions,
            'adjustments_applied': {
                'safety_based': avg_safety_score < 50 or avg_safety_score >= 70,
                'size_based': wallet_size < 25_000 or wallet_size >= 50_000,
                'market_based': market_conditions is not None
            }
        }
    
    def _calculate_optimal_position_count(self, wallet_size: float, safety_score: float) -> int:
        """
        Calculate optimal number of positions based on wallet size and safety.
        
        Args:
            wallet_size: Total wallet value
            safety_score: Average portfolio safety score
            
        Returns:
            Optimal number of positions
        """
        # Base count by wallet size
        if wallet_size < 1_000:
            base_count = 1
        elif wallet_size < 5_000:
            base_count = 2
        elif wallet_size < 10_000:
            base_count = 3
        elif wallet_size < 25_000:
            base_count = 4
        elif wallet_size < 50_000:
            base_count = 5
        elif wallet_size < 100_000:
            base_count = 7
        else:
            base_count = 10
        
        # Adjust based on safety
        if safety_score >= 70:
            # Very safe = can concentrate more
            return max(1, base_count - 1)
        elif safety_score < 40:
            # Low safety = need more diversification
            return min(15, base_count + 2)
        
        return base_count
    
    def _get_wallet_size_category(self, wallet_size: float) -> str:
        """
        Categorize wallet size.
        
        Args:
            wallet_size: Wallet value in USD
            
        Returns:
            Category string
        """
        if wallet_size < 1_000:
            return "micro"
        elif wallet_size < 10_000:
            return "small"
        elif wallet_size < 25_000:
            return "medium"
        elif wallet_size < 50_000:
            return "large"
        elif wallet_size < 100_000:
            return "xlarge"
        else:
            return "whale"