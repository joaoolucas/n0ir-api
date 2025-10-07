#!/usr/bin/env python3
"""
Diagnostic script to check vault contract oracle configuration.
"""
from web3 import Web3
import os
from dotenv import load_dotenv

load_dotenv()

# Contract addresses
VAULT_ADDRESS = "0xE835Bbb6fAC87883a2F70b950185EB6bEADB0367"
WETH_ADDRESS = "0x4200000000000000000000000000000000000006"
CBBTC_ADDRESS = "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf"
WETH_USDC_POOL = "0xb2cc224c1c9feE385f8ad6a55b4d94E92359DC59"

# Initialize Web3
rpc_url = os.getenv("RPC_URL", "https://mainnet.base.org")
w3 = Web3(Web3.HTTPProvider(rpc_url))

print(f"Connected to Base: {w3.is_connected()}")
print(f"Chain ID: {w3.eth.chain_id}")
print()

# ABI for the functions we need
vault_abi = [
    {
        "inputs": [],
        "name": "pythOracle",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "token", "type": "address"}],
        "name": "getTokenPriceViaOracle",
        "outputs": [{"internalType": "uint256", "name": "price", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "hedgeManager",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]

vault = w3.eth.contract(address=Web3.to_checksum_address(VAULT_ADDRESS), abi=vault_abi)

print("=" * 60)
print("VAULT CONTRACT DIAGNOSTICS")
print("=" * 60)
print(f"Vault Address: {VAULT_ADDRESS}")
print()

# Check Pyth Oracle
try:
    pyth_oracle = vault.functions.pythOracle().call()
    print(f"✓ Pyth Oracle: {pyth_oracle}")
    if pyth_oracle == "0x0000000000000000000000000000000000000000":
        print("  ⚠️  WARNING: Oracle not initialized!")
except Exception as e:
    print(f"✗ Error reading pythOracle: {e}")

print()

# Check HedgeManager
try:
    hedge_manager = vault.functions.hedgeManager().call()
    print(f"✓ Hedge Manager: {hedge_manager}")
    if hedge_manager == "0x0000000000000000000000000000000000000000":
        print("  ⚠️  WARNING: HedgeManager not initialized!")
except Exception as e:
    print(f"✗ Error reading hedgeManager: {e}")

print()

# Check token prices
print("Token Price Checks:")
print("-" * 60)

for token_name, token_addr in [("WETH", WETH_ADDRESS), ("cbBTC", CBBTC_ADDRESS)]:
    try:
        price = vault.functions.getTokenPriceViaOracle(Web3.to_checksum_address(token_addr)).call()
        price_usd = price / 1e6  # Convert from 6 decimals
        print(f"✓ {token_name}: ${price_usd:,.2f}")
    except Exception as e:
        print(f"✗ {token_name}: FAILED - {str(e)[:100]}")

print()
print("=" * 60)

# Try a simple simulateHedge call
print("\nTesting simulateHedge call:")
print("-" * 60)

simulate_abi = [{
    "inputs": [
        {"internalType": "uint256", "name": "usdcAmount", "type": "uint256"},
        {"internalType": "address", "name": "pool", "type": "address"},
        {"internalType": "int24", "name": "tickLower", "type": "int24"},
        {"internalType": "int24", "name": "tickUpper", "type": "int24"},
        {"internalType": "uint256", "name": "collateralRatioBps", "type": "uint256"},
        {"internalType": "uint256", "name": "hedgeRatio", "type": "uint256"}
    ],
    "name": "simulateHedge",
    "outputs": [
        {
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
            "name": "simulation",
            "type": "tuple"
        }
    ],
    "stateMutability": "view",
    "type": "function"
}]

vault_sim = w3.eth.contract(address=Web3.to_checksum_address(VAULT_ADDRESS), abi=simulate_abi)

try:
    result = vault_sim.functions.simulateHedge(
        100_000_000,  # 100 USDC (6 decimals)
        Web3.to_checksum_address(WETH_USDC_POOL),
        -83200,  # Example ticks
        -82200,
        6000,  # 60% collateral
        9500   # 95% hedge
    ).call()

    print(f"✓ simulateHedge call succeeded!")
    print(f"  Hedge Asset: {result[0]}")
    print(f"  Asset Price: ${result[2] / 1e6:,.2f}")
    print(f"  Health Factor: {result[9] / 1e18:.2f}")
    print(f"  Is Healthy: {result[12]}")

except Exception as e:
    error_msg = str(e)
    print(f"✗ simulateHedge call FAILED:")
    print(f"  {error_msg[:200]}")

    # Try to decode common errors
    if "OraclePriceUnavailable" in error_msg:
        print("\n  → Issue: Pyth oracle not returning valid prices")
        print("  → Check: Oracle may not be initialized or price feeds are stale")
    elif "InvalidTokenPrice" in error_msg:
        print("\n  → Issue: Token price returned as 0 or invalid")
    elif "execution reverted" in error_msg:
        print("\n  → Issue: Contract reverted during execution")

print()
print("=" * 60)
print("DIAGNOSTICS COMPLETE")
print("=" * 60)
