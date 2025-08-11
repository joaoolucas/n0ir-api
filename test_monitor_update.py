#!/usr/bin/env python3
"""
Test the updated monitor endpoint.
"""
import asyncio
from app.core.strategy_service import strategy_service
from app.schemas.strategy import MonitorPositionsRequest

async def test_monitor_update():
    print("Testing updated monitor endpoint...")
    
    # Test with user address only
    request = MonitorPositionsRequest(
        user_address="0x27f4f543c35ee533A7566663C0207Eb179FbA656"
    )
    
    try:
        response = await strategy_service.monitor_positions(request)
        print(f"✓ Monitor endpoint works with user address only")
        print(f"  - Found {len(response.positions)} positions")
        print(f"  - Portfolio value: ${response.portfolio_metrics.total_value:.2f}")
        print(f"  - Risk score: {response.portfolio_metrics.risk_score:.1f}")
        
        for pos in response.positions[:3]:
            print(f"  - Position {pos.token_id}: {pos.status}, Health={pos.health_score:.1f}")
            
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_monitor_update())