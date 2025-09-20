"""High-level service for fetching and transforming blockchain data from CDP SQL API."""

from typing import Dict, List, Optional, Any
from decimal import Decimal
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.services.cdp.client import (
    CDPSQLClient,
    CDPAPIError,
    CDPRateLimitError,
    CDPTimeoutError,
    CDPValidationError,
    CDPAuthenticationError,
    CDPAuthorizationError
)
from app.services.cdp.queries import CDPQueryBuilder
from app.services.cdp.cache_manager import CDPCacheManager
from app.services.cdp.models import (
    WalletMetrics,
    LiquidityEventMetrics,
    TransactionData,
    TransferData,
    EventData
)
# Blockchain sync tables removed - using transactions table instead
from app.core.cache import cache_manager as cache
from app.core.config import settings
from loguru import logger


class BlockchainDataService:
    """High-level service for fetching and transforming blockchain data."""
    
    def __init__(self):
        self.cdp_client = CDPSQLClient() if settings.cdp_client_api_key else None
        self.query_builder = CDPQueryBuilder()
        self.cache_manager = CDPCacheManager()
        self.cdp_enabled = bool(settings.cdp_client_api_key)
    
    async def get_wallet_performance_data(
        self,
        user_id: str,
        cdp_wallet: Optional[str],
        lookback_hours: int = 24,
        include_liquidity_events: bool = True,
        db_session: Optional[AsyncSession] = None,
        save_to_db: bool = True
    ) -> Dict[str, Any]:
        """Fetch comprehensive wallet performance data from blockchain.
        
        Args:
            user_id: User ID
            cdp_wallet: CDP wallet address
            lookback_hours: Hours to look back for data
            include_liquidity_events: Whether to include liquidity events
            
        Returns:
            Dictionary with wallet performance metrics
        """
        if not cdp_wallet or not self.cdp_enabled:
            return self._empty_performance_data()
        
        # Check cache first
        cache_params = {
            'wallet': cdp_wallet,
            'lookback_hours': lookback_hours,
            'include_events': include_liquidity_events
        }
        cached = await self.cache_manager.get_cached_result('wallet_performance', cache_params)
        if cached:
            return cached
        
        try:
            # Calculate time boundaries
            start_time = datetime.utcnow() - timedelta(hours=lookback_hours)
            
            # Fetch wallet history (transactions + transfers)
            wallet_data = await self._fetch_wallet_data(cdp_wallet, start_time)
            
            # Save to database if requested and session provided
            if save_to_db and db_session:
                await self._save_wallet_data_to_db(
                    wallet_data, 
                    user_id, 
                    cdp_wallet,
                    db_session
                )
            
            # Fetch liquidity events if requested
            liquidity_events = None
            if include_liquidity_events:
                liquidity_events = await self._fetch_liquidity_events(cdp_wallet, start_time)
                
                # Save liquidity events to database
                if save_to_db and db_session and liquidity_events:
                    await self._save_liquidity_events_to_db(
                        liquidity_events,
                        user_id,
                        db_session
                    )
            
            # Transform and aggregate data
            performance_data = self._transform_performance_data(
                wallet_data,
                liquidity_events
            )
            
            # Cache the result
            if self.cache_manager.should_cache_result({'result': performance_data}):
                await self.cache_manager.set_cached_result(
                    'wallet_performance',
                    cache_params,
                    performance_data,
                    custom_ttl=30  # 30 seconds for performance data
                )
            
            return performance_data
            
        except CDPAuthenticationError as e:
            logger.error(f"CDP authentication failed - check API key: {e}")
            # Return empty data but include error info for monitoring
            result = self._empty_performance_data()
            result['error'] = 'authentication_failed'
            return result
            
        except CDPRateLimitError as e:
            logger.warning(f"CDP rate limit reached: {e}")
            # Return cached data if available, otherwise empty
            fallback_cache = await self.cache_manager.get_stale_cache('wallet_performance', cache_params)
            if fallback_cache:
                logger.info("Using stale cache due to rate limit")
                return fallback_cache
            result = self._empty_performance_data()
            result['error'] = 'rate_limited'
            return result
            
        except CDPTimeoutError as e:
            logger.warning(f"CDP query timeout: {e}")
            # Return partial data if any was fetched
            result = self._empty_performance_data()
            result['error'] = 'timeout'
            return result
            
        except CDPValidationError as e:
            logger.error(f"CDP query validation error: {e}")
            result = self._empty_performance_data()
            result['error'] = 'validation_error'
            return result
            
        except CDPAuthorizationError as e:
            logger.error(f"CDP authorization error - check permissions: {e}")
            result = self._empty_performance_data()
            result['error'] = 'authorization_failed'
            return result
            
        except Exception as e:
            # Use warning for expected external service issues
            if "Server error 500" in str(e) or "internal_server_error" in str(e):
                logger.warning(f"CDP API experiencing issues: {e}")
            else:
                logger.error(f"Unexpected error fetching wallet performance data: {e}")
            # For unexpected errors, check if we have any cached data
            fallback_cache = await self.cache_manager.get_stale_cache('wallet_performance', cache_params)
            if fallback_cache:
                logger.info("Using stale cache due to CDP API error")
                return fallback_cache
            return self._empty_performance_data()
    
    async def _fetch_wallet_data(
        self,
        wallet_address: str,
        start_time: datetime
    ) -> Dict[str, Any]:
        """Fetch wallet transactions and transfers with error handling.
        
        Args:
            wallet_address: Wallet address
            start_time: Start time for data fetch
            
        Returns:
            Dictionary with transactions and transfers
            
        Raises:
            CDPAPIError: Re-raises CDP API errors for handling by caller
        """
        transactions = []
        transfers = []
        
        try:
            # Fetch ETH transactions
            eth_query = self.query_builder.wallet_history_query(
                wallet_address,
                start_time
            )
            
            # Generate cache key for ETH
            eth_cache_key = self.cache_manager.generate_cache_key(
                'eth_wallet',
                {'wallet': wallet_address, 'start': start_time.isoformat()}
            )
            
            logger.info(f"Fetching ETH transactions for wallet {wallet_address}")
            
            # Execute ETH query
            eth_result = await self.cdp_client.execute_query(
                eth_query,
                cache_key=eth_cache_key,
                cache_ttl=60
            )
            
            logger.info(f"Found {len(eth_result.result)} ETH transactions")
            
            # Add ETH transactions
            for row in eth_result.result:
                row['tx_type'] = 'eth_transaction'
                # Calculate gas_cost_eth manually since CDP SQL doesn't support AS aliases
                if row.get('gas') and row.get('gas_price'):
                    gas = int(row['gas']) if row['gas'] else 0
                    gas_price = int(row['gas_price']) if row['gas_price'] else 0
                    row['gas_cost_eth'] = (gas * gas_price) / 1e18
                else:
                    row['gas_cost_eth'] = 0
                transactions.append(row)
            
            # Try to fetch USDC transfers
            try:
                usdc_query = self.query_builder.usdc_transfers_query(
                    wallet_address,
                    start_time
                )
                
                # Generate cache key for USDC
                usdc_cache_key = self.cache_manager.generate_cache_key(
                    'usdc_wallet',
                    {'wallet': wallet_address, 'start': start_time.isoformat()}
                )
                
                logger.info(f"Fetching USDC transfers for wallet {wallet_address}")
                
                # Execute USDC query
                usdc_result = await self.cdp_client.execute_query(
                    usdc_query,
                    cache_key=usdc_cache_key,
                    cache_ttl=60
                )
                
                logger.info(f"Found {len(usdc_result.result)} USDC transfer events")
                
                # Parse USDC transfers
                for row in usdc_result.result:
                    # Extract addresses from topics
                    topics = row.get('topics', [])
                    if len(topics) >= 3:
                        # Check if it's a Transfer event (topic[0])
                        if topics[0] == '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef':
                            row['tx_type'] = 'usdc_transfer'
                            row['from_address'] = '0x' + topics[1][-40:] if len(topics[1]) >= 40 else topics[1]
                            row['to_address'] = '0x' + topics[2][-40:] if len(topics[2]) >= 40 else topics[2]
                            # Value is in data field as hex
                            row['value'] = row.get('data', '0x0')
                            transfers.append(row)
                
            except Exception as e:
                logger.warning(f"Failed to fetch USDC transfers: {e}")
                # Continue with just ETH transactions
                
        except CDPAPIError:
            # Re-raise CDP errors for proper handling
            raise
        except Exception as e:
            # Wrap unexpected errors
            logger.error(f"Unexpected error in _fetch_wallet_data: {e}")
            raise CDPAPIError(f"Failed to fetch wallet data: {e}") from e
        
        return {
            'transactions': transactions,
            'transfers': transfers
        }
    
    async def _fetch_liquidity_events(
        self,
        wallet_address: str,
        start_time: datetime
    ) -> List[Dict[str, Any]]:
        """Fetch liquidity manager events for wallet.
        
        Args:
            wallet_address: Wallet address (owner of positions)
            start_time: Start time for data fetch
            
        Returns:
            List of liquidity events
        """
        # Calculate start block (approximate)
        # Base produces ~2 blocks per second
        blocks_per_hour = 3600 / 2  # 1800 blocks
        hours_back = (datetime.utcnow() - start_time).total_seconds() / 3600
        
        # Get current block from a recent transaction (if available)
        # For now, we'll use a conservative estimate
        current_block = 22000000  # Approximate current block on Base
        start_block = int(current_block - (blocks_per_hour * hours_back))
        
        # Build query
        events_query = self.query_builder.position_events_with_decode_query(
            owner_address=wallet_address,
            start_block=start_block
        )
        
        # Generate cache key
        cache_key = self.cache_manager.generate_cache_key(
            'position_events',
            {'wallet': wallet_address, 'start_block': start_block}
        )
        
        # Execute query with caching
        result = await self.cdp_client.execute_query(
            events_query,
            cache_key=cache_key,
            cache_ttl=300  # 5 minute cache for events
        )
        
        return result.result
    
    def _transform_performance_data(
        self,
        wallet_data: Dict[str, Any],
        liquidity_events: Optional[List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """Transform raw blockchain data into performance metrics.
        
        Args:
            wallet_data: Raw wallet transaction/transfer data
            liquidity_events: Raw liquidity events
            
        Returns:
            Transformed performance metrics
        """
        transactions = wallet_data.get('transactions', [])
        transfers = wallet_data.get('transfers', [])
        
        # Calculate gas costs
        total_gas_eth = Decimal(0)
        for tx in transactions:
            gas_cost = tx.get('gas_cost_eth', 0)
            if gas_cost:
                total_gas_eth += Decimal(str(gas_cost))
        
        # Assume ETH price (should be fetched from price service)
        eth_price_usdc = Decimal('3500')  # Placeholder
        total_gas_usdc = total_gas_eth * eth_price_usdc
        
        # Calculate USDC flows
        usdc_in = Decimal(0)
        usdc_out = Decimal(0)
        
        for transfer in transfers:
            amount = Decimal(str(transfer.get('value', 0))) / Decimal(1e6)  # Convert from base units
            direction = transfer.get('direction', '')
            
            if 'in' in str(transfer.get('tx_type', '')):
                usdc_in += amount
            elif 'out' in str(transfer.get('tx_type', '')):
                usdc_out += amount
        
        net_usdc_flow = usdc_in - usdc_out
        
        # Process liquidity events
        positions_created = 0
        positions_closed = 0
        position_events = []
        
        if liquidity_events:
            for event in liquidity_events:
                event_sig = event.get('event_signature', '')
                decoded = event.get('decoded_params', {})
                
                if 'PositionCreated' in event_sig:
                    positions_created += 1
                    position_events.append({
                        'type': 'created',
                        'token_id': decoded.get('token_id'),
                        'timestamp': event.get('block_timestamp'),
                        'tx_hash': event.get('transaction_hash')
                    })
                elif 'PositionClosed' in event_sig:
                    positions_closed += 1
                    position_events.append({
                        'type': 'closed',
                        'token_id': decoded.get('token_id'),
                        'timestamp': event.get('block_timestamp'),
                        'tx_hash': event.get('transaction_hash')
                    })
        
        # Build response
        return {
            'wallet_metrics': {
                'transaction_count': len(transactions),
                'total_gas_eth': float(total_gas_eth),
                'total_gas_usdc': float(total_gas_usdc),
                'usdc_in': float(usdc_in),
                'usdc_out': float(usdc_out),
                'net_usdc_flow': float(net_usdc_flow)
            },
            'liquidity_metrics': {
                'positions_created': positions_created,
                'positions_closed': positions_closed,
                'events': position_events[:10]  # Limit to 10 most recent
            },
            'summary': {
                'total_transactions': len(transactions),
                'total_transfers': len(transfers),
                'total_gas_spent_usdc': float(total_gas_usdc),
                'net_usdc_change': float(net_usdc_flow - total_gas_usdc),
                'positions_created': positions_created,
                'positions_closed': positions_closed
            },
            'raw_data': {
                'transactions': transactions[:10],  # Limit for response size
                'transfers': transfers[:10],
                'events': liquidity_events[:10] if liquidity_events else []
            }
        }
    
    def _empty_performance_data(self) -> Dict[str, Any]:
        """Return empty performance data structure.
        
        Returns:
            Empty performance data dictionary
        """
        return {
            'wallet_metrics': {
                'transaction_count': 0,
                'total_gas_eth': 0,
                'total_gas_usdc': 0,
                'usdc_in': 0,
                'usdc_out': 0,
                'net_usdc_flow': 0
            },
            'liquidity_metrics': {
                'positions_created': 0,
                'positions_closed': 0,
                'events': []
            },
            'summary': {
                'total_transactions': 0,
                'total_transfers': 0,
                'total_gas_spent_usdc': 0,
                'net_usdc_change': 0,
                'positions_created': 0,
                'positions_closed': 0
            },
            'raw_data': {
                'transactions': [],
                'transfers': [],
                'events': []
            }
        }
    
    async def get_agent_wallet_history(
        self,
        wallet_address: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> WalletMetrics:
        """Get detailed wallet history for an agent.
        
        Args:
            wallet_address: Agent wallet address
            start_time: Start time for history
            end_time: End time for history
            
        Returns:
            WalletMetrics with detailed history
        """
        # Build query
        query = self.query_builder.wallet_history_query(
            wallet_address,
            start_time,
            end_time,
            include_gas_costs=True
        )
        
        # Execute query
        result = await self.cdp_client.execute_query(query)
        
        # Transform to WalletMetrics
        metrics = WalletMetrics(wallet_address=wallet_address)
        
        for row in result.result:
            # Create TransactionData
            tx = TransactionData(
                transaction_hash=row['transaction_hash'],
                block_number=row['block_number'],
                block_timestamp=datetime.fromisoformat(row['block_timestamp']),
                from_address=row['from_address'],
                to_address=row.get('to_address'),
                value=row['value'],
                gas_used=row.get('gas_used'),
                gas_price=row.get('gas_price'),
                gas_cost_eth=Decimal(str(row.get('gas_cost_eth', 0)))
            )
            metrics.transactions.append(tx)
            
            # Update aggregates
            if tx.from_address.lower() == wallet_address.lower():
                metrics.transaction_count += 1
                metrics.total_gas_eth += tx.gas_cost_eth or Decimal(0)
        
        # Set timestamps
        if metrics.transactions:
            metrics.first_tx_timestamp = metrics.transactions[-1].block_timestamp
            metrics.last_tx_timestamp = metrics.transactions[0].block_timestamp
        
        return metrics
    
    async def get_liquidity_events_for_manager(
        self,
        start_block: Optional[int] = None,
        end_block: Optional[int] = None
    ) -> LiquidityEventMetrics:
        """Get liquidity events from the liquidity manager contract.
        
        Args:
            start_block: Starting block number
            end_block: Ending block number
            
        Returns:
            LiquidityEventMetrics with aggregated data
        """
        # Build query
        query = self.query_builder.liquidity_events_query(
            start_block=start_block,
            end_block=end_block
        )
        
        # Execute query
        result = await self.cdp_client.execute_query(query)
        
        # Transform to LiquidityEventMetrics
        metrics = LiquidityEventMetrics()
        
        for row in result.result:
            # Create EventData
            event = EventData(
                transaction_hash=row['transaction_hash'],
                block_number=row['block_number'],
                block_timestamp=datetime.fromisoformat(row['block_timestamp']),
                log_index=row['log_index'],
                event_signature=row['event_signature'],
                contract_address=row['contract_address'],
                topics=row.get('topics', []),
                data=row.get('data'),
                decoded_params=row.get('decoded_params')
            )
            metrics.events.append(event)
            
            # Update counters
            if 'PositionCreated' in event.event_signature:
                metrics.positions_created += 1
            elif 'PositionClosed' in event.event_signature:
                metrics.positions_closed += 1
        
        return metrics
    
    async def _save_wallet_data_to_db(
        self,
        wallet_data: Dict[str, Any],
        user_id: str,
        wallet_address: str,
        db_session: AsyncSession
    ):
        """Save wallet transaction data to database using Transaction table."""
        # Import Transaction model
        from app.database.models import Transaction
        
        try:
            transactions = wallet_data.get('transactions', [])
            transfers = wallet_data.get('transfers', [])
            
            # Combine transactions and transfers
            all_txs = transactions + transfers
            logger.info(f"Saving {len(all_txs)} transactions to database ({len(transactions)} ETH, {len(transfers)} USDC)")
            
            saved_count = 0
            for tx_data in all_txs:
                # Check if transaction already exists
                existing = await db_session.execute(
                    select(Transaction).where(
                        Transaction.tx_hash == tx_data['transaction_hash']
                    )
                )
                if existing.scalar_one_or_none():
                    continue
                
                # Determine transaction type
                from_addr = tx_data['from_address'].lower()
                to_addr = tx_data.get('to_address', '').lower()
                wallet_addr = wallet_address.lower()
                
                # Determine if it's a deposit or withdrawal
                if from_addr == user_id.lower() and to_addr == wallet_addr:
                    tx_type = 'DEPOSIT'  # From owner to CDP wallet
                elif from_addr == wallet_addr and to_addr == user_id.lower():
                    tx_type = 'WITHDRAW'  # From CDP wallet to owner
                else:
                    # Skip other transactions for now
                    continue
                
                # Parse value as USDC amount if it's a transfer
                amount_usdc = Decimal(0)
                if 'value' in tx_data and tx_data['value']:
                    # If it's a USDC transfer, value is already in USDC
                    # If it's ETH, we'll skip it for now
                    if 'usdc' in str(tx_data.get('token_symbol', '')).lower():
                        amount_usdc = Decimal(str(tx_data['value'])) / Decimal(10**6)  # Convert from base units
                
                # Create new transaction
                wallet_tx = Transaction(
                    user_id=user_id,
                    tx_type=tx_type,
                    amount_usdc=amount_usdc,
                    tx_hash=tx_data['transaction_hash'],
                    status='CONFIRMED',
                    event_data={
                        'type': 'wallet_transaction',
                        'block_number': tx_data['block_number'],
                        'from_address': tx_data['from_address'],
                        'to_address': tx_data.get('to_address'),
                        'value': tx_data.get('value'),
                        'gas': tx_data.get('gas'),
                        'gas_price': tx_data.get('gas_price'),
                        'gas_cost_eth': str(tx_data.get('gas_cost_eth', 0)),
                        'timestamp': tx_data['timestamp'],
                        'is_agent_wallet': (from_addr == wallet_addr or to_addr == wallet_addr)
                    }
                )
                db_session.add(wallet_tx)
                saved_count += 1
            
            await db_session.commit()
            logger.info(f"Saved {saved_count} new wallet transactions to database")
            
        except Exception as e:
            logger.error(f"Error saving wallet data to database: {e}")
            await db_session.rollback()
    
    async def _save_liquidity_events_to_db(
        self,
        events: List[Dict[str, Any]],
        user_id: str,
        db_session: AsyncSession
    ):
        """Save liquidity events to database using Transaction table."""
        # Import Transaction model
        from app.database.models import Transaction
        
        try:
            for event_data in events:
                # Check if event already exists in transactions table
                existing = await db_session.execute(
                    select(Transaction).where(
                        Transaction.tx_hash == event_data['transaction_hash']
                    )
                )
                if existing.scalar_one_or_none():
                    continue
                
                # Parse decoded params if available
                decoded = event_data.get('decoded_params', {})
                token_id = None
                owner_address = None
                
                if decoded:
                    if isinstance(decoded, str):
                        import json
                        try:
                            decoded = json.loads(decoded)
                        except:
                            pass
                    
                    token_id = decoded.get('token_id')
                    owner_address = decoded.get('owner')
                
                # Determine transaction type based on event
                event_name = event_data.get('event_name', '').lower()
                if 'mint' in event_name or 'increase' in event_name:
                    tx_type = 'POSITION_CREATED'
                elif 'burn' in event_name or 'decrease' in event_name:
                    tx_type = 'POSITION_CLOSED'
                else:
                    tx_type = 'POSITION_CREATED'  # Default
                
                # Store liquidity event as transaction with event data in metadata
                event = Transaction(
                    user_id=user_id,
                    tx_type=tx_type,
                    amount_usdc=Decimal(0),  # Will be updated when we get more details
                    tx_hash=event_data['transaction_hash'],
                    status='CONFIRMED',
                    event_data={
                        'type': 'liquidity_event',
                        'event_name': event_data.get('event_name'),
                        'event_signature': event_data['event_signature'],
                        'block_number': event_data['block_number'],
                        'log_index': event_data['log_index'],
                        'contract_address': event_data['address'],
                        'parameters': event_data.get('parameters'),
                        'topics': event_data.get('topics'),
                        'tokenId': str(token_id) if token_id else None,
                        'owner_address': owner_address,
                        'timestamp': event_data['timestamp']
                    }
                )
                db_session.add(event)
            
            await db_session.commit()
            logger.info(f"Saved {len(events)} liquidity events to database")
            
        except Exception as e:
            logger.error(f"Error saving liquidity events to database: {e}")
            await db_session.rollback()
    
    async def close(self):
        """Clean up resources."""
        await self.cdp_client.close()