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
    WITHDRAWAL = "WITHDRAWAL"
    STAKING = "STAKING"
    POSITION_CREATED = "POSITION_CREATED"
    POSITION_CLOSED = "POSITION_CLOSED"
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
        """
        position_event = None
        usdc_flows = {"in": 0, "out": 0}
        aero_flows = {"in": 0, "out": 0}
        pool_addresses = set()  # Track all potential pool addresses

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
            if to_addr == self.LIQUIDITY_MANAGER and from_addr == cdp_wallet:
                if len(input_data) >= 10:
                    method_sig = input_data[:10]
                    if method_sig in self.POSITION_METHOD_SIGNATURES:
                        position_event = {
                            "method_sig": method_sig,
                            "method_name": self.POSITION_METHOD_SIGNATURES[method_sig]
                        }
            
            # Track USDC transfers
            elif to_addr == self.USDC_ADDRESS:
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
            elif to_addr == self.AERO_ADDRESS:
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
            # Use the first pool address found (usually there's only one)
            pool_address = list(pool_addresses)[0] if pool_addresses else None

            position_event.update({
                "usdc_in": usdc_flows["in"],
                "usdc_out": usdc_flows["out"],
                "aero_in": aero_flows["in"],
                "aero_out": aero_flows["out"],
                "pool": pool_address
            })
            return position_event
        
        return None
    
    def _categorize_transaction(
        self,
        tx_data: Dict,
        owner_wallet: str,
        cdp_wallet: str
    ) -> Tuple[TransactionType, Dict[str, Any]]:
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
        found_staking = False
        deposit_amount = 0
        withdrawal_amount = 0
        
        # Check for position events first (highest priority)
        position_event = self._analyze_position_event(traces, cdp_wallet)
        if position_event:
            method_name = position_event["method_name"]
            
            if method_name == "openPosition":
                # For position creation, the net amount is what the user actually invested (usdc_out - usdc_in)
                # usdc_out is what left the wallet, usdc_in is what came back (if any)
                net_amount = position_event["usdc_out"] - position_event["usdc_in"]
                details["amount"] = max(0, net_amount)  # Ensure non-negative
                details["description"] = f"Position opened via LiquidityManager"
                details["method_sig"] = position_event["method_sig"]
                details["usdc_in"] = position_event["usdc_in"]
                details["usdc_out"] = position_event["usdc_out"]
                details["aero_in"] = position_event["aero_in"]
                details["aero_out"] = position_event["aero_out"]
                details["pool"] = position_event.get("pool")  # Include pool address
                return TransactionType.POSITION_CREATED, details
            
            elif method_name == "closePosition":
                details["amount"] = position_event["usdc_in"] if position_event["usdc_in"] > 0 else position_event["usdc_out"]
                details["description"] = f"Position closed via LiquidityManager"
                details["method_sig"] = position_event["method_sig"]
                details["usdc_in"] = position_event["usdc_in"]
                details["usdc_out"] = position_event["usdc_out"] 
                details["aero_in"] = position_event["aero_in"]
                details["aero_out"] = position_event["aero_out"]
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
            if from_addr == cdp_wallet:
                for pm in self.POSITION_MANAGERS:
                    if to_addr == pm:
                        found_staking = True
                        break
        
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
            return TransactionType.WITHDRAWAL, details
        
        if found_staking:
            details["description"] = "Interaction with position manager (staking)"
            details["cdp_wallet"] = cdp_wallet
            return TransactionType.STAKING, details
        
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
            TransactionType.WITHDRAWAL: [],
            TransactionType.STAKING: [],
            TransactionType.POSITION_CREATED: [],
            TransactionType.POSITION_CLOSED: [],
            TransactionType.UNKNOWN: []
        }
        
        total_deposited = Decimal(0)
        total_withdrawn = Decimal(0)
        
        for tx in transactions:
            tx_type, details = self._categorize_transaction(
                tx, 
                user_id, 
                cdp_wallet_address
            )
            
            if details:
                categorized[tx_type].append(details)
                
                # Track totals
                if tx_type == TransactionType.DEPOSIT:
                    total_deposited += Decimal(details["amount"]) / Decimal(1_000_000)
                elif tx_type == TransactionType.WITHDRAWAL:
                    total_withdrawn += Decimal(details["amount"]) / Decimal(1_000_000)
                
                # Save to database if it's a financial or position transaction
                if tx_type in [TransactionType.DEPOSIT, TransactionType.WITHDRAWAL,
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
            "withdrawals": len(categorized[TransactionType.WITHDRAWAL]),
            "stakings": len(categorized[TransactionType.STAKING]),
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
            
            # Add position-specific data if available
            if tx_type in ["POSITION_CREATED", "POSITION_CLOSED"]:
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

                    # Try to fetch pool name from pools_service
                    try:
                        pool_data = await pools_service.get_pool(details["pool"], include_effective_apr=False)
                        symbol = pool_data.get('symbol', '')
                        # Extract just the token pair (remove fee percentage)
                        if symbol and '-' in symbol:
                            # Get everything before the last dash (handles token pairs like WETH-USDC)
                            parts = symbol.rsplit('-', 1)  # Split from right to remove fee percentage
                            pool_name = parts[0]
                        else:
                            pool_name = symbol

                        if pool_name:
                            event_data["pool_name"] = pool_name
                            logger.debug(f"Found pool name {pool_name} for pool {details['pool']}")
                    except Exception as e:
                        logger.warning(f"Could not fetch pool info for {details['pool']}: {e}")
            
            # Store the USDC amount in event_data to avoid conflict with property
            event_data["amount_usdc"] = float(amount_usdc)
            
            transaction = Transaction(
                tx_hash=details["tx_hash"],
                user_id=user_id,
                tx_type=tx_type,
                status="CONFIRMED",
                block_number=details.get("block"),
                block_timestamp=datetime.fromisoformat(details["timestamp"].replace("Z", "+00:00")) if details.get("timestamp") else None,
                event_data=event_data
            )
            
            self.db.add(transaction)
            logger.info(f"Saved {tx_type} transaction: {details['tx_hash'][:10]}... Amount: {amount_usdc} USDC")
        else:
            # Update existing transaction if needed
            if existing_tx.tx_type == "UNKNOWN" and tx_type != "UNKNOWN":
                existing_tx.tx_type = tx_type
                existing_tx.event_data = existing_tx.event_data or {}
                existing_tx.event_data["recategorized"] = True
                existing_tx.event_data["description"] = details.get("description", "")
                logger.info(f"Recategorized transaction {details['tx_hash'][:10]}... as {tx_type}")