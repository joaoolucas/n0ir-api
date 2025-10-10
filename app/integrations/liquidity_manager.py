"""LiquidityManager contract interface for delta-neutral position management."""

import json
from typing import Dict, Optional, Any, Tuple
from decimal import Decimal
from web3 import Web3
from web3.contract import Contract
from app.core.config import settings
from app.core.logger import logger


class LiquidityManagerClient:
    """Client for interacting with n0ir LiquidityManager contract."""
    
    # Contract addresses on Base Mainnet
    ROUTE_FINDER = "0x77e616a845B2b5Eb97a4f4e2d09547D555752C77"
    
    # Uniswap V3 contracts
    POSITION_MANAGER = "0x827922686190790b37229fd06084350E74485b72"
    SWAP_ROUTER = "0xBB9D64Df3d6Ba82F84fC59251BdFF32E1D93FF50"
    
    # Token addresses
    USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
    WETH = "0x4200000000000000000000000000000000000006"
    AERO = "0x940181a94A35A4569E4529A3CDfB74e38FD98631"
    
    def __init__(self):
        """Initialize the LiquidityManager client."""
        self._w3: Optional[Web3] = None
        self._liquidity_manager: Optional[Contract] = None
        self._abi_loaded = False
        self._abi_data = None
        
    def _get_w3(self) -> Web3:
        """Get or create Web3 instance."""
        if self._w3 is None:
            self._w3 = Web3(Web3.HTTPProvider(settings.rpc_url))
            if not self._w3.is_connected():
                raise Exception(f"Failed to connect to RPC endpoint: {settings.rpc_url}")
        return self._w3
    
    def _load_abi(self) -> list:
        """Load the LiquidityManager ABI from file."""
        if not self._abi_loaded:
            try:
                # Try to load from the specs/abi.json file
                import os
                abi_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    'specs', 'abi.json'
                )
                with open(abi_path, 'r') as f:
                    self._abi_data = json.load(f)
                self._abi_loaded = True
            except Exception as e:
                logger.warning(f"Could not load ABI from file: {e}")
                # Use minimal ABI as fallback
                self._abi_data = self._get_minimal_abi()
                self._abi_loaded = True
        return self._abi_data
    
    def _get_minimal_abi(self) -> list:
        """Get minimal ABI for essential functions."""
        return [
            {
                "inputs": [
                    {"internalType": "address", "name": "poolAddress", "type": "address"},
                    {"internalType": "uint256", "name": "totalUSDC", "type": "uint256"},
                    {"internalType": "uint256", "name": "rangePercentage", "type": "uint256"}
                ],
                "name": "calculateOptimalUsdcAllocation",
                "outputs": [
                    {"internalType": "uint256", "name": "usdc0", "type": "uint256"},
                    {"internalType": "uint256", "name": "usdc1", "type": "uint256"}
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "address", "name": "pool", "type": "address"},
                    {"internalType": "uint256", "name": "rangePercentage", "type": "uint256"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                    {"internalType": "uint256", "name": "usdcAmount", "type": "uint256"},
                    {"internalType": "uint256", "name": "slippageBps", "type": "uint256"},
                    {"internalType": "uint256", "name": "hedgeRatio", "type": "uint256"},
                    {"internalType": "uint256", "name": "collateralRatioBps", "type": "uint256"}
                ],
                "name": "createPosition",
                "outputs": [
                    {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
                    {"internalType": "uint128", "name": "liquidity", "type": "uint128"}
                ],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
                    {"internalType": "address", "name": "pool", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                    {"internalType": "uint256", "name": "minUsdcOut", "type": "uint256"},
                    {"internalType": "uint256", "name": "slippageBps", "type": "uint256"}
                ],
                "name": "closePosition",
                "outputs": [
                    {"internalType": "uint256", "name": "totalUsdcOut", "type": "uint256"}
                ],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "tokenId", "type": "uint256"}
                ],
                "name": "getPositionDetails",
                "outputs": [
                    {"internalType": "address", "name": "owner", "type": "address"},
                    {"internalType": "uint256", "name": "collateral", "type": "uint256"},
                    {"internalType": "uint256", "name": "debt", "type": "uint256"},
                    {"internalType": "address", "name": "hedgedAsset", "type": "address"},
                    {"internalType": "bool", "name": "isHedged", "type": "bool"},
                    {"internalType": "uint256", "name": "collateralSupplyAPY", "type": "uint256"},
                    {"internalType": "uint256", "name": "hedgedAssetBorrowAPY", "type": "uint256"}
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "address", "name": "user", "type": "address"}
                ],
                "name": "getUserPositions",
                "outputs": [
                    {"internalType": "uint256[]", "name": "", "type": "uint256[]"}
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "usdcAmount", "type": "uint256"},
                    {"internalType": "address", "name": "pool", "type": "address"},
                    {"internalType": "uint256", "name": "rangePercentage", "type": "uint256"},
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
                        "name": "",
                        "type": "tuple"
                    }
                ],
                "stateMutability": "view",
                "type": "function"
            }
        ]
    
    def _get_liquidity_manager(self) -> Contract:
        """Get or create LiquidityManager contract instance."""
        if self._liquidity_manager is None:
            w3 = self._get_w3()
            abi = self._load_abi()
            self._liquidity_manager = w3.eth.contract(
                address=Web3.to_checksum_address(settings.liquidity_manager_address),
                abi=abi
            )
        return self._liquidity_manager
    
    async def get_position_details(self, nft_token_id: int) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a position including hedge status.

        Args:
            nft_token_id: NFT token ID of the LP position

        Returns:
            Dictionary with position details or None if error
        """
        try:
            contract = self._get_liquidity_manager()
            result = contract.functions.getPositionDetails(nft_token_id).call()

            return {
                "owner": result[0],
                "collateral": result[1],
                "debt": result[2],
                "hedgedAsset": result[3],
                "isHedged": result[4],
                "collateralSupplyAPY": result[5],
                "hedgedAssetBorrowAPY": result[6]
            }

        except Exception as e:
            logger.error(f"Error fetching position details for NFT {nft_token_id}: {e}")
            return None

    async def get_user_positions(self, user_address: str) -> list:
        """
        Get all position token IDs for a user.

        Args:
            user_address: User's wallet address

        Returns:
            List of NFT token IDs
        """
        try:
            contract = self._get_liquidity_manager()
            positions = contract.functions.getUserPositions(
                Web3.to_checksum_address(user_address)
            ).call()

            return list(positions)

        except Exception as e:
            logger.error(f"Error fetching user positions for {user_address}: {e}")
            return []

    async def simulate_hedge(
        self,
        usdc_amount: int,
        pool_address: str,
        range_percentage: int,
        collateral_ratio_bps: int,
        hedge_ratio: int
    ) -> Optional[Dict[str, Any]]:
        """
        Simulate hedge for a position before creating it.

        Args:
            usdc_amount: Amount of USDC to invest (in wei)
            pool_address: Pool address
            range_percentage: Range percentage in bps (e.g., 1000 = 10%)
            collateral_ratio_bps: Collateral ratio in bps (e.g., 20000 = 200%)
            hedge_ratio: Hedge ratio in bps (e.g., 5000 = 50%)

        Returns:
            Dictionary with hedge simulation results
        """
        try:
            contract = self._get_liquidity_manager()
            result = contract.functions.simulateHedge(
                usdc_amount,
                Web3.to_checksum_address(pool_address),
                range_percentage,
                collateral_ratio_bps,
                hedge_ratio
            ).call()

            return {
                "hedgeAsset": result[0],
                "assetDecimals": result[1],
                "currentAssetPrice": result[2],
                "assetExposureBps": result[3],
                "collateralAmount": result[4],
                "lpBaseAmount": result[5],
                "borrowAmountUSD": result[6],
                "borrowAmountAsset": result[7],
                "totalLPAmount": result[8],
                "expectedHealthFactor": result[9],
                "liquidationPrice": result[10],
                "leverageMultiplierBps": result[11],
                "isHealthy": result[12]
            }

        except Exception as e:
            logger.error(f"Error simulating hedge: {e}")
            return None

    async def calculate_optimal_usdc_allocation(
        self,
        pool_address: str,
        total_usdc: float,
        range_percentage: int
    ) -> Dict[str, float]:
        """
        Calculate optimal USDC allocation for a given pool and range.

        Args:
            pool_address: Address of the pool
            total_usdc: Total USDC amount to allocate
            range_percentage: Range percentage (e.g., 5 for 5%)

        Returns:
            Dictionary with usdc0 and usdc1 allocations
        """
        try:
            contract = self._get_liquidity_manager()

            # Convert USDC to wei (6 decimals)
            total_usdc_wei = int(total_usdc * 10**6)

            # Call the contract function
            result = contract.functions.calculateOptimalUsdcAllocation(
                Web3.to_checksum_address(pool_address),
                total_usdc_wei,
                range_percentage * 100  # Convert to basis points
            ).call()

            # Convert back from wei
            usdc0 = result[0] / 10**6
            usdc1 = result[1] / 10**6

            logger.info(f"Optimal allocation for pool {pool_address}: "
                       f"USDC0={usdc0:.2f}, USDC1={usdc1:.2f}, Range={range_percentage}%")

            return {
                "usdc0": usdc0,
                "usdc1": usdc1,
                "total": usdc0 + usdc1,
                "ratio": usdc1 / (usdc0 + usdc1) if (usdc0 + usdc1) > 0 else 0.5
            }

        except Exception as e:
            logger.error(f"Error calculating optimal allocation: {e}")
            # Fallback to simple 50/50 split
            half = total_usdc / 2
            return {
                "usdc0": half,
                "usdc1": half,
                "total": total_usdc,
                "ratio": 0.5
            }