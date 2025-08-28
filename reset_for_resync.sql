-- Reset tables for full resync
-- This will clear transactions and positions so the watcher can rebuild with correct amounts

-- Delete all transactions
DELETE FROM transactions;

-- Delete all positions  
DELETE FROM positions;

-- Keep users table intact
-- User balance is calculated from transactions, so no need to update users table

SELECT 'Tables reset for resync' as status;