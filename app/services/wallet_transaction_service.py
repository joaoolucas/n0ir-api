"""Service for fetching and categorizing wallet transactions from CDP API."""

import time
from typing import List, Dict, Any, Optional, Tuple
from decimal import Decimal
from datetime import datetime
from enum import Enum
import requests
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from app.database.models import Transaction
from app.core.config import settings
from app.core.pools_service import pools_service


class TransactionType(Enum):
    """Transaction types for categorization."""
    DEPOSIT = "DEPOSIT"
    WITHDRAW = "WITHDRAW"  # Changed from WITHDRAWAL to match schema
    STAKING = "STAKING"  # NFT position staked to gauge or interaction with position manager
    POSITION_CREATED = "POSITION_CREATED"
    POSITION_CLOSED = "POSITION_CLOSED"
    AERO_SWAP = "AERO_SWAP"
    UNKNOWN = "UNKNOWN"


class WalletTransactionService:
    """Service for fetching and analyzing wallet transactions."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.base_url = "https://api.cdp.coinbase.com/platform"
        
        # Known token addresses on Base
        self.USDC_ADDRESS = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913".lower()
        self.AERO_ADDRESS = settings.aero_token_address.lower()
        
        # LiquidityManager contract for position open/close detection
        self.LIQUIDITY_MANAGER = settings.liquidity_manager_address.lower()

        # NFT Position Manager - the ERC721 contract that holds position NFTs
        self.NFT_POSITION_MANAGER = "0x827922686190790b37229fd06084350e74485b72".lower()  # Aerodrome NFT Position Manager

        # Position manager contracts (for staking detection)
        self.POSITION_MANAGERS = [
            "0x827922686190790b37229fd06084350e74485b72".lower(),  # Main position manager
            "0xf33a96b5932d9e9b9a0eda447abd8c9d48d2e0c8".lower(),  # Another position manager
        ]
        
        # Method signatures for LiquidityManager
        self.POSITION_METHOD_SIGNATURES = {
            "0x3a1e3569": "openPosition",
            "0x2b17db59": "openPosition",  # Alternative openPosition signature
            "0xe0891d91": "closePosition"
        }
    
    async def fetch_and_sync_transactions(
        self,
        user_id: str,
        cdp_wallet_address: str,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Fetch transactions from CDP API and sync to database.
        
        Args:
            user_id: The user's owner wallet address (EOA)
            cdp_wallet_address: The user's CDP managed wallet address
            limit: Maximum number of transactions to fetch
            
        Returns:
            Summary of fetched and categorized transactions
        """
        if not cdp_wallet_address:
            return {
                "success": False,
                "error": "No CDP wallet address provided",
                "transactions_synced": 0
            }
        
        # Check if CDP API key is configured
        if not settings.cdp_client_api_key:
            return {
                "success": False,
                "error": "CDP API key not configured",
                "transactions_synced": 0
            }
        
        try:
            # Fetch all transactions with pagination
            all_transactions = await self._fetch_all_transactions(
                cdp_wallet_address, 
                settings.cdp_client_api_key,
                limit
            )
            
            if not all_transactions:
                return {
                    "success": True,
                    "transactions_synced": 0,
                    "deposits": 0,
                    "withdrawals": 0,
                    "stakings": 0
                }
            
            # Categorize and save transactions
            result = await self._process_and_save_transactions(
                all_transactions,
                user_id,
                cdp_wallet_address
            )
            
            return {
                "success": True,
                "transactions_synced": result["total"],
                "deposits": result["deposits"],
                "withdrawals": result["withdrawals"],
                "stakings": result["stakings"],
                "positions_opened": result["positions_opened"],
                "positions_closed": result["positions_closed"],
                "unknown": result["unknown"],
                "total_deposited_usdc": float(result["total_deposited"]),
                "total_withdrawn_usdc": float(result["total_withdrawn"])
            }
            
        except Exception as e:
            logger.error(f"Error syncing transactions for user {user_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "transactions_synced": 0
            }
    
    async def _fetch_all_transactions(
        self, 
        wallet_address: str, 
        api_key: str,
        max_transactions: int = 100
    ) -> List[Dict]:
        """Fetch all transactions using pagination with retry logic."""
        endpoint = f"/v1/networks/base-mainnet/addresses/{wallet_address}/transactions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        all_transactions = []
        page = None
        page_count = 0
        max_retries = 3
        base_delay = 2.0
        batch_size = 20  # Smaller batch size to avoid rate limits
        
        while len(all_transactions) < max_transactions:
            retry_count = 0
            success = False
            
            while retry_count < max_retries and not success:
                logger.info(f"Fetching page {page_count + 1} for wallet {wallet_address}...")
                
                params = {"limit": min(batch_size, max_transactions - len(all_transactions))}
                if page:
                    params["page"] = page
                
                try:
                    response = requests.get(
                        f"{self.base_url}{endpoint}",
                        headers=headers,
                        params=params
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        transactions = data.get("data", [])
                        all_transactions.extend(transactions)
                        page_count += 1
                        success = True
                        
                        logger.info(f"  Found {len(transactions)} transactions (total: {len(all_transactions)})")
                        
                        # Check if there are more pages
                        has_more = data.get("has_more", False)
                        next_page = data.get("next_page")
                        
                        if not has_more or not next_page or len(all_transactions) >= max_transactions:
                            return all_transactions
                        
                        page = next_page
                        time.sleep(0.5)  # Delay between successful requests
                        
                    elif response.status_code == 429:
                        # Rate limited - retry with exponential backoff
                        retry_count += 1
                        if retry_count < max_retries:
                            delay = base_delay * (2 ** retry_count)
                            logger.warning(f"  Rate limited, waiting {delay}s (attempt {retry_count + 1}/{max_retries})")
                            time.sleep(delay)
                    else:
                        logger.error(f"  API error: {response.status_code}")
                        return all_transactions
                        
                except requests.exceptions.RequestException as e:
                    logger.error(f"  Request failed: {e}")
                    retry_count += 1
                    if retry_count < max_retries:
                        delay = base_delay * (2 ** retry_count)
                        time.sleep(delay)
            
            if not success:
                logger.warning(f"  Failed to fetch page after {max_retries} retries")
                break
        
        return all_transactions
    
    async def _get_pool_name(self, pool_address: str) -> Optional[str]:
        """Get pool name from pools service."""
        # Skip addresses that are clearly not pools
        if not pool_address or len(pool_address) != 42:
            return None

        # Skip addresses that look like special/system contracts (e.g., start with many zeros)
        if pool_address.lower().startswith('0x0000') or pool_address.lower().startswith('0x0001'):
            logger.debug(f"Skipping non-pool address: {pool_address}")
            return None

        try:
            pool_data = await pools_service.get_pool(pool_address, include_effective_apr=False)
            symbol = pool_data.get('symbol', '')
            # Symbol format is "TOKEN0/TOKEN1-0.3%"
            # We want to keep "TOKEN0/TOKEN1" format
            if symbol and '-' in symbol:
                # Remove fee percentage (everything after last dash)
                pool_name = symbol.rsplit('-', 1)[0]  # Gets "TOKEN0/TOKEN1"
            else:
                pool_name = symbol
            return pool_name if pool_name else None
        except Exception as e:
            # Only log as debug for execution reverted errors (common for non-pool contracts)
            if "execution reverted" in str(e).lower():
                logger.debug(f"Address {pool_address} is not a valid pool contract")
            else:
                logger.warning(f"Could not fetch pool info for {pool_address}: {e}")
            return None

    def _decode_erc20_input(self, input_data: str) -> Optional[Dict[str, Any]]:
        """Decode ERC20 method calls from input data."""
        if not input_data or len(input_data) < 10:
            return None
        
        method_sig = input_data[:10]
        
        # transfer(address,uint256)
        if method_sig == "0xa9059cbb" and len(input_data) >= 138:
            return {
                "method": "transfer",
                "to": "0x" + input_data[34:74],
                "amount": int(input_data[74:138], 16) if input_data[74:138] else 0
            }
        
        # transferFrom(address,address,uint256)
        elif method_sig == "0x23b872dd" and len(input_data) >= 202:
            return {
                "method": "transferFrom",
                "from": "0x" + input_data[34:74],
                "to": "0x" + input_data[98:138],
                "amount": int(input_data[138:202], 16) if input_data[138:202] else 0
            }
        
        return None
    
    def _analyze_position_event(
        self,
        traces: List[Dict],
        cdp_wallet: str
    ) -> Optional[Dict[str, Any]]:
        """Analyze traces to extract position event details.

        Returns dict with:
        - method_sig: Method signature used
        - method_name: openPosition or closePosition
        - usdc_in: USDC amount going into position
        - usdc_out: USDC amount coming out of position
        - aero_in: AERO amount received
        - aero_out: AERO amount sent
        - pool: Pool address if found
        - nft_token_id: NFT position token ID if found
        """
        position_event = None
        usdc_flows = {"in": 0, "out": 0}
        aero_flows = {"in": 0, "out": 0}
        pool_addresses = set()  # Track all potential pool addresses

        # PRIORITY 1: Check for PositionClosed or PositionOpened events in logs
        # Events are the source of truth - they explicitly tell us what happened
        for trace in traces:
            # Check if trace has logs/events
            if "logs" in trace:
                logger.debug(f"Checking {len(trace.get('logs', []))} logs in trace")
                for log in trace.get("logs", []):
                    # Look for event signatures
                    # PositionClosed event signature would be in topics[0]
                    topics = log.get("topics", [])
                    if topics:
                        event_sig = topics[0] if topics else None
                        # Event signatures for position management
                        # These are standard Uniswap V3 NonfungiblePositionManager events
                        DECREASE_LIQUIDITY_EVENT = "0x26f6a048ee9138f2c0ce266f322cb99228e8d619ae2bff30c67f8dcf9d2377b4"  # DecreaseLiquidity
                        INCREASE_LIQUIDITY_EVENT = "0x3067048beee31b25b2f1681f88dac838c8bba36af25bfb2b7cf7473a5847e35f"  # IncreaseLiquidity
                        COLLECT_EVENT = "0x40d0efd1a53d60ecbf40971b9daf7dc90178c3aadc7aab1765632738fa8b8f01"  # Collect
                        # ERC721 Transfer event for NFT staking detection
                        ERC721_TRANSFER_EVENT = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"  # Transfer(from, to, tokenId)

                        if event_sig:
                            # Normalize event signature for comparison
                            event_sig_normalized = event_sig.lower() if isinstance(event_sig, str) else str(event_sig).lower()

                            # Try to extract NFT token ID from the log
                            # For DecreaseLiquidity and IncreaseLiquidity events, tokenId is usually the first topic after event signature
                            nft_token_id = None
                            if len(topics) > 1:
                                # Topics[1] typically contains the indexed tokenId parameter
                                try:
                                    # Remove 0x prefix and convert hex to int
                                    token_id_hex = topics[1].replace('0x', '') if isinstance(topics[1], str) else str(topics[1]).replace('0x', '')
                                    nft_token_id = int(token_id_hex, 16) if token_id_hex else None
                                except (ValueError, TypeError):
                                    pass

                            # Check for position closing events (DecreaseLiquidity to 0 or Collect after decrease)
                            if event_sig_normalized == DECREASE_LIQUIDITY_EVENT.lower() or event_sig_normalized == COLLECT_EVENT.lower():
                                # Check if this is a full close (liquidity decreased to 0)
                                # For now, treat any decrease/collect as potential close
                                # More sophisticated logic could check if liquidity went to 0
                                position_event = {
                                    "method_sig": "0xe0891d91",  # closePosition method signature
                                    "method_name": "closePosition",
                                    "event_detected": "DecreaseLiquidity/Collect",
                                    "event_signature": event_sig_normalized
                                }
                                if nft_token_id:
                                    position_event["nft_token_id"] = nft_token_id
                                # Don't break - keep looking for more specific events

                            # Check for position opening events (IncreaseLiquidity)
                            elif event_sig_normalized == INCREASE_LIQUIDITY_EVENT.lower():
                                position_event = {
                                    "method_sig": trace.get("input", "")[:10] if trace.get("input") else "0x3a1e3569",
                                    "method_name": "openPosition",
                                    "event_detected": "IncreaseLiquidity",
                                    "event_signature": event_sig_normalized
                                }
                                if nft_token_id:
                                    position_event["nft_token_id"] = nft_token_id
                                # Don't break - keep looking for more specific events

                            # Also check for text-based event names in the log data
                            log_str = str(log).lower()
                            if "positionclosed" in log_str or "position closed" in log_str:
                                position_event = {
                                    "method_sig": "0xe0891d91",  # closePosition method signature
                                    "method_name": "closePosition",
                                    "event_detected": "PositionClosed",
                                    "event_signature": event_sig_normalized
                                }
                                break  # This is definitive
                            elif "positionopened" in log_str or "position opened" in log_str:
                                position_event = {
                                    "method_sig": trace.get("input", "")[:10] if trace.get("input") else "0x3a1e3569",
                                    "method_name": "openPosition",
                                    "event_detected": "PositionOpened",
                                    "event_signature": event_sig_normalized
                                }
                                break  # This is definitive

                            # Check for ERC721 Transfer events (NFT staking)
                            elif event_sig_normalized == ERC721_TRANSFER_EVENT.lower():
                                # Check if this is from the NFT Position Manager contract
                                log_address = log.get("address", "").lower() if log.get("address") else ""
                                logger.debug(f"Found ERC721 Transfer event from {log_address}, NFT Manager: {self.NFT_POSITION_MANAGER}")
                                if log_address == self.NFT_POSITION_MANAGER:
                                    # ERC721 Transfer has 3 indexed params: from, to, tokenId
                                    # topics[0] = event signature
                                    # topics[1] = from address (padded)
                                    # topics[2] = to address (padded)
                                    # topics[3] = tokenId
                                    if len(topics) >= 4:
                                        try:
                                            # Extract addresses (remove 0x prefix and padding)
                                            from_addr_hex = topics[1][-40:] if isinstance(topics[1], str) else str(topics[1])[-40:]
                                            to_addr_hex = topics[2][-40:] if isinstance(topics[2], str) else str(topics[2])[-40:]
                                            from_addr = ("0x" + from_addr_hex).lower()
                                            to_addr = ("0x" + to_addr_hex).lower()

                                            # Extract token ID
                                            token_id_hex = topics[3].replace('0x', '') if isinstance(topics[3], str) else str(topics[3]).replace('0x', '')
                                            nft_token_id = int(token_id_hex, 16) if token_id_hex else None

                                            # Check if this is a stake (CDP wallet transferring NFT to a gauge)
                                            if from_addr == cdp_wallet and nft_token_id:
                                                # To determine if it's a stake, we need to check if the recipient is a gauge
                                                # We'll mark it as potential stake and verify the gauge address later
                                                position_event = {
                                                    "type": "STAKING",
                                                    "from_address": from_addr,
                                                    "to_address": to_addr,
                                                    "nft_token_id": nft_token_id,
                                                    "event_detected": "ERC721Transfer",
                                                    "event_signature": event_sig_normalized
                                                }
                                                logger.debug(f"Detected NFT transfer from CDP wallet: token {nft_token_id} to {to_addr}")
                                        except (ValueError, TypeError, IndexError) as e:
                                            logger.warning(f"Failed to parse ERC721 Transfer event: {e}")

        # PRIORITY 2: If no events found, fall back to method signature analysis
        # But only if we didn't already find a position event
        if not position_event:
            for trace in traces:
                from_addr = trace.get("from", "").lower()
                to_addr = trace.get("to", "").lower()
                input_data = trace.get("input", "")

                # Track interactions with contracts that might be pools
                # Pools typically interact with token contracts and liquidity managers
                # Look for contracts that aren't known token/protocol addresses
                if to_addr and to_addr not in [
                    self.USDC_ADDRESS,
                    self.AERO_ADDRESS,
                    self.LIQUIDITY_MANAGER,
                    cdp_wallet
                ] and not to_addr.startswith("0x000000"):  # Exclude zero addresses
                    # Check if it looks like a pool contract (has certain patterns)
                    # Pools typically receive calls from liquidity manager or interact with tokens
                    if from_addr == self.LIQUIDITY_MANAGER or to_addr != from_addr:
                        pool_addresses.add(to_addr)

                # Check for LiquidityManager interaction (only if no event-based detection)
                if not position_event and to_addr == self.LIQUIDITY_MANAGER and from_addr == cdp_wallet:
                    if len(input_data) >= 10:
                        method_sig = input_data[:10]
                        if method_sig in self.POSITION_METHOD_SIGNATURES:
                            position_event = {
                                "method_sig": method_sig,
                                "method_name": self.POSITION_METHOD_SIGNATURES[method_sig],
                                "event_detected": "method_signature_fallback"
                            }

        # Always track USDC transfers regardless of position detection
        for trace in traces:
            from_addr = trace.get("from", "").lower()
            to_addr = trace.get("to", "").lower()
            input_data = trace.get("input", "")

            # Track USDC transfers
            if to_addr == self.USDC_ADDRESS:
                decoded = self._decode_erc20_input(input_data)
                if decoded:
                    if decoded["method"] == "transfer":
                        if from_addr == cdp_wallet:
                            usdc_flows["out"] += decoded["amount"]
                        elif decoded["to"].lower() == cdp_wallet:
                            usdc_flows["in"] += decoded["amount"]
                    elif decoded["method"] == "transferFrom":
                        if decoded["from"].lower() == cdp_wallet:
                            usdc_flows["out"] += decoded["amount"]
                        elif decoded["to"].lower() == cdp_wallet:
                            usdc_flows["in"] += decoded["amount"]

            # Track AERO transfers
            if to_addr == self.AERO_ADDRESS:
                decoded = self._decode_erc20_input(input_data)
                if decoded:
                    if decoded["method"] == "transfer":
                        if from_addr == cdp_wallet:
                            aero_flows["out"] += decoded["amount"]
                        elif decoded["to"].lower() == cdp_wallet:
                            aero_flows["in"] += decoded["amount"]
                    elif decoded["method"] == "transferFrom":
                        if decoded["from"].lower() == cdp_wallet:
                            aero_flows["out"] += decoded["amount"]
                        elif decoded["to"].lower() == cdp_wallet:
                            aero_flows["in"] += decoded["amount"]
        
        if position_event:
            # Don't use pool addresses from traces - they're often wrong
            # The actual pool address should be looked up from the position NFT
            # Only include pool if we're confident it's correct
            position_event.update({
                "usdc_in": usdc_flows["in"],
                "usdc_out": usdc_flows["out"],
                "aero_in": aero_flows["in"],
                "aero_out": aero_flows["out"],
                "pool": None  # Will be fetched from position data later
            })
            return position_event
        
        return None
    
    async def _categorize_transaction(
        self,
        tx_data: Dict,
        owner_wallet: str,
        cdp_wallet: str
    ) -> Tuple[TransactionType, Dict[str, Any]]:
        # Log STAKING transaction structure for debugging
        if tx_data.get("hash") and "c033aabc" in tx_data.get("hash", ""):
            logger.info(f"STAKE tx structure keys: {list(tx_data.keys())}")
            logger.info(f"STAKE tx has traces: {'traces' in tx_data}")
            if 'traces' in tx_data and tx_data['traces']:
                first_trace = tx_data['traces'][0] if tx_data['traces'] else {}
                logger.info(f"STAKE tx first trace keys: {list(first_trace.keys())}")
                if 'logs' in first_trace:
                    logger.info(f"STAKE tx has {len(first_trace['logs'])} logs")
        """Categorize transaction based on wallet relationships.
        
        Args:
            tx_data: Raw transaction data from CDP API
            owner_wallet: User's owner wallet address (user_id)
            cdp_wallet: User's CDP managed wallet address
            
        Returns:
            Tuple of (transaction_type, details)
        """
        content = tx_data.get("content", {})
        traces = content.get("flattened_traces", [])
        
        if not traces:
            return TransactionType.UNKNOWN, {}
        
        # Basic transaction info
        details = {
            "tx_hash": traces[0].get("transaction_hash", ""),
            "block": traces[0].get("block_number", ""),
            "timestamp": content.get("block_timestamp", ""),
            "amount": 0,
            "description": ""
        }
        
        # Normalize addresses
        owner_wallet = owner_wallet.lower()
        cdp_wallet = cdp_wallet.lower()
        
        # Track what we find
        found_deposit = False
        found_withdrawal = False
        deposit_amount = 0
        withdrawal_amount = 0
        
        # Check for position events first (highest priority)
        position_event = self._analyze_position_event(traces, cdp_wallet)
        if position_event:
            # Handle STAKING type separately
            if position_event.get("type") == "STAKING":
                details["nft_token_id"] = position_event["nft_token_id"]
                details["gauge_address"] = position_event["to_address"]
                details["description"] = f"Staked NFT position {position_event['nft_token_id']} to gauge"
                details["amount"] = 0  # Staking doesn't have a USDC amount

                # Try to get the position details to find pool name
                from app.database.models.position import Position
                from sqlalchemy import select
                stmt = select(Position).where(Position.token_id == position_event["nft_token_id"])
                result = await self.db.execute(stmt)
                position = result.scalar_one_or_none()

                if position:
                    details["pool_name"] = position.pool_name
                    details["pool"] = position.pool_address

                return TransactionType.STAKING, details

            method_name = position_event["method_name"]

            # Additional logic: detect swaps and position closes

            # POSITION_CLOSED: if both USDC and AERO are coming IN (highest priority)
            # When closing a position, you get both tokens back
            if position_event["usdc_in"] > 0 and position_event["aero_in"] > 0:
                # This is a position close
                method_name = "closePosition"
                position_event["method_name"] = "closePosition"

            # AERO_SWAP: AERO (and possibly USDC) goes OUT and net USDC comes IN
            # This happens when swapping tokens, potentially with some USDC out too
            elif position_event["aero_out"] > 0 and position_event["usdc_in"] > 0:
                # This is a swap: selling AERO for USDC
                # Net amount is USDC received minus USDC sent
                net_usdc = position_event["usdc_in"] - position_event["usdc_out"]
                details["amount"] = net_usdc  # Can be negative if more USDC went out
                details["description"] = f"Swapped AERO for USDC"
                details["method_sig"] = position_event["method_sig"]
                details["usdc_in"] = position_event["usdc_in"]
                details["usdc_out"] = position_event["usdc_out"]
                details["aero_in"] = position_event["aero_in"]
                details["aero_out"] = position_event["aero_out"]
                details["pool"] = position_event.get("pool")

                # Try to get pool name
                if position_event.get("pool"):
                    details["pool_name"] = await self._get_pool_name(position_event["pool"])

                return TransactionType.AERO_SWAP, details

            if method_name == "openPosition":
                # For position creation, the net amount is what the user actually invested (usdc_out - usdc_in)
                # usdc_out is what left the wallet, usdc_in is what came back (if any)
                net_amount = position_event["usdc_out"] - position_event["usdc_in"]

                # Skip if net amount is 0 or negative (not a real position creation)
                if net_amount <= 0:
                    logger.warning(f"Skipping position event with zero/negative net amount: {details['tx_hash'][:10]}...")
                    return TransactionType.UNKNOWN, details

                details["amount"] = net_amount
                details["description"] = f"Position opened via LiquidityManager"
                details["method_sig"] = position_event["method_sig"]
                details["usdc_in"] = position_event["usdc_in"]
                details["usdc_out"] = position_event["usdc_out"]
                details["aero_in"] = position_event["aero_in"]
                details["aero_out"] = position_event["aero_out"]
                details["pool"] = position_event.get("pool")  # Include pool address

                # Try to get pool name
                if position_event.get("pool"):
                    details["pool_name"] = await self._get_pool_name(position_event["pool"])

                return TransactionType.POSITION_CREATED, details
            
            elif method_name == "closePosition":
                details["amount"] = position_event["usdc_in"] if position_event["usdc_in"] > 0 else position_event["usdc_out"]
                details["description"] = f"Position closed via LiquidityManager"
                details["method_sig"] = position_event["method_sig"]
                details["usdc_in"] = position_event["usdc_in"]
                details["usdc_out"] = position_event["usdc_out"]
                details["aero_in"] = position_event["aero_in"]
                details["aero_out"] = position_event["aero_out"]
                details["pool"] = position_event.get("pool")  # Include pool address
                details["nft_token_id"] = position_event.get("nft_token_id")  # Include NFT token ID

                # Try to get pool name
                if position_event.get("pool"):
                    details["pool_name"] = await self._get_pool_name(position_event["pool"])

                return TransactionType.POSITION_CLOSED, details
        
        # Check all traces for patterns
        for trace in traces:
            from_addr = trace.get("from", "").lower()
            to_addr = trace.get("to", "").lower()
            input_data = trace.get("input", "")
            
            # Decode ERC20 operations
            decoded = self._decode_erc20_input(input_data)
            
            # Check for USDC transfers
            if to_addr == self.USDC_ADDRESS and decoded:
                recipient = decoded.get("to", "").lower() if decoded.get("to") else ""
                amount = decoded.get("amount", 0)
                
                # For transfer method
                if decoded.get("method") == "transfer":
                    # DEPOSIT: Owner wallet sending USDC to CDP wallet
                    if from_addr == owner_wallet and recipient == cdp_wallet:
                        found_deposit = True
                        deposit_amount += amount
                    
                    # WITHDRAWAL: CDP wallet sending USDC to owner wallet
                    elif from_addr == cdp_wallet and recipient == owner_wallet:
                        found_withdrawal = True
                        withdrawal_amount += amount
                
                # For transferFrom method
                elif decoded.get("method") == "transferFrom":
                    transfer_from = decoded.get("from", "").lower() if decoded.get("from") else ""
                    transfer_to = decoded.get("to", "").lower() if decoded.get("to") else ""
                    
                    # DEPOSIT: USDC from owner wallet to CDP wallet
                    if transfer_from == owner_wallet and transfer_to == cdp_wallet:
                        found_deposit = True
                        deposit_amount += amount
                    
                    # WITHDRAWAL: USDC from CDP wallet to owner wallet
                    elif transfer_from == cdp_wallet and transfer_to == owner_wallet:
                        found_withdrawal = True
                        withdrawal_amount += amount
            
            # STAKING: Check if CDP wallet is interacting with position managers
            # This is a fallback if ERC721 Transfer events aren't available
            if from_addr == cdp_wallet:
                for pm in self.POSITION_MANAGERS:
                    if to_addr == pm:
                        # This is likely a staking transaction
                        # Try to extract NFT token ID from input data
                        if input_data and len(input_data) > 10:
                            method_sig = input_data[:10]
                            # Common staking method signatures
                            # 0x6e553f65 = deposit(uint256,address)
                            # 0x1526fe27 = gauges(address)
                            logger.info(f"Found potential staking to position manager with method: {method_sig}")
                            details["description"] = f"NFT position staked to gauge"
                            details["gauge_address"] = to_addr
                            details["cdp_wallet"] = cdp_wallet

                            # Try to extract NFT ID from recent positions
                            # This is a workaround since we can't get it from the transaction directly
                            from app.database.models.position import Position
                            from sqlalchemy import select
                            stmt = select(Position).where(
                                Position.user_id == owner_wallet,
                                Position.status == 'ACTIVE'
                            ).order_by(Position.created_at.desc()).limit(1)
                            result = await self.db.execute(stmt)
                            position = result.scalar_one_or_none()

                            if position:
                                details["nft_token_id"] = position.token_id
                                details["pool_name"] = position.pool_name
                                details["pool"] = position.pool_address
                                details["description"] = f"Staked NFT position {position.token_id} to gauge"

                            return TransactionType.STAKING, details
        
        # Return based on what we found (prioritize financial transactions)
        if found_deposit:
            details["amount"] = deposit_amount
            details["description"] = f"USDC deposit from owner wallet"
            details["cdp_wallet"] = cdp_wallet
            return TransactionType.DEPOSIT, details
        
        if found_withdrawal:
            details["amount"] = withdrawal_amount
            details["description"] = f"USDC withdrawal to owner wallet"
            details["cdp_wallet"] = cdp_wallet
            return TransactionType.WITHDRAW, details
        
        
        details["cdp_wallet"] = cdp_wallet
        return TransactionType.UNKNOWN, details
    
    async def _process_and_save_transactions(
        self,
        transactions: List[Dict],
        user_id: str,
        cdp_wallet_address: str
    ) -> Dict[str, Any]:
        """Process transactions and save to database.
        
        Args:
            transactions: List of raw transactions from CDP API
            user_id: User's owner wallet address
            cdp_wallet_address: User's CDP wallet address
            
        Returns:
            Summary of processed transactions
        """
        categorized = {
            TransactionType.DEPOSIT: [],
            TransactionType.WITHDRAW: [],
            TransactionType.STAKING: [],
            TransactionType.POSITION_CREATED: [],
            TransactionType.POSITION_CLOSED: [],
            TransactionType.AERO_SWAP: [],
            TransactionType.UNKNOWN: []
        }
        
        total_deposited = Decimal(0)
        total_withdrawn = Decimal(0)
        
        for tx in transactions:
            tx_type, details = await self._categorize_transaction(
                tx,
                user_id,
                cdp_wallet_address
            )

            if details:
                # Log what we found
                logger.info(f"Categorized tx {details.get('tx_hash', 'unknown')[:20]}... as {tx_type.value}")
                categorized[tx_type].append(details)
                
                # Track totals
                if tx_type == TransactionType.DEPOSIT:
                    total_deposited += Decimal(details["amount"]) / Decimal(1_000_000)
                elif tx_type == TransactionType.WITHDRAW:
                    total_withdrawn += Decimal(details["amount"]) / Decimal(1_000_000)
                
                # Save to database if it's a financial or position transaction
                if tx_type in [TransactionType.DEPOSIT, TransactionType.WITHDRAW,
                              TransactionType.POSITION_CREATED, TransactionType.POSITION_CLOSED,
                              TransactionType.AERO_SWAP, TransactionType.STAKING]:
                    await self._save_transaction(
                        user_id=user_id,
                        tx_type=tx_type.value,
                        details=details
                    )
                else:
                    logger.info(f"Not saving {tx_type.value} transaction: {details.get('tx_hash', '')[:20]}...")
        
        # Commit all database changes
        await self.db.commit()
        
        return {
            "total": len(transactions),
            "deposits": len(categorized[TransactionType.DEPOSIT]),
            "withdrawals": len(categorized[TransactionType.WITHDRAW]),
            "stakings": len(categorized[TransactionType.STAKING]),
            "positions_opened": len(categorized[TransactionType.POSITION_CREATED]),
            "positions_closed": len(categorized[TransactionType.POSITION_CLOSED]),
            "aero_swaps": len(categorized[TransactionType.AERO_SWAP]),
            "unknown": len(categorized[TransactionType.UNKNOWN]),
            "total_deposited": total_deposited,
            "total_withdrawn": total_withdrawn
        }
    
    async def _save_transaction(
        self,
        user_id: str,
        tx_type: str,
        details: Dict[str, Any]
    ) -> None:
        """Save or update a transaction in the database."""
        from sqlalchemy import select

        # Check if transaction already exists
        stmt = select(Transaction).where(
            Transaction.tx_hash == details["tx_hash"]
        )
        result = await self.db.execute(stmt)
        existing_tx = result.scalar_one_or_none()
        
        if not existing_tx:
            # Create new transaction
            amount_usdc = Decimal(details["amount"]) / Decimal(1_000_000) if details.get("amount") else Decimal(0)
            
            # Build event data based on transaction type
            event_data = {
                "description": details.get("description", ""),
                "categorized_by": "wallet_transaction_service",
                "cdp_wallet": details.get("cdp_wallet", "")
            }
            
            # Add position-specific and swap data if available
            if tx_type in ["POSITION_CREATED", "POSITION_CLOSED", "AERO_SWAP", "STAKING"]:
                if details.get("method_sig"):
                    event_data["method_sig"] = details["method_sig"]
                if details.get("usdc_in") is not None:
                    event_data["usdc_in"] = details["usdc_in"]
                if details.get("usdc_out") is not None:
                    event_data["usdc_out"] = details["usdc_out"]
                if details.get("aero_in") is not None:
                    event_data["aero_in"] = details["aero_in"]
                if details.get("aero_out") is not None:
                    event_data["aero_out"] = details["aero_out"]
                if details.get("pool"):
                    event_data["pool"] = details["pool"]

                # Add gauge address for STAKING transactions
                if tx_type == "STAKING" and details.get("gauge_address"):
                    event_data["gauge_address"] = details["gauge_address"]

                # Add NFT token ID if available
                if details.get("nft_token_id"):
                    event_data["nft_token_id"] = details["nft_token_id"]
                elif tx_type in ["POSITION_CREATED", "POSITION_CLOSED"]:
                    # Try to find the NFT token ID by matching position
                    nft_token_id = await self._find_position_for_transaction(
                        user_id, tx_type, amount_usdc, details
                    )
                    if nft_token_id:
                        event_data["nft_token_id"] = nft_token_id
                        logger.info(f"Found matching position {nft_token_id} for {tx_type} transaction")

                # Use pool_name from details if available, otherwise try to fetch it
                if details.get("pool_name"):
                    event_data["pool_name"] = details["pool_name"]

                # Get pool address - from details or from position for POSITION_CLOSED
                pool_address = details.get("pool")
                if not pool_address and tx_type == "POSITION_CLOSED" and event_data.get("nft_token_id"):
                    # For POSITION_CLOSED, look up the position to get pool_address
                    from app.database.models import Position
                    from sqlalchemy import select

                    stmt = select(Position).where(Position.token_id == event_data["nft_token_id"])
                    result = await self.db.execute(stmt)
                    position = result.scalar_one_or_none()
                    if position:
                        pool_address = position.pool_address
                        event_data["pool"] = pool_address  # Store for reference
                        logger.debug(f"Found pool address {pool_address} from position {event_data['nft_token_id']}")

                if pool_address and not event_data.get("pool_name"):
                    # Fetch pool name from pools_service
                    try:
                        pool_data = await pools_service.get_pool(pool_address, include_effective_apr=False)
                        symbol = pool_data.get('symbol', '')
                        # Symbol format is "TOKEN0/TOKEN1-0.3%"
                        # We want to keep "TOKEN0/TOKEN1" format
                        if symbol and '-' in symbol:
                            # Remove fee percentage (everything after last dash)
                            pool_name = symbol.rsplit('-', 1)[0]  # Gets "TOKEN0/TOKEN1"
                        else:
                            pool_name = symbol

                        if pool_name:
                            event_data["pool_name"] = pool_name
                            logger.debug(f"Found pool name {pool_name} for pool {pool_address}")
                    except Exception as e:
                        logger.warning(f"Could not fetch pool info for {pool_address}: {e}")
            
            # Store the USDC amount in event_data to avoid conflict with property
            event_data["amount_usdc"] = float(amount_usdc)

            # Extract nft_token_id from details or event_data
            nft_id = details.get("nft_token_id") or event_data.get("nft_token_id")

            # Extract position_id from nft_token_id for database column
            position_id_value = None
            if nft_id:
                position_id_value = nft_id
            elif "nft_token_id" in event_data:
                position_id_value = event_data["nft_token_id"]

            transaction = Transaction(
                tx_hash=details["tx_hash"],
                user_id=user_id,
                tx_type=tx_type,
                status="CONFIRMED",
                block_number=details.get("block"),
                block_timestamp=datetime.fromisoformat(details["timestamp"].replace("Z", "+00:00")) if details.get("timestamp") else None,
                event_data=event_data,
                position_id=position_id_value  # Set the foreign key column
            )

            self.db.add(transaction)
            logger.info(f"Saved {tx_type} transaction: {details['tx_hash'][:10]}... Amount: {amount_usdc} USDC")

            # If this is a POSITION_CLOSED transaction, update the position status
            if tx_type == "POSITION_CLOSED" and nft_id:
                logger.info(f"Closing position {nft_id} for tx {details['tx_hash'][:10]}...")
                await self._close_position_if_needed(user_id, nft_id, details["tx_hash"], amount_usdc)
        else:
            # Update existing transaction if needed
            if existing_tx.tx_type == "UNKNOWN" and tx_type != "UNKNOWN":
                existing_tx.tx_type = tx_type
                existing_tx.event_data = existing_tx.event_data or {}
                existing_tx.event_data["recategorized"] = True
                existing_tx.event_data["description"] = details.get("description", "")
                logger.info(f"Recategorized transaction {details['tx_hash'][:10]}... as {tx_type}")

    async def _find_position_for_transaction(
        self,
        user_id: str,
        tx_type: str,
        amount_usdc: Decimal,
        details: Dict[str, Any]
    ) -> Optional[int]:
        """Find matching position for a transaction that's missing nft_token_id."""
        from app.database.models import Position
        from sqlalchemy import select, and_, func

        try:
            timestamp = datetime.fromisoformat(details["timestamp"].replace("Z", "+00:00")) if details.get("timestamp") else datetime.utcnow()

            if tx_type == "POSITION_CREATED":
                # Find position created around the same time with similar amount
                stmt = select(Position).where(
                    and_(
                        Position.user_id == user_id,
                        func.abs(Position.entry_amount_usdc - amount_usdc) < 0.01,
                        # Position created within 5 minutes of transaction
                        func.abs(
                            func.extract('epoch', Position.created_at - timestamp)
                        ) < 300
                    )
                ).order_by(
                    func.abs(Position.entry_amount_usdc - amount_usdc),
                    func.abs(func.extract('epoch', Position.created_at - timestamp))
                )

                result = await self.db.execute(stmt)
                position = result.scalar_one_or_none()

                if position:
                    # Update position's entry_tx_hash if missing
                    if not position.entry_tx_hash:
                        position.entry_tx_hash = details["tx_hash"]
                    return position.token_id

            elif tx_type == "POSITION_CLOSED":
                # Find active position or recently closed position
                # First try to find an active position that should be closed
                stmt = select(Position).where(
                    and_(
                        Position.user_id == user_id,
                        Position.status == 'ACTIVE',
                        Position.created_at < timestamp
                    )
                ).order_by(
                    # Prefer positions created closer to the close time
                    func.abs(func.extract('epoch', Position.created_at - timestamp))
                )

                result = await self.db.execute(stmt)
                positions = result.scalars().all()

                # Check if any of these positions don't have a POSITION_CLOSED transaction
                from app.database.models import Transaction
                for position in positions:
                    # Check if this position already has a POSITION_CLOSED transaction
                    tx_stmt = select(Transaction).where(
                        and_(
                            Transaction.tx_type == 'POSITION_CLOSED',
                            Transaction.event_data['nft_token_id'].astext == str(position.token_id)
                        )
                    )
                    tx_result = await self.db.execute(tx_stmt)
                    if not tx_result.scalar_one_or_none():
                        # This position doesn't have a POSITION_CLOSED transaction yet
                        return position.token_id

                # If no active position without close transaction, try recently closed positions
                stmt = select(Position).where(
                    and_(
                        Position.user_id == user_id,
                        Position.status == 'CLOSED',
                        Position.exit_date != None,
                        func.abs(
                            func.extract('epoch', Position.exit_date - timestamp)
                        ) < 300
                    )
                ).order_by(
                    func.abs(func.extract('epoch', Position.exit_date - timestamp))
                )

                result = await self.db.execute(stmt)
                position = result.scalar_one_or_none()

                if position:
                    return position.token_id

            return None

        except Exception as e:
            logger.error(f"Error finding position for transaction: {e}")
            return None

    async def _close_position_if_needed(
        self,
        user_id: str,
        nft_token_id: int,
        tx_hash: str,
        final_value_usdc: Decimal
    ) -> None:
        """Close a position when a POSITION_CLOSED transaction is detected."""
        from app.database.models import Position
        from sqlalchemy import select, and_

        try:
            # Check if position exists and is active
            stmt = select(Position).where(
                and_(
                    Position.token_id == nft_token_id,
                    Position.user_id == user_id,
                    Position.status == 'ACTIVE'
                )
            )
            result = await self.db.execute(stmt)
            position = result.scalar_one_or_none()

            if position:
                # Calculate realized PnL
                realized_pnl = final_value_usdc - position.entry_amount_usdc

                # Update position to CLOSED
                position.status = 'CLOSED'
                position.exit_date = datetime.utcnow()
                position.exit_tx_hash = tx_hash
                position.realized_pnl_usdc = realized_pnl
                position.current_value_usdc = final_value_usdc
                # unrealized_pnl_usdc is a computed property, not a column

                logger.info(f"Closed position {nft_token_id} for user {user_id} with realized PnL: {realized_pnl} USDC")
            else:
                logger.warning(f"Position {nft_token_id} not found or already closed for user {user_id}")
        except Exception as e:
            logger.error(f"Error closing position {nft_token_id}: {e}")