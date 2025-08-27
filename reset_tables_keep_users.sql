-- Reset all tables except users table
-- This script clears all data but keeps user records

BEGIN;

-- Delete all positions
DELETE FROM positions;

-- Delete all transactions
DELETE FROM transactions;

-- Reset any cached balance data in users table (if needed)
UPDATE users SET 
    realized_pnl_usd = 0,
    unrealized_pnl_usd = 0,
    realized_pnl_percentage = 0,
    unrealized_pnl_percentage = 0
WHERE realized_pnl_usd IS NOT NULL 
   OR unrealized_pnl_usd IS NOT NULL 
   OR realized_pnl_percentage IS NOT NULL 
   OR unrealized_pnl_percentage IS NOT NULL;

-- Log the operation
SELECT 
    'Tables reset completed' as status,
    (SELECT COUNT(*) FROM users) as users_kept,
    (SELECT COUNT(*) FROM positions) as positions_after,
    (SELECT COUNT(*) FROM transactions) as transactions_after;

COMMIT;