-- Complete database reset
-- This will clear ALL tables

-- Delete all data from all tables
DELETE FROM transactions;
DELETE FROM positions;
DELETE FROM users;
DELETE FROM daily_metrics;
DELETE FROM agent_events;
DELETE FROM executor_stats;
DELETE FROM pool_metrics;
DELETE FROM strategy_decisions;

-- Keep table structure intact but data is cleared
SELECT 'Complete database reset done' as status;