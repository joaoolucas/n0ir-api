#!/usr/bin/env python3
"""
Test simulateHedge with real parameters matching what the API uses.
"""
from web3 import Web3
import os
from dotenv import load_dotenv

load_dotenv()

VAULT_ADDRESS = os.getenv("LIQUIDITY_MANAGER_ADDRESS", "0xE835Bbb6fAC87883a2F70b950185EB6bEADB0367")
WETH_USDC_POOL = "0xb2cc224c1c9feE385f8ad6a55b4d94E92359DC59"

rpc_url = os.getenv("RPC_URL")
w3 = Web3(Web3.HTTPProvider(rpc_url))

print(f"Using vault address: {VAULT_ADDRESS}")
print(f"Connected: {w3.is_connected()}\n")

# Full ABI for simulateHedge
abi = [{
    "inputs": [
        {"internalType": "uint256", "name": "usdcAmount", "type": "uint256"},
        {"internalType": "address", "name": "pool", "type": "address"},
        {"internalType": "int24", "name": "tickLower", "type": "int24"},
        {"internalType": "int24", "name": "tickUpper", "type": "int24"},
        {"internalType": "uint256", "name": "collateralRatioBps", "type": "uint256"},
        {"internalType": "uint256", "name": "hedgeRatio", "type": "uint256"}
    ],
    "name": "simulateHedge",
    "outputs": [{
        "components": [
            {"internalType": "address", "name": "hedgeAsset", "type": "address"},
            {"internalType": "uint8", "name": "assetDecimals", "type": "uint8"},
            {"internalType": "uint256", "name": "currentAssetPrice", "type": "uint256"},
            {"internalType": "uint256", "name": "assetExposureBps", "type": "uint256"},
            {"internalType": "uint256", "name": "collateralAmount", "type": "uint256"},
            {"internalType": "uint256", "name": "lpBaseAmount", "type": "uint256"},
            {"internalType": "uint256", "name": "borrowAmountUSD", "type": "uint256"},
            {"internalType": "uint256", "name": "borrowAmountAsset", "type": "uint256"},
            {"internalType": "uint256", "name": "totalLPAmount", "type": "uint256"},
            {"internalType": "uint256", "name": "expectedHealthFactor", "type": "uint256"},
            {"internalType": "uint256", "name": "liquidationPrice", "type": "uint256"},
            {"internalType": "uint256", "name": "leverageMultiplierBps", "type": "uint256"},
            {"internalType": "bool", "name": "isHealthy", "type": "bool"}
        ],
        "internalType": "struct HedgeManager.HedgeSimulation",
        "name": "",
        "type": "tuple"
    }],
    "stateMutability": "view",
    "type": "function"
}]

contract = w3.eth.contract(
    address=Web3.to_checksum_address(VAULT_ADDRESS),
    abi=abi
)

# Get current tick from pool
pool_abi = [{
    "inputs": [],
    "name": "slot0",
    "outputs": [
        {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
        {"internalType": "int24", "name": "tick", "type": "int24"},
        {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
        {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
        {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
        {"internalType": "bool", "name": "unlocked", "type": "bool"}
    ],
    "stateMutability": "view",
    "type": "function"
}]

pool_contract = w3.eth.contract(address=Web3.to_checksum_address(WETH_USDC_POOL), abi=pool_abi)
slot0 = pool_contract.functions.slot0().call()
current_tick = slot0[1]

print(f"Current tick: {current_tick}")

# Calculate ticks for 20% range (±10%)
range_percentage = 20
tick_spacing = 100
range_multiplier = range_percentage / 200
tick_distance = int(current_tick * range_multiplier)
tick_lower = ((current_tick - tick_distance) // tick_spacing) * tick_spacing
tick_upper = ((current_tick + tick_distance) // tick_spacing) * tick_spacing

print(f"Range: ±{range_percentage/2}%")
print(f"Tick lower: {tick_lower}")
print(f"Tick upper: {tick_upper}\n")

print("Testing grid search parameters...")
print("=" * 80)

success_count = 0
fail_count = 0

for collateral_ratio in range(5500, 7000, 500):
    for hedge_ratio in range(9200, 10000, 200):
        try:
            result = contract.functions.simulateHedge(
                20_000_000,  # 20 USDC
                Web3.to_checksum_address(WETH_USDC_POOL),
                tick_lower,
                tick_upper,
                collateral_ratio,
                hedge_ratio
            ).call()

            # Parse result
            health_factor = result[9] / 1e18
            is_healthy = result[12]

            if is_healthy and health_factor >= 1.75:
                success_count += 1
                print(f"✓ {collateral_ratio/100}% collateral, {hedge_ratio/100}% hedge: HF={health_factor:.2f}")
            else:
                fail_count += 1
                print(f"✗ {collateral_ratio/100}% collateral, {hedge_ratio/100}% hedge: HF={health_factor:.2f} (unhealthy)")

        except Exception as e:
            fail_count += 1
            error = str(e)[:100]
            print(f"✗ {collateral_ratio/100}% collateral, {hedge_ratio/100}% hedge: ERROR - {error}")

print("=" * 80)
print(f"\nResults: {success_count} succeeded, {fail_count} failed")

if success_count == 0:
    print("\n⚠️  NO VIABLE STRATEGIES FOUND!")
    print("This explains why your API is falling back to default values.")
else:
    print(f"\n✓ Found {success_count} viable strategies")
