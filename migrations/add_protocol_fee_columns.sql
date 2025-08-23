-- Add missing protocol fee columns to positions table
-- These columns track protocol fees charged on positions

-- Add protocol_fee_amount column
ALTER TABLE positions 
ADD COLUMN IF NOT EXISTS protocol_fee_amount DECIMAL(20, 8) DEFAULT 0;

-- Add protocol_fee_collected column  
ALTER TABLE positions
ADD COLUMN IF NOT EXISTS protocol_fee_collected BOOLEAN DEFAULT FALSE;

-- Add protocol_fee_tx_hash column
ALTER TABLE positions
ADD COLUMN IF NOT EXISTS protocol_fee_tx_hash VARCHAR(255);

-- Add indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_positions_protocol_fee_collected 
ON positions(protocol_fee_collected) 
WHERE protocol_fee_collected = FALSE;

-- Add comment to explain the columns
COMMENT ON COLUMN positions.protocol_fee_amount IS 'Amount of protocol fee charged for this position in USDC';
COMMENT ON COLUMN positions.protocol_fee_collected IS 'Whether the protocol fee has been collected';
COMMENT ON COLUMN positions.protocol_fee_tx_hash IS 'Transaction hash of the protocol fee collection';