"""Constants and ABIs for pool operations."""

# DexScreener API configuration
DEXSCREENER_API_BASE = "https://api.dexscreener.com/latest/dex"
API_RATE_LIMIT_DELAY = 0.1  # seconds between API calls
API_BATCH_SIZE = 10  # number of concurrent requests

# Tick spacing to fee tier mapping (in basis points)
TICK_SPACING_TO_FEE_TIER = {
    1: 100,      # 0.01%
    10: 100,     # 0.01%
    50: 500,     # 0.05%
    100: 500,    # 0.05%
    200: 3000,   # 0.30%
    2000: 10000  # 1.00%
}

# Sugar contract ABI (minimal)
SUGAR_ABI = [
    {
        "name": "all",
        "type": "function",
        "inputs": [
            {"name": "_limit", "type": "uint256"},
            {"name": "_offset", "type": "uint256"}
        ],
        "outputs": [{"name": "", "type": "tuple[]", "components": [
            {"name": "lp", "type": "address"},
            {"name": "symbol", "type": "string"},
            {"name": "decimals", "type": "uint8"},
            {"name": "liquidity", "type": "uint256"},
            {"name": "type", "type": "int24"},
            {"name": "tick", "type": "int24"},
            {"name": "sqrt_ratio", "type": "uint160"},
            {"name": "token0", "type": "address"},
            {"name": "reserve0", "type": "uint256"},
            {"name": "staked0", "type": "uint256"},
            {"name": "token1", "type": "address"},
            {"name": "reserve1", "type": "uint256"},
            {"name": "staked1", "type": "uint256"},
            {"name": "gauge", "type": "address"},
            {"name": "gauge_liquidity", "type": "uint256"},
            {"name": "gauge_alive", "type": "bool"},
            {"name": "fee", "type": "address"},
            {"name": "bribe", "type": "address"},
            {"name": "factory", "type": "address"},
            {"name": "emissions", "type": "uint256"},
            {"name": "emissions_token", "type": "address"},
            {"name": "pool_fee", "type": "uint256"},
            {"name": "unstaked_fee", "type": "uint256"},
            {"name": "token0_fees", "type": "uint256"},
            {"name": "token1_fees", "type": "uint256"}
        ]}],
        "stateMutability": "view"
    },
    {
        "inputs": [{"name": "_pool", "type": "address"}],
        "name": "byAddress",
        "outputs": [{"name": "", "type": "tuple", "components": [
            {"name": "lp", "type": "address"},
            {"name": "symbol", "type": "string"},
            {"name": "decimals", "type": "uint8"},
            {"name": "liquidity", "type": "uint256"},
            {"name": "type", "type": "int24"},
            {"name": "tick", "type": "int24"},
            {"name": "sqrt_ratio", "type": "uint160"},
            {"name": "token0", "type": "address"},
            {"name": "reserve0", "type": "uint256"},
            {"name": "staked0", "type": "uint256"},
            {"name": "token1", "type": "address"},
            {"name": "reserve1", "type": "uint256"},
            {"name": "staked1", "type": "uint256"},
            {"name": "gauge", "type": "address"},
            {"name": "gauge_liquidity", "type": "uint256"},
            {"name": "gauge_alive", "type": "bool"},
            {"name": "fee", "type": "address"},
            {"name": "bribe", "type": "address"},
            {"name": "factory", "type": "address"},
            {"name": "emissions", "type": "uint256"},
            {"name": "emissions_token", "type": "address"},
            {"name": "pool_fee", "type": "uint256"},
            {"name": "unstaked_fee", "type": "uint256"},
            {"name": "token0_fees", "type": "uint256"},
            {"name": "token1_fees", "type": "uint256"}
        ]}],
        "stateMutability": "view",
        "type": "function"
    }
]

# ERC20 Token ABI (minimal)
TOKEN_ABI = [
    {
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function",
        "stateMutability": "view"
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
        "stateMutability": "view"
    },
    {
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function",
        "stateMutability": "view"
    }
]

# Sugar data field indices for tuple unpacking
class SugarFields:
    """Field indices for Sugar contract response tuples."""
    LP = 0
    SYMBOL = 1
    DECIMALS = 2
    LIQUIDITY = 3
    TYPE = 4  # tick_spacing for CL pools
    TICK = 5
    SQRT_RATIO = 6
    TOKEN0 = 7
    RESERVE0 = 8
    STAKED0 = 9
    TOKEN1 = 10
    RESERVE1 = 11
    STAKED1 = 12
    GAUGE = 13
    GAUGE_LIQUIDITY = 14
    GAUGE_ALIVE = 15
    FEE = 16
    BRIBE = 17
    FACTORY = 18
    EMISSIONS = 19
    EMISSIONS_TOKEN = 20
    POOL_FEE = 21
    UNSTAKED_FEE = 22
    TOKEN0_FEES = 23
    TOKEN1_FEES = 24