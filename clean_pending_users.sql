-- Clean up the user with "pending" wallet address
-- This user was created before we fixed the unique constraint issue

-- First, check which user has the "pending" address
SELECT user_id, cdp_wallet_address, cdp_wallet_name, created_at 
FROM users 
WHERE cdp_wallet_address = 'pending';

-- Update it to use the unique placeholder format
UPDATE users 
SET cdp_wallet_address = CONCAT('pending_', user_id)
WHERE cdp_wallet_address = 'pending';

-- Verify the update
SELECT user_id, cdp_wallet_address, cdp_wallet_name, created_at 
FROM users 
WHERE cdp_wallet_address LIKE 'pending_%';