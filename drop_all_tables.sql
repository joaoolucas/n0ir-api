-- Script to drop all tables and recreate them
-- WARNING: This will DELETE ALL DATA!

-- Drop all tables (in correct order to handle foreign key constraints)
DROP TABLE IF EXISTS strategy_decisions CASCADE;
DROP TABLE IF EXISTS pool_metrics CASCADE;
DROP TABLE IF EXISTS daily_metrics CASCADE;
DROP TABLE IF EXISTS agent_states CASCADE;
DROP TABLE IF EXISTS transactions CASCADE;
DROP TABLE IF EXISTS positions CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- Drop any remaining sequences
DROP SEQUENCE IF EXISTS transactions_transaction_id_seq CASCADE;
DROP SEQUENCE IF EXISTS agent_states_state_id_seq CASCADE;
DROP SEQUENCE IF EXISTS daily_metrics_id_seq CASCADE;
DROP SEQUENCE IF EXISTS pool_metrics_id_seq CASCADE;
DROP SEQUENCE IF EXISTS strategy_decisions_id_seq CASCADE;

-- Drop enums
DROP TYPE IF EXISTS transactiontype CASCADE;
DROP TYPE IF EXISTS transactionstatus CASCADE;
DROP TYPE IF EXISTS positionstatus CASCADE;
DROP TYPE IF EXISTS agentstatus CASCADE;
DROP TYPE IF EXISTS strategyaction CASCADE;

-- Recreate enums
CREATE TYPE transactiontype AS ENUM ('DEPOSIT', 'WITHDRAW', 'POSITION_ENTRY', 'POSITION_EXIT', 'FEE_COLLECTION');
CREATE TYPE transactionstatus AS ENUM ('PENDING', 'CONFIRMED', 'FAILED');
CREATE TYPE positionstatus AS ENUM ('active', 'closed', 'liquidated');
CREATE TYPE agentstatus AS ENUM ('IDLE', 'POSITION_OPEN', 'POSITION_CLOSED', 'REBALANCING', 'ERROR');
CREATE TYPE strategyaction AS ENUM ('OPEN_POSITION', 'CLOSE_POSITION', 'REBALANCE', 'HOLD', 'EMERGENCY_EXIT');

