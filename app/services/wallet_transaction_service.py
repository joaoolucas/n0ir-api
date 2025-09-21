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
    SWAP = "SWAP"
    FEE_TRANSFER = "FEE_TRANSFER"  # Fee transfers to 0xfD75350A7e2C4914908fF7E3082c45Af5762f5FE
    UNKNOWN = "UNKNOWN"


class WalletTransactionService:
    """Service for fetching and analyzing wallet transactions."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.base_url = "https://api.cdp.coinbase.com/platform"
        
        # Known token addresses on Base
        self.USDC_ADDRESS = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913".lower()
        self.AERO_ADDRESS = settings.aero_token_address.lower()

        # Fee recipient address for TRANSFER_FEE transactions
        self.FEE_RECIPIENT = "0xfD75350A7e2C4914908fF7E3082c45Af5762f5FE".lower()

        # LiquidityManager contract for position open/close detection
        self.LIQUIDITY_MANAGER = settings.liquidity_manager_address.lower()

        # NFT Position Manager - the ERC721 contract that holds position NFTs
        self.NFT_POSITION_MANAGER = "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1".lower()  # Uniswap V3 NFT Position Manager

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

    async def _ensure_position_data(
        self,
        tx_type: str,
        event_data: Dict[str, Any],
        details: Dict[str, Any],
        user_id: str
    ) -> tuple[Optional[int], Dict[str, Any]]:
        """
        Ensure position_id and pool_name are present for position-related transactions.
        Returns: (position_id, updated_event_data)
        """
        # Skip non-position transactions
        if tx_type not in ['POSITION_CREATED', 'POSITION_CLOSED', 'STAKING']:
            return None, event_data

        position_id = None

        # Step 1: Try to get position_id from multiple sources
        # Priority: nft_token_id > token_id > position_id
        potential_ids = [
            details.get("nft_token_id"),
            event_data.get("nft_token_id"),
            event_data.get("token_id"),
            event_data.get("position_id"),
            details.get("token_id"),
            details.get("position_id")
        ]

        for pid in potential_ids:
            if pid is not None:
                position_id = int(pid) if isinstance(pid, (str, float)) else pid
                break

        # Step 2: If still no position_id, try to find it
        if not position_id and tx_type in ['POSITION_CREATED', 'POSITION_CLOSED']:
            # Try to match by transaction details
            position_id = await self._find_position_for_transaction(
                user_id, tx_type,
                Decimal(str(event_data.get('amount_usdc', 0))),
                details
            )
            if position_id:
                logger.info(f"Auto-discovered position_id {position_id} for {tx_type}")

        # Step 3: Get pool information from position or event data
        pool_address = None
        pool_name = event_data.get('pool_name')

        if position_id:
            # Try to get pool info from position table
            from app.database.models import Position
            from sqlalchemy import select

            stmt = select(Position).where(Position.token_id == position_id)
            result = await self.db.execute(stmt)
            position = result.scalar_one_or_none()

            if position:
                pool_address = position.pool_address
                if position.pool_name and not pool_name:
                    pool_name = position.pool_name
                    event_data['pool_name'] = pool_name

        # Step 4: If no pool_address from position, try event data
        if not pool_address:
            pool_address = event_data.get('pool') or details.get('pool')

        # Step 5: If we have pool_address but no pool_name, fetch it
        if pool_address and not pool_name:
            fetched_name = await self._get_pool_name(pool_address)
            if fetched_name:
                pool_name = fetched_name
                event_data['pool_name'] = pool_name
            else:
                # Fallback: use abbreviated pool address
                event_data['pool_name'] = f"Pool-{pool_address[:6]}...{pool_address[-4:]}"
                logger.warning(f"Using fallback pool name for {pool_address}")

        # Step 6: Store all discovered IDs in event_data for consistency
        if position_id:
            event_data['nft_token_id'] = position_id
            event_data['token_id'] = position_id
            event_data['position_id'] = position_id

        if pool_address:
            event_data['pool'] = pool_address

        # Step 7: Flag if data is incomplete for review
        if tx_type in ['POSITION_CREATED', 'POSITION_CLOSED', 'STAKING']:
            if not position_id or not pool_name or pool_name.startswith('Pool-'):
                event_data['needs_review'] = True
                event_data['missing_fields'] = []
                if not position_id:
                    event_data['missing_fields'].append('position_id')
                    logger.error(f"Missing position_id for {tx_type} - tx_hash: {details.get('tx_hash', 'unknown')}")
                if not pool_name:
                    event_data['missing_fields'].append('pool_name')
                    logger.error(f"Missing pool_name for {tx_type} - position_id: {position_id}, tx_hash: {details.get('tx_hash', 'unknown')}")
                elif pool_name.startswith('Pool-'):
                    event_data['missing_fields'].append('pool_name_incomplete')
                    logger.warning(f"Using fallback pool_name for {tx_type} - position_id: {position_id}")

        return position_id, event_data

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
    
    async def _fetch_rpc_logs(self, tx_hash: str) -> List[Dict]:
        """Fetch transaction logs directly from RPC when CDP data is incomplete."""
        try:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(settings.rpc_url))

            logger.info(f"Fetching RPC logs for tx {tx_hash[:10]}...")
            receipt = w3.eth.get_transaction_receipt(tx_hash)

            # Convert logs to dict format similar to CDP traces
            logs = []
            for log in receipt.logs:
                logs.append({
                    "address": log.address.lower(),
                    "topics": [topic.hex() if hasattr(topic, 'hex') else str(topic) for topic in log.topics],
                    "data": log.data.hex() if hasattr(log.data, 'hex') else log.data
                })

            logger.info(f"Found {len(logs)} logs from RPC for {tx_hash[:10]}...")
            return logs
        except Exception as e:
            logger.error(f"Failed to fetch RPC logs for {tx_hash}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    async def _analyze_position_event(
        self,
        traces: List[Dict],
        cdp_wallet: str,
        owner_wallet: str = None,
        tx_hash: str = None
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
                                # Only set if we don't already have a definitive burn event
                                if not (position_event and position_event.get("is_definitive")):
                                    position_event = {
                                        "method_sig": "0xe0891d91",  # closePosition method signature
                                        "method_name": "closePosition",
                                        "event_detected": "PositionClosed",
                                        "event_signature": event_sig_normalized
                                    }
                            elif "positionopened" in log_str or "position opened" in log_str:
                                position_event = {
                                    "method_sig": trace.get("input", "")[:10] if trace.get("input") else "0x3a1e3569",
                                    "method_name": "openPosition",
                                    "event_detected": "PositionOpened",
                                    "event_signature": event_sig_normalized
                                }
                                break  # This is definitive

                            # Check for PositionCreated event from Liquidity Manager
                            # Event signature: PositionCreated(address indexed user, uint256 indexed positionId, address indexed pool, ...)
                            elif event_sig_normalized == "0x8d53117d19441d0a7f168d2728ff066eed66d078efdaf9bf249eef6e20887ae5":
                                log_address = log.get("address", "").lower() if log.get("address") else ""

                                # Check if this is from the Liquidity Manager
                                if log_address == self.LIQUIDITY_MANAGER:
                                    logger.debug(f"Found PositionCreated event from Liquidity Manager")

                                    # Extract indexed parameters
                                    if len(topics) >= 4:
                                        try:
                                            # Topic 1: user address (CDP wallet)
                                            user_addr = ("0x" + topics[1][-40:] if isinstance(topics[1], str) else "0x" + str(topics[1])[-40:]).lower()
                                            # Topic 2: position ID (NFT token ID)
                                            position_id = int(topics[2].hex() if hasattr(topics[2], 'hex') else topics[2], 16)
                                            # Topic 3: pool address
                                            pool_addr = ("0x" + topics[3][-40:] if isinstance(topics[3], str) else "0x" + str(topics[3])[-40:]).lower()

                                            if user_addr == cdp_wallet:
                                                logger.info(f"✅ Detected PositionCreated for CDP wallet: position {position_id} in pool {pool_addr}")
                                                position_event = {
                                                    "method_sig": "0x3a1e3569",  # openPosition method signature
                                                    "method_name": "openPosition",
                                                    "nft_token_id": position_id,
                                                    "pool": pool_addr,
                                                    "event_detected": "PositionCreated",
                                                    "event_signature": event_sig_normalized
                                                }
                                                logger.info(f"✅ Position event created with NFT ID: {position_id}")
                                        except (ValueError, TypeError, AttributeError) as e:
                                            logger.warning(f"Failed to parse PositionCreated event: {e}")

                            # Check for PositionClosed event from Liquidity Manager (if it exists)
                            # Event signature would be similar: PositionClosed(address indexed user, uint256 indexed positionId, ...)
                            elif event_sig_normalized == "0x1234567890abcdef":  # TODO: Find actual PositionClosed event signature
                                log_address = log.get("address", "").lower() if log.get("address") else ""

                                if log_address == self.LIQUIDITY_MANAGER:
                                    logger.debug(f"Found PositionClosed event from Liquidity Manager")
                                    # Similar parsing logic for PositionClosed
                                    if len(topics) >= 2:
                                        try:
                                            position_id = int(topics[1].hex() if hasattr(topics[1], 'hex') else topics[1], 16)
                                            position_event = {
                                                "method_sig": "0xe0891d91",  # closePosition method signature
                                                "method_name": "closePosition",
                                                "nft_token_id": position_id,
                                                "event_detected": "PositionClosed",
                                                "event_signature": event_sig_normalized
                                            }
                                        except (ValueError, TypeError, AttributeError) as e:
                                            logger.warning(f"Failed to parse PositionClosed event: {e}")

                            # Check for ERC721 Transfer events (NFT minting, burning, and staking)
                            elif event_sig_normalized == ERC721_TRANSFER_EVENT.lower():
                                # Check if this is from the NFT Position Manager contract
                                log_address = log.get("address", "").lower() if log.get("address") else ""
                                logger.debug(f"Found ERC721 Transfer event from {log_address}, NFT Manager: {self.NFT_POSITION_MANAGER}")

                                # Accept NFTs from Position Manager
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

                                            # Check for MINT (position creation) - from address 0x0 to CDP wallet
                                            zero_address = "0x" + "0" * 40
                                            if from_addr == zero_address and to_addr == cdp_wallet and nft_token_id:
                                                logger.debug(f"Detected NFT mint to CDP wallet: token {nft_token_id}")
                                                # Don't override if we already have a position event, just add the NFT ID
                                                if position_event and position_event.get("method_name") == "openPosition":
                                                    position_event["nft_token_id"] = nft_token_id
                                                else:
                                                    position_event = {
                                                        "method_sig": "0x3a1e3569",  # openPosition method signature
                                                        "method_name": "openPosition",
                                                        "nft_token_id": nft_token_id,
                                                        "event_detected": "ERC721Mint",
                                                        "event_signature": event_sig_normalized
                                                    }

                                            # Check for BURN (position close) - from CDP wallet to address 0x0
                                            elif from_addr == cdp_wallet and to_addr == zero_address and nft_token_id:
                                                logger.debug(f"Detected NFT burn from CDP wallet: token {nft_token_id}")
                                                # NFT burn is the most reliable indicator of position close
                                                # Always use this as the primary event for POSITION_CLOSED
                                                position_event = {
                                                    "method_sig": "0xe0891d91",  # closePosition method signature
                                                    "method_name": "closePosition",
                                                    "nft_token_id": nft_token_id,
                                                    "event_detected": "ERC721Burn",
                                                    "event_signature": event_sig_normalized,
                                                    "is_definitive": True  # Mark this as definitive position close
                                                }
                                                # Stop looking for other events once we find a burn
                                                break

                                            # Check if this is a stake (CDP wallet transferring NFT to a gauge)
                                            elif from_addr == cdp_wallet and nft_token_id and to_addr != zero_address:
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

        # PRIORITY 1.5: If no position event found in CDP traces and we have a tx_hash,
        # fetch logs directly from RPC as CDP might not include all events
        if not position_event and tx_hash:
            logger.info(f"No position event in CDP data for {tx_hash[:10]}..., fetching from RPC")
            rpc_logs = await self._fetch_rpc_logs(tx_hash)

            # Check RPC logs for PositionCreated or PositionClosed events from Liquidity Manager
            liquidity_manager_lower = self.LIQUIDITY_MANAGER.lower()
            logger.info(f"Looking for Position events from Liquidity Manager: {liquidity_manager_lower}")

            for i, log in enumerate(rpc_logs):
                if not log.get("topics"):
                    continue

                event_sig = log["topics"][0].lower() if log["topics"] else None
                log_address = log["address"].lower()

                # Log all events from Liquidity Manager for debugging
                if log_address == liquidity_manager_lower:
                    logger.info(f"Log #{i} from Liquidity Manager: sig={event_sig[:10]}...")

                # Check for PositionCreated event (0x8d53117d...)
                # Note: RPC returns signatures without 0x prefix, CDP with prefix
                position_created_sig = "8d53117d19441d0a7f168d2728ff066eed66d078efdaf9bf249eef6e20887ae5"
                position_closed_sig = "f98d21d5137adb0b9f5e1aefb5c39fa87946c23d83391239e912a27362e2a3f5"

                # Check for PositionCreated event
                if (event_sig == position_created_sig or event_sig == f"0x{position_created_sig}") and log_address == liquidity_manager_lower:
                    if len(log["topics"]) >= 4:
                        try:
                            # Extract position details from PositionCreated event
                            user_addr = ("0x" + log["topics"][1][-40:]).lower()
                            position_id = int(log["topics"][2], 16)
                            pool_addr = ("0x" + log["topics"][3][-40:]).lower()

                            if user_addr == cdp_wallet:
                                logger.info(f"✅ Found PositionCreated in RPC logs: position {position_id} in pool {pool_addr}")
                                position_event = {
                                    "method_sig": "0x3a1e3569",
                                    "method_name": "openPosition",
                                    "nft_token_id": position_id,
                                    "pool": pool_addr,
                                    "event_detected": "PositionCreated_RPC",
                                    "event_signature": event_sig
                                }
                                break
                        except Exception as e:
                            logger.warning(f"Failed to parse RPC PositionCreated event: {e}")

                # Check for PositionClosed event
                if (event_sig == position_closed_sig or event_sig == f"0x{position_closed_sig}") and log_address == liquidity_manager_lower:
                    if len(log["topics"]) >= 3:
                        try:
                            # Extract position details from PositionClosed event
                            # PositionClosed(address indexed user, uint256 indexed positionId)
                            user_addr = ("0x" + log["topics"][1][-40:]).lower()
                            position_id = int(log["topics"][2], 16)

                            if user_addr == cdp_wallet:
                                logger.info(f"✅ Found PositionClosed in RPC logs: position {position_id}")
                                position_event = {
                                    "method_sig": "0xe0891d91",  # closePosition method signature
                                    "method_name": "closePosition",
                                    "nft_token_id": position_id,
                                    "event_detected": "PositionClosed_RPC",
                                    "event_signature": event_sig
                                }
                                break
                        except Exception as e:
                            logger.warning(f"Failed to parse RPC PositionClosed event: {e}")

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

                # Check for LiquidityManager interaction
                # Relaxed check: allow indirect calls (not just from CDP wallet)
                if not position_event and to_addr == self.LIQUIDITY_MANAGER:
                    if len(input_data) >= 10:
                        method_sig = input_data[:10]

                        # Check if it's a known position method
                        if method_sig in self.POSITION_METHOD_SIGNATURES:
                            position_event = {
                                "method_sig": method_sig,
                                "method_name": self.POSITION_METHOD_SIGNATURES[method_sig],
                                "event_detected": "method_signature_fallback",
                                "from_address": from_addr
                            }
                            logger.info(f"Detected position event via method signature: {method_sig} from {from_addr[:10]}...")
                        # Also check for other potential close position signatures
                        elif method_sig in ["0xfcdf9752", "0x8e005082", "0x4f1eb3d8"]:  # Other possible closePosition variants
                            position_event = {
                                "method_sig": method_sig,
                                "method_name": "closePosition",
                                "event_detected": "alternative_close_signature",
                                "from_address": from_addr
                            }
                            logger.info(f"Detected position close via alternative signature: {method_sig}")

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
        
        # Final fallback: If we have significant USDC/AERO flows but no position event detected,
        # check if this might be a position close based on token flows
        # BUT: Don't confuse deposits (from owner wallet) with position closes (from pools/contracts)
        if not position_event and (usdc_flows["in"] > 0 or aero_flows["in"] > 0):
            # Look for patterns that suggest position activity
            is_likely_close = False

            # Check if USDC is coming from a non-owner source (likely a pool or liquidity manager)
            # We need to distinguish between deposits and position closes
            is_from_owner = False
            if owner_wallet:  # Only check if owner_wallet is provided
                for trace in traces:
                    to_addr = trace.get("to", "").lower()
                    if to_addr == self.USDC_ADDRESS:
                        decoded = self._decode_erc20_input(trace.get("input", ""))
                        if decoded and decoded.get("method") == "transfer":
                            from_addr = trace.get("from", "").lower()
                            if from_addr == owner_wallet.lower():
                                is_from_owner = True
                                break

            # Only consider position close if USDC is NOT from owner wallet
            if not is_from_owner:
                # Pattern 1: Both USDC and AERO coming IN (classic position close)
                if usdc_flows["in"] > 0 and aero_flows["in"] > 0:
                    is_likely_close = True
                    logger.info(f"Detected likely position close based on token flows: USDC in={usdc_flows['in']}, AERO in={aero_flows['in']}")

                # Pattern 2: Significant USDC coming IN with no USDC going OUT (pure return)
                # Only if it's NOT from the owner wallet (which would be a deposit)
                elif usdc_flows["in"] > 1000 and usdc_flows["out"] == 0:  # More than 1000 USDC returned
                    is_likely_close = True
                    logger.info(f"Detected likely position close based on USDC return: {usdc_flows['in']} USDC")

            if is_likely_close:
                position_event = {
                    "method_sig": "0xe0891d91",  # Default closePosition signature
                    "method_name": "closePosition",
                    "event_detected": "flow_pattern_detection",
                    "detected_reason": f"USDC_in={usdc_flows['in']}, AERO_in={aero_flows['in']}"
                }
                logger.warning(f"Using flow pattern detection for potential position close")

        if position_event:
            # Don't use pool addresses from traces - they're often wrong
            # The actual pool address should be looked up from the position NFT
            # Only include pool if we're confident it's correct
            # BUT: If we already have a pool from a PositionCreated event, keep it!
            position_event.update({
                "usdc_in": usdc_flows["in"],
                "usdc_out": usdc_flows["out"],
                "aero_in": aero_flows["in"],
                "aero_out": aero_flows["out"]
            })
            # Only set pool to None if we don't already have one from an event
            if "pool" not in position_event:
                position_event["pool"] = None  # Will be fetched from position data later

            # Log the complete position event for debugging
            logger.info(f"✅ Final position_event: method={position_event.get('method_name')}, nft_id={position_event.get('nft_token_id')}, usdc_out={position_event.get('usdc_out')}, usdc_in={position_event.get('usdc_in')}")
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
            "description": "",
            "cdp_wallet": cdp_wallet  # Always include CDP wallet
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
        # Extract tx_hash from details for RPC fallback
        tx_hash = details.get("tx_hash")
        position_event = await self._analyze_position_event(traces, cdp_wallet, owner_wallet, tx_hash)

        # Debug logging for transactions that might be position events but weren't detected
        if not position_event:
            # Check if this looks like it might be a position event based on flows
            has_significant_usdc = False
            has_significant_aero = False

            for trace in traces:
                to_addr = trace.get("to", "").lower()

                # Check for any interaction with liquidity-related contracts
                if to_addr == self.LIQUIDITY_MANAGER:
                    logger.warning(f"Transaction {details['tx_hash'][:10]}... interacts with LiquidityManager but wasn't detected as position event")
                    logger.warning(f"  From: {trace.get('from', '')[:10]}... To: {to_addr[:10]}...")
                    logger.warning(f"  Method sig: {trace.get('input', '')[:10] if trace.get('input') else 'none'}")

                # Check for NFT burns (which would indicate position close)
                if "logs" in trace:
                    for log in trace.get("logs", []):
                        topics = log.get("topics", [])
                        if topics and len(topics) >= 4:
                            # ERC721 Transfer event
                            if topics[0] and "ddf252ad" in str(topics[0]).lower():
                                # Check if it's a burn (to address 0x0)
                                to_addr_hex = topics[2][-40:] if len(topics) > 2 else ""
                                if to_addr_hex == "0" * 40:
                                    logger.warning(f"Transaction {details['tx_hash'][:10]}... has NFT burn but wasn't detected as POSITION_CLOSED")

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
            method_sig = position_event.get("method_sig", "")

            # Additional logic: detect swaps and position closes based on token flows
            # TOKEN FLOWS ARE MORE RELIABLE THAN METHOD SIGNATURES

            # POSITION_CLOSED: Check token flows to determine if this is actually a close
            # Prioritize flow patterns over method signatures as they're more reliable

            # Pattern 1: Both USDC and AERO coming IN (classic position close)
            # BUT: Must have an NFT burn or a valid position_id to be a real close
            if position_event["usdc_in"] > 0 and position_event["aero_in"] > 0:
                # Check if we have evidence of an actual position being closed
                has_nft_burn = position_event.get("event_detected") == "ERC721Burn"
                has_position_id = position_event.get("nft_token_id") is not None

                if has_nft_burn or has_position_id:
                    # This is definitely a position close
                    method_name = "closePosition"
                    position_event["method_name"] = "closePosition"
                    logger.info(f"Overriding method based on flows: USDC+AERO IN with NFT indicates close (was {method_name})")
                else:
                    # Tokens coming in but no NFT activity - likely a failed tx or swap
                    logger.warning(f"USDC+AERO IN but no NFT burn/ID - not a position close: {details['tx_hash'][:10]}...")
                    return TransactionType.UNKNOWN, details

            # Pattern 2: Significant USDC coming IN with minimal/no USDC OUT
            # This happens when closing a position that only had USDC liquidity
            # BUT: Must have NFT evidence to be a real position close
            elif position_event["usdc_in"] > 1000 and position_event["usdc_out"] < position_event["usdc_in"] * 0.1:
                # Check for NFT evidence
                has_nft_burn = position_event.get("event_detected") == "ERC721Burn"
                has_position_id = position_event.get("nft_token_id") is not None

                if has_nft_burn or has_position_id:
                    # Net positive USDC flow with NFT activity suggests position close
                    method_name = "closePosition"
                    position_event["method_name"] = "closePosition"
                    logger.info(f"Overriding method based on large USDC return with NFT: {position_event['usdc_in']} USDC IN (was {method_name})")
                else:
                    # Large USDC in but no NFT - might be a deposit or failed tx
                    logger.warning(f"Large USDC IN but no NFT activity - not a position close: {details['tx_hash'][:10]}...")
                    # Don't mark as UNKNOWN yet, let it fall through to other checks

            # SWAP: AERO (and possibly USDC) goes OUT and net USDC comes IN
            # This happens when swapping tokens, potentially with some USDC out too
            # BUT: Require meaningful amounts to avoid false positives on empty/failed txs
            elif position_event["aero_out"] > 0 and position_event["usdc_in"] > 0:
                # Check if amounts are meaningful (at least $1 worth)
                if position_event["aero_out"] < 0.01 and position_event["usdc_in"] < 1:
                    # Too small to be a real swap, likely an empty/failed transaction
                    logger.info(f"Skipping tiny amounts as swap: AERO={position_event['aero_out']}, USDC={position_event['usdc_in']}")
                    return TransactionType.UNKNOWN, details

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

                return TransactionType.SWAP, details

            if method_name == "openPosition":
                # For position creation, the net amount is what the user actually invested (usdc_out - usdc_in)
                # usdc_out is what left the wallet, usdc_in is what came back (if any)
                net_amount = position_event["usdc_out"] - position_event["usdc_in"]

                # IMPORTANT: Check for NFT mint first - this is the most reliable indicator
                has_nft_mint = position_event.get("nft_token_id") is not None

                # Skip if no NFT was actually minted (no position created)
                # This prevents saving empty/failed transactions as POSITION_CREATED
                if not has_nft_mint:
                    logger.warning(f"Skipping openPosition without NFT mint (likely failed/empty tx): {details['tx_hash'][:10]}...")
                    return TransactionType.UNKNOWN, details

                # Allow 0-value positions if there's an NFT mint (e.g., gauge-minted positions)
                # But skip negative amounts as those indicate errors
                if net_amount < 0:
                    logger.warning(f"Skipping openPosition with negative net amount: {details['tx_hash'][:10]}...")
                    return TransactionType.UNKNOWN, details
                elif net_amount == 0 and has_nft_mint:
                    logger.info(f"Position created with 0 USDC (gauge-minted or special position): {details['tx_hash'][:10]}...")

                details["amount"] = net_amount
                details["description"] = f"Position opened via LiquidityManager"
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

                return TransactionType.POSITION_CREATED, details

            elif method_name == "closePosition":
                # For position closing, the amount received back is what matters
                # This is typically usdc_in (what comes back to wallet) plus any AERO converted to USDC
                amount_received = position_event["usdc_in"]

                # Don't skip closePosition transactions even if amount is 0
                # Some positions might close with only AERO rewards and no USDC
                # The important indicator is the NFT burn or the method itself

                details["amount"] = amount_received
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

                logger.info(f"Detected POSITION_CLOSED: {details['tx_hash'][:10]}... Amount: {amount_received} USDC, NFT: {details.get('nft_token_id')}")
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

                    # FEE_TRANSFER: CDP wallet sending USDC to fee recipient
                    elif from_addr == cdp_wallet and recipient == self.FEE_RECIPIENT:
                        details["amount"] = amount
                        details["description"] = f"Fee transfer to {self.FEE_RECIPIENT}"
                        details["fee_recipient"] = self.FEE_RECIPIENT
                        return TransactionType.FEE_TRANSFER, details
                
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

                    # FEE_TRANSFER: CDP wallet sending USDC to fee recipient
                    elif transfer_from == cdp_wallet and transfer_to == self.FEE_RECIPIENT:
                        details["amount"] = amount
                        details["description"] = f"Fee transfer to {self.FEE_RECIPIENT}"
                        details["fee_recipient"] = self.FEE_RECIPIENT
                        return TransactionType.FEE_TRANSFER, details
            
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
            TransactionType.SWAP: [],
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
                              TransactionType.SWAP, TransactionType.STAKING]:
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
            "swaps": len(categorized[TransactionType.SWAP]),
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
        from sqlalchemy import select, and_

        # Check if transaction already exists by tx_hash
        stmt = select(Transaction).where(
            Transaction.tx_hash == details["tx_hash"]
        )
        result = await self.db.execute(stmt)
        existing_tx = result.scalar_one_or_none()

        # For POSITION_CLOSED, also check if this position already has a close transaction
        if not existing_tx and tx_type == "POSITION_CLOSED":
            nft_token_id = details.get("nft_token_id")
            if nft_token_id:
                # Check if this position already has a POSITION_CLOSED transaction
                stmt = select(Transaction).where(
                    and_(
                        Transaction.user_id == user_id,
                        Transaction.position_id == nft_token_id,
                        Transaction.tx_type == "POSITION_CLOSED"
                    )
                )
                result = await self.db.execute(stmt)
                existing_close = result.scalar_one_or_none()

                if existing_close:
                    logger.warning(f"Position {nft_token_id} already has a POSITION_CLOSED transaction, skipping duplicate")
                    return

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
            if tx_type in ["POSITION_CREATED", "POSITION_CLOSED", "SWAP", "STAKING", "FEE_TRANSFER"]:
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

                # Add fee recipient for FEE_TRANSFER transactions
                if tx_type == "FEE_TRANSFER" and details.get("fee_recipient"):
                    event_data["fee_recipient"] = details["fee_recipient"]

                # The position and pool data fetching is now handled by _ensure_position_data
                # Just pass through any initial data we have
                if details.get("nft_token_id"):
                    event_data["nft_token_id"] = details["nft_token_id"]
                if details.get("pool_name"):
                    event_data["pool_name"] = details["pool_name"]
                if details.get("pool"):
                    event_data["pool"] = details["pool"]
            
            # Store the USDC amount in event_data to avoid conflict with property
            event_data["amount_usdc"] = float(amount_usdc)

            # Ensure complete data for position-related transactions
            position_id_value, event_data = await self._ensure_position_data(
                tx_type, event_data, details, user_id
            )

            # For non-position transactions, check if we still have a position_id
            if position_id_value is None:
                # Extract nft_token_id from details or event_data for backward compatibility
                nft_id = details.get("nft_token_id") or event_data.get("nft_token_id")
                if nft_id:
                    position_id_value = nft_id

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

            # If this is a POSITION_CREATED transaction, create the position
            if tx_type == "POSITION_CREATED" and position_id_value:
                await self._create_position_if_needed(
                    user_id=user_id,
                    position_id=position_id_value,
                    pool_address=event_data.get("pool"),
                    pool_name=event_data.get("pool_name"),
                    tx_hash=details["tx_hash"],
                    amount_usdc=amount_usdc
                )

            # If this is a STAKING transaction, update position's staked status
            elif tx_type == "STAKING" and position_id_value:
                await self._update_position_staking(
                    user_id=user_id,
                    position_id=position_id_value,
                    gauge_address=event_data.get("gauge_address")
                )

            # If this is a POSITION_CLOSED transaction, update the position status
            elif tx_type == "POSITION_CLOSED":
                if nft_id:
                    logger.info(f"Closing position {nft_id} for tx {details['tx_hash'][:10]}...")
                    await self._close_position_if_needed(user_id, nft_id, details["tx_hash"], amount_usdc)
                else:
                    # Try to find the position to close based on transaction timing and amount
                    logger.warning(f"POSITION_CLOSED detected without NFT ID, attempting to find position...")
                    found_position_id = await self._find_position_to_close(user_id, amount_usdc, details)
                    if found_position_id:
                        logger.info(f"Found position {found_position_id} to close for tx {details['tx_hash'][:10]}...")
                        await self._close_position_if_needed(user_id, found_position_id, details["tx_hash"], amount_usdc)
                        # Update the transaction with the found position_id
                        transaction.position_id = found_position_id
                        if not transaction.event_data:
                            transaction.event_data = {}
                        transaction.event_data["nft_token_id"] = found_position_id
                    else:
                        logger.error(f"Could not find position to close for tx {details['tx_hash'][:10]}... Amount: {amount_usdc}")
        else:
            # Update existing transaction if needed
            if existing_tx.tx_type == "UNKNOWN" and tx_type != "UNKNOWN":
                existing_tx.tx_type = tx_type
                existing_tx.event_data = existing_tx.event_data or {}
                existing_tx.event_data["recategorized"] = True
                existing_tx.event_data["description"] = details.get("description", "")
                logger.info(f"Recategorized transaction {details['tx_hash'][:10]}... as {tx_type}")

            # IMPORTANT: Check if this is a POSITION_CREATED transaction that hasn't created its position yet
            if existing_tx.tx_type == "POSITION_CREATED":
                # Get position_id from either the column or event_data
                position_id = existing_tx.position_id
                if not position_id and existing_tx.event_data:
                    position_id = existing_tx.event_data.get('position_id') or existing_tx.event_data.get('nft_token_id') or existing_tx.event_data.get('token_id')

                # Convert to int if it's a string
                if position_id and isinstance(position_id, str):
                    try:
                        position_id = int(position_id)
                    except (ValueError, TypeError):
                        logger.error(f"Invalid position_id format: {position_id}")
                        position_id = None

                if position_id:
                    # Check if the position exists
                    from app.database.models import Position
                    from sqlalchemy import select, and_

                    check_stmt = select(Position).where(
                        and_(
                            Position.token_id == position_id,
                            Position.user_id == existing_tx.user_id
                        )
                    )
                    result = await self.db.execute(check_stmt)
                    position = result.scalar_one_or_none()

                    if not position:
                        logger.warning(f"Found POSITION_CREATED transaction without position {position_id}, creating it now...")
                        # Get data from event_data
                        amount_usdc = Decimal(str(existing_tx.event_data.get('amount_usdc', 0))) if existing_tx.event_data else Decimal(0)
                        pool_address = existing_tx.event_data.get('pool') if existing_tx.event_data else None
                        pool_name = existing_tx.event_data.get('pool_name') if existing_tx.event_data else None

                        await self._create_position_if_needed(
                            user_id=existing_tx.user_id,
                            position_id=position_id,
                            pool_address=pool_address,
                            pool_name=pool_name,
                            tx_hash=existing_tx.tx_hash,
                            amount_usdc=amount_usdc
                        )

            # IMPORTANT: Check if this is a STAKING transaction that hasn't updated its position yet
            elif existing_tx.tx_type == "STAKING":
                # Get position_id from either the column or event_data
                position_id = existing_tx.position_id
                if not position_id and existing_tx.event_data:
                    position_id = existing_tx.event_data.get('position_id') or existing_tx.event_data.get('nft_token_id') or existing_tx.event_data.get('token_id')

                # Convert to int if it's a string
                if position_id and isinstance(position_id, str):
                    try:
                        position_id = int(position_id)
                    except (ValueError, TypeError):
                        logger.error(f"Invalid position_id format: {position_id}")
                        position_id = None

                if position_id:
                    # Check if the position exists and needs staking update
                    from app.database.models import Position
                    from sqlalchemy import select, and_

                    check_stmt = select(Position).where(
                        and_(
                            Position.token_id == position_id,
                            Position.user_id == existing_tx.user_id
                        )
                    )
                    result = await self.db.execute(check_stmt)
                    position = result.scalar_one_or_none()

                    if position and not position.staked:
                        logger.warning(f"Found STAKING transaction for unstaked position {position_id}, updating it now...")
                        gauge_address = existing_tx.event_data.get('gauge_address') if existing_tx.event_data else None

                        await self._update_position_staking(
                            user_id=existing_tx.user_id,
                            position_id=position_id,
                            gauge_address=gauge_address
                        )

            # IMPORTANT: Check if this is a POSITION_CLOSED transaction that hasn't closed its position yet
            elif existing_tx.tx_type == "POSITION_CLOSED" and existing_tx.position_id:
                # Check if the position is still ACTIVE
                from app.database.models import Position
                from sqlalchemy import select, and_

                check_stmt = select(Position).where(
                    and_(
                        Position.token_id == existing_tx.position_id,
                        Position.user_id == existing_tx.user_id,
                        Position.status == 'ACTIVE'
                    )
                )
                result = await self.db.execute(check_stmt)
                active_position = result.scalar_one_or_none()

                if active_position:
                    logger.warning(f"Found POSITION_CLOSED transaction with ACTIVE position {existing_tx.position_id}, closing it now...")
                    # Use the amount from event_data
                    amount_usdc = Decimal(str(existing_tx.event_data.get('amount_usdc', 0))) if existing_tx.event_data else Decimal(0)
                    await self._close_position_if_needed(
                        existing_tx.user_id,
                        existing_tx.position_id,
                        existing_tx.tx_hash,
                        amount_usdc
                    )

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

    async def _find_position_to_close(
        self,
        user_id: str,
        amount_usdc: Decimal,
        details: Dict[str, Any]
    ) -> Optional[int]:
        """Find an active position to close when we don't have the NFT ID."""
        from app.database.models import Position
        from sqlalchemy import select, and_

        try:
            # Look for the most recently created ACTIVE position for this user
            # This is a reasonable assumption since positions are usually closed in order
            stmt = select(Position).where(
                and_(
                    Position.user_id == user_id,
                    Position.status == 'ACTIVE'
                )
            ).order_by(Position.created_at.desc())

            result = await self.db.execute(stmt)
            positions = result.scalars().all()

            if len(positions) == 1:
                # If there's only one active position, it must be the one being closed
                logger.info(f"Found single active position {positions[0].token_id} to close")
                return positions[0].token_id

            elif len(positions) > 1:
                # Multiple active positions - try to match by expected return amount
                # The position with entry_amount closest to the return amount is likely the one
                best_match = None
                best_diff = float('inf')

                for position in positions:
                    # Check if return amount is reasonable for this position
                    # (typically 80-120% of entry amount for normal closes)
                    diff = abs(float(position.entry_amount_usdc) - float(amount_usdc))
                    if diff < best_diff:
                        best_diff = diff
                        best_match = position

                if best_match and best_diff < float(amount_usdc) * 0.5:  # Within 50% of return amount
                    logger.info(f"Found best matching position {best_match.token_id} with entry {best_match.entry_amount_usdc} USDC")
                    return best_match.token_id
                else:
                    logger.warning(f"Could not confidently match position. Found {len(positions)} active positions")

            return None

        except Exception as e:
            logger.error(f"Error finding position to close: {e}")
            return None

    async def ensure_positions_for_transactions(self, user_id: str) -> None:
        """Ensure all POSITION_CREATED transactions have corresponding Position records."""
        from app.database.models import Transaction, Position
        from sqlalchemy import select, and_

        try:
            # Get all POSITION_CREATED transactions for user
            stmt = select(Transaction).where(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.tx_type == "POSITION_CREATED"
                )
            )
            result = await self.db.execute(stmt)
            position_created_txs = result.scalars().all()

            for tx in position_created_txs:
                # Get position_id from either column or event_data
                position_id = tx.position_id
                if not position_id and tx.event_data:
                    position_id = tx.event_data.get('position_id') or tx.event_data.get('nft_token_id') or tx.event_data.get('token_id')

                # Convert to int if string
                if position_id and isinstance(position_id, str):
                    try:
                        position_id = int(position_id)
                    except (ValueError, TypeError):
                        continue

                if position_id:
                    # Check if position exists
                    check_stmt = select(Position).where(
                        and_(
                            Position.token_id == position_id,
                            Position.user_id == user_id
                        )
                    )
                    result = await self.db.execute(check_stmt)
                    position = result.scalar_one_or_none()

                    if not position:
                        # Create position
                        logger.info(f"Creating missing position {position_id} for user {user_id}")
                        amount_usdc = Decimal(str(tx.event_data.get('amount_usdc', 0))) if tx.event_data else Decimal(0)
                        pool_address = tx.event_data.get('pool') if tx.event_data else None
                        pool_name = tx.event_data.get('pool_name') if tx.event_data else None

                        await self._create_position_if_needed(
                            user_id=user_id,
                            position_id=position_id,
                            pool_address=pool_address,
                            pool_name=pool_name,
                            tx_hash=tx.tx_hash,
                            amount_usdc=amount_usdc
                        )

            # Also check STAKING transactions to update positions
            stmt = select(Transaction).where(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.tx_type == "STAKING"
                )
            )
            result = await self.db.execute(stmt)
            staking_txs = result.scalars().all()

            for tx in staking_txs:
                # Get position_id
                position_id = tx.position_id
                if not position_id and tx.event_data:
                    position_id = tx.event_data.get('position_id') or tx.event_data.get('nft_token_id') or tx.event_data.get('token_id')

                # Convert to int if string
                if position_id and isinstance(position_id, str):
                    try:
                        position_id = int(position_id)
                    except (ValueError, TypeError):
                        continue

                if position_id:
                    # Check if position exists and needs staking update
                    check_stmt = select(Position).where(
                        and_(
                            Position.token_id == position_id,
                            Position.user_id == user_id
                        )
                    )
                    result = await self.db.execute(check_stmt)
                    position = result.scalar_one_or_none()

                    if position and not position.staked:
                        gauge_address = tx.event_data.get('gauge_address') if tx.event_data else None
                        await self._update_position_staking(
                            user_id=user_id,
                            position_id=position_id,
                            gauge_address=gauge_address
                        )

        except Exception as e:
            logger.error(f"Error ensuring positions for transactions: {e}")

    async def _update_position_staking(
        self,
        user_id: str,
        position_id: int,
        gauge_address: Optional[str]
    ) -> None:
        """Update position's staking status when a STAKING transaction is detected."""
        from app.database.models import Position
        from sqlalchemy import select, and_

        try:
            # Find the position
            stmt = select(Position).where(
                and_(
                    Position.token_id == position_id,
                    Position.user_id == user_id
                )
            )
            result = await self.db.execute(stmt)
            position = result.scalar_one_or_none()

            if position:
                position.staked = True
                position.gauge_address = gauge_address
                await self.db.commit()
                logger.info(f"Updated position {position_id} as staked to gauge {gauge_address}")
            else:
                logger.warning(f"Position {position_id} not found when trying to update staking status")

        except Exception as e:
            logger.error(f"Failed to update position {position_id} staking status: {e}")

    async def _create_position_if_needed(
        self,
        user_id: str,
        position_id: int,
        pool_address: Optional[str],
        pool_name: Optional[str],
        tx_hash: str,
        amount_usdc: Decimal
    ) -> None:
        """Create a position when a POSITION_CREATED transaction is detected."""
        from app.database.models import Position
        from sqlalchemy import select, and_

        try:
            # Check if position already exists
            stmt = select(Position).where(
                and_(
                    Position.token_id == position_id,
                    Position.user_id == user_id
                )
            )
            result = await self.db.execute(stmt)
            existing_position = result.scalar_one_or_none()

            if existing_position:
                logger.info(f"Position {position_id} already exists for user {user_id}")
                return

            # Create new position
            new_position = Position(
                user_id=user_id,
                token_id=position_id,
                nft_token_id=position_id,  # Same as token_id for compatibility
                pool_address=pool_address,
                pool_name=pool_name,
                status='ACTIVE',
                entry_date=datetime.utcnow(),
                entry_tx_hash=tx_hash,
                entry_amount_usdc=amount_usdc,
                current_value_usdc=amount_usdc,  # Initial value is entry amount
                staked=False,  # Will be updated by STAKING transaction
                liquidity="0",  # Will be fetched from blockchain later
                tick_lower=None,  # Will be fetched from blockchain later
                tick_upper=None   # Will be fetched from blockchain later
            )

            self.db.add(new_position)
            await self.db.commit()
            logger.info(f"Created position {position_id} for user {user_id} in pool {pool_name or pool_address}")

        except Exception as e:
            logger.error(f"Failed to create position {position_id}: {e}")

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