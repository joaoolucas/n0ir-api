-- Hotfix: Add missing strategy columns
-- Run this directly in production database to fix deployment

-- Add active_strategies column to users table if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='users' AND column_name='active_strategies') THEN
        ALTER TABLE users ADD COLUMN active_strategies JSONB;
        RAISE NOTICE 'Added users.active_strategies column';
    ELSE
        RAISE NOTICE 'users.active_strategies column already exists';
    END IF;
END $$;

-- Add strategy_type column to transactions table if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='transactions' AND column_name='strategy_type') THEN
        ALTER TABLE transactions ADD COLUMN strategy_type VARCHAR(50);
        RAISE NOTICE 'Added transactions.strategy_type column';
    ELSE
        RAISE NOTICE 'transactions.strategy_type column already exists';
    END IF;
END $$;

-- Mark migration 039 as complete in alembic_version
INSERT INTO alembic_version (version_num)
VALUES ('039_add_missing_strategy_columns')
ON CONFLICT (version_num) DO NOTHING;
