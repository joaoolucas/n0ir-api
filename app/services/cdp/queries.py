"""SQL query builders for CDP API."""

from typing import List, Optional
from datetime import datetime, timedelta


class CDPQueryBuilder:
    """Build optimized SQL queries for CDP API."""
    
    # Known contract addresses
    USDC_ADDRESS = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
    LIQUIDITY_MANAGER_ADDRESS = "0xA933aAa8222De2f85E7A904E3E3e940652FBFdFD"
    
    @staticmethod
    def wallet_history_query(
        wallet_address: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        include_gas_costs: bool = True
    ) -> str:
        """Build query for wallet transaction history.
        
        Args:
            wallet_address: Wallet address to query
            start_time: Start time for filtering
            end_time: End time for filtering
            include_gas_costs: Whether to calculate gas costs
            
        Returns:
            SQL query string
        """
        # Keep original case - CDP SQL API is case-sensitive
        wallet = wallet_address
        
        # Time filters (using 'timestamp' not 'block_timestamp')
        time_filter = ""
        if start_time:
            time_filter += f" AND timestamp >= '{start_time.isoformat()}'"
        if end_time:
            time_filter += f" AND timestamp <= '{end_time.isoformat()}'"
        
        # Gas cost calculation (using 'gas' not 'gas_used')
        gas_calc = ""
        if include_gas_costs:
            gas_calc = ", (gas * gas_price) / 1e18 as gas_cost_eth"
        
        return f"""
        SELECT 
            transaction_hash,
            block_number,
            timestamp,
            from_address,
            to_address,
            value,
            gas,
            gas_price
            {gas_calc}
        FROM base.transactions
        WHERE (from_address = '{wallet}' OR to_address = '{wallet}')
            {time_filter}
        ORDER BY timestamp DESC, block_number DESC
        """
    
    @staticmethod
    def usdc_transfers_query(
        wallet_address: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> str:
        """Build query for USDC transfers using Transfer events.
        
        Args:
            wallet_address: Wallet address to query
            start_time: Start time for filtering
            end_time: End time for filtering
            
        Returns:
            SQL query string
        """
        # Keep original case
        wallet = wallet_address
        usdc = CDPQueryBuilder.USDC_ADDRESS
        
        # Time filters
        time_filter = ""
        if start_time:
            time_filter += f" AND timestamp >= '{start_time.isoformat()}'"
        if end_time:
            time_filter += f" AND timestamp <= '{end_time.isoformat()}'"
        
        # Query Transfer events from USDC contract
        # Transfer event signature: Transfer(address,address,uint256)
        return f"""
        SELECT 
            transaction_hash,
            block_number,
            timestamp,
            event_name,
            parameters,
            topics
        FROM base.events
        WHERE address = '{usdc}'
            AND event_signature = 'Transfer(address,address,uint256)'
            AND (topics[2] LIKE '%{wallet[2:].lower()}%' 
                OR topics[3] LIKE '%{wallet[2:].lower()}%')
            {time_filter}
        ORDER BY timestamp DESC, block_number DESC
        """
    
    @staticmethod
    def liquidity_events_query(
        liquidity_manager: Optional[str] = None,
        event_signatures: Optional[List[str]] = None,
        start_block: Optional[int] = None,
        end_block: Optional[int] = None
    ) -> str:
        """Build query for liquidity manager events.
        
        Args:
            liquidity_manager: Liquidity manager contract address
            event_signatures: List of event signatures to filter
            start_block: Starting block number
            end_block: Ending block number
            
        Returns:
            SQL query string
        """
        # Keep original case - CDP SQL API is case-sensitive
        manager = liquidity_manager or CDPQueryBuilder.LIQUIDITY_MANAGER_ADDRESS
        
        # Default event signatures for position management
        if not event_signatures:
            event_signatures = [
                'PositionCreated(uint256,address,address,uint256,uint256)',
                'PositionClosed(uint256,address,uint256,uint256)'
            ]
        
        # Build event signature filter
        sig_filter = " OR ".join([f"event_signature = '{sig}'" for sig in event_signatures])
        
        # Block filters
        block_filter = ""
        if start_block:
            block_filter += f" AND block_number >= {start_block}"
        if end_block:
            block_filter += f" AND block_number <= {end_block}"
        
        return f"""
        SELECT 
            transaction_hash,
            block_number,
            timestamp,
            log_index,
            event_signature,
            event_name,
            address,
            topics,
            parameters
        FROM base.events
        WHERE address = '{manager}'
            AND ({sig_filter})
            {block_filter}
        ORDER BY block_number DESC, log_index DESC
        """
    
    @staticmethod
    def wallet_summary_query(
        wallet_addresses: List[str],
        lookback_hours: int = 24
    ) -> str:
        """Build query for aggregated wallet performance summary.
        
        Args:
            wallet_addresses: List of wallet addresses
            lookback_hours: Hours to look back (default: 24)
            
        Returns:
            SQL query string
        """
        wallets = ", ".join([f"'{w}'" for w in wallet_addresses])
        start_time = (datetime.utcnow() - timedelta(hours=lookback_hours)).isoformat()
        
        return f"""
        SELECT 
            from_address as wallet,
            COUNT(*) as tx_count,
            SUM(gas * gas_price) / 1e18 as total_gas_eth,
            MIN(timestamp) as first_tx,
            MAX(timestamp) as last_tx
        FROM base.transactions
        WHERE from_address IN ({wallets})
            AND timestamp >= '{start_time}'
        GROUP BY from_address
        """
    
    @staticmethod
    def combined_wallet_data_query(
        wallet_address: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> str:
        """Build a combined query for wallet transactions and USDC transfer events.
        
        Args:
            wallet_address: Wallet address to query
            start_time: Start time for filtering
            end_time: End time for filtering
            
        Returns:
            SQL query string
        """
        wallet = wallet_address
        usdc = CDPQueryBuilder.USDC_ADDRESS
        
        # Time filters
        time_filter = ""
        if start_time:
            time_filter += f" AND timestamp >= '{start_time.isoformat()}'"
        if end_time:
            time_filter += f" AND timestamp <= '{end_time.isoformat()}'"
        
        # Query both ETH transactions and USDC Transfer events
        return f"""
        WITH eth_transactions AS (
            SELECT 
                transaction_hash,
                block_number,
                timestamp,
                from_address,
                to_address,
                value,
                gas,
                gas_price,
                (gas * gas_price) / 1e18 as gas_cost_eth,
                'eth_transaction' as tx_type
            FROM base.transactions
            WHERE (from_address = '{wallet}' OR to_address = '{wallet}')
            {time_filter}
        ),
        usdc_transfers AS (
            SELECT 
                e.transaction_hash,
                e.block_number,
                e.timestamp,
                -- Extract from address (topic[1])
                CONCAT('0x', SUBSTRING(e.topics[2], 27)) as from_address,
                -- Extract to address (topic[2])
                CONCAT('0x', SUBSTRING(e.topics[3], 27)) as to_address,
                -- Extract value from data field
                e.data as value,
                t.gas,
                t.gas_price,
                (t.gas * t.gas_price) / 1e18 as gas_cost_eth,
                'usdc_transfer' as tx_type
            FROM base.events e
            JOIN base.transactions t ON e.transaction_hash = t.transaction_hash
            WHERE e.address = '{usdc}'
                AND e.event_signature = 'Transfer(address,address,uint256)'
                AND (
                    LOWER(e.topics[2]) LIKE '%{wallet[2:].lower()}%' 
                    OR LOWER(e.topics[3]) LIKE '%{wallet[2:].lower()}%'
                )
                {time_filter}
        )
        SELECT * FROM eth_transactions
        UNION ALL
        SELECT * FROM usdc_transfers
        ORDER BY timestamp DESC, block_number DESC
        """
    
    @staticmethod
    def position_events_with_decode_query(
        liquidity_manager: Optional[str] = None,
        owner_address: Optional[str] = None,
        start_block: Optional[int] = None
    ) -> str:
        """Build query for position events with parameter decoding.
        
        Args:
            liquidity_manager: Liquidity manager contract address
            owner_address: Filter by position owner
            start_block: Starting block number
            
        Returns:
            SQL query string with event decoding
        """
        manager = (liquidity_manager or CDPQueryBuilder.LIQUIDITY_MANAGER_ADDRESS).lower()
        
        # Owner filter
        owner_filter = ""
        if owner_address:
            owner_filter = f" AND topics[2] LIKE '%{owner_address.lower()[2:]}'"
        
        # Block filter
        block_filter = f" AND block_number >= {start_block}" if start_block else ""
        
        return f"""
        SELECT 
            transaction_hash,
            block_number,
            block_timestamp,
            log_index,
            event_signature,
            contract_address,
            topics,
            data,
            CASE 
                WHEN event_signature = 'PositionCreated(uint256,address,address,uint256,uint256)' THEN
                    JSON_OBJECT(
                        'event_type', 'position_created',
                        'token_id', topics[1],
                        'owner', CONCAT('0x', SUBSTRING(topics[2], 27)),
                        'pool', CONCAT('0x', SUBSTRING(topics[3], 27))
                    )
                WHEN event_signature = 'PositionClosed(uint256,address,uint256,uint256)' THEN
                    JSON_OBJECT(
                        'event_type', 'position_closed',
                        'token_id', topics[1],
                        'owner', CONCAT('0x', SUBSTRING(topics[2], 27))
                    )
                ELSE JSON_OBJECT('event_type', 'unknown')
            END as decoded_params
        FROM base.events
        WHERE LOWER(contract_address) = '{manager}'
            AND event_signature IN (
                'PositionCreated(uint256,address,address,uint256,uint256)',
                'PositionClosed(uint256,address,uint256,uint256)'
            )
            {owner_filter}
            {block_filter}
        ORDER BY block_number DESC, log_index DESC
        """