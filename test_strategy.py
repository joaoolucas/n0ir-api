#!/usr/bin/env python3
"""
Test script for strategy module endpoints.
"""
import asyncio
from app.core.strategy_service import strategy_service
from app.schemas.strategy import (
    OpportunitiesRequest,
    SlippageCalculationRequest,
    RiskAssessmentResponse
)

async def test_strategy_module():
    print("=" * 60)
    print("Testing n0ir Strategy Module")
    print("=" * 60)
    
    # Test 1: Find Opportunities
    print("\n1. Testing find_opportunities...")
    try:
        request = OpportunitiesRequest(
            executor_address='0x123',
            available_capital=10000.0,
            max_positions=5,
            exclude_addresses=[],
            risk_profile='balanced'
        )
        response = await strategy_service.find_opportunities(request)
        print(f"✓ Found {len(response.opportunities)} opportunities")
        for opp in response.opportunities[:3]:
            print(f"  - {opp.pair}: Score={opp.score:.1f}, APR={opp.expected_apr:.1f}%")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Test 2: Calculate Slippage
    print("\n2. Testing slippage calculation...")
    try:
        request = SlippageCalculationRequest(
            pool_address='0xb2cc224c1c9feE385f8ad6a55b4d94E92359DC59',  # WETH/USDC
            pair='WETH/USDC',
            action='enter',
            amount_usdc=5000.0,
            current_tvl=2000000.0,
            volatility_24h=15.0
        )
        response = await strategy_service.calculate_slippage(request)
        print(f"✓ Slippage calculated:")
        print(f"  - Base: {response.base_slippage:.2f}%")
        print(f"  - Size Impact: {response.size_impact:.2f}%")
        print(f"  - Total: {response.total_slippage:.2f}%")
        print(f"  - Classification: {response.pair_classification}")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Test 3: Risk Assessment
    print("\n3. Testing risk assessment...")
    try:
        response = await strategy_service.assess_risk()
        print(f"✓ Risk assessment complete:")
        print(f"  - Risk Score: {response.risk_score:.1f}/100")
        print(f"  - 1-day VaR: ${response.portfolio_var.var_1d_95:.2f}")
        print(f"  - Pool Concentration: {response.concentration_risk.highest_pool_percentage:.1f}%")
        print(f"  - Warnings: {len(response.warnings)}")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Test 4: Performance Analytics
    print("\n4. Testing performance analytics...")
    try:
        response = await strategy_service.get_performance_analytics('24h', None)
        print(f"✓ Performance analytics retrieved:")
        print(f"  - Total PnL: ${response.returns.total_pnl:.2f}")
        print(f"  - APR: {response.returns.apr:.1f}%")
        print(f"  - Sharpe Ratio: {response.risk_metrics.sharpe_ratio:.2f}")
        print(f"  - Win Rate: {response.risk_metrics.win_rate:.1%}")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    print("\n" + "=" * 60)
    print("Strategy module tests completed!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_strategy_module())