-- Manual fix for column names
-- Run this directly on the Railway PostgreSQL database

-- Step 1: Check current state
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'positions' 
AND column_name LIKE '%pnl%'
ORDER BY column_name;

-- Step 2: Rename columns if they exist with old names
DO $$
BEGIN
    -- Check and rename unrealized_pnl_usd to pnl_usdc
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'positions' AND column_name = 'unrealized_pnl_usd') THEN
        ALTER TABLE positions RENAME COLUMN unrealized_pnl_usd TO pnl_usdc;
        RAISE NOTICE 'Renamed unrealized_pnl_usd to pnl_usdc';
    ELSE
        RAISE NOTICE 'Column unrealized_pnl_usd not found or already renamed';
    END IF;
    
    -- Check and rename unrealized_pnl_pct to pnl_pct
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'positions' AND column_name = 'unrealized_pnl_pct') THEN
        ALTER TABLE positions RENAME COLUMN unrealized_pnl_pct TO pnl_pct;
        RAISE NOTICE 'Renamed unrealized_pnl_pct to pnl_pct';
    ELSE
        RAISE NOTICE 'Column unrealized_pnl_pct not found or already renamed';
    END IF;
    
    -- Check and rename realized_pnl_usd to realized_pnl_usdc
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'positions' AND column_name = 'realized_pnl_usd') THEN
        ALTER TABLE positions RENAME COLUMN realized_pnl_usd TO realized_pnl_usdc;
        RAISE NOTICE 'Renamed realized_pnl_usd to realized_pnl_usdc';
    ELSE
        RAISE NOTICE 'Column realized_pnl_usd not found or already renamed';
    END IF;
END $$;

-- Step 3: Verify the changes
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'positions' 
AND column_name IN ('pnl_usdc', 'pnl_pct', 'realized_pnl_usdc', 'unrealized_pnl_usd', 'unrealized_pnl_pct', 'realized_pnl_usd')
ORDER BY column_name;

-- Step 4: Update alembic version if needed
UPDATE alembic_version 
SET version_num = '029_consolidate_transactions'
WHERE version_num IN ('026_merge_hedge_into_positions', '027_remove_unused_columns', '028_convert_jsonb_to_columns');

-- Show final state
SELECT version_num FROM alembic_version;