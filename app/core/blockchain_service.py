"""
Blockchain service for fetching on-chain data.
"""

from typing import Optional, Dict, Any, List
from web3 import Web3
from web3.exceptions import ContractLogicError
from decimal import Decimal
import asyncio
from functools import lru_cache
from loguru import logger
import time
from app.core.config import settings

# USDC contract on Base
USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

# Minimal ERC20 ABI for balanceOf
ERC20_ABI = [
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]


class BlockchainService:
    """Service for interacting with blockchain."""
    
    def __init__(self):
        """Initialize blockchain service with Web3 connection."""
        self.w3 = None
        self._connect()
        self._balance_cache: Dict[str, tuple[float, float]] = {}  # address -> (balance, timestamp)
        self._cache_ttl = 30  # Cache for 30 seconds
        
    def _connect(self):
        """Connect to Base RPC."""
        # First try the configured RPC URL from environment
        primary_rpc = settings.rpc_url
        
        # Fallback RPC URLs if primary fails
        fallback_rpcs = [
            "https://base.llamarpc.com",
            "https://base.drpc.org",
            "https://mainnet.base.org",
        ]
        
        # Build list of RPCs to try (primary first, then fallbacks)
        rpc_urls = [primary_rpc] + [url for url in fallback_rpcs if url != primary_rpc]
        
        for rpc_url in rpc_urls:
            try:
                self.w3 = Web3(Web3.HTTPProvider(rpc_url))
                if self.w3.is_connected():
                    logger.info(f"Connected to Base RPC: {rpc_url}")
                    return
            except Exception as e:
                logger.warning(f"Failed to connect to {rpc_url}: {e}")
                continue
        
        logger.error("Failed to connect to any Base RPC endpoint")
        raise Exception("Could not connect to Base blockchain")
    
    async def get_usdc_balance(self, address: str, use_cache: bool = True) -> float:
        """
        Get USDC balance for an address.
        
        Args:
            address: Wallet address to check
            use_cache: Whether to use cached value if available
            
        Returns:
            USDC balance in human-readable format (with 6 decimals)
        """
        # Check cache first
        if use_cache and address in self._balance_cache:
            cached_balance, timestamp = self._balance_cache[address]
            if time.time() - timestamp < self._cache_ttl:
                logger.debug(f"Using cached balance for {address}: ${cached_balance:.6f}")
                return cached_balance
        
        try:
            # Ensure we're connected
            if not self.w3 or not self.w3.is_connected():
                self._connect()
            
            # Create contract instance
            usdc_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(USDC_ADDRESS),
                abi=ERC20_ABI
            )
            
            # Get balance (USDC has 6 decimals)
            balance_wei = usdc_contract.functions.balanceOf(
                Web3.to_checksum_address(address)
            ).call()
            
            # Convert to human readable
            balance = float(balance_wei) / 1e6
            
            # Cache the result
            self._balance_cache[address] = (balance, time.time())

            return balance
            
        except Exception as e:
            logger.error(f"Error fetching USDC balance for {address}: {e}")
            # Return cached value if available, even if expired
            if address in self._balance_cache:
                cached_balance, _ = self._balance_cache[address]
                logger.warning(f"Using expired cached balance: ${cached_balance:.6f}")
                return cached_balance
            raise
    
    async def get_eth_balance(self, address: str) -> float:
        """
        Get ETH balance for an address.
        
        Args:
            address: Wallet address to check
            
        Returns:
            ETH balance in human-readable format
        """
        try:
            # Ensure we're connected
            if not self.w3 or not self.w3.is_connected():
                self._connect()
            
            # Get balance in wei
            balance_wei = self.w3.eth.get_balance(Web3.to_checksum_address(address))
            
            # Convert to ETH
            balance = float(balance_wei) / 1e18

            return balance
            
        except Exception as e:
            logger.error(f"Error fetching ETH balance for {address}: {e}")
            raise
    
    def clear_cache(self, address: Optional[str] = None):
        """
        Clear balance cache.
        
        Args:
            address: Specific address to clear, or None to clear all
        """
        if address:
            self._balance_cache.pop(address, None)
            logger.debug(f"Cleared cache for {address}")
        else:
            self._balance_cache.clear()
            logger.debug("Cleared all balance cache")


# Singleton instance
blockchain_service = BlockchainService()