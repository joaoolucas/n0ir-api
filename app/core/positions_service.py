"""Service for handling position-related operations."""

import json
from typing import Dict, List, Optional, Any, Tuple
from web3 import Web3
from web3.contract import Contract

from app.core.config import settings
from app.core.cache import cache_manager
from app.schemas.positions import PositionInfo
from app.core.logger import logger
from app.core.pool_constants import SUGAR_ABI


class PositionsService:
    """Service for fetching and analyzing positions."""
    
    # Contract addresses
    POSITION_MANAGER_ADDRESS = "0x827922686190790b37229fd06084350E74485b72"
    POOL_FACTORY_ADDRESS = "0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A"
    LIQUIDITY_MANAGER_ADDRESS = "0x8123F467Fa2C53a31D8738D5FAa0DFd881F5DF8A"  # Our LiquidityManager contract
    SUGAR_ADDRESS = "0x27fc745390d1f4BaF8D184FBd97748340f786634"

    # Known legacy position IDs that should be ignored (deprecated contracts)
    IGNORED_POSITION_IDS = {25494740}
    
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
                "inputs": [{"internalType": "address", "name": "user", "type": "address"}],
                "name": "getUserPositions",
                "outputs": [{"internalType": "uint256[]", "name": "", "type": "uint256[]"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                "name": "positionOwners",
                "outputs": [{"internalType": "address", "name": "", "type": "address"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
                "name": "getPositionOwner",
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
                    {"name": "_limit", "type": "uint256"},
                    {"name": "_offset", "type": "uint256"},
                    {"name": "_account", "type": "address"}
                ],
                "name": "positions",
                "outputs": [
                    {
                        "components": [
                            {"name": "id", "type": "uint256"},
                            {"name": "lp", "type": "address"},
                            {"name": "liquidity", "type": "uint256"},
                            {"name": "staked", "type": "uint256"},
                            {"name": "amount0", "type": "uint256"},
                            {"name": "amount1", "type": "uint256"},
                            {"name": "staked0", "type": "uint256"},
                            {"name": "staked1", "type": "uint256"},
                            {"name": "unstaked_earned0", "type": "uint256"},
                            {"name": "unstaked_earned1", "type": "uint256"},
                            {"name": "emissions_earned", "type": "uint256"},
                            {"name": "tick_lower", "type": "int24"},
                            {"name": "tick_upper", "type": "int24"},
                            {"name": "sqrt_ratio_lower", "type": "uint160"},
                            {"name": "sqrt_ratio_upper", "type": "uint160"},
                            {"name": "alm", "type": "address"}
                        ],
                        "name": "",
                        "type": "tuple[]"
                    }
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [
                    {"name": "_limit", "type": "uint256"},
                    {"name": "_offset", "type": "uint256"},
                    {"name": "_account", "type": "address"}
                ],
                "name": "positionsUnstakedConcentrated",
                "outputs": [
                    {
                        "components": [
                            {"name": "id", "type": "uint256"},
                            {"name": "lp", "type": "address"},
                            {"name": "liquidity", "type": "uint256"},
                            {"name": "staked", "type": "uint256"},
                            {"name": "amount0", "type": "uint256"},
                            {"name": "amount1", "type": "uint256"},
                            {"name": "staked0", "type": "uint256"},
                            {"name": "staked1", "type": "uint256"},
                            {"name": "unstaked_earned0", "type": "uint256"},
                            {"name": "unstaked_earned1", "type": "uint256"},
                            {"name": "emissions_earned", "type": "uint256"},
                            {"name": "tick_lower", "type": "int24"},
                            {"name": "tick_upper", "type": "int24"},
                            {"name": "sqrt_ratio_lower", "type": "uint160"},
                            {"name": "sqrt_ratio_upper", "type": "uint160"},
                            {"name": "alm", "type": "address"}
                        ],
                        "name": "",
                        "type": "tuple[]"
                    }
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
                abi=SUGAR_ABI
            )
        return self._sugar
    
    async def _get_token_price_usd(self, token_address: str) -> float:
        """Get token price in USD using pools_service with fallback to last valid price."""
        from app.core.pools_service import pools_service
        
        # Use pools_service to get the price (it has DexScreener integration)
        prices = await pools_service.get_token_prices([token_address])
        price = prices.get(token_address.lower(), 0.0)
        
        if price == 0.0:
            # Try to get the last valid price from fallback cache
            fallback_price = await cache_manager.get_token_price_fallback(token_address)
            if fallback_price and fallback_price > 0:
                logger.warning(f"Could not determine current price for token {token_address}, using last valid price: ${fallback_price}")
                return fallback_price
            else:
                logger.warning(f"Could not determine price for token {token_address} and no fallback available")
        else:
            logger.info(f"Got price for {token_address}: ${price}")
        
        return price
    
    async def _get_token_decimals(self, token_address: str) -> int:
        """Get token decimals from contract."""
        # Cache key for token decimals
        cache_key = f"token_decimals:{token_address.lower()}"
        cached_decimals = await cache_manager.get_custom(cache_key, ttl=3600)  # 1 hour cache
        if cached_decimals is not None:
            return cached_decimals
        
        # Common token decimals
        known_decimals = {
            self.USDC_ADDRESS.lower(): 6,
            "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": 6,  # USDC on Base
            "0x50c5725949a6f0c72e6c4a641f24049a917db0cb": 18,  # DAI on Base
            self.WETH_ADDRESS.lower(): 18,
            self.AERO_ADDRESS.lower(): 18,
        }
        
        if token_address.lower() in known_decimals:
            decimals = known_decimals[token_address.lower()]
            await cache_manager.set_custom(cache_key, decimals, ttl=3600)
            return decimals
        
        try:
            # Try to get decimals from contract
            w3 = self._get_w3()
            token_contract = w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=[{"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"}]
            )
            decimals = token_contract.functions.decimals().call()
            await cache_manager.set_custom(cache_key, decimals, ttl=3600)
            return decimals
        except Exception as e:
            logger.warning(f"Failed to get decimals for {token_address}, defaulting to 18: {str(e)}")
            return 18  # Default to 18 decimals
    
    async def _fetch_position_from_sugar(self, position_id: int, owner_address: str, is_unstaked: bool = False) -> Optional[Dict]:
        """Fetch position details from Sugar contract."""
        try:
            sugar = await self._get_sugar()
            
            logger.info(f"Fetching {'unstaked' if is_unstaked else 'staked'} position {position_id} from Sugar contract for owner {owner_address}...")
            
            # Use different method based on staking status
            if is_unstaked:
                # Use positionsUnstakedConcentrated for unstaked positions
                positions_data = sugar.functions.positionsUnstakedConcentrated(
                    500,  # _limit
                    0,    # _offset
                    Web3.to_checksum_address(owner_address)  # _account (wallet address)
                ).call()
            else:
                # Use regular positions for staked positions
                positions_data = sugar.functions.positions(
                    100000,  # limit
                    0,       # offset
                    Web3.to_checksum_address(owner_address)  # account (owner address)
                ).call()
            
            logger.info(f"Sugar returned {len(positions_data)} {'unstaked' if is_unstaked else 'staked'} positions for owner {owner_address}")
            
            # Find the position with matching ID
            for position in positions_data:
                if position[0] == position_id:  # First element is position ID
                    logger.info(f"Found position {position_id} in Sugar data")
                    
                    if is_unstaked:
                        # For unstaked positions, we use amount0 and amount1 which represent the token amounts
                        # positionsUnstakedConcentrated returns same structure as positions
                        # amount0 and amount1 are at indices 4 and 5
                        return {
                            'id': position[0],
                            'staked0': position[4] if len(position) > 4 else 0,  # amount0 for unstaked positions
                            'staked1': position[5] if len(position) > 5 else 0,  # amount1 for unstaked positions
                            'emissions_earned': 0,  # No emissions for unstaked positions
                        }
                    else:
                        # For staked positions, use the regular indices
                        return {
                            'id': position[0],
                            'staked0': position[6] if len(position) > 6 else 0,  # staked0 (index 6)
                            'staked1': position[7] if len(position) > 7 else 0,  # staked1 (index 7)
                            'emissions_earned': position[10] if len(position) > 10 else 0,  # emissions_earned (index 10)
                        }
            
            logger.warning(f"Position {position_id} not found in Sugar data for owner {owner_address}")
            return None
        except Exception as e:
            logger.error(f"Failed to fetch position from Sugar: {e!r}", exc_info=True)
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
            
            # Always try to get owner from LiquidityManager first (CDP wallet address)
            cdp_wallet = None
            try:
                cdp_wallet = liquidity_manager.functions.getPositionOwner(token_id).call()
                if cdp_wallet and cdp_wallet != "0x0000000000000000000000000000000000000000":
                    logger.info(f"Position {token_id} CDP wallet from LiquidityManager.getPositionOwner: {cdp_wallet}")
            except Exception as e:
                logger.debug(f"Position {token_id} not in LiquidityManager: {e}")

            # Get NFT owner to determine staking status
            nft_owner = None
            try:
                nft_owner = position_manager.functions.ownerOf(token_id).call()
                logger.debug(f"Position {token_id} NFT owner: {nft_owner}")
            except Exception as e:
                raise ValueError(f"Position {token_id} not found: {e}")
            
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
            
            # Determine owner and staking status
            # If position is managed by LiquidityManager, use CDP wallet from getPositionOwner
            if cdp_wallet:
                owner = cdp_wallet
                # All LiquidityManager positions are auto-staked on creation
                staked = True
                logger.info(f"Position {token_id} - LiquidityManager position: owner={owner}, staked=True (auto-staked)")
            else:
                # Legacy position not managed by LiquidityManager
                owner = nft_owner
                # Check if staked directly in gauge (old flow)
                staked = gauge_address and nft_owner.lower() == gauge_address.lower()
                logger.info(f"Position {token_id} - Legacy position: owner={owner}, staked={staked}")

            # Calculate USD values from Sugar contract
            current_value_usd = None
            unclaimed_fees_usd = None
            unclaimed_rewards_aero = None

            # Use the owner (CDP wallet) for Sugar lookups
            sugar_position = await self._fetch_position_from_sugar(token_id, owner, is_unstaked=not staked)
            logger.info(f"Position {token_id} - Sugar data: {sugar_position}")
            
            if sugar_position:
                # Get token prices
                token0_price = await self._get_token_price_usd(token0)
                token1_price = await self._get_token_price_usd(token1)
                aero_price = await self._get_token_price_usd(self.AERO_ADDRESS)
                
                logger.info(f"Position {token_id} - Prices: token0={token0_price}, token1={token1_price}, aero={aero_price}")
                logger.info(f"Position {token_id} - Tokens: token0={token0}, token1={token1}")
                
                # Get token decimals
                token0_decimals = await self._get_token_decimals(token0)
                token1_decimals = await self._get_token_decimals(token1)
                
                logger.info(f"Position {token_id} - Decimals: token0={token0_decimals}, token1={token1_decimals}")
                
                # Calculate current value USD (staked0 * token0_price + staked1 * token1_price)
                staked0_amount = sugar_position['staked0'] / (10 ** token0_decimals)
                staked1_amount = sugar_position['staked1'] / (10 ** token1_decimals)
                current_value_usd = (staked0_amount * token0_price) + (staked1_amount * token1_price)
                
                logger.info(f"Position {token_id} - Staked amounts: token0={staked0_amount}, token1={staked1_amount}")
                logger.info(f"Position {token_id} - Current value USD: {current_value_usd}")
                
                # Calculate unclaimed fees USD (emissions_earned * aero_price)
                emissions_amount = sugar_position['emissions_earned'] / 1e18  # Assuming 18 decimals
                unclaimed_fees_usd = emissions_amount * aero_price
                unclaimed_rewards_aero = emissions_amount  # Store AERO amount
                
                logger.info(f"Position {token_id} - Emissions: {emissions_amount} AERO = ${unclaimed_fees_usd}")
            else:
                logger.warning(f"Position {token_id} - No Sugar data found")

            # Fetch pool APR and name from pools_service
            pool_apr = None
            pool_name = None
            try:
                from app.core.pools_service import pools_service
                pool_data = await pools_service.get_pool(pool_address, include_effective_apr=False)
                pool_apr = pool_data.get('apr', 0)

                # Extract pool name from symbol
                symbol = pool_data.get('symbol', '')
                if symbol and '-' in symbol:
                    pool_name = symbol.split('-')[0]  # Get everything before the dash (e.g., "WETH/USDC-0.3%" -> "WETH/USDC")
                else:
                    pool_name = symbol

                logger.info(f"Position {token_id} - Pool: {pool_name}, APR: {pool_apr}%")
            except Exception as e:
                logger.warning(f"Could not fetch pool data for position {token_id}: {e}")
                pool_apr = 0
                pool_name = None

            position_info = PositionInfo(
                id=token_id,
                owner=actual_user,  # Use actual_user instead of owner (which might be the gauge)
                pool_address=pool_address,
                tick_lower=tick_lower,
                tick_upper=tick_upper,
                current_tick=current_tick,
                liquidity=str(liquidity),
                in_range=in_range,
                staked=staked,
                current_value_usd=current_value_usd,
                unclaimed_fees_usd=unclaimed_fees_usd,
                unclaimed_rewards_aero=unclaimed_rewards_aero,
                gauge_address=gauge_address,
                token0=token0,
                token1=token1,
                tick_spacing=tick_spacing,
                pool_name=pool_name,  # Add pool name to position info
                apr=pool_apr  # Add APR to position info
            )
            
            # Cache the result
            await cache_manager.set_custom(cache_key, position_info.dict(), ttl=60)
            
            return position_info
            
        except Exception as e:
            raise Exception(f"Failed to fetch position {token_id}: {e!r}")
    
    async def get_positions_by_owner(self, owner_address: str, skip_cache: bool = False) -> List[PositionInfo]:
        """
        Get all positions owned by an address (both unstaked and staked) using Sugar contract.

        Args:
            owner_address: Owner's wallet address
            skip_cache: If True, bypass cache and fetch directly from blockchain

        Returns:
            List of PositionInfo objects
        """
        # Check cache first (unless skipping)
        cache_key = f"positions:owner:{owner_address.lower()}"
        if not skip_cache:
            cached_positions = await cache_manager.get_custom(cache_key, ttl=60)
            if cached_positions:
                return [PositionInfo(**p) for p in cached_positions]

        try:
            # Get Sugar contract
            if self._sugar is None:
                w3 = self._get_w3()
                self._sugar = w3.eth.contract(
                    address=Web3.to_checksum_address(self.SUGAR_ADDRESS),
                    abi=SUGAR_ABI
                )

            owner_address = Web3.to_checksum_address(owner_address)

            # Call Sugar contract to get all positions (both staked and unstaked)
            # Using limit=9000 and offset=0 to get all positions
            sugar_positions = self._sugar.functions.positions(
                9000,  # _limit
                0,     # _offset
                owner_address  # _account
            ).call()

            if not sugar_positions:
                logger.info(f"No positions found for {owner_address}")
                return []

            positions = []

            # Parse Sugar response and fetch additional details for each position
            for pos_data in sugar_positions:
                try:
                    token_id = pos_data[0]  # id field

                    # Skip ignored positions
                    if token_id in self.IGNORED_POSITION_IDS:
                        logger.info(f"Skipping legacy position {token_id}")
                        continue

                    # Get additional position details using existing method
                    position_info = await self.get_position_by_id(token_id)

                    # Override staked status based on Sugar data
                    # If staked liquidity > 0, position is staked
                    if pos_data[3] > 0:  # staked field
                        position_info.staked = True

                    positions.append(position_info)

                except Exception as e:
                    logger.error(f"Failed to process position {token_id}: {str(e)}")
                    continue

            # Cache the result
            if positions:
                await cache_manager.set_custom(cache_key, [p.dict() for p in positions], ttl=60)

            logger.info(f"Found {len(positions)} positions for {owner_address} via Sugar contract")
            return positions

        except Exception as e:
            logger.error(f"Sugar contract failed, falling back to direct NFT query: {str(e)}")

            # Fallback to the old method if Sugar fails
            try:
                position_manager = await self._get_position_manager()
                owner_address = Web3.to_checksum_address(owner_address)

                all_position_ids = []

                # Get unstaked positions only (NFTs held directly by the owner)
                try:
                    balance = position_manager.functions.balanceOf(owner_address).call()
                    for index in range(balance):
                        try:
                            token_id = position_manager.functions.tokenOfOwnerByIndex(owner_address, index).call()
                            if token_id in self.IGNORED_POSITION_IDS:
                                continue
                            all_position_ids.append(token_id)
                        except Exception as e:
                            logger.error(f"Failed to get position at index {index}: {str(e)}")
                            continue
                except Exception as e:
                    logger.error(f"Failed to get positions via NFT: {str(e)}")

                if not all_position_ids:
                    return []

                positions = []
                for token_id in all_position_ids:
                    try:
                        position_info = await self.get_position_by_id(token_id)
                        positions.append(position_info)
                    except Exception as e:
                        logger.error(f"Failed to load position {token_id}: {str(e)}")
                        continue

                return positions

            except Exception as e2:
                logger.error(f"Both Sugar and NFT methods failed: {str(e2)}")
                raise Exception(f"Failed to fetch positions for {owner_address}: {str(e)}")


# Create singleton instance
positions_service = PositionsService()
