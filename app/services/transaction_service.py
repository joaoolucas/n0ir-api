from typing import Optional, Dict, Any
import aiohttp
from app.core.config import settings
from app.core.cache import cache_manager
import logging

logger = logging.getLogger(__name__)


class TransactionService:
    def __init__(self):
        self.etherscan_base_url = "https://api.etherscan.io/v2/api"
        self.chain_id = settings.base_chain_id
        self.api_key = settings.etherscan_api_key
    
    async def get_transaction_status(self, tx_hash: str) -> Dict[str, Any]:
        """
        Get transaction receipt status from Etherscan API.
        
        Args:
            tx_hash: The transaction hash to check
            
        Returns:
            Dictionary containing transaction status information
        """
        # Check cache first
        cache_key = f"tx_status:{tx_hash}"
        cached_result = await cache_manager.get_custom(cache_key)
        if cached_result:
            return cached_result
        
        if not self.api_key:
            raise ValueError("Etherscan API key is not configured")
        
        params = {
            "chainid": self.chain_id,
            "module": "transaction",
            "action": "gettxreceiptstatus",
            "txhash": tx_hash,
            "apikey": self.api_key
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.etherscan_base_url, params=params) as response:
                    # Check if response is JSON
                    content_type = response.headers.get('Content-Type', '')
                    if 'application/json' not in content_type:
                        text = await response.text()
                        logger.error(f"Non-JSON response from Basescan: {text[:200]}")
                        raise Exception(f"Invalid response from Basescan API (status: {response.status})")
                    
                    data = await response.json()
                    
                    if data.get("status") == "1" and data.get("result"):
                        result = data["result"]
                        formatted_result = {
                            "tx_hash": tx_hash,
                            "status": result.get("status", "0"),  # 0 = Failed, 1 = Success
                            "status_text": "Success" if result.get("status") == "1" else "Failed",
                            "message": data.get("message", "OK"),
                            "raw_result": result
                        }
                        
                        # Cache successful results for 60 seconds
                        await cache_manager.set_custom(cache_key, formatted_result, ttl=60)
                        return formatted_result
                    else:
                        error_message = data.get("message", "Unknown error")
                        logger.error(f"Etherscan API error for tx {tx_hash}: {error_message}")
                        return {
                            "tx_hash": tx_hash,
                            "status": None,
                            "status_text": "Unknown",
                            "error": error_message,
                            "message": data.get("message", "Error fetching transaction status")
                        }
                        
        except aiohttp.ClientError as e:
            logger.error(f"HTTP error while fetching tx status for {tx_hash}: {str(e)}")
            raise Exception(f"Failed to fetch transaction status: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error while fetching tx status for {tx_hash}: {str(e)}")
            raise Exception(f"Unexpected error: {str(e)}")
    
    async def get_transaction_details(self, tx_hash: str) -> Dict[str, Any]:
        """
        Get full transaction details from Etherscan API.
        
        Args:
            tx_hash: The transaction hash to check
            
        Returns:
            Dictionary containing full transaction details
        """
        if not self.api_key:
            raise ValueError("Etherscan API key is not configured")
        
        params = {
            "chainid": self.chain_id,
            "module": "proxy",
            "action": "eth_getTransactionByHash",
            "txhash": tx_hash,
            "apikey": self.api_key
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.etherscan_base_url, params=params) as response:
                    # Check if response is JSON
                    content_type = response.headers.get('Content-Type', '')
                    if 'application/json' not in content_type:
                        text = await response.text()
                        logger.error(f"Non-JSON response from Basescan: {text[:200]}")
                        raise Exception(f"Invalid response from Basescan API (status: {response.status})")
                    
                    data = await response.json()
                    
                    if data.get("result"):
                        return {
                            "tx_hash": tx_hash,
                            "details": data["result"],
                            "message": "OK"
                        }
                    else:
                        return {
                            "tx_hash": tx_hash,
                            "details": None,
                            "error": data.get("message", "Transaction not found")
                        }
                        
        except Exception as e:
            logger.error(f"Error fetching transaction details for {tx_hash}: {str(e)}")
            raise Exception(f"Failed to fetch transaction details: {str(e)}")


# Singleton instance
transaction_service = TransactionService()