-- Create users table
CREATE TABLE users (
    user_id VARCHAR PRIMARY KEY,
    balance_usdc NUMERIC(20, 6) DEFAULT 0 NOT NULL,
    unrealized_pnl_usdc NUMERIC(20, 6) DEFAULT 0,
    realized_pnl_usdc NUMERIC(20, 6) DEFAULT 0,
    unrealized_pnl_percentage NUMERIC(10, 4) DEFAULT 0,
    realized_pnl_percentage NUMERIC(10, 4) DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create positions table
CREATE TABLE positions (
    nft_token_id INTEGER PRIMARY KEY,
    user_id VARCHAR REFERENCES users(user_id) NOT NULL,
    pool_address VARCHAR NOT NULL,
    pool_name VARCHAR,
    token0_address VARCHAR NOT NULL,
    token1_address VARCHAR NOT NULL,
    tick_lower INTEGER NOT NULL,
    tick_upper INTEGER NOT NULL,
    tick_spacing INTEGER NOT NULL,
    liquidity VARCHAR NOT NULL,
    staked BOOLEAN DEFAULT FALSE NOT NULL,
    gauge_address VARCHAR,
    entry_amount_usdc NUMERIC(20, 6) NOT NULL,
    current_value_usdc NUMERIC(20, 6),
    realized_pnl_usdc NUMERIC(20, 6) DEFAULT 0 NOT NULL,
    unrealized_pnl_usdc NUMERIC(20, 6) DEFAULT 0 NOT NULL,
    fees_earned_usdc NUMERIC(20, 6) DEFAULT 0 NOT NULL,
    rewards_earned_usdc NUMERIC(20, 6) DEFAULT 0 NOT NULL,
    protocol_fee_amount NUMERIC(20, 6) DEFAULT 0 NOT NULL,
    protocol_fee_collected BOOLEAN DEFAULT FALSE NOT NULL,
    protocol_fee_tx_hash VARCHAR,
    status positionstatus DEFAULT 'active' NOT NULL,
    entry_tx_hash VARCHAR,
    exit_tx_hash VARCHAR,
    entry_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    exit_date TIMESTAMP WITH TIME ZONE,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Create transactions table
CREATE TABLE transactions (
    transaction_id SERIAL PRIMARY KEY,
    user_id VARCHAR REFERENCES users(user_id) NOT NULL,
    transaction_type transactiontype NOT NULL,
    amount_usdc NUMERIC(20, 6) NOT NULL,
    pool_name VARCHAR,
    realized_pnl_usdc NUMERIC(20, 6) DEFAULT 0,
    portfolio_value_at_time NUMERIC(20, 6),
    cost_basis_withdrawn NUMERIC(20, 6),
    tx_hash VARCHAR,
    block_number INTEGER,
    gas_used NUMERIC(20, 6),
    gas_price NUMERIC(20, 6),
    status transactionstatus DEFAULT 'PENDING' NOT NULL,
    tx_metadata TEXT,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    confirmed_at TIMESTAMP WITH TIME ZONE
);

-- Create agent_states table
CREATE TABLE agent_states (
    state_id SERIAL PRIMARY KEY,
    user_id VARCHAR REFERENCES users(user_id) NOT NULL,
    status agentstatus DEFAULT 'IDLE' NOT NULL,
    current_position_id INTEGER,
    last_action VARCHAR,
    last_action_time TIMESTAMP WITH TIME ZONE,
    state_metadata TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create daily_metrics table
CREATE TABLE daily_metrics (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR REFERENCES users(user_id) NOT NULL,
    date DATE NOT NULL,
    starting_value NUMERIC(20, 6) NOT NULL,
    ending_value NUMERIC(20, 6) NOT NULL,
    daily_pnl NUMERIC(20, 6) NOT NULL,
    daily_return_pct NUMERIC(10, 4) NOT NULL,
    high_value NUMERIC(20, 6),
    low_value NUMERIC(20, 6),
    total_fees_earned NUMERIC(20, 6) DEFAULT 0,
    total_gas_spent NUMERIC(20, 6) DEFAULT 0,
    num_transactions INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UNIQUE(user_id, date)
);

-- Create pool_metrics table
CREATE TABLE pool_metrics (
    id SERIAL PRIMARY KEY,
    pool_address VARCHAR NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    tvl_usd NUMERIC(20, 6),
    volume_24h_usd NUMERIC(20, 6),
    fees_24h_usd NUMERIC(20, 6),
    apr_24h NUMERIC(10, 4),
    tick INTEGER,
    sqrt_price_x96 VARCHAR,
    liquidity VARCHAR,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Create strategy_decisions table
CREATE TABLE strategy_decisions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR REFERENCES users(user_id) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    action strategyaction NOT NULL,
    pool_address VARCHAR,
    position_id INTEGER,
    reasoning TEXT,
    market_conditions TEXT,
    expected_return NUMERIC(10, 4),
    risk_score NUMERIC(5, 2),
    confidence_score NUMERIC(5, 2),
    metadata TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Create indexes
CREATE INDEX idx_position_user_id ON positions(user_id);
CREATE INDEX idx_position_pool ON positions(pool_address);
CREATE INDEX idx_position_status ON positions(status);
CREATE INDEX idx_position_entry_date ON positions(entry_date);
CREATE INDEX idx_position_exit_date ON positions(exit_date);
CREATE INDEX idx_position_user_status ON positions(user_id, status);
CREATE INDEX idx_position_staked ON positions(staked);
CREATE INDEX idx_position_protocol_fee_tx ON positions(protocol_fee_tx_hash);

CREATE INDEX idx_transaction_user_id ON transactions(user_id);
CREATE INDEX idx_transaction_type ON transactions(transaction_type);
CREATE INDEX idx_transaction_status ON transactions(status);
CREATE INDEX idx_transaction_created ON transactions(created_at);
CREATE INDEX idx_transaction_tx_hash ON transactions(tx_hash);

CREATE INDEX idx_agent_state_user_id ON agent_states(user_id);
CREATE INDEX idx_agent_state_status ON agent_states(status);

CREATE INDEX idx_daily_metrics_user_date ON daily_metrics(user_id, date);
CREATE INDEX idx_pool_metrics_pool_time ON pool_metrics(pool_address, timestamp);
CREATE INDEX idx_strategy_user_time ON strategy_decisions(user_id, timestamp);

-- Verify tables were created
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;