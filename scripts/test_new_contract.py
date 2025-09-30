#!/usr/bin/env python3
"""
Test the new contract with rangePercentage parameter.
"""
from web3 import Web3
import os
from dotenv import load_dotenv

load_dotenv()

VAULT_ADDRESS = "0x961B51122c3dD5324b034884AF01e9cD1A5e363A"
WETH_USDC_POOL = "0xb2cc224c1c9feE385f8ad6a55b4d94E92359DC59"

rpc_url = os.getenv("RPC_URL")
w3 = Web3(Web3.HTTPProvider(rpc_url))

print(f"Testing vault at: {VAULT_ADDRESS}")
print(f"Connected: {w3.is_connected()}\n")

# New ABI with rangePercentage
abi = [{
    "inputs": [
        {"internalType": "uint256", "name": "usdcAmount", "type": "uint256"},
        {"internalType": "address", "name": "pool", "type": "address"},
        {"internalType": "uint256", "name": "rangePercentage", "type": "uint256"},
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

contract = w3.eth.contract(address=Web3.to_checksum_address(VAULT_ADDRESS), abi=abi)

print("Testing NEW simulateHedge with rangePercentage...")
print("=" * 80)

success_count = 0
results = []

for collateral_ratio in range(5500, 7000, 500):
    for hedge_ratio in range(9200, 10000, 200):
        try:
            result = contract.functions.simulateHedge(
                20_000_000,  # 20 USDC
                Web3.to_checksum_address(WETH_USDC_POOL),
                10,  # 10% range (±5%)
                collateral_ratio,
                hedge_ratio
            ).call()

            health_factor = result[9] / 1e18
            is_healthy = result[12]

            if is_healthy and health_factor >= 1.75:
                success_count += 1
                results.append({
                    'collateral': collateral_ratio,
                    'hedge': hedge_ratio,
                    'hf': health_factor
                })
                print(f"✓ {collateral_ratio/100}% collateral, {hedge_ratio/100}% hedge: HF={health_factor:.2f}")

        except Exception as e:
            print(f"✗ {collateral_ratio/100}% / {hedge_ratio/100}%: {str(e)[:80]}")

print("=" * 80)
print(f"\n✅ SUCCESS: {success_count}/12 parameter combinations work!")

if results:
    print("\nBest result:")
    best = max(results, key=lambda x: x['hf'])
    print(f"  Collateral: {best['collateral']/100}%")
    print(f"  Hedge: {best['hedge']/100}%")
    print(f"  Health Factor: {best['hf']:.2f}")
else:
    print("\n⚠️  No viable strategies found")
