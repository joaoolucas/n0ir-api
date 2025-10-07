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
    WITHDRAW = "WITHDRAW"
    POSITION_CREATED = "POSITION_CREATED"  # Includes staking (positions are auto-staked)
    POSITION_CLOSED = "POSITION_CLOSED"    # Includes swaps and fee transfers
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
    
    async def _batch_fetch_rpc_logs(self, tx_hashes: List[str]) -> Dict[str, List[Dict]]:
        """Batch fetch transaction logs from RPC for multiple transactions in parallel."""
        from web3 import Web3
        import asyncio

        if not tx_hashes:
            return {}

        def _sync_fetch(tx_hash: str):
            try:
                w3 = Web3(Web3.HTTPProvider(settings.rpc_url))
                receipt = w3.eth.get_transaction_receipt(tx_hash)

                # Convert logs to dict format
                logs = []
                for log in receipt.logs:
                    logs.append({
                        "address": log.address.lower(),
                        "topics": [topic.hex() if hasattr(topic, 'hex') else str(topic) for topic in log.topics],
                        "data": log.data.hex() if hasattr(log.data, 'hex') else log.data
                    })
                return tx_hash, logs
            except Exception as e:
                logger.error(f"Failed to fetch RPC logs for {tx_hash[:10]}: {e}")
                return tx_hash, []

        # Run all RPC calls in parallel using thread pool
        results = await asyncio.gather(*[
            asyncio.to_thread(_sync_fetch, tx_hash) for tx_hash in tx_hashes
        ])

        # Convert results to dict
        logs_cache = {tx_hash: logs for tx_hash, logs in results}

        return logs_cache

    async def _fetch_rpc_logs(self, tx_hash: str, logs_cache: Optional[Dict[str, List[Dict]]] = None) -> List[Dict]:
        """Fetch transaction logs directly from RPC when CDP data is incomplete."""
        # Check cache first if provided
        if logs_cache and tx_hash in logs_cache:
            return logs_cache[tx_hash]

        try:
            from web3 import Web3
            import asyncio

            def _sync_fetch():
                w3 = Web3(Web3.HTTPProvider(settings.rpc_url))
                return w3.eth.get_transaction_receipt(tx_hash)

            # Run sync web3 call in thread pool to avoid blocking event loop
            receipt = await asyncio.to_thread(_sync_fetch)

            # Convert logs to dict format similar to CDP traces
            logs = []
            for log in receipt.logs:
                logs.append({
                    "address": log.address.lower(),
                    "topics": [topic.hex() if hasattr(topic, 'hex') else str(topic) for topic in log.topics],
                    "data": log.data.hex() if hasattr(log.data, 'hex') else log.data
                })

            return logs
        except Exception as e:
            logger.error(f"Failed to fetch RPC logs for {tx_hash}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    async def _get_token_price_usd(self, token_address: str) -> float:
        """Get token price in USD."""
        try:
            prices = await pools_service.get_token_prices([token_address])
            price = prices.get(token_address.lower(), 0.0)
            if price > 0:
                return price
            logger.warning(f"Could not get price for token {token_address}, defaulting to 0")
            return 0.0
        except Exception as e:
            logger.error(f"Error fetching token price for {token_address}: {e}")
            return 0.0

    def _calculate_usdc_returned_from_transfers(self, traces: List[Dict], cdp_wallet: str, liquidity_manager: str) -> int:
        """Calculate USDC returned to user by analyzing Transfer events.

        Looks for USDC Transfer from LiquidityManager back to CDP wallet.

        Returns:
            USDC amount returned in wei (6 decimals)
        """
        USDC_ADDRESS = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
        TRANSFER_EVENT_SIG = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"  # Transfer(address,address,uint256)

        usdc_returned = 0

        for trace in traces:
            if "logs" in trace:
                for log in trace.get("logs", []):
                    topics = log.get("topics", [])
                    if not topics:
                        continue

                    log_address = log.get("address", "").lower()
                    event_sig = topics[0].lower() if isinstance(topics[0], str) else str(topics[0]).lower()

                    # Check if this is a USDC Transfer event
                    if log_address == USDC_ADDRESS.lower() and event_sig == TRANSFER_EVENT_SIG.lower():
                        if len(topics) >= 3:
                            try:
                                # Topic 1: from address
                                from_addr = ("0x" + topics[1][-40:] if isinstance(topics[1], str) else "0x" + str(topics[1])[-40:]).lower()
                                # Topic 2: to address
                                to_addr = ("0x" + topics[2][-40:] if isinstance(topics[2], str) else "0x" + str(topics[2])[-40:]).lower()

                                # Check if this is a transfer FROM LiquidityManager TO CDP wallet
                                if from_addr == liquidity_manager.lower() and to_addr == cdp_wallet.lower():
                                    # Parse amount from data field
                                    data = log.get("data", "0x")
                                    if isinstance(data, str):
                                        data = data[2:] if data.startswith("0x") else data
                                    else:
                                        data = data.hex() if hasattr(data, 'hex') else str(data)

                                    if len(data) >= 64:
                                        amount = int(data[0:64], 16)
                                        usdc_returned += amount
                            except Exception as e:
                                logger.warning(f"Failed to parse USDC Transfer event: {e}")

        return usdc_returned

    async def _parse_position_created_data(self, data: str, traces: List[Dict] = None, cdp_wallet: str = None) -> tuple:
        """Parse PositionCreated event data and calculate net USDC.

        Returns:
            Tuple of (event_data dict, usdc_amount in wei, hedge_debt_usd_value for logging)
        """
        event_data = {}
        usdc_amount = 0
        hedge_debt_usd_value = 0

        if len(data) >= 128:
            try:
                # Parse all fields from event data
                # Note: Solidity event encoding pads each value to 32 bytes (64 hex chars)
                liquidity = int(data[0:64], 16)
                usdc_invested = int(data[64:128], 16)
                # tick_lower and tick_upper are int24 (signed 24-bit integers)
                # They're stored in the last 24 bits (6 hex chars) of each 32-byte word
                tick_lower_raw = int(data[186:192], 16) if len(data) >= 192 else 0  # Last 6 hex chars of word
                tick_lower = tick_lower_raw if tick_lower_raw < 2**23 else tick_lower_raw - 2**24
                tick_upper_raw = int(data[250:256], 16) if len(data) >= 256 else 0  # Last 6 hex chars of word
                tick_upper = tick_upper_raw if tick_upper_raw < 2**23 else tick_upper_raw - 2**24
                staked = bool(int(data[256:320], 16)) if len(data) >= 320 else False
                is_hedged = bool(int(data[320:384], 16)) if len(data) >= 384 else False
                hedge_collateral = int(data[384:448], 16) if len(data) >= 448 else 0
                hedge_debt = int(data[448:512], 16) if len(data) >= 512 else 0
                hedged_asset = "0x" + data[536:576] if len(data) >= 576 else "0x0"

                event_data = {
                    "liquidity": liquidity,
                    "usdc_invested": usdc_invested,
                    "tick_lower": tick_lower,
                    "tick_upper": tick_upper,
                    "staked": staked,
                    "is_hedged": is_hedged,
                    "hedge_collateral": hedge_collateral,
                    "hedge_debt": hedge_debt,
                    "hedged_asset": hedged_asset
                }

                # Calculate net USDC amount
                # Net = LP investment + collateral - borrowed amount (in USD)
                hedge_debt_usd = 0

                if is_hedged and hedge_debt > 0 and hedged_asset != "0x0":
                    try:
                        # Get token decimals (WETH = 18, cbBTC = 8)
                        token_decimals = 18 if "0x42000000" in hedged_asset else 8
                        hedge_debt_tokens = hedge_debt / (10 ** token_decimals)

                        # Get token price
                        token_price = await self._get_token_price_usd(hedged_asset)
                        if token_price > 0:
                            hedge_debt_usd = int(hedge_debt_tokens * token_price * 1e6)  # Convert to USDC wei
                            hedge_debt_usd_value = hedge_debt_usd / 1e6
                        else:
                            logger.warning(f"Could not get price for hedged asset {hedged_asset}, setting hedge_debt_usd to 0")
                    except Exception as price_error:
                        logger.error(f"Error calculating hedge debt USD: {price_error}")
                        hedge_debt_usd = 0

                # Store hedge info in event_data for reference
                event_data["hedge_debt_usd"] = hedge_debt_usd_value

                # Calculate USDC returned from transfer logs if available
                usdc_returned = 0
                if traces and cdp_wallet:
                    usdc_returned = self._calculate_usdc_returned_from_transfers(traces, cdp_wallet, self.LIQUIDITY_MANAGER)
                    if usdc_returned > 0:
                        event_data["usdc_returned"] = usdc_returned

                usdc_amount = usdc_invested + hedge_collateral - hedge_debt_usd - usdc_returned
            except Exception as e:
                logger.warning(f"Failed to parse PositionCreated data field: {e}")

        return event_data, usdc_amount, hedge_debt_usd_value

    async def _analyze_position_event(
        self,
        traces: List[Dict],
        cdp_wallet: str,
        owner_wallet: str = None,
        tx_hash: str = None,
        logs_cache: Optional[Dict[str, List[Dict]]] = None
    ) -> Optional[Dict[str, Any]]:
        """Analyze traces to detect PositionCreated or PositionClosed events from LiquidityManager.

        Returns dict with:
        - method_name: "openPosition" or "closePosition"
        - nft_token_id: NFT position token ID
        - pool: Pool address (for PositionCreated)
        - usdc_amount: USDC amount (extracted from token flows)
        - event_data: Additional event data
        """
        position_event = None

        # Event signatures from LiquidityManager contract (0x8123F467Fa2C53a31D8738D5FAa0DFd881F5DF8A)
        # New ABI with enriched event data
        POSITION_CREATED_EVENT = "0x22c1b606e32c54081d4813a6daf0b6ab4522b84a2829c0dfa181ac6f12c62b7c"
        POSITION_CLOSED_EVENT = "0xfc4e6ac706594637404ad0c7694a5353537a522cc0cf04a16ca51a228b0f2bd4"

        # Check CDP logs for PositionCreated or PositionClosed events
        # Collect ALL events first (don't break early) to handle cases where both exist
        position_created_event = None
        position_closed_event = None

        for trace in traces:
            if "logs" in trace:
                for log in trace.get("logs", []):
                    topics = log.get("topics", [])
                    if not topics:
                        continue

                    event_sig = topics[0] if topics else None
                    if not event_sig:
                        continue

                    # Normalize event signature
                    event_sig_normalized = event_sig.lower() if isinstance(event_sig, str) else str(event_sig).lower()
                    log_address = log.get("address", "").lower() if log.get("address") else ""

                    # Only process events from LiquidityManager
                    if log_address != self.LIQUIDITY_MANAGER:
                        continue

                    # Check for PositionCreated event
                    if event_sig_normalized == POSITION_CREATED_EVENT.lower():
                        if len(topics) >= 4:
                            try:
                                # Extract indexed parameters
                                # Topic 1: user address (CDP wallet)
                                user_addr = ("0x" + topics[1][-40:] if isinstance(topics[1], str) else "0x" + str(topics[1])[-40:]).lower()
                                # Topic 2: position ID (NFT token ID)
                                position_id_hex = topics[2].hex() if hasattr(topics[2], 'hex') else topics[2]
                                if isinstance(position_id_hex, str):
                                    position_id_hex = position_id_hex.replace('0x', '')
                                position_id = int(position_id_hex, 16)
                                # Topic 3: pool address
                                pool_addr = ("0x" + topics[3][-40:] if isinstance(topics[3], str) else "0x" + str(topics[3])[-40:]).lower()

                                if user_addr == cdp_wallet.lower():
                                    # Parse data field for non-indexed parameters
                                    # Data: liquidity(uint128), usdcInvested(uint256), tickLower(int24), tickUpper(int24),
                                    #       staked(bool), isHedged(bool), hedgeCollateral(uint256), hedgeDebt(uint256), hedgedAsset(address)
                                    data = log.get("data", "0x")
                                    if isinstance(data, str):
                                        data = data[2:] if data.startswith("0x") else data
                                    else:
                                        data = data.hex() if hasattr(data, 'hex') else str(data)

                                    # Use shared parsing method with traces to calculate USDC returned
                                    event_data, usdc_amount, hedge_debt_usd_value = await self._parse_position_created_data(data, traces, cdp_wallet)

                                    position_created_event = {
                                        "method_name": "openPosition",
                                        "nft_token_id": position_id,
                                        "pool": pool_addr,
                                        "event_detected": "PositionCreated",
                                        "event_data": event_data,
                                        "usdc_amount": usdc_amount,
                                        "usdc_out": usdc_amount,  # Net USDC deployed
                                        "usdc_in": 0,  # No USDC returned on creation
                                        "aero_out": 0,
                                        "aero_in": 0,
                                        # Add hedge info at top level for visibility
                                        "usdc_invested": event_data.get("usdc_invested", 0),
                                        "hedge_collateral": event_data.get("hedge_collateral", 0),
                                        "hedge_debt": event_data.get("hedge_debt", 0),
                                        "hedge_debt_usd": event_data.get("hedge_debt_usd", 0),
                                        "is_hedged": event_data.get("is_hedged", False),
                                        "hedged_asset": event_data.get("hedged_asset", "0x0")
                                    }
                            except (ValueError, TypeError, AttributeError) as e:
                                logger.warning(f"Failed to parse PositionCreated event: {e}")

                    # Check for PositionClosed event
                    elif event_sig_normalized == POSITION_CLOSED_EVENT.lower():
                        if len(topics) >= 4:
                            try:
                                # Extract indexed parameters
                                # Topic 1: user address (CDP wallet)
                                user_addr = ("0x" + topics[1][-40:] if isinstance(topics[1], str) else "0x" + str(topics[1])[-40:]).lower()
                                # Topic 2: position ID (NFT token ID)
                                position_id_hex = topics[2].hex() if hasattr(topics[2], 'hex') else topics[2]
                                if isinstance(position_id_hex, str):
                                    position_id_hex = position_id_hex.replace('0x', '')
                                position_id = int(position_id_hex, 16)
                                # Topic 3: pool address
                                pool_addr = ("0x" + topics[3][-40:] if isinstance(topics[3], str) else "0x" + str(topics[3])[-40:]).lower()

                                if user_addr == cdp_wallet.lower():
                                    # Parse data field for non-indexed parameters
                                    # Data: usdcReturned(uint256), wasStaked(bool), wasHedged(bool), hedgeCollateralReturned(uint256)
                                    data = log.get("data", "0x")
                                    if isinstance(data, str):
                                        data = data[2:] if data.startswith("0x") else data
                                    else:
                                        data = data.hex() if hasattr(data, 'hex') else str(data)

                                    event_data = {}
                                    usdc_amount = 0

                                    if len(data) >= 64:
                                        try:
                                            usdc_returned = int(data[0:64], 16)
                                            was_staked = bool(int(data[64:128], 16)) if len(data) >= 128 else False
                                            was_hedged = bool(int(data[128:192], 16)) if len(data) >= 192 else False
                                            hedge_collateral_returned = int(data[192:256], 16) if len(data) >= 256 else 0

                                            event_data = {
                                                "usdc_returned": usdc_returned,
                                                "was_staked": was_staked,
                                                "was_hedged": was_hedged,
                                                "hedge_collateral_returned": hedge_collateral_returned
                                            }
                                            usdc_amount = usdc_returned
                                        except Exception as e:
                                            logger.warning(f"Failed to parse PositionClosed data field: {e}")

                                    position_closed_event = {
                                        "method_name": "closePosition",
                                        "nft_token_id": position_id,
                                        "pool": pool_addr,
                                        "event_detected": "PositionClosed",
                                        "event_data": event_data,
                                        "usdc_amount": usdc_amount
                                    }
                            except (ValueError, TypeError, AttributeError) as e:
                                logger.warning(f"Failed to parse PositionClosed event: {e}")

        # Prioritize PositionCreated over PositionClosed when both exist
        # This handles position replacement scenarios
        if position_created_event:
            position_event = position_created_event
            if position_closed_event:
                logger.info(f"Transaction has both PositionCreated and PositionClosed - prioritizing PositionCreated (position replacement)")
        elif position_closed_event:
            position_event = position_closed_event

        # If not found in CDP logs and we have a tx_hash, check RPC logs as fallback
        if not position_event and tx_hash:
            rpc_logs = await self._fetch_rpc_logs(tx_hash, logs_cache)

            rpc_position_created = None
            rpc_position_closed = None

            for log in rpc_logs:
                if not log.get("topics") or len(log["topics"]) < 2:
                    continue

                event_sig = log["topics"][0].lower() if log["topics"] else None
                log_address = log["address"].lower()

                # Only check logs from LiquidityManager
                if log_address != self.LIQUIDITY_MANAGER.lower():
                    continue

                # Check for PositionCreated event (with or without 0x prefix)
                if event_sig in [POSITION_CREATED_EVENT.lower(), POSITION_CREATED_EVENT[2:].lower()]:
                    if len(log["topics"]) >= 4:
                        try:
                            user_addr = ("0x" + log["topics"][1][-40:]).lower()
                            position_id = int(log["topics"][2], 16)
                            pool_addr = ("0x" + log["topics"][3][-40:]).lower()

                            if user_addr == cdp_wallet.lower():
                                # Parse data field
                                data = log.get("data", "0x")
                                if isinstance(data, str):
                                    data = data[2:] if data.startswith("0x") else data

                                # Convert RPC logs to traces-like structure for USDC calculation
                                traces_from_rpc = [{"logs": rpc_logs}]

                                # Use shared parsing method with RPC logs
                                event_data, usdc_amount, hedge_debt_usd_value = await self._parse_position_created_data(data, traces_from_rpc, cdp_wallet)

                                rpc_position_created = {
                                    "method_name": "openPosition",
                                    "nft_token_id": position_id,
                                    "pool": pool_addr,
                                    "event_detected": "PositionCreated_RPC",
                                    "event_data": event_data,
                                    "usdc_amount": usdc_amount,
                                    "usdc_out": usdc_amount,  # Net USDC deployed
                                    "usdc_in": 0,  # No USDC returned on creation
                                    "aero_out": 0,
                                    "aero_in": 0,
                                    # Add hedge info at top level for visibility
                                    "usdc_invested": event_data.get("usdc_invested", 0),
                                    "hedge_collateral": event_data.get("hedge_collateral", 0),
                                    "hedge_debt": event_data.get("hedge_debt", 0),
                                    "hedge_debt_usd": event_data.get("hedge_debt_usd", 0),
                                    "is_hedged": event_data.get("is_hedged", False),
                                    "hedged_asset": event_data.get("hedged_asset", "0x0")
                                }
                        except Exception as e:
                            logger.warning(f"Failed to parse RPC PositionCreated event: {e}")

                # Check for PositionClosed event
                elif event_sig in [POSITION_CLOSED_EVENT.lower(), POSITION_CLOSED_EVENT[2:].lower()]:
                    if len(log["topics"]) >= 4:
                        try:
                            user_addr = ("0x" + log["topics"][1][-40:]).lower()
                            position_id = int(log["topics"][2], 16)
                            pool_addr = ("0x" + log["topics"][3][-40:]).lower()

                            if user_addr == cdp_wallet.lower():
                                # Parse data field
                                data = log.get("data", "0x")
                                if isinstance(data, str):
                                    data = data[2:] if data.startswith("0x") else data

                                event_data = {}
                                usdc_amount = 0
                                if len(data) >= 64:
                                    try:
                                        usdc_returned = int(data[0:64], 16)
                                        was_staked = bool(int(data[64:128], 16)) if len(data) >= 128 else False
                                        was_hedged = bool(int(data[128:192], 16)) if len(data) >= 192 else False
                                        hedge_collateral_returned = int(data[192:256], 16) if len(data) >= 256 else 0

                                        event_data = {
                                            "usdc_returned": usdc_returned,
                                            "was_staked": was_staked,
                                            "was_hedged": was_hedged,
                                            "hedge_collateral_returned": hedge_collateral_returned
                                        }
                                        usdc_amount = usdc_returned
                                    except Exception as e:
                                        logger.warning(f"Failed to parse RPC PositionClosed data: {e}")

                                rpc_position_closed = {
                                    "method_name": "closePosition",
                                    "nft_token_id": position_id,
                                    "pool": pool_addr,
                                    "event_detected": "PositionClosed_RPC",
                                    "event_data": event_data,
                                    "usdc_amount": usdc_amount
                                }
                        except Exception as e:
                            logger.warning(f"Failed to parse RPC PositionClosed event: {e}")

            # Prioritize PositionCreated over PositionClosed in RPC logs too
            if rpc_position_created:
                position_event = rpc_position_created
                if rpc_position_closed:
                    logger.info(f"RPC logs have both PositionCreated and PositionClosed - prioritizing PositionCreated")
            elif rpc_position_closed:
                position_event = rpc_position_closed

        # If we found a position event, use the USDC amount from event data
        if position_event:
            # Get USDC amount directly from parsed event data (already set during parsing)
            usdc_amount = position_event.get("usdc_amount", 0)

            # Set token flows based on event type
            if position_event["method_name"] == "openPosition":
                # Position created: USDC goes out (invested)
                position_event["usdc_in"] = 0
                position_event["usdc_out"] = usdc_amount
            elif position_event["method_name"] == "closePosition":
                # Position closed: USDC comes in (returned)
                position_event["usdc_in"] = usdc_amount
                position_event["usdc_out"] = 0

            # AERO flows not tracked in new events, set to 0
            position_event["aero_in"] = 0
            position_event["aero_out"] = 0
            return position_event

        return None

    async def _categorize_transaction(
        self,
        tx_data: Dict,
        owner_wallet: str,
        cdp_wallet: str,
        logs_cache: Optional[Dict[str, List[Dict]]] = None
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
        position_event = await self._analyze_position_event(traces, cdp_wallet, owner_wallet, tx_hash, logs_cache)

        # Debug logging for transactions that might be position events but weren't detected
        if not position_event:
            # Check if this looks like it might be a position event based on flows
            has_significant_usdc = False
            has_significant_aero = False

            for trace in traces:
                to_addr = trace.get("to", "").lower()


        if position_event:
            method_name = position_event["method_name"]

            if method_name == "openPosition":
                # POSITION_CREATED - includes auto-staking since positions are staked when created
                net_amount = position_event["usdc_out"] - position_event["usdc_in"]

                details["amount"] = net_amount
                details["description"] = f"Position created in pool"
                details["nft_token_id"] = position_event.get("nft_token_id")
                details["pool"] = position_event.get("pool")

                # Get pool name if available
                if position_event.get("pool"):
                    details["pool_name"] = await self._get_pool_name(position_event["pool"])

                # Store token flows in event_data (includes staking amounts)
                details["usdc_in"] = position_event["usdc_in"]
                details["usdc_out"] = position_event["usdc_out"]
                details["aero_in"] = position_event["aero_in"]
                details["aero_out"] = position_event["aero_out"]

                # Add enriched event data (tick range, hedge info, staking status)
                if "event_data" in position_event:
                    details["event_data"] = position_event["event_data"]

                return TransactionType.POSITION_CREATED, details

            elif method_name == "closePosition":
                # POSITION_CLOSED - includes swaps and fee transfers
                amount_received = position_event["usdc_in"]

                details["amount"] = amount_received
                details["description"] = f"Position closed"
                details["nft_token_id"] = position_event.get("nft_token_id")

                # Store all token flows (swaps and fees are included in these flows)
                details["usdc_in"] = position_event["usdc_in"]
                details["usdc_out"] = position_event["usdc_out"]
                details["aero_in"] = position_event["aero_in"]
                details["aero_out"] = position_event["aero_out"]

                # If AERO was received, it means it was swapped to USDC as part of closing
                if position_event["aero_out"] > 0:
                    details["aero_swapped_to_usdc"] = position_event["aero_out"]

                # Add enriched event data (staking status, hedge info returned)
                if "event_data" in position_event:
                    details["event_data"] = position_event["event_data"]

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

                    # Note: Fee transfers are now part of POSITION_CLOSED transactions
                
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

                    # Note: Fee transfers and staking are now part of POSITION_CREATED/CLOSED transactions
        
        # Also check event logs for USDC transfers (handles Account Abstraction txs)
        # This is crucial for detecting transfers in smart contract wallet transactions
        if not found_deposit and not found_withdrawal:
            logs = content.get("logs", [])
            for log in logs:
                # Check for USDC Transfer events
                if log.get("address", "").lower() == self.USDC_ADDRESS:
                    topics = log.get("topics", [])
                    if topics and len(topics) >= 3:
                        # ERC20 Transfer event signature
                        transfer_sig = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
                        if topics[0] == transfer_sig:
                            # Extract from and to addresses from topics
                            from_addr_log = "0x" + topics[1][-40:] if len(topics[1]) > 40 else topics[1]
                            to_addr_log = "0x" + topics[2][-40:] if len(topics[2]) > 40 else topics[2]

                            from_addr_log = from_addr_log.lower()
                            to_addr_log = to_addr_log.lower()

                            # Extract amount from data field
                            data = log.get("data", "0x0")
                            try:
                                amount = int(data, 16) if data.startswith("0x") else int(data)

                                # Check for deposit: owner -> CDP wallet
                                if from_addr_log == owner_wallet and to_addr_log == cdp_wallet and amount > 0:
                                    found_deposit = True
                                    deposit_amount += amount

                                # Check for withdrawal: CDP wallet -> owner
                                elif from_addr_log == cdp_wallet and to_addr_log == owner_wallet and amount > 0:
                                    found_withdrawal = True
                                    withdrawal_amount += amount
                            except Exception as e:
                                logger.warning(f"Failed to parse USDC transfer amount: {e}")

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
            TransactionType.POSITION_CREATED: [],
            TransactionType.POSITION_CLOSED: [],
            TransactionType.UNKNOWN: []
        }

        total_deposited = Decimal(0)
        total_withdrawn = Decimal(0)

        # Batch fetch RPC logs for all transactions to avoid sequential RPC calls
        tx_hashes = [tx.get("hash") for tx in transactions if tx.get("hash")]
        logs_cache = await self._batch_fetch_rpc_logs(tx_hashes) if tx_hashes else {}

        for tx in transactions:
            tx_type, details = await self._categorize_transaction(
                tx,
                user_id,
                cdp_wallet_address,
                logs_cache
            )

            if details:
                categorized[tx_type].append(details)
                
                # Track totals
                if tx_type == TransactionType.DEPOSIT:
                    total_deposited += Decimal(details["amount"]) / Decimal(1_000_000)
                elif tx_type == TransactionType.WITHDRAW:
                    total_withdrawn += Decimal(details["amount"]) / Decimal(1_000_000)
                
                # Save to database if it's a financial or position transaction
                if tx_type in [TransactionType.DEPOSIT, TransactionType.WITHDRAW,
                              TransactionType.POSITION_CREATED, TransactionType.POSITION_CLOSED]:
                    await self._save_transaction(
                        user_id=user_id,
                        tx_type=tx_type.value,
                        details=details
                    )
        
        # Commit all database changes
        await self.db.commit()
        
        return {
            "total": len(transactions),
            "deposits": len(categorized[TransactionType.DEPOSIT]),
            "withdrawals": len(categorized[TransactionType.WITHDRAW]),
            "stakings": 0,  # Stakings are now included in POSITION_CREATED
            "positions_opened": len(categorized[TransactionType.POSITION_CREATED]),
            "positions_closed": len(categorized[TransactionType.POSITION_CLOSED]),
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

            # Merge enriched event data from position events (includes hedge info, tick ranges, etc.)
            if "event_data" in details and isinstance(details["event_data"], dict):
                event_data.update(details["event_data"])

            # Add position-specific data if available (may override merged data)
            if tx_type in ["POSITION_CREATED", "POSITION_CLOSED"]:
                # Store token flows (includes staking amounts for CREATED, swaps/fees for CLOSED)
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

                # For POSITION_CLOSED, include swap information if AERO was swapped
                if tx_type == "POSITION_CLOSED" and details.get("aero_swapped_to_usdc"):
                    event_data["aero_swapped_to_usdc"] = details["aero_swapped_to_usdc"]

                # The position and pool data fetching is now handled by _ensure_position_data
                # Just pass through any initial data we have
                if details.get("nft_token_id"):
                    event_data["nft_token_id"] = details["nft_token_id"]
                    event_data["tokenId"] = str(details["nft_token_id"])  # Also store as string with tokenId key
                    event_data["token_id"] = details["nft_token_id"]  # Also store with underscore
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

            try:
                self.db.add(transaction)
                await self.db.flush()  # Flush to catch unique constraint violations immediately
            except Exception as e:
                # Handle duplicate transaction gracefully (race condition from concurrent syncs)
                if "duplicate key value violates unique constraint" in str(e):
                    logger.warning(f"Transaction {details['tx_hash']} already exists, skipping (race condition)")
                    await self.db.rollback()
                    return
                else:
                    raise

            # If this is a DEPOSIT transaction, publish balance change event for agent manager
            # NOTE: Only update balance if it hasn't been recently synced to avoid duplicates
            if tx_type == "DEPOSIT":
                try:
                    # Get user's current balance to calculate the new balance
                    from app.database.models import User
                    from sqlalchemy import select
                    from web3 import Web3
                    import os

                    stmt = select(User).where(User.user_id == user_id)
                    result = await self.db.execute(stmt)
                    user = result.scalar_one_or_none()

                    if user and user.cdp_wallet_address:
                        # Get current on-chain balance to avoid duplicate updates
                        try:
                            rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')
                            w3 = Web3(Web3.HTTPProvider(rpc_url))
                            usdc_address = Web3.to_checksum_address("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
                            usdc_abi = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]
                            usdc_contract = w3.eth.contract(address=usdc_address, abi=usdc_abi)

                            checksum_address = Web3.to_checksum_address(user.cdp_wallet_address)
                            balance_wei = usdc_contract.functions.balanceOf(checksum_address).call()
                            onchain_balance = Decimal(balance_wei) / Decimal(10 ** 6)

                            db_balance = Decimal(str(user.usdc_balance or 0))

                            # Only update if the database balance is significantly different from on-chain
                            # This prevents duplicate events when balance was already synced
                            if abs(onchain_balance - db_balance) > Decimal('0.01'):
                                old_balance = db_balance
                                new_balance = onchain_balance

                                # Update user balance
                                user.usdc_balance = new_balance

                                # Check if this is first 50+ USDC deposit
                                if not user.has_deposited_50_usdc and new_balance >= Decimal('50'):
                                    user.has_deposited_50_usdc = True

                                # Publish balance change event for agent manager
                                try:
                                    from app.services.balance_updater import publish_balance_change_event
                                    await publish_balance_change_event(
                                        user_id=user_id,
                                        old_balance=old_balance,
                                        new_balance=new_balance,
                                        event_type='DEPOSIT',
                                        has_deposited_50_usdc=user.has_deposited_50_usdc
                                    )
                                except Exception as e:
                                    logger.error(f"Failed to publish deposit event: {e}")

                                # Also try stream publishing as backup
                                try:
                                    from app.services.balance_stream_publisher import publish_balance_change_to_stream
                                    await publish_balance_change_to_stream(
                                        user_id=user_id,
                                        old_balance=old_balance,
                                        new_balance=new_balance,
                                        event_type='DEPOSIT',
                                        has_deposited_50_usdc=user.has_deposited_50_usdc
                                    )
                                except Exception as e:
                                    logger.error(f"Failed to publish deposit event to stream: {e}")
                        except Exception as e:
                            logger.warning(f"Failed to check on-chain balance for deduplication: {e}")
                            # Fall back to not publishing to avoid duplicates

                except Exception as e:
                    logger.error(f"Failed to process deposit event: {e}")

            # If this is a POSITION_CREATED transaction, create the position
            if tx_type == "POSITION_CREATED" and position_id_value:
                try:
                    await self._create_position_if_needed(
                        user_id=user_id,
                        position_id=position_id_value,
                        pool_address=event_data.get("pool"),
                        pool_name=event_data.get("pool_name"),
                        tx_hash=details["tx_hash"],
                        amount_usdc=amount_usdc
                    )
                except Exception as e:
                    logger.error(f"Failed to create position for POSITION_CREATED transaction: {e}")
                    # Continue processing other transactions

            # If this is a STAKING transaction, update position's staked status
            elif tx_type == "STAKING" and position_id_value:
                await self._update_position_staking(
                    user_id=user_id,
                    position_id=position_id_value,
                    gauge_address=event_data.get("gauge_address")
                )

            # If this is a POSITION_CLOSED transaction, update the position status
            elif tx_type == "POSITION_CLOSED":
                if position_id_value:
                    await self._close_position_if_needed(user_id, position_id_value, details["tx_hash"], amount_usdc)
                else:
                    # Try to find the position to close based on transaction timing and amount
                    logger.warning(f"POSITION_CLOSED detected without NFT ID, attempting to find position...")
                    found_position_id = await self._find_position_to_close(user_id, amount_usdc, details)
                    if found_position_id:
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
            # Allow recategorization of UNKNOWN transactions OR if the new category is WITHDRAW/DEPOSIT
            # This handles Account Abstraction transactions that may be initially miscategorized
            should_update = False
            if existing_tx.tx_type == "UNKNOWN" and tx_type != "UNKNOWN":
                should_update = True
            elif tx_type in ["WITHDRAW", "DEPOSIT"] and existing_tx.tx_type not in ["WITHDRAW", "DEPOSIT"]:
                # Allow updating to WITHDRAW/DEPOSIT if current type is not already a financial transaction
                should_update = True
                logger.info(f"Updating transaction {details['tx_hash'][:10]}... from {existing_tx.tx_type} to {tx_type}")

            if should_update:
                existing_tx.tx_type = tx_type
                existing_tx.event_data = existing_tx.event_data or {}
                existing_tx.event_data["recategorized"] = True
                existing_tx.event_data["description"] = details.get("description", "")
                existing_tx.event_data["previous_type"] = existing_tx.tx_type if existing_tx.tx_type != tx_type else None

                # Update amount for withdrawals/deposits
                if tx_type in ["WITHDRAW", "DEPOSIT"] and details.get("amount"):
                    amount_usdc = Decimal(details["amount"]) / Decimal(1_000_000)
                    existing_tx.event_data["amount_usdc"] = float(amount_usdc)

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
        from sqlalchemy.exc import IntegrityError

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

            positions_created = 0
            for tx in position_created_txs:
                # Get position_id from either column or event_data
                position_id = tx.position_id
                if not position_id and tx.event_data:
                    # Try multiple possible keys in event_data
                    for key in ['position_id', 'nft_token_id', 'tokenId', 'token_id']:
                        position_id = tx.event_data.get(key)
                        if position_id:
                            break

                # Convert to int if string
                if position_id:
                    if isinstance(position_id, str):
                        try:
                            position_id = int(position_id)
                        except (ValueError, TypeError):
                            logger.error(f"Invalid position_id format in transaction {tx.tx_hash}: {position_id}")
                            continue

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
                        logger.info(f"Creating missing position {position_id} for user {user_id} from tx {tx.tx_hash[:10]}...")
                        amount_usdc = Decimal(str(tx.event_data.get('amount_usdc', 0))) if tx.event_data else Decimal(0)
                        pool_address = tx.event_data.get('pool') if tx.event_data else None
                        pool_name = tx.event_data.get('pool_name') if tx.event_data else None

                        try:
                            await self._create_position_if_needed(
                                user_id=user_id,
                                position_id=position_id,
                                pool_address=pool_address,
                                pool_name=pool_name,
                                tx_hash=tx.tx_hash,
                                amount_usdc=amount_usdc
                            )
                            positions_created += 1
                        except IntegrityError as ie:
                            # Race condition - another process created this position
                            logger.info(f"Position {position_id} created by concurrent process, skipping")
                            await self.db.rollback()  # Rollback to clear the error
                            continue
                        except Exception as e:
                            logger.error(f"Failed to create position {position_id}: {e}")
                            await self.db.rollback()  # Rollback to clear the error
                            continue
                else:
                    logger.warning(f"POSITION_CREATED transaction {tx.tx_hash[:10]}... has no position_id")

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

            # Commit all position creations and updates
            if positions_created > 0:
                await self.db.commit()
                logger.info(f"Committed {positions_created} new positions for user {user_id}")

        except Exception as e:
            logger.error(f"Error ensuring positions for transactions: {e}")
            await self.db.rollback()  # Rollback on error

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
                # Don't commit here - let the caller handle the commit
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
        from sqlalchemy.exc import IntegrityError

        try:
            # Ensure position_id is an integer
            if isinstance(position_id, str):
                position_id = int(position_id)

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
                return

            # Create new position
            new_position = Position(
                user_id=user_id,
                token_id=position_id,  # This is the NFT token ID (nft_token_id is a computed property)
                pool_address=pool_address or "",  # Ensure not None
                pool_name=pool_name,
                status='ACTIVE',
                entry_date=datetime.utcnow(),
                entry_tx_hash=tx_hash,
                entry_amount_usdc=amount_usdc,
                current_value_usdc=amount_usdc,  # Initial value is entry amount
                staked=False,  # Will be updated by STAKING transaction
                liquidity="0",  # Will be fetched from blockchain later
                tick_lower=None,  # Will be fetched from blockchain later
                tick_upper=None,  # Will be fetched from blockchain later
                # Set default token addresses - will be updated when position is enriched
                token0_address="",  # Will be fetched from pool data
                token1_address=""   # Will be fetched from pool data
            )

            self.db.add(new_position)
            # Don't commit here - let the caller handle the commit
            # This ensures all operations happen in the same transaction

        except IntegrityError as e:
            # Position might already exist (race condition from concurrent syncs)
            # Re-raise so the caller can handle it appropriately
            logger.debug(f"IntegrityError creating position {position_id} - likely concurrent creation")
            raise
        except ValueError as e:
            logger.error(f"Invalid position_id format {position_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to create position {position_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise  # Re-raise to make failures visible

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
            else:
                logger.warning(f"Position {nft_token_id} not found or already closed for user {user_id}")
        except Exception as e:
            logger.error(f"Error closing position {nft_token_id}: {e}")