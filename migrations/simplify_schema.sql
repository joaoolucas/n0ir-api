-- Migration: Simplify database schema
-- Description: Remove redundant fields, use NFT ID as position PK, integrate fee tracking

-- Step 1: Remove redundant columns from users table
ALTER TABLE users 
DROP COLUMN IF EXISTS cdp_owner_wallet_address,
DROP COLUMN IF EXISTS cdp_owner_wallet_name;

-- Step 2: Add protocol fee tracking to positions table
ALTER TABLE positions 
ADD COLUMN IF NOT EXISTS protocol_fee_amount DECIMAL(20,6) DEFAULT 0,
ADD COLUMN IF NOT EXISTS protocol_fee_collected BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS protocol_fee_tx_hash VARCHAR;

-- Step 3: Add related position to transactions
ALTER TABLE transactions 
ADD COLUMN IF NOT EXISTS related_position_id INTEGER,
ADD CONSTRAINT fk_transaction_position 
    FOREIGN KEY (related_position_id) 
    REFERENCES positions(nft_token_id);

-- Step 4: Create index for protocol fee queries
CREATE INDEX IF NOT EXISTS idx_position_protocol_fee_collected 
ON positions(protocol_fee_collected);

CREATE INDEX IF NOT EXISTS idx_position_protocol_fee_tx 
ON positions(protocol_fee_tx_hash);

CREATE INDEX IF NOT EXISTS idx_transaction_related_position 
ON transactions(related_position_id);

-- Step 5: Migrate existing protocol_fees data to positions (if table exists)
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'protocol_fees') THEN
        -- Update positions with fee data
        UPDATE positions p
        SET protocol_fee_amount = pf.fee_amount_usdc,
            protocol_fee_collected = pf.collected,
            protocol_fee_tx_hash = pf.collection_tx_hash
        FROM protocol_fees pf
        WHERE p.position_id = pf.position_id;
        
        -- Create fee collection transactions for collected fees
        INSERT INTO transactions (
            transaction_id,
            user_id,
            transaction_type,
            amount_usdc,
            related_position_id,
            tx_hash,
            status,
            created_at,
            confirmed_at
        )
        SELECT 
            gen_random_uuid(),
            pf.user_id,
            'protocol_fee',
            pf.fee_amount_usdc,
            p.nft_token_id,
            pf.collection_tx_hash,
            'confirmed',
            pf.created_at,
            pf.collected_at
        FROM protocol_fees pf
        JOIN positions p ON p.position_id = pf.position_id
        WHERE pf.collected = TRUE;
    END IF;
END $$;

-- Step 6: Drop protocol_fees table
DROP TABLE IF EXISTS protocol_fees CASCADE;

-- Step 7: Update position primary key (COMPLEX - needs careful handling)
-- Note: This is tricky because we need to preserve foreign key relationships
-- Run this only if you're sure nft_token_id is unique and not null for all positions

-- First, ensure nft_token_id is unique and not null
ALTER TABLE positions 
ALTER COLUMN nft_token_id SET NOT NULL;

-- Add unique constraint if not exists
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'positions_nft_token_id_key'
    ) THEN
        ALTER TABLE positions 
        ADD CONSTRAINT positions_nft_token_id_key UNIQUE (nft_token_id);
    END IF;
END $$;

-- Note: To fully switch primary key from position_id to nft_token_id,
-- you'll need to update all foreign key references first.
-- This is a complex operation that should be done carefully.

-- Step 8: Update transaction type enum (if using enums)
-- This requires recreating the enum type
ALTER TYPE transactiontype RENAME TO transactiontype_old;
CREATE TYPE transactiontype AS ENUM ('deposit', 'withdraw', 'position_entry', 'position_exit', 'protocol_fee');
ALTER TABLE transactions 
    ALTER COLUMN transaction_type TYPE transactiontype USING transaction_type::text::transactiontype;
DROP TYPE transactiontype_old;

-- Step 9: Clean up old indexes
DROP INDEX IF EXISTS idx_user_cdp_owner;

-- Step 10: Add comments for documentation
COMMENT ON COLUMN positions.protocol_fee_amount IS 'Protocol fee amount (5% of profits)';
COMMENT ON COLUMN positions.protocol_fee_collected IS 'Whether protocol fee has been collected';
COMMENT ON COLUMN positions.protocol_fee_tx_hash IS 'Transaction hash of fee collection';
COMMENT ON COLUMN transactions.related_position_id IS 'NFT token ID of related position (for entry/exit/fee transactions)';

-- Verification queries
SELECT 'Users table columns' as check_type, column_name 
FROM information_schema.columns 
WHERE table_name = 'users' 
ORDER BY ordinal_position;

SELECT 'Protocol fees migrated' as check_type, COUNT(*) as count 
FROM positions 
WHERE protocol_fee_amount > 0;

SELECT 'Protocol fee transactions created' as check_type, COUNT(*) as count 
FROM transactions 
WHERE transaction_type = 'protocol_fee';