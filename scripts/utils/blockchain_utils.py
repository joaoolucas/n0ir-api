#!/usr/bin/env python3
"""Blockchain utilities for interacting with on-chain data."""

import asyncio
import argparse
import sys
import json
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pathlib import Path
from web3 import Web3
from eth_account import Account

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.utils.config import (
    get_rpc_url,
    LIQUIDITY_MANAGER_ADDRESS,
    SUGAR_CONTRACT_ADDRESS,
    USDC_ADDRESS,
    WETH_ADDRESS,
    AERO_TOKEN_ADDRESS,
    BASE_CHAIN_ID
)
from app.core.logger import logger


class BlockchainUtils:
    """Utility class for blockchain operations."""
    
    def __init__(self):
        """Initialize Web3 connection."""
        self.w3 = Web3(Web3.HTTPProvider(get_rpc_url()))
        if not self.w3.is_connected():
            raise ConnectionError("Failed to connect to RPC endpoint")
            
        # Load common ABIs
        self.erc20_abi = self._load_erc20_abi()
        self.liquidity_manager_abi = self._load_liquidity_manager_abi()
        
    def _load_erc20_abi(self) -> List[Dict]:
        """Load minimal ERC20 ABI."""
        return [
            {
                "inputs": [{"name": "account", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "symbol",
                "outputs": [{"name": "", "type": "string"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
        
    def _load_liquidity_manager_abi(self) -> List[Dict]:
        """Load minimal Liquidity Manager ABI."""
        return [
            {
                "inputs": [{"name": "tokenId", "type": "uint256"}],
                "name": "positions",
                "outputs": [
                    {"name": "nonce", "type": "uint96"},
                    {"name": "operator", "type": "address"},
                    {"name": "token0", "type": "address"},
                    {"name": "token1", "type": "address"},
                    {"name": "tickSpacing", "type": "int24"},
                    {"name": "tickLower", "type": "int24"},
                    {"name": "tickUpper", "type": "int24"},
                    {"name": "liquidity", "type": "uint128"},
                    {"name": "feeGrowthInside0LastX128", "type": "uint256"},
                    {"name": "feeGrowthInside1LastX128", "type": "uint256"},
                    {"name": "tokensOwed0", "type": "uint128"},
                    {"name": "tokensOwed1", "type": "uint128"}
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [{"name": "owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [
                    {"name": "owner", "type": "address"},
                    {"name": "index", "type": "uint256"}
                ],
                "name": "tokenOfOwnerByIndex",
                "outputs": [{"name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
        
    async def check_balance(self, address: str, token: Optional[str] = None):
        """Check token balance for an address.
        
        Args:
            address: Ethereum address to check
            token: Token address (defaults to USDC)
        """
        if not Web3.is_checksum_address(address):
            address = Web3.to_checksum_address(address)
            
        # Default to USDC
        if not token:
            token = USDC_ADDRESS
            
        # Get native ETH balance
        eth_balance = self.w3.eth.get_balance(address)
        eth_balance_ether = Web3.from_wei(eth_balance, 'ether')
        print(f"\n{'='*60}")
        print(f"Address: {address}")
        print(f"ETH Balance: {eth_balance_ether:.6f} ETH")
        
        # Check token balances
        tokens = {
            'USDC': USDC_ADDRESS,
            'WETH': WETH_ADDRESS,
            'AERO': AERO_TOKEN_ADDRESS
        }
        
        if token not in tokens.values():
            tokens['Custom'] = token
            
        for name, token_addr in tokens.items():
            try:
                contract = self.w3.eth.contract(
                    address=Web3.to_checksum_address(token_addr),
                    abi=self.erc20_abi
                )
                
                balance = contract.functions.balanceOf(address).call()
                decimals = contract.functions.decimals().call()
                symbol = contract.functions.symbol().call()
                
                adjusted_balance = balance / (10 ** decimals)
                
                if adjusted_balance > 0:
                    print(f"{symbol}: {adjusted_balance:,.4f}")
                    
            except Exception as e:
                logger.error(f"Error checking {name}: {e}")
                
    async def check_position(self, token_id: int):
        """Check position details on-chain.
        
        Args:
            token_id: NFT position token ID
        """
        try:
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(LIQUIDITY_MANAGER_ADDRESS),
                abi=self.liquidity_manager_abi
            )
            
            position = contract.functions.positions(token_id).call()
            
            print(f"\n{'='*60}")
            print(f"Position #{token_id}")
            print(f"  Token0: {position[2]}")
            print(f"  Token1: {position[3]}")
            print(f"  Tick Spacing: {position[4]}")
            print(f"  Tick Lower: {position[5]}")
            print(f"  Tick Upper: {position[6]}")
            print(f"  Liquidity: {position[7]}")
            print(f"  Tokens Owed 0: {position[10]}")
            print(f"  Tokens Owed 1: {position[11]}")
            
        except Exception as e:
            logger.error(f"Error checking position: {e}")
            
    async def find_user_positions(self, user_address: str):
        """Find all positions owned by a user.
        
        Args:
            user_address: User's Ethereum address
        """
        if not Web3.is_checksum_address(user_address):
            user_address = Web3.to_checksum_address(user_address)
            
        try:
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(LIQUIDITY_MANAGER_ADDRESS),
                abi=self.liquidity_manager_abi
            )
            
            # Get number of positions
            balance = contract.functions.balanceOf(user_address).call()
            
            print(f"\n{'='*60}")
            print(f"User {user_address} has {balance} positions")
            
            if balance > 0:
                positions = []
                for i in range(min(balance, 10)):  # Limit to 10 for display
                    token_id = contract.functions.tokenOfOwnerByIndex(
                        user_address, i
                    ).call()
                    positions.append(token_id)
                    
                print(f"Position Token IDs: {positions}")
                
                # Show details for first position
                if positions:
                    await self.check_position(positions[0])
                    
        except Exception as e:
            logger.error(f"Error finding positions: {e}")
            
    async def get_transaction(self, tx_hash: str):
        """Get transaction details.
        
        Args:
            tx_hash: Transaction hash
        """
        try:
            tx = self.w3.eth.get_transaction(tx_hash)
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            
            print(f"\n{'='*60}")
            print(f"Transaction: {tx_hash}")
            print(f"  From: {tx['from']}")
            print(f"  To: {tx['to']}")
            print(f"  Value: {Web3.from_wei(tx['value'], 'ether')} ETH")
            print(f"  Gas Used: {receipt['gasUsed']}")
            print(f"  Status: {'Success' if receipt['status'] == 1 else 'Failed'}")
            print(f"  Block: {tx['blockNumber']}")
            
            # Decode logs if possible
            if receipt['logs']:
                print(f"\n  Event Logs ({len(receipt['logs'])} total):")
                for i, log in enumerate(receipt['logs'][:5]):  # Show first 5
                    print(f"    Log {i}: {log['address'][:10]}... Topic: {log['topics'][0].hex()[:16]}...")
                    
        except Exception as e:
            logger.error(f"Error getting transaction: {e}")
            
    async def monitor_blocks(self, duration: int = 60):
        """Monitor new blocks for a duration.
        
        Args:
            duration: Monitoring duration in seconds
        """
        print(f"Monitoring blocks for {duration} seconds...")
        
        start_block = self.w3.eth.block_number
        end_time = asyncio.get_event_loop().time() + duration
        
        while asyncio.get_event_loop().time() < end_time:
            current_block = self.w3.eth.block_number
            
            if current_block > start_block:
                block = self.w3.eth.get_block(current_block)
                print(f"Block #{current_block}: {len(block['transactions'])} txs, "
                      f"Gas: {block['gasUsed']:,}")
                start_block = current_block
                
            await asyncio.sleep(2)
            
        print(f"Monitoring complete")
        
    async def estimate_gas(self, from_addr: str, to_addr: str, data: str = '0x'):
        """Estimate gas for a transaction.
        
        Args:
            from_addr: From address
            to_addr: To address
            data: Transaction data
        """
        try:
            gas_estimate = self.w3.eth.estimate_gas({
                'from': Web3.to_checksum_address(from_addr),
                'to': Web3.to_checksum_address(to_addr),
                'data': data
            })
            
            gas_price = self.w3.eth.gas_price
            
            print(f"\n{'='*60}")
            print(f"Gas Estimation:")
            print(f"  Estimated Gas: {gas_estimate:,}")
            print(f"  Gas Price: {Web3.from_wei(gas_price, 'gwei'):.2f} Gwei")
            print(f"  Estimated Cost: {Web3.from_wei(gas_estimate * gas_price, 'ether'):.6f} ETH")
            
        except Exception as e:
            logger.error(f"Error estimating gas: {e}")


async def main():
    """Main entry point for blockchain utilities."""
    parser = argparse.ArgumentParser(description='Blockchain utilities')
    parser.add_argument('command', choices=[
        'balance',
        'position',
        'find-positions',
        'transaction',
        'monitor',
        'estimate-gas'
    ], help='Command to execute')
    
    parser.add_argument('--address', type=str, help='Ethereum address')
    parser.add_argument('--token', type=str, help='Token address')
    parser.add_argument('--token-id', type=int, help='Position token ID')
    parser.add_argument('--tx-hash', type=str, help='Transaction hash')
    parser.add_argument('--duration', type=int, default=60, help='Monitoring duration')
    parser.add_argument('--from', dest='from_addr', type=str, help='From address')
    parser.add_argument('--to', dest='to_addr', type=str, help='To address')
    parser.add_argument('--data', type=str, default='0x', help='Transaction data')
    
    args = parser.parse_args()
    
    utils = BlockchainUtils()
    
    try:
        if args.command == 'balance':
            if not args.address:
                parser.error('--address required for balance check')
            await utils.check_balance(args.address, args.token)
            
        elif args.command == 'position':
            if not args.token_id:
                parser.error('--token-id required for position check')
            await utils.check_position(args.token_id)
            
        elif args.command == 'find-positions':
            if not args.address:
                parser.error('--address required for finding positions')
            await utils.find_user_positions(args.address)
            
        elif args.command == 'transaction':
            if not args.tx_hash:
                parser.error('--tx-hash required for transaction check')
            await utils.get_transaction(args.tx_hash)
            
        elif args.command == 'monitor':
            await utils.monitor_blocks(args.duration)
            
        elif args.command == 'estimate-gas':
            if not args.from_addr or not args.to_addr:
                parser.error('--from and --to required for gas estimation')
            await utils.estimate_gas(args.from_addr, args.to_addr, args.data)
            
    except Exception as e:
        logger.error(f"Error executing command: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())