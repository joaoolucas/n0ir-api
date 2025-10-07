-- Migration: Clean up redundant fields and optimize schema
-- Date: 2025-01-16
-- Description: Remove redundant fields, simplify schema, improve performance

-- Step 1: Remove redundant agent fields from users table (already in user_metadata)
ALTER TABLE users 
DROP COLUMN IF EXISTS agent_started_at,
DROP COLUMN IF EXISTS agent_stopped_at,
DROP COLUMN IF EXISTS last_balance_check,
DROP COLUMN IF EXISTS agent_metadata;

-- Step 2: Remove protocol fee fields from positions (move to transactions)
-- First, migrate any existing protocol fee data to transactions
INSERT INTO transactions (
    id,
    user_id,
    tx_type,
    amount_usdc,
    position_id,
    tx_hash,
    status,
    event_data,
    created_at
)
SELECT 
    gen_random_uuid(),
    p.user_id,
    'POSITION_CLOSED',  -- Protocol fees are part of closing
    p.protocol_fee_amount,
    p.token_id,
    p.protocol_fee_tx_hash,
    'CONFIRMED',
    jsonb_build_object(
        'fee_type', 'protocol_fee',
        'fee_collected', p.protocol_fee_collected
    ),
    COALESCE(p.exit_date, p.updated_at)
FROM positions p
WHERE p.protocol_fee_amount > 0
  AND NOT EXISTS (
    SELECT 1 FROM transactions t 
    WHERE t.position_id = p.token_id 
      AND t.event_data->>'fee_type' = 'protocol_fee'
  );

-- Now remove the columns
ALTER TABLE positions
DROP COLUMN IF EXISTS protocol_fee_amount,
DROP COLUMN IF EXISTS protocol_fee_collected,
DROP COLUMN IF EXISTS protocol_fee_tx_hash;

-- Step 3: Standardize transaction types - Update old types to new simplified types
UPDATE transactions 
SET tx_type = CASE 
    WHEN tx_type IN ('WITHDRAWAL', 'withdraw') THEN 'WITHDRAW'
    WHEN tx_type IN ('deposit', 'DEPOSIT') THEN 'DEPOSIT'
    WHEN tx_type IN ('POSITION_OPENED', 'position_opened', 'POSITION_ENTRY', 'position_entry', 'STAKING', 'staking') THEN 'POSITION_CREATED'
    WHEN tx_type IN ('POSITION_EXIT', 'position_exit', 'FEE_COLLECTION', 'fee_collection', 'AERO_SWAP', 'aero_swap', 'PROTOCOL_FEE', 'protocol_fee') THEN 'POSITION_CLOSED'
    ELSE tx_type
END
WHERE tx_type NOT IN ('DEPOSIT', 'WITHDRAW', 'POSITION_CREATED', 'POSITION_CLOSED');

-- Step 4: Add index for simplified transaction types
DROP INDEX IF EXISTS idx_transactions_type;
CREATE INDEX idx_transactions_type ON transactions(tx_type, status);

-- Step 5: Remove unused columns from positions that are always NULL or unused
-- (Based on the hybrid model analysis, these JSONB fields are never used)
ALTER TABLE positions
DROP COLUMN IF EXISTS position_data,
DROP COLUMN IF EXISTS blockchain_data;

-- Step 6: Optimize user_metadata structure - ensure it's not null
UPDATE users 
SET user_metadata = '{}'::jsonb 
WHERE user_metadata IS NULL;

ALTER TABLE users 
ALTER COLUMN user_metadata SET DEFAULT '{}'::jsonb,
ALTER COLUMN user_metadata SET NOT NULL;

-- Step 7: Create optimized indexes for common queries
-- Drop redundant indexes first
DROP INDEX IF EXISTS idx_users_pnl;
DROP INDEX IF EXISTS idx_positions_user_status;

-- Create new optimized indexes
CREATE INDEX IF NOT EXISTS idx_users_balance_active 
ON users(usdc_balance) 
WHERE user_metadata->>'status' = 'ACTIVE' OR user_metadata->>'status' IS NULL;

CREATE INDEX IF NOT EXISTS idx_positions_user_active 
ON positions(user_id, status) 
WHERE status = 'ACTIVE';

CREATE INDEX IF NOT EXISTS idx_transactions_recent 
ON transactions(user_id, created_at DESC) 
WHERE status = 'CONFIRMED';

-- Step 8: Add constraints to ensure data integrity
ALTER TABLE transactions
ADD CONSTRAINT chk_tx_type 
CHECK (tx_type IN ('DEPOSIT', 'WITHDRAW', 'POSITION_CREATED', 'POSITION_CLOSED'));

-- Step 9: Clean up positions with NULL or invalid data
UPDATE positions 
SET realized_pnl_usdc = 0 
WHERE realized_pnl_usdc IS NULL;

UPDATE positions 
SET fees_earned_usdc = 0 
WHERE fees_earned_usdc IS NULL;

UPDATE positions 
SET rewards_earned_usdc = 0 
WHERE rewards_earned_usdc IS NULL;

-- Step 10: Create a summary view for quick user stats
CREATE OR REPLACE VIEW user_summary AS
SELECT 
    u.user_id,
    u.cdp_wallet_address,
    u.usdc_balance,
    COUNT(DISTINCT p.token_id) FILTER (WHERE p.status = 'ACTIVE') as active_positions,
    COUNT(DISTINCT p.token_id) as total_positions,
    COALESCE(SUM(p.current_value_usdc) FILTER (WHERE p.status = 'ACTIVE'), 0) as total_position_value,
    COALESCE(u.unrealized_pnl_usd + u.realized_pnl_usd, 0) as total_pnl_usd,
    u.created_at,
    u.updated_at
FROM users u
LEFT JOIN positions p ON u.user_id = p.user_id
GROUP BY u.user_id;

-- Verification queries
SELECT 'Migration completed successfully' as status;

SELECT 
    'Transaction types simplified' as check,
    tx_type, 
    COUNT(*) as count 
FROM transactions 
GROUP BY tx_type 
ORDER BY count DESC;

SELECT 
    'Positions cleaned' as check,
    COUNT(*) as total_positions,
    COUNT(*) FILTER (WHERE status = 'ACTIVE') as active_positions
FROM positions;

SELECT 
    'Users metadata normalized' as check,
    COUNT(*) as total_users,
    COUNT(*) FILTER (WHERE user_metadata IS NOT NULL) as with_metadata
FROM users;