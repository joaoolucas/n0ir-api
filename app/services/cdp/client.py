"""CDP SQL API client for blockchain data queries."""

import httpx
from typing import Dict, List, Optional, Any
from decimal import Decimal
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.services.cdp.models import CDPQueryResponse
from app.core.cache import cache_manager as cache
from app.core.config import settings
from loguru import logger


class CDPSQLClient:
    """Client for CDP SQL API with caching and retry logic."""
    
    BASE_URL = "https://api.cdp.coinbase.com/platform/v2"
    MAX_ROWS = 10000
    QUERY_TIMEOUT = 30
    
    def __init__(self):
        self.api_key = settings.cdp_client_api_key
        self.client = httpx.AsyncClient(timeout=35.0)
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError, CDPRateLimitError))
    )
    async def execute_query(
        self, 
        sql: str, 
        cache_key: Optional[str] = None, 
        cache_ttl: int = 300
    ) -> CDPQueryResponse:
        """Execute SQL query against CDP API with production-grade error handling.
        
        Args:
            sql: SQL query to execute
            cache_key: Optional cache key for storing results
            cache_ttl: Cache TTL in seconds (default: 5 minutes)
            
        Returns:
            CDPQueryResponse with query results
            
        Raises:
            CDPAPIError: For API-specific errors
            CDPRateLimitError: When rate limited
            CDPTimeoutError: On timeout
            CDPValidationError: For query validation errors
        """
        # Check cache first if key provided
        if cache_key:
            try:
                cached_result = await cache.get(cache_key)
                if cached_result:
                    logger.debug(f"Cache hit for key: {cache_key}")
                    return CDPQueryResponse(**cached_result)
            except Exception as e:
                # Log cache error but continue with query
                logger.warning(f"Cache retrieval error (non-fatal): {e}")
        
        # Validate API key presence
        if not self.api_key:
            raise CDPAuthenticationError("CDP API key not configured")
        
        # Prepare request
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {"sql": sql}
        
        try:
            response = await self.client.post(
                f"{self.BASE_URL}/data/query/run",
                headers=headers,
                json=payload
            )
            
            # Handle different response codes
            if response.status_code == 200:
                result_data = response.json()
                
                # Validate response structure
                if not isinstance(result_data, dict):
                    raise CDPValidationError(f"Invalid response format: expected dict, got {type(result_data)}")
                
                # Parse into model with validation
                try:
                    result = CDPQueryResponse(**result_data)
                except Exception as e:
                    raise CDPValidationError(f"Failed to parse response: {e}")
                
                # Cache successful result if key provided
                if cache_key and result.result:
                    try:
                        await cache.set(cache_key, result.model_dump(), ttl=cache_ttl)
                        logger.debug(f"Cached result for key: {cache_key} with TTL: {cache_ttl}s")
                    except Exception as e:
                        # Log cache error but don't fail the request
                        logger.warning(f"Failed to cache result (non-fatal): {e}")
                
                return result
                
            elif response.status_code == 429:
                # Rate limited - extract retry-after if available
                retry_after = response.headers.get('Retry-After', '60')
                logger.warning(f"Rate limited by CDP API, retry after {retry_after}s")
                raise CDPRateLimitError(f"Rate limited, retry after {retry_after}s")
                
            elif response.status_code == 400:
                # Query validation error
                try:
                    error_detail = response.json().get('error', response.text)
                except:
                    error_detail = response.text
                logger.error(f"Query validation error: {error_detail}")
                raise CDPValidationError(f"Invalid query: {error_detail}")
                
            elif response.status_code == 401:
                logger.error("Authentication failed - check CDP API key")
                raise CDPAuthenticationError("Invalid or expired CDP API key")
                
            elif response.status_code == 403:
                logger.error(f"Access denied to resource: {response.text}")
                raise CDPAuthorizationError(f"Access denied: {response.text}")
                
            elif 500 <= response.status_code < 600:
                logger.error(f"CDP API server error {response.status_code}: {response.text}")
                raise CDPServerError(f"Server error {response.status_code}")
                
            else:
                logger.error(f"Unexpected status {response.status_code}: {response.text}")
                raise CDPAPIError(f"Unexpected status {response.status_code}")
                
        except httpx.TimeoutException as e:
            logger.error(f"Query timeout after {self.QUERY_TIMEOUT}s: {str(e)}")
            raise CDPTimeoutError(f"Query timed out after {self.QUERY_TIMEOUT}s") from e
            
        except httpx.NetworkError as e:
            logger.error(f"Network error connecting to CDP API: {str(e)}")
            raise CDPNetworkError("Failed to connect to CDP API") from e
            
        except (CDPAPIError, CDPRateLimitError, CDPTimeoutError, CDPValidationError,
                CDPAuthenticationError, CDPAuthorizationError, CDPServerError, CDPNetworkError):
            # Re-raise our custom exceptions
            raise
            
        except Exception as e:
            logger.error(f"Unexpected error executing query: {str(e)}")
            raise CDPAPIError(f"Unexpected error: {str(e)}") from e
    
    async def paginated_query(
        self, 
        base_sql: str, 
        limit: int = MAX_ROWS
    ) -> List[Dict[str, Any]]:
        """Execute paginated queries for large result sets.
        
        Args:
            base_sql: Base SQL query (without LIMIT/OFFSET)
            limit: Maximum number of rows to retrieve
            
        Returns:
            List of all result rows
        """
        all_results = []
        offset = 0
        
        while True:
            # Add pagination to query
            paginated_sql = f"{base_sql} LIMIT {min(limit - len(all_results), self.MAX_ROWS)} OFFSET {offset}"
            
            result = await self.execute_query(paginated_sql)
            rows = result.result
            
            if not rows:
                break
            
            all_results.extend(rows)
            
            # Check if we've reached our limit or got fewer rows than max
            if len(all_results) >= limit or len(rows) < self.MAX_ROWS:
                break
            
            offset += self.MAX_ROWS
        
        return all_results[:limit]
    
    async def get_wallet_transactions(
        self,
        wallet_address: str,
        start_timestamp: Optional[str] = None,
        end_timestamp: Optional[str] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Get transactions for a specific wallet address.
        
        Args:
            wallet_address: Wallet address to query
            start_timestamp: Start timestamp (ISO format)
            end_timestamp: End timestamp (ISO format)
            limit: Maximum number of results
            
        Returns:
            List of transaction data
        """
        wallet = wallet_address.lower()
        
        # Build time filter
        time_filter = ""
        if start_timestamp:
            time_filter += f" AND block_timestamp >= '{start_timestamp}'"
        if end_timestamp:
            time_filter += f" AND block_timestamp <= '{end_timestamp}'"
        
        sql = f"""
        SELECT 
            transaction_hash,
            block_number,
            block_timestamp,
            from_address,
            to_address,
            value,
            gas_used,
            gas_price
        FROM base.transactions
        WHERE (LOWER(from_address) = '{wallet}' OR LOWER(to_address) = '{wallet}')
            {time_filter}
        ORDER BY block_timestamp DESC
        LIMIT {limit}
        """
        
        result = await self.execute_query(sql)
        return result.result
    
    async def get_wallet_transfers(
        self,
        wallet_address: str,
        token_address: str = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",  # USDC
        start_timestamp: Optional[str] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Get token transfers for a specific wallet.
        
        Args:
            wallet_address: Wallet address to query
            token_address: Token contract address (default: USDC)
            start_timestamp: Start timestamp (ISO format)
            limit: Maximum number of results
            
        Returns:
            List of transfer data
        """
        wallet = wallet_address.lower()
        token = token_address.lower()
        
        time_filter = f" AND block_timestamp >= '{start_timestamp}'" if start_timestamp else ""
        
        sql = f"""
        SELECT 
            transaction_hash,
            block_number,
            block_timestamp,
            from_address,
            to_address,
            token_address,
            value
        FROM base.transfers
        WHERE (LOWER(from_address) = '{wallet}' OR LOWER(to_address) = '{wallet}')
            AND LOWER(token_address) = '{token}'
            {time_filter}
        ORDER BY block_timestamp DESC
        LIMIT {limit}
        """
        
        result = await self.execute_query(sql)
        return result.result
    
    async def get_contract_events(
        self,
        contract_address: str,
        event_signatures: List[str],
        start_block: Optional[int] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Get events from a specific contract.
        
        Args:
            contract_address: Contract address to query
            event_signatures: List of event signatures to filter
            start_block: Starting block number
            limit: Maximum number of results
            
        Returns:
            List of event data
        """
        contract = contract_address.lower()
        
        # Build event signature filter
        sig_filter = " OR ".join([f"event_signature = '{sig}'" for sig in event_signatures])
        
        # Block filter
        block_filter = f" AND block_number >= {start_block}" if start_block else ""
        
        sql = f"""
        SELECT 
            transaction_hash,
            block_number,
            block_timestamp,
            log_index,
            event_signature,
            contract_address,
            topics,
            data
        FROM base.events
        WHERE LOWER(contract_address) = '{contract}'
            AND ({sig_filter})
            {block_filter}
        ORDER BY block_number DESC, log_index DESC
        LIMIT {limit}
        """
        
        result = await self.execute_query(sql)
        return result.result
    
    async def close(self):
        """Close the HTTP client."""
        try:
            await self.client.aclose()
        except Exception as e:
            logger.warning(f"Error closing CDP client: {e}")


# Custom exception classes for production error handling
class CDPAPIError(Exception):
    """Base exception for CDP API errors."""
    pass

class CDPRateLimitError(CDPAPIError):
    """Raised when rate limited by CDP API."""
    pass

class CDPTimeoutError(CDPAPIError):
    """Raised when query times out."""
    pass

class CDPValidationError(CDPAPIError):
    """Raised when query validation fails."""
    pass

class CDPAuthenticationError(CDPAPIError):
    """Raised when authentication fails."""
    pass

class CDPAuthorizationError(CDPAPIError):
    """Raised when access is denied."""
    pass

class CDPServerError(CDPAPIError):
    """Raised when CDP API has server errors."""
    pass

class CDPNetworkError(CDPAPIError):
    """Raised when network connection fails."""
    pass