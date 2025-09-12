-- Fix schema column names
-- This script renames old column names to new ones

-- Check and rename PnL columns if they exist with old names
DO $$
BEGIN
    -- Check if old column exists and new doesn't
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'positions' AND column_name = 'unrealized_pnl_usd')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'positions' AND column_name = 'pnl_usdc') THEN
        ALTER TABLE positions RENAME COLUMN unrealized_pnl_usd TO pnl_usdc;
        RAISE NOTICE 'Renamed unrealized_pnl_usd to pnl_usdc';
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'positions' AND column_name = 'unrealized_pnl_pct')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'positions' AND column_name = 'pnl_pct') THEN
        ALTER TABLE positions RENAME COLUMN unrealized_pnl_pct TO pnl_pct;
        RAISE NOTICE 'Renamed unrealized_pnl_pct to pnl_pct';
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'positions' AND column_name = 'realized_pnl_usd')
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'positions' AND column_name = 'realized_pnl_usdc') THEN
        ALTER TABLE positions RENAME COLUMN realized_pnl_usd TO realized_pnl_usdc;
        RAISE NOTICE 'Renamed realized_pnl_usd to realized_pnl_usdc';
    END IF;
    
    -- Update alembic version if needed
    IF EXISTS (SELECT 1 FROM alembic_version WHERE version_num = '026_merge_hedge_into_positions') THEN
        UPDATE alembic_version SET version_num = '027_remove_unused_columns';
        RAISE NOTICE 'Updated alembic version to 027';
    END IF;
END $$;

-- Verify the changes
SELECT 
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns 
WHERE table_name = 'positions' 
AND column_name IN ('pnl_usdc', 'pnl_pct', 'realized_pnl_usdc', 'unrealized_pnl_usd', 'unrealized_pnl_pct', 'realized_pnl_usd')
ORDER BY column_name;