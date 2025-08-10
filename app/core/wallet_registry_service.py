"""Service for managing wallet registry operations."""

import asyncio
from typing import Dict, List, Optional, Any, Tuple
from web3 import Web3
from web3.contract import Contract
from eth_account import Account
from eth_account.signers.local import LocalAccount

from app.core.config import settings
from app.core.cache import cache_manager
from app.core.logger import logger


class WalletRegistryService:
    """Service for interacting with the Wallet Registry smart contract."""
    
    # Contract ABI
    WALLET_REGISTRY_ABI = [
        {"inputs":[],"stateMutability":"nonpayable","type":"constructor"},
        {"inputs":[],"name":"AlreadyRegistered","type":"error"},
        {"inputs":[],"name":"ArrayTooLarge","type":"error"},
        {"inputs":[],"name":"EmptyArray","type":"error"},
        {"inputs":[],"name":"InvalidAddress","type":"error"},
        {"inputs":[],"name":"NotRegistered","type":"error"},
        {"inputs":[{"internalType":"address","name":"owner","type":"address"}],"name":"OwnableInvalidOwner","type":"error"},
        {"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"OwnableUnauthorizedAccount","type":"error"},
        {"inputs":[],"name":"Unauthorized","type":"error"},
        {"anonymous":False,"inputs":[{"indexed":False,"internalType":"uint256","name":"processed","type":"uint256"},{"indexed":False,"internalType":"uint256","name":"skipped","type":"uint256"}],"name":"BatchOperationCompleted","type":"event"},
        {"anonymous":False,"inputs":[{"indexed":True,"internalType":"address","name":"operator","type":"address"},{"indexed":False,"internalType":"bool","name":"status","type":"bool"}],"name":"OperatorSet","type":"event"},
        {"anonymous":False,"inputs":[{"indexed":True,"internalType":"address","name":"previousOwner","type":"address"},{"indexed":True,"internalType":"address","name":"newOwner","type":"address"}],"name":"OwnershipTransferred","type":"event"},
        {"anonymous":False,"inputs":[{"indexed":True,"internalType":"address","name":"wallet","type":"address"},{"indexed":True,"internalType":"address","name":"registeredBy","type":"address"}],"name":"WalletRegistered","type":"event"},
        {"anonymous":False,"inputs":[{"indexed":True,"internalType":"address","name":"wallet","type":"address"},{"indexed":True,"internalType":"address","name":"removedBy","type":"address"}],"name":"WalletRemoved","type":"event"},
        {"inputs":[{"internalType":"address[]","name":"wallets","type":"address[]"}],"name":"areWalletsRegistered","outputs":[{"internalType":"bool[]","name":"statuses","type":"bool[]"}],"stateMutability":"view","type":"function"},
        {"inputs":[],"name":"getRegistryStats","outputs":[{"internalType":"uint256","name":"walletCount","type":"uint256"},{"internalType":"uint256","name":"operatorCount","type":"uint256"}],"stateMutability":"view","type":"function"},
        {"inputs":[{"internalType":"address","name":"operator","type":"address"}],"name":"isAuthorizedOperator","outputs":[{"internalType":"bool","name":"authorized","type":"bool"}],"stateMutability":"view","type":"function"},
        {"inputs":[{"internalType":"address","name":"","type":"address"}],"name":"isOperator","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},
        {"inputs":[{"internalType":"address","name":"wallet","type":"address"}],"name":"isRegisteredWallet","outputs":[{"internalType":"bool","name":"registered","type":"bool"}],"stateMutability":"view","type":"function"},
        {"inputs":[{"internalType":"address","name":"","type":"address"}],"name":"isWallet","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},
        {"inputs":[],"name":"owner","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},
        {"inputs":[{"internalType":"address","name":"wallet","type":"address"}],"name":"registerWallet","outputs":[],"stateMutability":"nonpayable","type":"function"},
        {"inputs":[{"internalType":"address[]","name":"wallets","type":"address[]"}],"name":"registerWalletsBatch","outputs":[],"stateMutability":"nonpayable","type":"function"},
        {"inputs":[{"internalType":"address","name":"wallet","type":"address"}],"name":"removeWallet","outputs":[],"stateMutability":"nonpayable","type":"function"},
        {"inputs":[{"internalType":"address[]","name":"wallets","type":"address[]"}],"name":"removeWalletsBatch","outputs":[],"stateMutability":"nonpayable","type":"function"},
        {"inputs":[],"name":"renounceOwnership","outputs":[],"stateMutability":"nonpayable","type":"function"},
        {"inputs":[{"internalType":"address","name":"operator","type":"address"},{"internalType":"bool","name":"status","type":"bool"}],"name":"setOperator","outputs":[],"stateMutability":"nonpayable","type":"function"},
        {"inputs":[{"internalType":"address[]","name":"operators","type":"address[]"},{"internalType":"bool","name":"status","type":"bool"}],"name":"setOperatorsBatch","outputs":[],"stateMutability":"nonpayable","type":"function"},
        {"inputs":[],"name":"totalOperators","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
        {"inputs":[],"name":"totalWallets","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
        {"inputs":[{"internalType":"address","name":"newOwner","type":"address"}],"name":"transferOwnership","outputs":[],"stateMutability":"nonpayable","type":"function"}
    ]
    
    def __init__(self):
        """Initialize the WalletRegistryService."""
        self._w3: Optional[Web3] = None
        self._contract: Optional[Contract] = None
        self._account: Optional[LocalAccount] = None
        
    def _get_w3(self) -> Web3:
        """Get or create Web3 instance."""
        if self._w3 is None:
            self._w3 = Web3(Web3.HTTPProvider(settings.rpc_url))
            if not self._w3.is_connected():
                raise Exception(f"Failed to connect to RPC endpoint: {settings.rpc_url}")
        return self._w3
    
    def _get_account(self) -> LocalAccount:
        """Get the operator account from private key."""
        if self._account is None:
            if not settings.wallet_registry_operator_private_key:
                raise ValueError("WALLET_REGISTRY_OPERATOR_PRIVATE_KEY not configured")
            self._account = Account.from_key(settings.wallet_registry_operator_private_key)
            logger.info(f"Using operator account: {self._account.address}")
        return self._account
    
    def _get_contract(self) -> Contract:
        """Get or create contract instance."""
        if self._contract is None:
            w3 = self._get_w3()
            self._contract = w3.eth.contract(
                address=Web3.to_checksum_address(settings.wallet_registry_contract_address),
                abi=self.WALLET_REGISTRY_ABI
            )
        return self._contract
    
    def _normalize_address(self, address: str) -> str:
        """Normalize and validate an Ethereum address."""
        try:
            return Web3.to_checksum_address(address)
        except Exception as e:
            logger.error(f"Invalid address {address}: {e}")
            raise ValueError(f"Invalid Ethereum address: {address}")
    
    def _normalize_addresses(self, addresses: List[str]) -> List[str]:
        """Normalize and validate multiple Ethereum addresses."""
        return [self._normalize_address(addr) for addr in addresses]
    
    async def _estimate_gas(self, transaction: Dict[str, Any]) -> int:
        """Estimate gas for a transaction with multiplier."""
        w3 = self._get_w3()
        try:
            estimated = await asyncio.to_thread(w3.eth.estimate_gas, transaction)
            gas_with_buffer = int(estimated * settings.gas_multiplier)
            logger.debug(f"Estimated gas: {estimated}, with buffer: {gas_with_buffer}")
            return gas_with_buffer
        except Exception as e:
            # Check if it's an Unauthorized error (0x3a81d6fc)
            error_msg = str(e)
            if '0x3a81d6fc' in error_msg:
                logger.error(f"Gas estimation failed - Operator not authorized: {self._get_account().address}")
                raise ValueError(f"Operator {self._get_account().address} is not authorized on the contract")
            logger.warning(f"Gas estimation failed, using default: {e}")
            # Return a reasonable default
            return 500000
    
    async def _get_gas_price(self) -> int:
        """Get current gas price with max limit."""
        w3 = self._get_w3()
        try:
            gas_price = await asyncio.to_thread(lambda: w3.eth.gas_price)
            max_gas_price = Web3.to_wei(settings.max_gas_price_gwei, 'gwei')
            
            if gas_price > max_gas_price:
                logger.warning(f"Gas price {gas_price} exceeds max {max_gas_price}, using max")
                return max_gas_price
            
            return gas_price
        except Exception as e:
            logger.error(f"Failed to get gas price: {e}")
            # Return a reasonable default
            return Web3.to_wei(10, 'gwei')
    
    async def _send_transaction(self, func, *args, max_retries: int = None) -> Dict[str, Any]:
        """Send a transaction with retry logic."""
        w3 = self._get_w3()
        account = self._get_account()
        
        if max_retries is None:
            max_retries = settings.max_retry_attempts
        
        for attempt in range(max_retries):
            try:
                # Get fresh nonce for each attempt (including retries)
                nonce = await asyncio.to_thread(
                    w3.eth.get_transaction_count,
                    account.address,
                    'pending'  # Include pending transactions
                )
                
                # Prepare transaction data first
                tx_data = func(*args)._encode_transaction_data()
                
                # Estimate gas
                gas_estimate = await self._estimate_gas({
                    'from': account.address,
                    'to': self._get_contract().address,
                    'data': tx_data
                })
                
                # Build transaction
                transaction = await asyncio.to_thread(
                    func(*args).build_transaction,
                    {
                        'from': account.address,
                        'nonce': nonce,
                        'gas': gas_estimate,
                        'gasPrice': await self._get_gas_price(),
                        'chainId': 8453  # Base mainnet
                    }
                )
                
                # Sign transaction
                signed_txn = account.sign_transaction(transaction)
                
                # Send transaction
                tx_hash = await asyncio.to_thread(
                    w3.eth.send_raw_transaction,
                    signed_txn.raw_transaction
                )
                
                logger.info(f"Transaction sent: {tx_hash.hex()}")
                
                # Wait for receipt with timeout
                receipt = await asyncio.wait_for(
                    asyncio.to_thread(
                        w3.eth.wait_for_transaction_receipt,
                        tx_hash,
                        timeout=settings.transaction_timeout
                    ),
                    timeout=settings.transaction_timeout
                )
                
                if receipt['status'] == 1:
                    logger.info(f"Transaction successful: {tx_hash.hex()}")
                    return {
                        'success': True,
                        'tx_hash': tx_hash.hex(),
                        'gas_used': receipt['gasUsed'],
                        'block_number': receipt['blockNumber']
                    }
                else:
                    logger.error(f"Transaction failed: {tx_hash.hex()}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    return {
                        'success': False,
                        'tx_hash': tx_hash.hex(),
                        'error': 'Transaction reverted'
                    }
                    
            except asyncio.TimeoutError:
                logger.error(f"Transaction timeout on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return {
                    'success': False,
                    'error': 'Transaction timeout'
                }
                
            except Exception as e:
                error_msg = str(e)
                # Check for specific errors
                if 'nonce too low' in error_msg:
                    logger.warning(f"Nonce too low on attempt {attempt + 1}, retrying with fresh nonce")
                elif '0x3a81d6fc' in error_msg or 'Unauthorized' in error_msg:
                    logger.error(f"Operator not authorized: {account.address}")
                    return {
                        'success': False,
                        'error': f'Operator {account.address} is not authorized on the contract'
                    }
                else:
                    logger.error(f"Transaction error on attempt {attempt + 1}: {e}")
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return {
                    'success': False,
                    'error': str(e)
                }
        
        return {
            'success': False,
            'error': f'Failed after {max_retries} attempts'
        }
    
    async def register_wallet(self, address: str) -> Dict[str, Any]:
        """Register a single wallet address."""
        try:
            normalized_address = self._normalize_address(address)
            
            # Check if already registered
            is_registered = await self.is_wallet_registered(normalized_address)
            if is_registered:
                logger.warning(f"Wallet already registered: {normalized_address}")
                return {
                    'success': False,
                    'error': 'Wallet already registered',
                    'address': normalized_address
                }
            
            contract = self._get_contract()
            result = await self._send_transaction(
                contract.functions.registerWallet,
                normalized_address
            )
            
            if result['success']:
                # Clear cache for this wallet
                cache_key = f"wallet_status:{normalized_address.lower()}"
                await cache_manager.cache.delete(cache_key)
                
            result['address'] = normalized_address
            return result
            
        except Exception as e:
            logger.error(f"Failed to register wallet {address}: {e}")
            return {
                'success': False,
                'error': str(e),
                'address': address
            }
    
    async def register_wallets_batch(self, addresses: List[str]) -> Dict[str, Any]:
        """Register multiple wallet addresses in batch."""
        try:
            if not addresses:
                return {
                    'success': False,
                    'error': 'Empty address list'
                }
            
            if len(addresses) > 100:
                return {
                    'success': False,
                    'error': 'Batch size exceeds maximum of 100 addresses'
                }
            
            normalized_addresses = self._normalize_addresses(addresses)
            
            # Check which are already registered
            statuses = await self.check_wallets_batch(normalized_addresses)
            already_registered = [
                addr for addr, registered in zip(normalized_addresses, statuses)
                if registered
            ]
            
            to_register = [
                addr for addr, registered in zip(normalized_addresses, statuses)
                if not registered
            ]
            
            if not to_register:
                return {
                    'success': True,
                    'registered': [],
                    'already_registered': already_registered,
                    'message': 'All wallets already registered'
                }
            
            contract = self._get_contract()
            result = await self._send_transaction(
                contract.functions.registerWalletsBatch,
                to_register
            )
            
            if result['success']:
                # Clear cache for registered wallets
                for addr in to_register:
                    cache_key = f"wallet_status:{addr.lower()}"
                    await cache_manager.cache.delete(cache_key)
                
                return {
                    'success': True,
                    'tx_hash': result['tx_hash'],
                    'registered': to_register,
                    'already_registered': already_registered,
                    'gas_used': result.get('gas_used')
                }
            else:
                return {
                    'success': False,
                    'error': result.get('error', 'Transaction failed'),
                    'attempted': to_register,
                    'already_registered': already_registered
                }
                
        except Exception as e:
            logger.error(f"Failed to register wallets batch: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def remove_wallet(self, address: str) -> Dict[str, Any]:
        """Remove a single wallet from registry."""
        try:
            normalized_address = self._normalize_address(address)
            
            # Check if registered
            is_registered = await self.is_wallet_registered(normalized_address)
            if not is_registered:
                logger.warning(f"Wallet not registered: {normalized_address}")
                return {
                    'success': False,
                    'error': 'Wallet not registered',
                    'address': normalized_address
                }
            
            contract = self._get_contract()
            result = await self._send_transaction(
                contract.functions.removeWallet,
                normalized_address
            )
            
            if result['success']:
                # Clear cache for this wallet
                cache_key = f"wallet_status:{normalized_address.lower()}"
                await cache_manager.cache.delete(cache_key)
                
            result['address'] = normalized_address
            return result
            
        except Exception as e:
            logger.error(f"Failed to remove wallet {address}: {e}")
            return {
                'success': False,
                'error': str(e),
                'address': address
            }
    
    async def remove_wallets_batch(self, addresses: List[str]) -> Dict[str, Any]:
        """Remove multiple wallets from registry in batch."""
        try:
            if not addresses:
                return {
                    'success': False,
                    'error': 'Empty address list'
                }
            
            if len(addresses) > 100:
                return {
                    'success': False,
                    'error': 'Batch size exceeds maximum of 100 addresses'
                }
            
            normalized_addresses = self._normalize_addresses(addresses)
            
            # Check which are registered
            statuses = await self.check_wallets_batch(normalized_addresses)
            not_registered = [
                addr for addr, registered in zip(normalized_addresses, statuses)
                if not registered
            ]
            
            to_remove = [
                addr for addr, registered in zip(normalized_addresses, statuses)
                if registered
            ]
            
            if not to_remove:
                return {
                    'success': True,
                    'removed': [],
                    'not_registered': not_registered,
                    'message': 'No wallets to remove'
                }
            
            contract = self._get_contract()
            result = await self._send_transaction(
                contract.functions.removeWalletsBatch,
                to_remove
            )
            
            if result['success']:
                # Clear cache for removed wallets
                for addr in to_remove:
                    cache_key = f"wallet_status:{addr.lower()}"
                    await cache_manager.cache.delete(cache_key)
                
                return {
                    'success': True,
                    'tx_hash': result['tx_hash'],
                    'removed': to_remove,
                    'not_registered': not_registered,
                    'gas_used': result.get('gas_used')
                }
            else:
                return {
                    'success': False,
                    'error': result.get('error', 'Transaction failed'),
                    'attempted': to_remove,
                    'not_registered': not_registered
                }
                
        except Exception as e:
            logger.error(f"Failed to remove wallets batch: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def is_wallet_registered(self, address: str) -> bool:
        """Check if a wallet is registered."""
        try:
            normalized_address = self._normalize_address(address)
            
            # Check cache first
            cache_key = f"wallet_status:{normalized_address.lower()}"
            cached = await cache_manager.get_custom(cache_key)
            if cached is not None:
                return cached
            
            # Query contract
            w3 = self._get_w3()
            contract = self._get_contract()
            
            is_registered = await asyncio.to_thread(
                contract.functions.isRegisteredWallet(normalized_address).call
            )
            
            # Cache result for 5 minutes
            await cache_manager.set_custom(cache_key, is_registered, ttl=300)
            
            return is_registered
            
        except Exception as e:
            logger.error(f"Failed to check wallet status {address}: {e}")
            raise
    
    async def check_wallets_batch(self, addresses: List[str]) -> List[bool]:
        """Check registration status for multiple wallets."""
        try:
            if not addresses:
                return []
            
            normalized_addresses = self._normalize_addresses(addresses)
            
            # Check cache for all addresses
            cache_results = {}
            uncached_addresses = []
            
            for addr in normalized_addresses:
                cache_key = f"wallet_status:{addr.lower()}"
                cached = await cache_manager.get_custom(cache_key)
                if cached is not None:
                    cache_results[addr] = cached
                else:
                    uncached_addresses.append(addr)
            
            # Query contract for uncached addresses
            if uncached_addresses:
                w3 = self._get_w3()
                contract = self._get_contract()
                
                statuses = await asyncio.to_thread(
                    contract.functions.areWalletsRegistered(uncached_addresses).call
                )
                
                # Cache results
                for addr, status in zip(uncached_addresses, statuses):
                    cache_key = f"wallet_status:{addr.lower()}"
                    await cache_manager.set_custom(cache_key, status, ttl=300)
                    cache_results[addr] = status
            
            # Return results in original order
            return [cache_results[addr] for addr in normalized_addresses]
            
        except Exception as e:
            logger.error(f"Failed to check wallets batch: {e}")
            raise
    
    async def is_operator_authorized(self, address: str = None) -> bool:
        """Check if an operator is authorized."""
        try:
            if address is None:
                address = self._get_account().address
            
            normalized_address = self._normalize_address(address)
            
            # Check cache first
            cache_key = f"operator_status:{normalized_address.lower()}"
            cached = await cache_manager.get_custom(cache_key)
            if cached is not None:
                return cached
            
            # Query contract
            w3 = self._get_w3()
            contract = self._get_contract()
            
            is_authorized = await asyncio.to_thread(
                contract.functions.isAuthorizedOperator(normalized_address).call
            )
            
            # Cache result for 5 minutes
            await cache_manager.set_custom(cache_key, is_authorized, ttl=300)
            
            logger.info(f"Operator {normalized_address} authorization status: {is_authorized}")
            return is_authorized
            
        except Exception as e:
            logger.error(f"Failed to check operator status {address}: {e}")
            raise
    
    async def get_registry_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        try:
            # Check cache first
            cache_key = "wallet_registry:stats"
            cached = await cache_manager.get_custom(cache_key)
            if cached is not None:
                return cached
            
            # Query contract
            w3 = self._get_w3()
            contract = self._get_contract()
            
            wallet_count, operator_count = await asyncio.to_thread(
                contract.functions.getRegistryStats().call
            )
            
            stats = {
                'wallet_count': wallet_count,
                'operator_count': operator_count,
                'contract_address': settings.wallet_registry_contract_address,
                'operator_address': settings.wallet_registry_operator_address
            }
            
            # Cache for 1 minute
            await cache_manager.set_custom(cache_key, stats, ttl=60)
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get registry stats: {e}")
            raise
    
    async def is_authorized_operator(self) -> bool:
        """Check if the configured operator is authorized."""
        try:
            account = self._get_account()
            w3 = self._get_w3()
            contract = self._get_contract()
            
            is_authorized = await asyncio.to_thread(
                contract.functions.isAuthorizedOperator(account.address).call
            )
            
            return is_authorized
            
        except Exception as e:
            logger.error(f"Failed to check operator authorization: {e}")
            return False


# Create a singleton instance
wallet_registry_service = WalletRegistryService()