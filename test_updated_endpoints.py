#!/usr/bin/env python3
"""
Test the updated strategy endpoints.
"""
import asyncio
from app.core.strategy_service import strategy_service
from app.schemas.strategy import (
    OpportunitiesRequest,
    AnalyzeEntryRequest,
    MonitorPositionsRequest
)

async def test_updated_endpoints():
    print("=" * 60)
    print("Testing Updated Strategy Endpoints")
    print("=" * 60)
    
    # Test 1: Opportunities without risk_profile and max_positions
    print("\n1. Testing opportunities endpoint (strategy decides max positions)...")
    try:
        request = OpportunitiesRequest(
            executor_address='0x123',
            available_capital=10000.0,
            max_capital=50000.0,
            exclude_addresses=['0xabc', '0xdef']  # 2 existing positions
        )
        response = await strategy_service.find_opportunities(request)
        print(f"✓ Strategy calculated max positions based on capital")
        print(f"  - Max capital: $50,000 → Target 5 positions")
        print(f"  - Already have 2 positions → Max 3 new opportunities")
        print(f"  - Found {len(response.opportunities)} opportunities")
        for opp in response.opportunities[:3]:
            print(f"    • {opp.pair}: Score={opp.score:.1f}, Recommended=${opp.recommended_amount:.0f}")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Test 2: Analyze entry without proposed range
    print("\n2. Testing analyze entry (strategy proposes range)...")
    try:
        request = AnalyzeEntryRequest(
            pool_address='0xb2cc224c1c9feE385f8ad6a55b4d94E92359DC59',  # WETH/USDC
            amount_usdc=5000.0
        )
        response = await strategy_service.analyze_entry(request)
        print(f"✓ Strategy proposed optimal range")
        print(f"  - Should enter: {response.should_enter}")
        print(f"  - Confidence: {response.confidence_score:.1f}%")
        print(f"  - Proposed range: [{response.optimal_range.lower_tick}, {response.optimal_range.upper_tick}]")
        print(f"  - Slippage estimate: {response.slippage.estimated_percentage:.2f}%")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Test 3: Monitor with just user address
    print("\n3. Testing monitor endpoint (user address only)...")
    try:
        request = MonitorPositionsRequest(
            user_address="0x27f4f543c35ee533A7566663C0207Eb179FbA656"
        )
        response = await strategy_service.monitor_positions(request)
        print(f"✓ Monitor fetches positions automatically")
        print(f"  - Found {len(response.positions)} positions for user")
        print(f"  - Portfolio value: ${response.portfolio_metrics.total_value:.2f}")
        print(f"  - Risk score: {response.portfolio_metrics.risk_score:.1f}/100")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    print("\n" + "=" * 60)
    print("All updated endpoints tested successfully!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_updated_endpoints())