# n0ir Simplified Database Schema

## Core Design Principles
1. **Wallet-as-Identity**: User's wallet address serves as primary key
2. **On-chain Truth**: NFT token IDs are primary keys for positions
3. **Integrated Fee Tracking**: Protocol fees tracked within positions
4. **Comprehensive Audit Trail**: All money movements in transactions table

---

## 1. USERS Table
**Purpose:** User account management with Web3 authentication

```sql
CREATE TABLE users (
    user_id VARCHAR PRIMARY KEY,        -- User's EOA wallet address (e.g., "0x742...")
    wallet_address VARCHAR UNIQUE NOT NULL,  -- CDP smart wallet for trading
    cdp_wallet_name VARCHAR NOT NULL,    -- Human-readable CDP wallet identifier
    status ENUM('active', 'suspended', 'closed') DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_user_wallet_address ON users(wallet_address);
CREATE INDEX idx_user_status ON users(status);
CREATE INDEX idx_user_created_at ON users(created_at);
```

**Key Points:**
- No passwords - wallet IS the authentication
- Each user gets one CDP trading wallet
- user_id = their MetaMask/wallet address

---

## 2. POSITIONS Table
**Purpose:** Track liquidity positions with integrated fee management

```sql
CREATE TABLE positions (
    nft_token_id INTEGER PRIMARY KEY,    -- Aerodrome NFT ID (on-chain truth)
    user_id VARCHAR NOT NULL REFERENCES users(user_id),
    
    -- Pool information
    pool_address VARCHAR NOT NULL,
    token0_address VARCHAR NOT NULL,
    token1_address VARCHAR NOT NULL,
    tick_lower INTEGER NOT NULL,
    tick_upper INTEGER NOT NULL,
    liquidity VARCHAR NOT NULL,          -- Large number as string
    
    -- Financial metrics
    entry_amount_usdc DECIMAL(20,6) NOT NULL,
    current_value_usdc DECIMAL(20,6),
    realized_pnl_usdc DECIMAL(20,6) DEFAULT 0,
    fees_earned_usdc DECIMAL(20,6) DEFAULT 0,
    rewards_earned_usdc DECIMAL(20,6) DEFAULT 0,
    
    -- Protocol fee tracking (5% of profits)
    protocol_fee_amount DECIMAL(20,6) DEFAULT 0,
    protocol_fee_collected BOOLEAN DEFAULT FALSE,
    protocol_fee_tx_hash VARCHAR,
    
    -- Status and timestamps
    status ENUM('active', 'closed', 'liquidated') DEFAULT 'active',
    entry_tx_hash VARCHAR,
    exit_tx_hash VARCHAR,
    entry_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    exit_date TIMESTAMP WITH TIME ZONE,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_position_user_id ON positions(user_id);
CREATE INDEX idx_position_pool ON positions(pool_address);
CREATE INDEX idx_position_status ON positions(status);
CREATE INDEX idx_position_protocol_fee_collected ON positions(protocol_fee_collected);
```

**Key Points:**
- NFT ID is the primary key (matches blockchain)
- Protocol fees tracked directly in position
- No separate fee table needed

---

## 3. TRANSACTIONS Table
**Purpose:** Complete audit trail of all money movements

```sql
CREATE TABLE transactions (
    transaction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR NOT NULL REFERENCES users(user_id),
    
    -- Transaction details
    transaction_type ENUM('deposit', 'withdraw', 'position_entry', 'position_exit', 'protocol_fee'),
    amount_usdc DECIMAL(20,6) NOT NULL,
    related_position_id INTEGER REFERENCES positions(nft_token_id),
    
    -- Blockchain data
    tx_hash VARCHAR UNIQUE,
    block_number INTEGER,
    gas_used INTEGER,
    gas_price DECIMAL(20,9),
    
    -- Status tracking
    status ENUM('pending', 'confirmed', 'failed', 'cancelled') DEFAULT 'pending',
    tx_metadata TEXT,  -- JSON for flexibility
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    confirmed_at TIMESTAMP WITH TIME ZONE
);

-- Indexes
CREATE INDEX idx_transaction_user_id ON transactions(user_id);
CREATE INDEX idx_transaction_type ON transactions(transaction_type);
CREATE INDEX idx_transaction_status ON transactions(status);
CREATE INDEX idx_transaction_related_position ON transactions(related_position_id);
```

