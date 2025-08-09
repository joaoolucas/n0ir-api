"""Service for handling position-related operations."""

import json
from typing import Dict, List, Optional, Any, Tuple
from web3 import Web3
from web3.contract import Contract

from app.core.config import settings
from app.core.cache import cache_manager
from app.schemas.positions import PositionInfo


class PositionsService:
    """Service for fetching and analyzing positions."""
    
    # Contract addresses
    POSITION_MANAGER_ADDRESS = "0x827922686190790b37229fd06084350E74485b72"
    POOL_FACTORY_ADDRESS = "0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A"
    LIQUIDITY_MANAGER_ADDRESS = "0xC3958B5DA451Beee3D7C04E37981d6F596454999"
    SUGAR_ADDRESS = "0x27fc745390d1f4BaF8D184FBd97748340f786634"
    
    # Token addresses
    AERO_ADDRESS = "0x940181a94A35A4569E4529A3CDfB74e38FD98631"
    USDC_ADDRESS = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
    WETH_ADDRESS = "0x4200000000000000000000000000000000000006"
    
    def __init__(self):
        """Initialize the PositionsService."""
        self._w3: Optional[Web3] = None
        self._position_manager: Optional[Contract] = None
        self._pool_factory: Optional[Contract] = None
        self._liquidity_manager: Optional[Contract] = None
        self._sugar: Optional[Contract] = None
        self._pool_contracts: Dict[str, Contract] = {}
        self._token_contracts: Dict[str, Contract] = {}
        
    def _get_w3(self) -> Web3:
        """Get or create Web3 instance."""
        if self._w3 is None:
            self._w3 = Web3(Web3.HTTPProvider(settings.rpc_url))
            if not self._w3.is_connected():
                raise Exception(f"Failed to connect to RPC endpoint: {settings.rpc_url}")
        return self._w3
    
    def _get_position_manager_abi(self) -> List[Dict]:
        """Get position manager ABI."""
        # Simplified ABI with only the functions we need
        return [
            {
                "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
                "name": "positions",
                "outputs": [
                    {"internalType": "uint96", "name": "nonce", "type": "uint96"},
                    {"internalType": "address", "name": "operator", "type": "address"},
                    {"internalType": "address", "name": "token0", "type": "address"},
                    {"internalType": "address", "name": "token1", "type": "address"},
                    {"internalType": "int24", "name": "tickSpacing", "type": "int24"},
                    {"internalType": "int24", "name": "tickLower", "type": "int24"},
                    {"internalType": "int24", "name": "tickUpper", "type": "int24"},
                    {"internalType": "uint128", "name": "liquidity", "type": "uint128"},
                    {"internalType": "uint256", "name": "feeGrowthInside0LastX128", "type": "uint256"},
                    {"internalType": "uint256", "name": "feeGrowthInside1LastX128", "type": "uint256"},
                    {"internalType": "uint128", "name": "tokensOwed0", "type": "uint128"},
                    {"internalType": "uint128", "name": "tokensOwed1", "type": "uint128"}
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
                "name": "ownerOf",
                "outputs": [{"internalType": "address", "name": "", "type": "address"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [{"internalType": "address", "name": "owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "address", "name": "owner", "type": "address"},
                    {"internalType": "uint256", "name": "index", "type": "uint256"}
                ],
                "name": "tokenOfOwnerByIndex",
                "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
    
    def _get_pool_factory_abi(self) -> List[Dict]:
        """Get pool factory ABI."""
        return [
            {
                "inputs": [
                    {"internalType": "address", "name": "", "type": "address"},
                    {"internalType": "address", "name": "", "type": "address"},
                    {"internalType": "int24", "name": "", "type": "int24"}
                ],
                "name": "getPool",
                "outputs": [{"internalType": "address", "name": "", "type": "address"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
    
    def _get_pool_abi(self) -> List[Dict]:
        """Get pool ABI for slot0 function."""
        return [
            {
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
            },
            {
                "inputs": [],
                "name": "gauge",
                "outputs": [{"internalType": "address", "name": "", "type": "address"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
    
    def _get_liquidity_manager_abi(self) -> List[Dict]:
        """Get liquidity manager ABI for fetching staked positions."""
        return [
            {
                "inputs": [{"internalType": "address", "name": "owner", "type": "address"}],
                "name": "getStakedPositions",
                "outputs": [{"internalType": "uint256[]", "name": "positionIds", "type": "uint256[]"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                "name": "stakedPositionOwners",
                "outputs": [{"internalType": "address", "name": "", "type": "address"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
    
    def _get_sugar_abi(self) -> List[Dict]:
        """Get Sugar contract ABI for fetching position details."""
        return [
            {
                "inputs": [
                    {"internalType": "uint256", "name": "_limit", "type": "uint256"},
                    {"internalType": "uint256", "name": "_offset", "type": "uint256"},
                    {"internalType": "address", "name": "_account", "type": "address"}
                ],
                "name": "positions",
                "outputs": [
                    {"internalType": "tuple[]", "name": "", "type": "tuple[]"}
                ],
                "stateMutability": "view",
                "type": "function"
            }
        ]
    
    def _get_token_abi(self) -> List[Dict]:
        """Get minimal ERC20 ABI for token price queries."""
        return [
            {
                "inputs": [],
                "name": "decimals",
                "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "symbol",
                "outputs": [{"internalType": "string", "name": "", "type": "string"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
    
    async def _get_position_manager(self) -> Contract:
        """Get or create position manager contract instance."""
        if self._position_manager is None:
            w3 = self._get_w3()
            self._position_manager = w3.eth.contract(
                address=Web3.to_checksum_address(self.POSITION_MANAGER_ADDRESS),
                abi=self._get_position_manager_abi()
            )
        return self._position_manager
    
    async def _get_pool_factory(self) -> Contract:
        """Get or create pool factory contract instance."""
        if self._pool_factory is None:
            w3 = self._get_w3()
            self._pool_factory = w3.eth.contract(
                address=Web3.to_checksum_address(self.POOL_FACTORY_ADDRESS),
                abi=self._get_pool_factory_abi()
            )
        return self._pool_factory
    
    async def _get_pool_contract(self, pool_address: str) -> Contract:
        """Get or create pool contract instance."""
        if pool_address not in self._pool_contracts:
            w3 = self._get_w3()
            self._pool_contracts[pool_address] = w3.eth.contract(
                address=Web3.to_checksum_address(pool_address),
                abi=self._get_pool_abi()
            )
        return self._pool_contracts[pool_address]
    
    async def _get_liquidity_manager(self) -> Contract:
        """Get or create liquidity manager contract instance."""
        if self._liquidity_manager is None:
            w3 = self._get_w3()
            self._liquidity_manager = w3.eth.contract(
                address=Web3.to_checksum_address(self.LIQUIDITY_MANAGER_ADDRESS),
                abi=self._get_liquidity_manager_abi()
            )
        return self._liquidity_manager
    
    async def _get_sugar(self) -> Contract:
        """Get or create Sugar contract instance."""
        if self._sugar is None:
            w3 = self._get_w3()
            self._sugar = w3.eth.contract(
                address=Web3.to_checksum_address(self.SUGAR_ADDRESS),
                abi=self._get_sugar_abi()
            )
        return self._sugar
    
    async def _get_token_price_usd(self, token_address: str) -> float:
        """Get token price in USD. Simple implementation - should be replaced with proper oracle."""
        # Cache key for token price
        cache_key = f"token_price:{token_address.lower()}"
        cached_price = await cache_manager.get_custom(cache_key, ttl=60)
        if cached_price is not None:
            return cached_price
        
        # Hardcoded prices for common tokens (replace with oracle/API in production)
        prices = {
            self.USDC_ADDRESS.lower(): 1.0,
            self.WETH_ADDRESS.lower(): 3500.0,  # Example ETH price
            self.AERO_ADDRESS.lower(): 2.0,     # Example AERO price
        }
        
        price = prices.get(token_address.lower(), 0.0)
        
        # Cache the price
        await cache_manager.set_custom(cache_key, price, ttl=60)
        return price
    
    async def _fetch_position_from_sugar(self, position_id: int) -> Optional[Dict]:
        """Fetch position details from Sugar contract."""
        try:
            sugar = await self._get_sugar()
            
            # Fetch positions with high limit to ensure we get the position
            positions_data = sugar.functions.positions(
                100000,  # limit
                0,       # offset
                Web3.to_checksum_address(self.LIQUIDITY_MANAGER_ADDRESS)  # account (LiquidityManager)
            ).call()
            
            # Find the position with matching ID
            for position in positions_data:
                if position[0] == position_id:  # First element is position ID
                    return {
                        'id': position[0],
                        'staked0': position[7] if len(position) > 7 else 0,  # staked0
                        'staked1': position[8] if len(position) > 8 else 0,  # staked1
                        'emissions_earned': position[9] if len(position) > 9 else 0,  # emissions_earned
                    }
            
            return None
        except Exception as e:
            print(f"Failed to fetch position from Sugar: {str(e)}")
            return None
    
    async def get_position_by_id(self, token_id: int) -> PositionInfo:
        """
        Get position information by token ID.
        
        Args:
            token_id: NFT token ID of the position
            
        Returns:
            PositionInfo object with position details
        """
        # Check cache first
        cache_key = f"position:{token_id}"
        cached_position = await cache_manager.get_custom(cache_key, ttl=60)
        if cached_position:
            return PositionInfo(**cached_position)
        
        try:
            position_manager = await self._get_position_manager()
            pool_factory = await self._get_pool_factory()
            liquidity_manager = await self._get_liquidity_manager()
            
            # Get position data from position manager
            position_data = position_manager.functions.positions(token_id).call()
            
            # Get owner from LiquidityManager's stakedPositionOwners
            # This works for all positions tracked by LiquidityManager
            owner = liquidity_manager.functions.stakedPositionOwners(token_id).call()
            
            # If owner is zero address, the position doesn't exist or isn't tracked
            if not owner or owner == "0x0000000000000000000000000000000000000000":
                raise ValueError(f"Position {token_id} not found or not tracked by LiquidityManager")
            
            # Extract position data
            token0 = position_data[2]
            token1 = position_data[3]
            tick_spacing = position_data[4]
            tick_lower = position_data[5]
            tick_upper = position_data[6]
            liquidity = position_data[7]
            
            # Get pool address from factory
            pool_address = pool_factory.functions.getPool(token0, token1, tick_spacing).call()
            
            # Get current tick from pool to check if position is in range
            pool_contract = await self._get_pool_contract(pool_address)
            slot0_data = pool_contract.functions.slot0().call()
            current_tick = slot0_data[1]
            
            # Check if position is in range
            in_range = tick_lower <= current_tick < tick_upper
            
            # Get gauge address from pool
            gauge_address = None
            try:
                gauge_address = pool_contract.functions.gauge().call()
                if not gauge_address or gauge_address == "0x0000000000000000000000000000000000000000":
                    gauge_address = None
            except:
                gauge_address = None
            
            # Calculate USD values from Sugar contract
            current_value_usd = None
            unclaimed_fees_usd = None
            
            sugar_position = await self._fetch_position_from_sugar(token_id)
            if sugar_position:
                # Get token prices
                token0_price = await self._get_token_price_usd(token0)
                token1_price = await self._get_token_price_usd(token1)
                aero_price = await self._get_token_price_usd(self.AERO_ADDRESS)
                
                # Calculate unclaimed fees USD (staked0 * token0_price + staked1 * token1_price)
                staked0_amount = sugar_position['staked0'] / 1e18  # Assuming 18 decimals
                staked1_amount = sugar_position['staked1'] / 1e18  # Assuming 18 decimals
                unclaimed_fees_usd = (staked0_amount * token0_price) + (staked1_amount * token1_price)
                
                # Calculate current value USD (emissions_earned * aero_price)
                emissions_amount = sugar_position['emissions_earned'] / 1e18  # Assuming 18 decimals
                current_value_usd = emissions_amount * aero_price
            
            position_info = PositionInfo(
                id=token_id,
                owner=owner,
                pool_address=pool_address,
                tick_lower=tick_lower,
                tick_upper=tick_upper,
                current_tick=current_tick,
                liquidity=str(liquidity),
                in_range=in_range,
                current_value_usd=current_value_usd,
                unclaimed_fees_usd=unclaimed_fees_usd,
                gauge_address=gauge_address,
                token0=token0,
                token1=token1,
                tick_spacing=tick_spacing
            )
            
            # Cache the result
            await cache_manager.set_custom(cache_key, position_info.dict(), ttl=60)
            
            return position_info
            
        except Exception as e:
            raise Exception(f"Failed to fetch position {token_id}: {str(e)}")
    
    async def get_positions_by_owner(self, owner_address: str) -> List[PositionInfo]:
        """
        Get all positions owned by an address (both unstaked and staked).
        
        Args:
            owner_address: Owner's wallet address
            
        Returns:
            List of PositionInfo objects
        """
        # Check cache first
        cache_key = f"positions:owner:{owner_address.lower()}"
        cached_positions = await cache_manager.get_custom(cache_key, ttl=60)
        if cached_positions:
            return [PositionInfo(**p) for p in cached_positions]
        
        try:
            position_manager = await self._get_position_manager()
            liquidity_manager = await self._get_liquidity_manager()
            owner_address = Web3.to_checksum_address(owner_address)
            
            all_position_ids = []
            
            # 1. Get unstaked positions (NFTs held directly by the owner)
            try:
                balance = position_manager.functions.balanceOf(owner_address).call()
                for index in range(balance):
                    try:
                        token_id = position_manager.functions.tokenOfOwnerByIndex(owner_address, index).call()
                        all_position_ids.append(token_id)
                    except Exception as e:
                        print(f"Failed to get unstaked position at index {index}: {str(e)}")
                        continue
            except Exception as e:
                print(f"Failed to get unstaked positions: {str(e)}")
            
            # 2. Get staked positions from LiquidityManager
            try:
                staked_position_ids = liquidity_manager.functions.getStakedPositions(owner_address).call()
                all_position_ids.extend(staked_position_ids)
            except Exception as e:
                print(f"Failed to get staked positions: {str(e)}")
            
            # Remove duplicates (shouldn't happen, but just in case)
            all_position_ids = list(set(all_position_ids))
            
            if not all_position_ids:
                return []
            
            positions = []
            
            # Fetch details for each position
            for token_id in all_position_ids:
                try:
                    position_info = await self.get_position_by_id(token_id)
                    positions.append(position_info)
                except Exception as e:
                    print(f"Failed to load position {token_id}: {str(e)}")
                    continue
            
            # Cache the result
            await cache_manager.set_custom(cache_key, [p.dict() for p in positions], ttl=60)
            
            return positions
            
        except Exception as e:
            raise Exception(f"Failed to fetch positions for {owner_address}: {str(e)}")


# Create singleton instance
positions_service = PositionsService()