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
    LIQUIDITY_MANAGER = "0xF1D9a32A41593885b6eDdF0De166fC47F390d070"
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
                    {"internalType": "uint256", "name": "usdcAmount", "type": "uint256"},
                    {"internalType": "address", "name": "pool", "type": "address"},
                    {"internalType": "int24", "name": "tickLower", "type": "int24"},
                    {"internalType": "int24", "name": "tickUpper", "type": "int24"},
                    {"internalType": "bool", "name": "enableHedge", "type": "bool"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                    {"internalType": "uint256", "name": "slippageBps", "type": "uint256"}
                ],
                "name": "createPositionWithHedge",
                "outputs": [
                    {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
                    {"internalType": "uint256", "name": "hedgeId", "type": "uint256"}
                ],
                "stateMutability": "payable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                    {"internalType": "uint256", "name": "minUsdcOut", "type": "uint256"},
                    {"internalType": "uint256", "name": "slippageBps", "type": "uint256"}
                ],
                "name": "closePositionWithHedge",
                "outputs": [
                    {"internalType": "uint256", "name": "totalUsdcOut", "type": "uint256"}
                ],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "", "type": "uint256"}
                ],
                "name": "nftToHedgeId",
                "outputs": [
                    {"internalType": "uint256", "name": "", "type": "uint256"}
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "", "type": "uint256"}
                ],
                "name": "hedgeEnabled",
                "outputs": [
                    {"internalType": "bool", "name": "", "type": "bool"}
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "hedgeRatio",
                "outputs": [
                    {"internalType": "uint256", "name": "", "type": "uint256"}
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "maxLeverage",
                "outputs": [
                    {"internalType": "uint256", "name": "", "type": "uint256"}
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
                address=Web3.to_checksum_address(self.LIQUIDITY_MANAGER),
                abi=abi
            )
        return self._liquidity_manager
    
    async def get_hedge_id(self, nft_token_id: int) -> Optional[int]:
        """
        Get hedge ID associated with an NFT position.
        
        Args:
            nft_token_id: NFT token ID of the LP position
            
        Returns:
            Hedge ID if position has a hedge, None otherwise
        """
        try:
            contract = self._get_liquidity_manager()
            hedge_id = contract.functions.nftToHedgeId(nft_token_id).call()
            
            # Return None if no hedge (hedge_id == 0)
            return hedge_id if hedge_id > 0 else None
            
        except Exception as e:
            logger.error(f"Error fetching hedge ID for NFT {nft_token_id}: {e}")
            return None
    
    async def is_hedge_enabled(self, nft_token_id: int) -> bool:
        """
        Check if hedge is enabled for a position.
        
        Args:
            nft_token_id: NFT token ID of the LP position
            
        Returns:
            True if hedge is enabled, False otherwise
        """
        try:
            contract = self._get_liquidity_manager()
            return contract.functions.hedgeEnabled(nft_token_id).call()
            
        except Exception as e:
            logger.error(f"Error checking hedge status for NFT {nft_token_id}: {e}")
            return False
    
    async def get_hedge_parameters(self) -> Dict[str, Any]:
        """
        Get current hedge configuration parameters.
        
        Returns:
            Dictionary with hedge configuration
        """
        try:
            contract = self._get_liquidity_manager()
            
            hedge_ratio = contract.functions.hedgeRatio().call()
            max_leverage = contract.functions.maxLeverage().call()
            
            return {
                "hedge_ratio": hedge_ratio / 10000,  # Convert from basis points
                "max_leverage": max_leverage,
                "min_hedge_size": 10 * 10**6,  # 10 USDC
                "max_funding_apr_bps": 3000,  # 30% APR max funding
            }
            
        except Exception as e:
            logger.error(f"Error fetching hedge parameters: {e}")
            return {
                "hedge_ratio": 0.5,
                "max_leverage": 100,
                "min_hedge_size": 10 * 10**6,
                "max_funding_apr_bps": 3000,
            }
    
    async def simulate_hedged_position(
        self,
        pool_address: str,
        usdc_amount: int,
        tick_lower: int,
        tick_upper: int,
        enable_hedge: bool = True
    ) -> Dict[str, Any]:
        """
        Simulate creating a hedged position without executing.
        
        Args:
            pool_address: Address of the Uniswap V3 pool
            usdc_amount: Amount of USDC to invest
            tick_lower: Lower tick boundary
            tick_upper: Upper tick boundary
            enable_hedge: Whether to enable hedge
            
        Returns:
            Simulation results including estimated hedge size and costs
        """
        try:
            # Get hedge parameters
            params = await self.get_hedge_parameters()
            
            # Calculate hedge size
            hedge_size = 0
            hedge_collateral = 0
            
            if enable_hedge:
                # Hedge 50% of position value
                position_value = usdc_amount
                hedge_exposure = position_value * params["hedge_ratio"]
                
                # Calculate collateral needed (assuming 3x leverage)
                leverage = min(3, params["max_leverage"])
                hedge_collateral = hedge_exposure // leverage
                hedge_size = hedge_exposure
            
            return {
                "pool_address": pool_address,
                "usdc_investment": usdc_amount,
                "tick_lower": tick_lower,
                "tick_upper": tick_upper,
                "hedge_enabled": enable_hedge,
                "hedge_size_usdc": hedge_size,
                "hedge_collateral_usdc": hedge_collateral,
                "hedge_leverage": 3,
                "total_capital_required": usdc_amount + hedge_collateral,
                "estimated_gas": 500000,  # Rough estimate
            }
            
        except Exception as e:
            logger.error(f"Error simulating hedged position: {e}")
            raise
    
    def calculate_tick_range(
        self,
        current_tick: int,
        range_percentage: int,
        tick_spacing: int
    ) -> Tuple[int, int]:
        """
        Calculate tick range based on percentage from current price.
        
        Args:
            current_tick: Current tick of the pool
            range_percentage: Range as percentage * 100 (e.g., 500 = 5%)
            tick_spacing: Pool's tick spacing
            
        Returns:
            Tuple of (tick_lower, tick_upper)
        """
        # Calculate tick delta for the given percentage
        # Each tick represents ~0.01% price change
        tick_delta = int(range_percentage)
        
        # Align to tick spacing
        tick_lower = ((current_tick - tick_delta) // tick_spacing) * tick_spacing
        tick_upper = ((current_tick + tick_delta) // tick_spacing) * tick_spacing
        
        return (tick_lower, tick_upper)