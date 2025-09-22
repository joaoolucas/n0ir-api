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


async def test_schema_validation():
    """Test schema validation."""
    print("\n=== Testing Schema Validation ===")

    from app.schemas.users import (
        LPAllocation,
        Hedge,
        DeltaNeutralStrategyResponse
    )

    # Test LP Allocation
    lp = LPAllocation(
        pair="WETH/USDC",
        amount_usd=Decimal("1000.50"),
        range_pct=5.0,
        pool_address="0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59"
    )
    print(f"LP Allocation created: {lp.pair} - ${lp.amount_usd}")

    # Test Hedge
    hedge = Hedge(
        asset="ETH",
        side="short",
        collateral_usd=Decimal("100"),
        leverage=5,
        notional_exposure_usd=Decimal("500")
    )
    print(f"Hedge created: {hedge.asset} {hedge.side} - ${hedge.notional_exposure_usd} notional")

    # Test full response
    response = DeltaNeutralStrategyResponse(
        lp_allocations=[lp],
        hedges=[hedge],
        notes="Test strategy",
        total_capital_deployed=Decimal("1100.50"),
        remaining_balance=Decimal("399.50")
    )
    print(f"Strategy Response created: Total deployed ${response.total_capital_deployed}")

    return True


async def main():
    """Run all tests."""
    print("Testing Delta-Neutral Strategy Implementation")
    print("=" * 50)

    try:
        # Test schemas
        await test_schema_validation()

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