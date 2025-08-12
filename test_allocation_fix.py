#!/usr/bin/env python3
"""
Test script to verify allocation improvements for $5k capital scenario.
This demonstrates the fixes for:
1. Under-allocation (was only 39% of capital)
2. Missing safer pools like USDC/WETH
3. Too conservative position sizes
"""

import asyncio
from app.core.strategy_service import strategy_service
from app.schemas.strategy import OpportunitiesRequest


async def test_allocation():
    """Test the improved allocation logic with $5k capital."""
    
    print("\n" + "="*60)
    print("Testing Strategy Allocation with $5,000 Capital")
    print("="*60)
    
    # Create request for $5k capital
    request = OpportunitiesRequest(
        executor_address="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",  # Test address
        available_capital=5000.0
    )
    
    # Get opportunities
    response = await strategy_service.find_opportunities(request)
    
    # Analyze results
    print(f"\nOptimal Position Count: {response.optimal_position_count}")
    print(f"Minimum Position Size: ${response.minimum_position_size:.2f}")
    print(f"Opportunities Found: {len(response.opportunities)}")
    
    total_allocated = 0
    print("\n" + "-"*60)
    print("RECOMMENDED ALLOCATIONS:")
    print("-"*60)
    
    for i, opp in enumerate(response.opportunities, 1):
        total_allocated += opp.recommended_amount
        allocation_pct = (opp.recommended_amount / request.available_capital) * 100
        
        print(f"\n{i}. {opp.pair}")
        print(f"   Pool Address: {opp.pool_address}")
        print(f"   Score: {opp.score:.1f}")
        print(f"   Effective APR: {opp.effective_apr:.1f}%")
        print(f"   APR Efficiency: {opp.apr_efficiency:.1f}%")
        print(f"   Recommended Amount: ${opp.recommended_amount:.2f} ({allocation_pct:.1f}% of capital)")
        print(f"   Range: {opp.recommended_range.lower_percentage:.1f}% below to {opp.recommended_range.upper_percentage:.1f}% above")
        print(f"   Entry Conditions Met: {opp.entry_conditions_met}")
    
    print("\n" + "="*60)
    print("ALLOCATION SUMMARY:")
    print("="*60)
    print(f"Total Capital Available: ${request.available_capital:,.2f}")
    print(f"Total Capital Allocated: ${total_allocated:,.2f}")
    print(f"Allocation Efficiency: {(total_allocated/request.available_capital)*100:.1f}%")
    print(f"Unallocated Capital: ${request.available_capital - total_allocated:,.2f}")
    
    # Check if we fixed the issues
    print("\n" + "="*60)
    print("ISSUE VERIFICATION:")
    print("="*60)
    
    allocation_efficiency = (total_allocated/request.available_capital)*100
    
    # Issue 1: Under-allocation (was 39%)
    if allocation_efficiency >= 75:
        print("✓ Issue 1 FIXED: Allocation efficiency is {:.1f}% (target: 75-90%)".format(allocation_efficiency))
    else:
        print("✗ Issue 1 NOT FIXED: Allocation efficiency is only {:.1f}% (target: 75-90%)".format(allocation_efficiency))
    
    # Issue 2: Check for USDC/WETH or similar safe pairs
    safe_pairs = ['USDC/WETH', 'WETH/USDC', 'USDC/cbBTC', 'EURC/USDC']
    has_safe_pair = any(opp.pair in safe_pairs or 
                        any(safe in opp.pair for safe in ['USDC', 'EURC']) 
                        for opp in response.opportunities)
    
    if has_safe_pair:
        print("✓ Issue 2 FIXED: Safer pairs are being recommended")
    else:
        print("✗ Issue 2 NOT FIXED: No safer pairs like USDC/WETH recommended")
    
    # Issue 3: Position sizes too small (was ~$650 each)
    if response.opportunities:
        avg_position = total_allocated / len(response.opportunities)
        if avg_position >= 1400:  # Should be ~$1,666 for 3 positions
            print(f"✓ Issue 3 FIXED: Average position size is ${avg_position:.2f} (target: $1,400+)")
        else:
            print(f"✗ Issue 3 NOT FIXED: Average position size is only ${avg_position:.2f} (target: $1,400+)")
    
    print("\n" + "="*60)
    print("Test Complete")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(test_allocation())