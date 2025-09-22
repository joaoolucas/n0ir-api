#!/usr/bin/env python3
"""Test the perps endpoint directly."""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
from app.core.perps_service import perps_service

# Test wallet address (CDP Wallet)
WALLET_ADDRESS = "0xAC65e18F7f4e5eDEA297b9E5433C153f1d9a7764"


async def test_perps_endpoint():
    """Test the perps service directly."""
    print("=" * 60)
    print(f"Testing perps endpoint for wallet: {WALLET_ADDRESS}")
    print("=" * 60)

    try:
        # Call the service directly
        result = await perps_service.get_positions_by_wallet(WALLET_ADDRESS)

        # Convert to dict for JSON serialization
        result_dict = result.model_dump()

        # Pretty print the result
        print(json.dumps(result_dict, indent=2))

        # Summary
        print("\n" + "=" * 60)
        print(f"✅ Total positions: {result.total_positions}")
        print(f"   - Short positions: {result.short_positions_count}")
        print(f"   - Long positions: {result.long_positions_count}")
        print(f"💰 Total collateral: ${result.total_collateral_usdc:.2f}")
        print(f"📊 Total notional: ${result.total_notional_usdc:.2f}")
        print(f"💹 Total P&L: ${result.total_pnl_usdc:.2f}")
        print("=" * 60)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_perps_endpoint())