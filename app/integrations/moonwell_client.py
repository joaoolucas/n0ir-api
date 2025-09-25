"""
Moonwell Protocol Client for interacting with lending markets.
Handles collateral, borrow positions, and account health calculations.
"""
from typing import Dict, List, Optional, Any
from decimal import Decimal
from web3 import Web3
from web3.contract import Contract
from loguru import logger

from app.core.config import settings


class MoonwellClient:
    """Client for interacting with Moonwell lending protocol."""

    # Contract addresses on Base
    COMPTROLLER_ADDRESS = "0xfBb21d0380beE3312B33c4353c8936a0F13EF26C"

    # Market addresses
    MARKETS = {
        "mUSDC": {
            "address": "0xEdc817A28E8B93B03976FBd4a3dDBc9f7D176c22",
            "underlying": "USDC",
            "decimals": 6,
            "underlying_decimals": 6
        },
        "mWETH": {
            "address": "0x628ff693426583D9a7FB391E54366292F509D457",
            "underlying": "WETH",
            "decimals": 8,
            "underlying_decimals": 18
        },
        "mcbBTC": {
            "address": "0xF877ACaFA28c19b96727966690b2f44d35aD5976",
            "underlying": "cbBTC",
            "decimals": 8,
            "underlying_decimals": 8
        }
    }

    # Minimal ABIs for the contracts we need
    COMPTROLLER_ABI = [
        {
            "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
            "name": "getAccountLiquidity",
            "outputs": [
                {"internalType": "uint256", "name": "error", "type": "uint256"},
                {"internalType": "uint256", "name": "liquidity", "type": "uint256"},
                {"internalType": "uint256", "name": "shortfall", "type": "uint256"}
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
            "name": "getAssetsIn",
            "outputs": [
                {"internalType": "address[]", "name": "", "type": "address[]"}
            ],
            "stateMutability": "view",
            "type": "function"
        }
    ]

    MTOKEN_ABI = [
        {
            "inputs": [{"internalType": "address", "name": "owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "exchangeRateCurrent",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "exchangeRateStored",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
            "name": "borrowBalanceCurrent",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
            "name": "borrowBalanceStored",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "supplyRatePerTimestamp",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "borrowRatePerTimestamp",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "totalBorrows",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "totalSupply",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "getCash",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function"
        }
    ]

    def __init__(self):
        """Initialize Moonwell client."""
        self._w3: Optional[Web3] = None
        self._comptroller: Optional[Contract] = None
        self._mtoken_contracts: Dict[str, Contract] = {}

    def _get_w3(self) -> Web3:
        """Get or create Web3 instance."""
        if self._w3 is None:
            self._w3 = Web3(Web3.HTTPProvider(settings.rpc_url))
            if not self._w3.is_connected():
                raise Exception(f"Failed to connect to RPC endpoint: {settings.rpc_url}")
        return self._w3

    def _get_comptroller(self) -> Contract:
        """Get or create Comptroller contract instance."""
        if self._comptroller is None:
            w3 = self._get_w3()
            self._comptroller = w3.eth.contract(
                address=Web3.to_checksum_address(self.COMPTROLLER_ADDRESS),
                abi=self.COMPTROLLER_ABI
            )
        return self._comptroller

    def _get_mtoken_contract(self, market_key: str) -> Contract:
        """Get or create mToken contract instance."""
        if market_key not in self._mtoken_contracts:
            if market_key not in self.MARKETS:
                raise ValueError(f"Unknown market: {market_key}")

            w3 = self._get_w3()
            market_info = self.MARKETS[market_key]
            self._mtoken_contracts[market_key] = w3.eth.contract(
                address=Web3.to_checksum_address(market_info["address"]),
                abi=self.MTOKEN_ABI
            )
        return self._mtoken_contracts[market_key]

    async def get_account_liquidity(self, wallet_address: str) -> Dict[str, Any]:
        """
        Get account liquidity from Comptroller.

        Returns:
            - error: Error code (0 = success)
            - liquidity: How much more can be borrowed safely (in USD)
            - shortfall: Amount underwater if > 0 (liquidatable)
        """
        try:
            comptroller = self._get_comptroller()
            result = comptroller.functions.getAccountLiquidity(
                Web3.to_checksum_address(wallet_address)
            ).call()

            # Result is (error, liquidity, shortfall)
            return {
                "error": result[0],
                "liquidity": result[1] / 1e18,  # Convert from Wei to USD
                "shortfall": result[2] / 1e18,  # Convert from Wei to USD
                "is_liquidatable": result[2] > 0
            }
        except Exception as e:
            logger.error(f"Error fetching account liquidity for {wallet_address}: {e}")
            return {
                "error": 1,
                "liquidity": 0,
                "shortfall": 0,
                "is_liquidatable": False
            }

    async def get_supply_position(self, wallet_address: str, market_key: str) -> Dict[str, Any]:
        """
        Get supply position for a specific market.

        Returns:
            - mtoken_balance: Amount of mTokens held
            - exchange_rate: Current exchange rate
            - underlying_balance: Actual underlying balance (with interest)
            - supply_apy: Current supply APY
        """
        try:
            mtoken = self._get_mtoken_contract(market_key)
            market_info = self.MARKETS[market_key]

            # Get mToken balance
            mtoken_balance = mtoken.functions.balanceOf(
                Web3.to_checksum_address(wallet_address)
            ).call()

            # Get exchange rate (stored version for view calls)
            exchange_rate = mtoken.functions.exchangeRateStored().call()

            # Calculate underlying balance
            # mToken has 8 decimals, underlying varies
            # Exchange rate is scaled by 1e18
            underlying_balance = (mtoken_balance * exchange_rate) / (10 ** (18 + market_info["decimals"]))

            # Get supply rate (per timestamp/second)
            supply_rate = mtoken.functions.supplyRatePerTimestamp().call()
            # Convert to APY: (1 + rate_per_second) ^ seconds_per_year - 1
            seconds_per_year = 365 * 24 * 60 * 60
            supply_apy = ((1 + supply_rate / 1e18) ** seconds_per_year - 1) * 100

            return {
                "market": market_key,
                "underlying_asset": market_info["underlying"],
                "mtoken_balance": mtoken_balance / (10 ** market_info["decimals"]),
                "exchange_rate": exchange_rate / 1e18,
                "underlying_balance": underlying_balance / (10 ** market_info["underlying_decimals"]),
                "underlying_balance_usd": 0,  # Will be calculated with prices
                "supply_apy": round(supply_apy, 2)
            }
        except Exception as e:
            logger.error(f"Error fetching supply position for {wallet_address} in {market_key}: {e}")
            return {
                "market": market_key,
                "underlying_asset": self.MARKETS[market_key]["underlying"],
                "mtoken_balance": 0,
                "exchange_rate": 0,
                "underlying_balance": 0,
                "underlying_balance_usd": 0,
                "supply_apy": 0
            }

    async def get_borrow_position(self, wallet_address: str, market_key: str) -> Dict[str, Any]:
        """
        Get borrow position for a specific market.

        Returns:
            - borrow_balance: Current borrow balance (with accrued interest)
            - borrow_apy: Current borrow APY
        """
        try:
            mtoken = self._get_mtoken_contract(market_key)
            market_info = self.MARKETS[market_key]

            # Get current borrow balance (includes accrued interest)
            # Using stored version to avoid state change
            borrow_balance = mtoken.functions.borrowBalanceStored(
                Web3.to_checksum_address(wallet_address)
            ).call()

            # Get borrow rate
            borrow_rate = mtoken.functions.borrowRatePerTimestamp().call()
            # Convert to APY
            seconds_per_year = 365 * 24 * 60 * 60
            borrow_apy = ((1 + borrow_rate / 1e18) ** seconds_per_year - 1) * 100

            return {
                "market": market_key,
                "underlying_asset": market_info["underlying"],
                "borrow_balance": borrow_balance / (10 ** market_info["underlying_decimals"]),
                "borrow_balance_usd": 0,  # Will be calculated with prices
                "borrow_apy": round(borrow_apy, 2)
            }
        except Exception as e:
            logger.error(f"Error fetching borrow position for {wallet_address} in {market_key}: {e}")
            return {
                "market": market_key,
                "underlying_asset": self.MARKETS[market_key]["underlying"],
                "borrow_balance": 0,
                "borrow_balance_usd": 0,
                "borrow_apy": 0
            }

    async def get_all_positions(self, wallet_address: str) -> Dict[str, Any]:
        """
        Get all supply and borrow positions for a wallet.
        """
        supplies = []
        borrows = []

        # Check each market
        for market_key in self.MARKETS.keys():
            # Get supply position
            supply = await self.get_supply_position(wallet_address, market_key)
            if supply["underlying_balance"] > 0:
                supplies.append(supply)

            # Get borrow position
            borrow = await self.get_borrow_position(wallet_address, market_key)
            if borrow["borrow_balance"] > 0:
                borrows.append(borrow)

        return {
            "supplies": supplies,
            "borrows": borrows
        }

    async def get_market_info(self, market_key: str) -> Dict[str, Any]:
        """
        Get market information including rates and liquidity.
        """
        try:
            mtoken = self._get_mtoken_contract(market_key)
            market_info = self.MARKETS[market_key]

            # Get market data
            total_supply = mtoken.functions.totalSupply().call()
            total_borrows = mtoken.functions.totalBorrows().call()
            cash = mtoken.functions.getCash().call()
            exchange_rate = mtoken.functions.exchangeRateStored().call()

            # Get rates
            supply_rate = mtoken.functions.supplyRatePerTimestamp().call()
            borrow_rate = mtoken.functions.borrowRatePerTimestamp().call()

            # Convert rates to APY
            seconds_per_year = 365 * 24 * 60 * 60
            supply_apy = ((1 + supply_rate / 1e18) ** seconds_per_year - 1) * 100
            borrow_apy = ((1 + borrow_rate / 1e18) ** seconds_per_year - 1) * 100

            # Calculate utilization
            total_supply_underlying = (total_supply * exchange_rate) / (10 ** (18 + market_info["decimals"]))
            utilization = (total_borrows / total_supply_underlying * 100) if total_supply_underlying > 0 else 0

            return {
                "market": market_key,
                "underlying_asset": market_info["underlying"],
                "total_supply": total_supply / (10 ** market_info["decimals"]),
                "total_borrows": total_borrows / (10 ** market_info["underlying_decimals"]),
                "available_liquidity": cash / (10 ** market_info["underlying_decimals"]),
                "utilization": round(utilization, 2),
                "supply_apy": round(supply_apy, 2),
                "borrow_apy": round(borrow_apy, 2),
                "exchange_rate": exchange_rate / 1e18
            }
        except Exception as e:
            logger.error(f"Error fetching market info for {market_key}: {e}")
            return None


# Singleton instance
moonwell_client = MoonwellClient()