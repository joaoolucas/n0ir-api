"""Blockchain service for direct on-chain queries."""

import os
from decimal import Decimal
from typing import Optional
import asyncio
from web3 import Web3
from loguru import logger

# Base RPC URL from environment or default
BASE_RPC_URL = os.getenv("BASE_RPC_URL", os.getenv("RPC_URL", ""))

# USDC contract on Base
USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
USDC_DECIMALS = 6

class BlockchainService:
    """Service for querying blockchain data directly."""
    
    def __init__(self):
        self.w3 = None
        if BASE_RPC_URL:
            try:
                self.w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
                if self.w3.is_connected():
                    logger.info("Connected to Base blockchain")
                else:
                    logger.warning("Failed to connect to Base blockchain")
                    self.w3 = None
            except Exception as e:
                logger.error(f"Error initializing Web3: {e}")
                self.w3 = None
    
    async def get_usdc_balance(self, wallet_address: str) -> Optional[Decimal]:
        """Get USDC balance for a wallet address.
        
        Args:
            wallet_address: The wallet address to check
            
        Returns:
            USDC balance or None if query fails
        """
        if not self.w3:
            logger.warning("Web3 not initialized, cannot query balance")
            return None
            
        try:
            # USDC contract ABI for balanceOf
            abi = [{
                "inputs": [{"name": "account", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "", "type": "uint256"}],
                "type": "function",
                "stateMutability": "view"
            }]
            
            # Create contract instance
            usdc_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(USDC_ADDRESS), 
                abi=abi
            )
            
            # Get balance (run in thread pool to avoid blocking)
            balance_wei = await asyncio.to_thread(
                usdc_contract.functions.balanceOf(
                    Web3.to_checksum_address(wallet_address)
                ).call
            )
            
            # Convert to USDC
            balance_usdc = Decimal(balance_wei) / Decimal(10 ** USDC_DECIMALS)
            
            logger.debug(f"Blockchain balance for {wallet_address}: {balance_usdc:.6f} USDC")
            return balance_usdc
            
        except Exception as e:
            logger.error(f"Error getting USDC balance for {wallet_address}: {e}")
            return None

# Singleton instance
blockchain_service = BlockchainService()