**Key Points:**
- Tracks ALL money movements
- Links to positions via related_position_id
- Protocol fees are just another transaction type

---

## 4. DAILY_METRICS Table
**Purpose:** Pre-aggregated analytics for performance

```sql
CREATE TABLE daily_metrics (
    metric_date DATE NOT NULL,
    metric_type VARCHAR NOT NULL,  -- 'platform', 'user:0x...', 'pool:0x...'
    
    -- Aggregated metrics
    total_volume_usdc DECIMAL(20,2) DEFAULT 0,
    positions_opened INTEGER DEFAULT 0,
    positions_closed INTEGER DEFAULT 0,
    active_users INTEGER DEFAULT 0,
    total_tvl_usdc DECIMAL(20,2) DEFAULT 0,
    protocol_fees_collected_usdc DECIMAL(20,2) DEFAULT 0,
    total_pnl_usdc DECIMAL(20,2) DEFAULT 0,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (metric_date, metric_type)
);

-- Indexes
CREATE INDEX idx_daily_metrics_date ON daily_metrics(metric_date);
CREATE INDEX idx_daily_metrics_type ON daily_metrics(metric_type);
```

---

## 5. POOL_METRICS Table
**Purpose:** Track pool performance for strategy decisions

```sql
CREATE TABLE pool_metrics (
    pool_address VARCHAR NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    
    -- Pool data
    tvl_usd DECIMAL(20,2),
    volume_24h_usd DECIMAL(20,2),
    fee_apr DECIMAL(10,2),
    reward_apr DECIMAL(10,2),
    
    PRIMARY KEY (pool_address, timestamp)
);

-- Indexes
CREATE INDEX idx_pool_metrics_timestamp ON pool_metrics(timestamp);
CREATE INDEX idx_pool_metrics_apr ON pool_metrics(fee_apr + reward_apr);
```

---

## Simplified Flow Examples

### User Onboarding
```sql
-- 1. User connects wallet (0xABC...)
INSERT INTO users (user_id, wallet_address, cdp_wallet_name)
VALUES ('0xABC...', '0xCDP...', 'CDP-0xABC');
```

### Position Lifecycle
```sql
-- 2. Open position
INSERT INTO positions (nft_token_id, user_id, pool_address, entry_amount_usdc)
VALUES (12345, '0xABC...', '0xPOOL...', 1000);

INSERT INTO transactions (user_id, transaction_type, amount_usdc, related_position_id)
VALUES ('0xABC...', 'position_entry', 1000, 12345);

-- 3. Close position with profit
UPDATE positions 
SET status = 'closed',
    realized_pnl_usdc = 100,
    protocol_fee_amount = 5,  -- 5% of 100
    exit_date = NOW()
WHERE nft_token_id = 12345;

INSERT INTO transactions (user_id, transaction_type, amount_usdc, related_position_id)
VALUES ('0xABC...', 'position_exit', 1100, 12345);

-- 4. Collect protocol fee
UPDATE positions 
SET protocol_fee_collected = TRUE,
    protocol_fee_tx_hash = '0xTX...'
WHERE nft_token_id = 12345;

INSERT INTO transactions (user_id, transaction_type, amount_usdc, related_position_id, tx_hash)
VALUES ('0xABC...', 'protocol_fee', 5, 12345, '0xTX...');
```

---

## Key Improvements

### ✅ What We Removed
- ❌ `cdp_owner_wallet_address` - Redundant with user_id
- ❌ `protocol_fees` table - Overcomplicated
- ❌ `position_id` UUID - NFT ID is the truth

### ✅ What We Added
- ✅ Protocol fee tracking in positions
- ✅ Related position in transactions
- ✅ NFT ID as primary key

### ✅ Benefits
- Fewer JOINs needed
- Direct blockchain mapping
- Simpler fee tracking
- Cleaner relationships
- Better performance

---

## Migration Safety

Before migrating:
1. **Backup everything**
2. **Test on staging first**
3. **Ensure all NFT IDs are unique**
4. **Update application code**
5. **Run migration in transaction**

The migration script handles:
- Data preservation
- Foreign key updates
- Index optimization
- Legacy data migration