"""Schema fixes for production database issues."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logger import logger


async def ensure_schema_compatibility(session: AsyncSession):
    """Ensure all required schema elements exist in the database."""
    
    try:
        # 1. Clean up old enum types (no longer needed with JSONB)
        result = await session.execute(text("""
            SELECT typname FROM pg_type 
            WHERE typname IN ('agentstatus', 'agent_status_enum')
        """))
        existing_enums = [row[0] for row in result.fetchall()]
        
        # Drop old enum types as we're using JSONB now
        for enum_type in existing_enums:
            try:
                await session.execute(text(f"DROP TYPE IF EXISTS {enum_type} CASCADE"))
                await session.commit()
                logger.info(f"Dropped old enum type: {enum_type}")
            except Exception as e:
                logger.warning(f"Could not drop enum {enum_type}: {e}")
        
        # 2. Agent status is now stored in user_metadata JSONB field
        # No need to add separate columns - using 3-table architecture
        logger.info("Agent status is stored in user_metadata JSONB field (3-table architecture)")
        
        # 3. Check and add related_position_id to transactions table if it doesn't exist
        result = await session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'transactions' 
            AND column_name = 'related_position_id'
        """))
        has_related_position = result.fetchone() is not None
        
        if not has_related_position:
            logger.info("Adding related_position_id to transactions table...")
            await session.execute(text("""
                ALTER TABLE transactions
                ADD COLUMN IF NOT EXISTS related_position_id BIGINT
            """))
            await session.commit()
            logger.info("Added related_position_id to transactions table")
        
        # 4. Check and drop old cdp_owner columns if they exist
        result = await session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users' 
            AND column_name IN ('cdp_owner_wallet_address', 'cdp_owner_wallet_name', 'cdp_owner_wallet_id')
        """))
        old_columns = [row[0] for row in result.fetchall()]
        
        if old_columns:
            logger.info(f"Found old cdp_owner columns to remove: {old_columns}")
            for column in old_columns:
                try:
                    await session.execute(text(f"ALTER TABLE users DROP COLUMN IF EXISTS {column}"))
                    await session.commit()
                    logger.info(f"Dropped column {column} from users table")
                except Exception as e:
                    logger.warning(f"Could not drop column {column}: {e}")
                    # Don't fail, just continue
        
        # 5. Migrate agent_status to user_metadata if using old columns
        # Check if using old agent_status column
        result = await session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users' 
            AND column_name = 'agent_status'
        """))
        has_old_agent_status = result.fetchone() is not None
        
        if has_old_agent_status:
            logger.info("Migrating agent_status to user_metadata JSONB field...")
            # Migrate data to user_metadata
            await session.execute(text("""
                UPDATE users 
                SET user_metadata = 
                    COALESCE(user_metadata, '{}'::jsonb) || 
                    jsonb_build_object(
                        'agent_status', agent_status::text,
                        'agent_started_at', agent_started_at,
                        'agent_stopped_at', agent_stopped_at,
                        'last_balance_check', last_balance_check
                    )
                WHERE agent_status IS NOT NULL
            """))
            
            # Drop old columns
            await session.execute(text("""
                ALTER TABLE users 
                DROP COLUMN IF EXISTS agent_status,
                DROP COLUMN IF EXISTS agent_started_at,
                DROP COLUMN IF EXISTS agent_stopped_at,
                DROP COLUMN IF EXISTS last_balance_check
            """))
            await session.commit()
            logger.info("Migrated agent_status to user_metadata")
        
        # 6. Add protocol fee columns to positions table if missing
        logger.info("Checking for protocol fee columns in positions table...")
        
        # Check which columns exist
        result = await session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'positions' 
            AND column_name IN ('protocol_fee_amount', 'protocol_fee_collected', 'protocol_fee_tx_hash')
        """))
        existing_columns = [row[0] for row in result.fetchall()]
        
        # Add missing columns
        if 'protocol_fee_amount' not in existing_columns:
            logger.info("Adding protocol_fee_amount column to positions table...")
            await session.execute(text("""
                ALTER TABLE positions 
                ADD COLUMN protocol_fee_amount DECIMAL(20, 8) DEFAULT 0
            """))
            await session.commit()
            logger.info("Added protocol_fee_amount column")
        
        if 'protocol_fee_collected' not in existing_columns:
            logger.info("Adding protocol_fee_collected column to positions table...")
            await session.execute(text("""
                ALTER TABLE positions
                ADD COLUMN protocol_fee_collected BOOLEAN DEFAULT FALSE
            """))
            await session.commit()
            logger.info("Added protocol_fee_collected column")
        
        if 'protocol_fee_tx_hash' not in existing_columns:
            logger.info("Adding protocol_fee_tx_hash column to positions table...")
            await session.execute(text("""
                ALTER TABLE positions
                ADD COLUMN protocol_fee_tx_hash VARCHAR(255)
            """))
            await session.commit()
            logger.info("Added protocol_fee_tx_hash column")
        
        # Add index for better query performance
        await session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_positions_protocol_fee_collected 
            ON positions(protocol_fee_collected) 
            WHERE protocol_fee_collected = FALSE
        """))
        await session.commit()
        
        # DROP unwanted tables if they exist (we only need 3 core tables)
        logger.info("Cleaning up unwanted tables...")
        
        # Drop tables that keep getting recreated
        tables_to_drop = [
            'wallet_transactions',
            'liquidity_events', 
            'blockchain_sync'
        ]
        
        for table in tables_to_drop:
            try:
                await session.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                logger.info(f"Dropped unwanted table: {table}")
            except Exception as e:
                logger.warning(f"Could not drop table {table}: {e}")
        
        await session.commit()
        logger.info("Cleaned up unwanted tables - using only 3 core tables (users, positions, transactions)")
        
        logger.info("Schema compatibility check completed")
        
    except Exception as e:
        logger.error(f"Error ensuring schema compatibility: {e}")
        # Don't fail the application startup, just log the error
        pass