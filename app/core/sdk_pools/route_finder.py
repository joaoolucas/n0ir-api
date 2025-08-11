"""Efficient route finding using CL Factory getPool function."""

import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

from dotenv import load_dotenv
from web3 import Web3

from .constants import USDC, WETH
from .models import SwapRoute

# Load environment variables
load_dotenv()


# CL Factory address on Base
CL_FACTORY_ADDRESS = "0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A"

# Common tick spacings for CL pools
TICK_SPACINGS = [1, 10, 50, 100, 200, 500]  # Common tick spacings to check

# Connector tokens for routing (lowercase for comparison)
CBBTC = "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf"  # cbBTC on Base

# Factory ABI (only getPool function)
FACTORY_ABI = [{
    "inputs": [
        {"internalType": "address", "name": "", "type": "address"},
        {"internalType": "address", "name": "", "type": "address"},
        {"internalType": "int24", "name": "", "type": "int24"}
    ],
    "name": "getPool",
    "outputs": [{"internalType": "address", "name": "", "type": "address"}],
    "stateMutability": "view",
    "type": "function"
}]


@dataclass
class PoolInfo:
    """Basic pool information."""
    address: str
    token0: str
    token1: str
    tick_spacing: int


class RouteFinder:
    """Find routes efficiently using Factory getPool queries."""
    
    def __init__(self, w3: Optional[Web3] = None):
        """Initialize with Web3 connection.
        
        Args:
            w3: Web3 instance connected to Base. If None, uses RPC_URL from environment.
        """
        if w3 is None:
            rpc_url = os.getenv("RPC_URL", "https://mainnet.base.org")
            self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        else:
            self.w3 = w3
            
        self.factory = self.w3.eth.contract(
            address=Web3.to_checksum_address(CL_FACTORY_ADDRESS),
            abi=FACTORY_ABI
        )
    
    def find_pool(self, token0: str, token1: str) -> Optional[PoolInfo]:
        """Find the best pool between two tokens.
        
        Args:
            token0: First token address
            token1: Second token address
            
        Returns:
            PoolInfo if pool exists, None otherwise
        """
        # Ensure addresses are checksummed
        token0_checksum = Web3.to_checksum_address(token0)
        token1_checksum = Web3.to_checksum_address(token1)
        
        # Order tokens (smaller address first)
        if token0_checksum.lower() > token1_checksum.lower():
            token0_checksum, token1_checksum = token1_checksum, token0_checksum
        
        # Try each tick spacing
        for tick_spacing in TICK_SPACINGS:
            try:
                pool_address = self.factory.functions.getPool(
                    token0_checksum,
                    token1_checksum,
                    tick_spacing
                ).call()
                
                # Check if pool exists (non-zero address)
                if pool_address != "0x0000000000000000000000000000000000000000":
                    return PoolInfo(
                        address=Web3.to_checksum_address(pool_address),
                        token0=token0_checksum,
                        token1=token1_checksum,
                        tick_spacing=tick_spacing
                    )
            except Exception:
                continue
        
        return None
    
    def find_routes_for_position_open(
        self,
        pool_token0: str,
        pool_token1: str,
        target_pool_address: Optional[str] = None,
        target_pool_tick_spacing: Optional[int] = None
    ) -> Tuple[Optional[SwapRoute], Optional[SwapRoute]]:
        """Find routes for opening a position (USDC → pool tokens).
        
        Optimized routing logic:
        1. If one token is USDC, use target pool for the other token
        2. If both have direct USDC pools, use separate swaps  
        3. If one lacks direct route, route through connector then target pool
        4. If neither has direct route, use WETH or cbBTC as intermediates
        
        Args:
            pool_token0: First token of the pool
            pool_token1: Second token of the pool
            target_pool_address: Optional address of the target pool to prefer when routing
            target_pool_tick_spacing: Optional tick spacing of the target pool
            
        Returns:
            Tuple of (token0_route, token1_route) where None means no swap needed
        """
        # Ensure addresses are checksummed
        usdc = Web3.to_checksum_address(USDC)
        token0 = Web3.to_checksum_address(pool_token0)
        token1 = Web3.to_checksum_address(pool_token1)
        
        # Case 1: One token is USDC - use target pool for the other
        if token0.lower() == usdc.lower():
            # Token0 is USDC, only need route for token1 via target pool
            if target_pool_address and target_pool_tick_spacing is not None:
                # Use the specific target pool with known tick spacing
                pool_address = Web3.to_checksum_address(target_pool_address)
                return None, SwapRoute(
                    pools=[pool_address],
                    tokens=[usdc, token1],
                    tick_spacings=[target_pool_tick_spacing]
                )
            else:
                # Find any pool between the tokens
                target_pool = self.find_pool(token0, token1)
                if target_pool:
                    return None, SwapRoute(
                        pools=[target_pool.address],
                        tokens=[usdc, token1],
                        tick_spacings=[target_pool.tick_spacing]
                    )
            # If no target pool found, return no routes
            return None, None
        
        if token1.lower() == usdc.lower():
            # Token1 is USDC, only need route for token0 via target pool
            if target_pool_address and target_pool_tick_spacing is not None:
                # Use the specific target pool with known tick spacing
                pool_address = Web3.to_checksum_address(target_pool_address)
                return SwapRoute(
                    pools=[pool_address],
                    tokens=[usdc, token0],
                    tick_spacings=[target_pool_tick_spacing]
                ), None
            else:
                # Find any pool between the tokens
                target_pool = self.find_pool(token0, token1)
                if target_pool:
                    return SwapRoute(
                        pools=[target_pool.address],
                        tokens=[usdc, token0],
                        tick_spacings=[target_pool.tick_spacing]
                    ), None
            # If no target pool found, return no routes
            return None, None
        
        # Check for direct USDC pools for both tokens
        token0_direct = self.find_pool(usdc, token0)
        token1_direct = self.find_pool(usdc, token1)
        
        # Case 2: Both tokens have direct USDC pools - use separate swaps
        if token0_direct and token1_direct:
            return (
                SwapRoute(
                    pools=[token0_direct.address],
                    tokens=[usdc, token0],
                    tick_spacings=[token0_direct.tick_spacing]
                ),
                SwapRoute(
                    pools=[token1_direct.address],
                    tokens=[usdc, token1],
                    tick_spacings=[token1_direct.tick_spacing]
                )
            )
        
        # Get the target pool info
        target_pool = self.find_pool(token0, token1)
        
        # Case 3: One token has direct route, other doesn't
        if token0_direct and not token1_direct and target_pool:
            # Can swap USDC → token0, then token0 → token1 via target pool
            # But we return separate routes for the atomic contract
            # Token1 needs multi-hop through token0
            return (
                SwapRoute(
                    pools=[token0_direct.address],
                    tokens=[usdc, token0],
                    tick_spacings=[token0_direct.tick_spacing]
                ),
                self._find_route_to_token_with_connectors(token1)
            )
        elif token1_direct and not token0_direct and target_pool:
            # Can swap USDC → token1, then token1 → token0 via target pool
            return (
                self._find_route_to_token_with_connectors(token0),
                SwapRoute(
                    pools=[token1_direct.address],
                    tokens=[usdc, token1],
                    tick_spacings=[token1_direct.tick_spacing]
                )
            )
        
        # Case 4: Neither token has direct USDC route - use connectors
        token0_route = self._find_route_to_token_with_connectors(token0)
        token1_route = self._find_route_to_token_with_connectors(token1)
        
        return token0_route, token1_route
    
    def find_routes_for_position_close(
        self,
        pool_token0: str,
        pool_token1: str
    ) -> Tuple[Optional[SwapRoute], Optional[SwapRoute]]:
        """Find routes for closing a position (pool tokens → USDC).
        
        Optimized routing logic mirrors the opening logic but in reverse.
        
        Args:
            pool_token0: First token of the pool
            pool_token1: Second token of the pool
            
        Returns:
            Tuple of (token0_route, token1_route) where None means no swap needed
        """
        # Ensure addresses are checksummed
        usdc = Web3.to_checksum_address(USDC)
        token0 = Web3.to_checksum_address(pool_token0)
        token1 = Web3.to_checksum_address(pool_token1)
        
        # If one token is USDC, only need route for the other
        if token0.lower() == usdc.lower():
            return None, self._find_route_from_token(token1)
        elif token1.lower() == usdc.lower():
            return self._find_route_from_token(token0), None
        
        # Otherwise find routes for both tokens
        token0_route = self._find_route_from_token(pool_token0)
        token1_route = self._find_route_from_token(pool_token1)
        
        return token0_route, token1_route
    
    def _find_route_to_token_with_connectors(self, target_token: str) -> Optional[SwapRoute]:
        """Find route from USDC to a target token using WETH or cbBTC as connectors.
        
        Args:
            target_token: Target token address
            
        Returns:
            SwapRoute if found, None if target is USDC or no route exists
        """
        # Ensure all addresses are checksummed
        usdc = Web3.to_checksum_address(USDC)
        weth = Web3.to_checksum_address(WETH)
        cbbtc = Web3.to_checksum_address(CBBTC)
        target = Web3.to_checksum_address(target_token)
        
        # If target is USDC, no route needed
        if target.lower() == usdc.lower():
            return None
        
        # Try direct USDC -> target
        direct_pool = self.find_pool(usdc, target)
        if direct_pool:
            return SwapRoute(
                pools=[direct_pool.address],
                tokens=[usdc, target],
                tick_spacings=[direct_pool.tick_spacing]
            )
        
        # Try USDC -> WETH -> target
        if target.lower() != weth.lower():
            usdc_weth_pool = self.find_pool(usdc, weth)
            weth_target_pool = self.find_pool(weth, target)
            
            if usdc_weth_pool and weth_target_pool:
                return SwapRoute(
                    pools=[usdc_weth_pool.address, weth_target_pool.address],
                    tokens=[usdc, weth, target],
                    tick_spacings=[usdc_weth_pool.tick_spacing, weth_target_pool.tick_spacing]
                )
        
        # Try USDC -> cbBTC -> target
        if target.lower() != cbbtc.lower():
            usdc_cbbtc_pool = self.find_pool(usdc, cbbtc)
            cbbtc_target_pool = self.find_pool(cbbtc, target)
            
            if usdc_cbbtc_pool and cbbtc_target_pool:
                return SwapRoute(
                    pools=[usdc_cbbtc_pool.address, cbbtc_target_pool.address],
                    tokens=[usdc, cbbtc, target],
                    tick_spacings=[usdc_cbbtc_pool.tick_spacing, cbbtc_target_pool.tick_spacing]
                )
        
        return None
    
    def _find_route_to_token(self, target_token: str) -> Optional[SwapRoute]:
        """Find route from USDC to a target token.
        
        This is kept for backward compatibility but delegates to the new method.
        
        Args:
            target_token: Target token address
            
        Returns:
            SwapRoute if found, None if target is USDC or no route exists
        """
        return self._find_route_to_token_with_connectors(target_token)
    
    def _find_route_from_token(self, source_token: str) -> Optional[SwapRoute]:
        """Find route from a token to USDC.
        
        Args:
            source_token: Source token address
            
        Returns:
            SwapRoute if found, None if source is USDC or no route exists
        """
        # Ensure all addresses are checksummed
        usdc = Web3.to_checksum_address(USDC)
        weth = Web3.to_checksum_address(WETH)
        cbbtc = Web3.to_checksum_address(CBBTC)
        source = Web3.to_checksum_address(source_token)
        
        # If source is USDC, no route needed
        if source.lower() == usdc.lower():
            return None
        
        # Try direct source -> USDC
        direct_pool = self.find_pool(source, usdc)
        if direct_pool:
            return SwapRoute(
                pools=[direct_pool.address],
                tokens=[source, usdc],
                tick_spacings=[direct_pool.tick_spacing]
            )
        
        # Try source -> WETH -> USDC
        if source.lower() != weth.lower():
            source_weth_pool = self.find_pool(source, weth)
            weth_usdc_pool = self.find_pool(weth, usdc)
            
            if source_weth_pool and weth_usdc_pool:
                return SwapRoute(
                    pools=[source_weth_pool.address, weth_usdc_pool.address],
                    tokens=[source, weth, usdc],
                    tick_spacings=[source_weth_pool.tick_spacing, weth_usdc_pool.tick_spacing]
                )
        
        # Try source -> cbBTC -> USDC
        if source.lower() != cbbtc.lower():
            source_cbbtc_pool = self.find_pool(source, cbbtc)
            cbbtc_usdc_pool = self.find_pool(cbbtc, usdc)
            
            if source_cbbtc_pool and cbbtc_usdc_pool:
                return SwapRoute(
                    pools=[source_cbbtc_pool.address, cbbtc_usdc_pool.address],
                    tokens=[source, cbbtc, usdc],
                    tick_spacings=[source_cbbtc_pool.tick_spacing, cbbtc_usdc_pool.tick_spacing]
                )
        
        return None