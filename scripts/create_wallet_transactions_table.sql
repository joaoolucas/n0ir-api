-- Create wallet_transactions table for storing CDP blockchain data
CREATE TABLE IF NOT EXISTS wallet_transactions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    transaction_hash VARCHAR(66) UNIQUE NOT NULL,
    block_number BIGINT NOT NULL,
    from_address VARCHAR(42) NOT NULL,
    to_address VARCHAR(42),
    value VARCHAR(78),  -- Store as string to handle large wei values
    gas BIGINT,
    gas_price BIGINT,
    gas_cost_eth NUMERIC(20, 10),
    timestamp TIMESTAMPTZ NOT NULL,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    is_agent_wallet BOOLEAN DEFAULT FALSE,
    user_id VARCHAR(42) REFERENCES users(user_id) ON DELETE CASCADE,
    
    -- Indexes for performance
    INDEX idx_wallet_tx_user (user_id),
    INDEX idx_wallet_tx_hash (transaction_hash),
    INDEX idx_wallet_tx_block (block_number),
    INDEX idx_wallet_tx_timestamp (timestamp),
    INDEX idx_wallet_tx_from (from_address),
    INDEX idx_wallet_tx_to (to_address)
);

-- Create liquidity_events table for storing position events
CREATE TABLE IF NOT EXISTS liquidity_events (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    transaction_hash VARCHAR(66) NOT NULL,
    block_number BIGINT NOT NULL,
    log_index INTEGER NOT NULL,
    event_signature VARCHAR(255) NOT NULL,
    event_name VARCHAR(100),
    owner_address VARCHAR(42),
    token_id BIGINT,
    tick_lower INTEGER,
    tick_upper INTEGER,
    liquidity VARCHAR(78),
    amount0 VARCHAR(78),
    amount1 VARCHAR(78),
    timestamp TIMESTAMPTZ NOT NULL,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    user_id VARCHAR(42) REFERENCES users(user_id) ON DELETE CASCADE,
    
    -- Ensure uniqueness of events
    UNIQUE(transaction_hash, log_index),
    
    -- Indexes for performance
    INDEX idx_liquidity_events_user (user_id),
    INDEX idx_liquidity_events_owner (owner_address),
    INDEX idx_liquidity_events_token (token_id),
    INDEX idx_liquidity_events_block (block_number),
    INDEX idx_liquidity_events_timestamp (timestamp)
);

-- Create blockchain_sync table for tracking sync status
CREATE TABLE IF NOT EXISTS blockchain_sync (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    sync_type VARCHAR(50) NOT NULL,  -- 'wallet_history', 'liquidity_events', etc.
    user_id VARCHAR(42),
    wallet_address VARCHAR(42),
    last_synced_block BIGINT,
    last_synced_at TIMESTAMPTZ,
    sync_status VARCHAR(20) DEFAULT 'idle',  -- 'idle', 'syncing', 'error'
    error_message TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Indexes
    INDEX idx_sync_user (user_id),
    INDEX idx_sync_wallet (wallet_address),
    INDEX idx_sync_type (sync_type),
    INDEX idx_sync_status (sync_status)
);