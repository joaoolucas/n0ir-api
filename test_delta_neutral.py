#!/usr/bin/env python3
"""
Test script for delta-neutral strategy endpoint.
"""
import asyncio
from decimal import Decimal
from app.core.gpt_strategy_service import gpt_strategy_service


async def test_gpt_strategy():
    """Test GPT strategy generation (will use fallback if no API key)."""
    print("\n=== Testing GPT Strategy Service ===")

    # Test initial strategy generation
    strategy = await gpt_strategy_service.generate_initial_strategy(
        balance=5000,
        existing_positions=[],
        pool_data={
            "WETH/USDC": {"apr": 120},
            "cbBTC/USDC": {"apr": 90},
            "eth_price": 3500,
            "btc_price": 65000,
            "eth_funding": -0.02,
            "btc_funding": -0.01
        }
    )

    print("\nInitial Strategy (balance=$5000):")
    print(f"  LP Allocations: {len(strategy['lp_allocations'])} positions")
    for lp in strategy['lp_allocations']:
        print(f"    - {lp['pair']}: ${lp['amount_usd']:.2f}")

    print(f"  Hedges: {len(strategy['hedges'])} positions")
    for hedge in strategy['hedges']:
        print(f"    - {hedge['asset']} {hedge['side']}: ${hedge['collateral_usd']:.2f} "
              f"(notional: ${hedge['notional_exposure_usd']:.2f})")

    print(f"  Notes: {strategy['notes']}")

    # Test range break evaluation
    range_action = await gpt_strategy_service.evaluate_range_break(
        position_data={
            "pool_name": "WETH/USDC",
            "current_value": 2000,
            "time_out_of_range": 12,
            "apr_in_range": 100
        },
        market_data={
            "current_price": 3600,
            "price_change_24h": 3.0,
            "volatility": "high",
            "trend": "bullish"
        },
        current_balance=1000
    )

    print("\nRange Break Action:")
    print(f"  Action: {range_action['action']}")
    print(f"  Reason: {range_action['reason']}")

    # Test with small balance (< $2000)
    small_strategy = await gpt_strategy_service.generate_initial_strategy(
        balance=1500,
        existing_positions=[],
        pool_data={
            "WETH/USDC": {"apr": 120},
            "cbBTC/USDC": {"apr": 90},
            "eth_price": 3500,
            "btc_price": 65000
        }
    )

    print("\nSmall Balance Strategy (balance=$1500):")
    print(f"  LP Allocations: {len(small_strategy['lp_allocations'])} positions")
    print(f"  Expected: Single position for balance < $2000")

    return True


async def test_unified_response():
    """Test unified response handling different scenarios."""
    print("\n=== Testing Unified Response Structure ===")

    from app.schemas.users import (
        LPAllocation,
        Hedge,
        DeltaNeutralStrategyResponse
    )

    # Test Initial Allocation Response
    lp = LPAllocation(
        pair="WETH/USDC",
        amount_usd=Decimal("1000.50"),
        range_pct=5.0
    )

    hedge = Hedge(
        asset="ETH",
        side="short",
        collateral_usd=Decimal("100"),
        leverage=5,
        notional_exposure_usd=Decimal("500")
    )

    initial_response = DeltaNeutralStrategyResponse(
        action="initial_allocation",
        notes="Initial delta-neutral strategy for new user",
        lp_allocations=[lp],
        hedges=[hedge],
        total_capital_deployed=Decimal("1100.50"),
        remaining_balance=Decimal("399.50")
    )
    print(f"✓ Initial allocation response: action={initial_response.action}, deployed=${initial_response.total_capital_deployed}")

    # Test Range Break Response
    range_break_response = DeltaNeutralStrategyResponse(
        action="close_and_reopen",
        notes="ETH broke out of range. Closing old LP and re-entering at adjusted range.",
        lp_allocations=[lp],
        hedges=[hedge],
        total_capital_deployed=Decimal("1100.50"),
        remaining_balance=Decimal("399.50"),
        out_of_range_positions=[123456],
        position_id=123456,
        reason="Position out of range for 24h, reopening to capture APR"
    )
    print(f"✓ Range break response: action={range_break_response.action}, out_of_range={range_break_response.out_of_range_positions}")

    # Test Maintain Response
    maintain_response = DeltaNeutralStrategyResponse(
        action="maintain",
        notes="All positions in range and performing well",
        total_capital_deployed=Decimal("5000"),
        remaining_balance=Decimal("100"),
        current_positions=[{"id": 123, "pool": "WETH/USDC", "value": 5000}],
        out_of_range_positions=[]
    )
    print(f"✓ Maintain response: action={maintain_response.action}")

    return True


async def main():
    """Run all tests."""
    print("Testing Delta-Neutral Strategy Implementation")
    print("=" * 50)

    try:
        # Test unified response structure
        await test_unified_response()

        # Test GPT strategy
        await test_gpt_strategy()

        print("\n" + "=" * 50)
        print("✅ All tests passed!")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())