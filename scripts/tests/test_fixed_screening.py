import asyncio
from app.schemas.strategy import OpportunitiesRequest
from app.core.strategy_service import strategy_service

async def test():
    # Test with the user that has CDP wallet positions
    executor = '0xC2952cc28EDf37B053188D89e6ac888B9855d132'
    
    request = OpportunitiesRequest(
        executor_address=executor,
        available_capital=12.5  # Small amount for testing
    )
    
    print(f"Testing screening for {executor}")
    print(f"Available capital: ${request.available_capital}")
    
    response = await strategy_service.find_opportunities(request)
    
    print(f"\nFound {len(response.opportunities)} opportunities")
    for opp in response.opportunities[:3]:  # Show first 3
        print(f"  - {opp.pool_name}: APR {opp.apr_estimate:.1f}%")
        print(f"    Pool address: {opp.pool_address}")
    
    # Check if WETH/USDC pool is in the results
    weth_usdc_pool = '0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59'
    pool_addresses = [opp.pool_address.lower() for opp in response.opportunities]
    
    if weth_usdc_pool in pool_addresses:
        print(f"\n✗ ERROR: WETH/USDC pool is STILL being suggested (should be excluded)")
    else:
        print(f"\n✓ SUCCESS: WETH/USDC pool is NOT in suggestions (correctly excluded)")

if __name__ == "__main__":
    asyncio.run(test())