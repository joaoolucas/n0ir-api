-- Fix allocated capital for user 0xa388Ed18DAE0DA9d16BAF9f57Eb9dE03512dBAF4
-- This user has $48.73 in their wallet but $50 allocated to strategy n1
-- Update allocated capital to match actual portfolio value

UPDATE user_strategies
SET allocated_capital_usd = (
    SELECT total_portfolio_value
    FROM users
    WHERE user_id = '0xa388Ed18DAE0DA9d16BAF9f57Eb9dE03512dBAF4'
),
updated_at = CURRENT_TIMESTAMP
WHERE user_id = '0xa388Ed18DAE0DA9d16BAF9f57Eb9dE03512dBAF4'
AND status = 'active';

-- Verify the update
SELECT
    u.user_id,
    u.total_portfolio_value,
    us.strategy_type,
    us.allocated_capital_usd,
    us.deployed_capital_usd
FROM users u
JOIN user_strategies us ON u.user_id = us.user_id
WHERE u.user_id = '0xa388Ed18DAE0DA9d16BAF9f57Eb9dE03512dBAF4'
AND us.status = 'active';
