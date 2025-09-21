#!/usr/bin/env python3
"""
Create position in database from the POSITION_CREATED transaction.
"""

import asyncio
import asyncpg
from datetime import datetime

async def create_position():
    """Create the position."""
    
    database_url = "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"
    
    position_id = 26256789
    user_id = '0xAC65e18F7f4e5eDEA297b9E5433C153f1d9a7764'  # Owner wallet
    pool_address = '0xb2cc224c1c9feE385f8ad6a55b4d94E92359DC59'
    tx_hash = '0x6760b89cbe37d7441dd49de1e1239f9362f0f9741c024f0ac93dec4b7bc46d00'
    gauge_address = '0x827922686190790b37229fd06084350E74485b72'  # From the gauge that minted it
    
    print("CREATING POSITION FROM TRANSACTION")
    print("="*60)
    print(f"Position ID: {position_id}")
    print(f"User: {user_id}")
    print(f"Pool: {pool_address}")
    
    conn = await asyncpg.connect(database_url)
    
    try:
        # Check if position exists
        exists = await conn.fetchval(
            "SELECT token_id FROM positions WHERE token_id = $1",
            position_id
        )
        
        if exists:
            print(f"⚠️ Position {position_id} already exists")
            return
        
        # Get transaction details for timestamp
        tx_data = await conn.fetchrow(
            "SELECT block_timestamp, amount_usdc FROM transactions WHERE tx_hash = $1",
            tx_hash
        )
        
        if tx_data:
            entry_date = tx_data['block_timestamp']
            entry_amount = tx_data['amount_usdc'] or 49.98  # From our analysis
        else:
            entry_date = datetime.utcnow()
            entry_amount = 49.98
        
        # Create the position with all required fields
        insert_query = """
        INSERT INTO positions (
            token_id,
            user_id,
            pool_address,
            pool_name,
            gauge_address,
            entry_date,
            entry_tx_hash,
            entry_amount_usdc,
            current_value_usdc,
            fees_earned_usdc,
            rewards_earned_usdc,
            realized_pnl_usdc,
            status,
            staked,
            liquidity,
            token0_address,
            token1_address,
            created_at,
            updated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, NOW(), NOW())
        RETURNING token_id
        """
        
        result = await conn.fetchval(
            insert_query,
            position_id,
            user_id,
            pool_address,
            'WETH/USDC',  # Pool name
            gauge_address,
            entry_date,
            tx_hash,
            entry_amount,
            50.01,  # Current value from blockchain endpoint
            0.0,
            0.0,
            0.0,
            'ACTIVE',
            True,  # Staked
            '49961398751505',  # Liquidity from blockchain
            '0x4200000000000000000000000000000000000006',  # WETH
            '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'   # USDC
        )
        
        if result:
            print(f"✅ Created position {result}")
            
            # Update the transaction to link it to the position
            await conn.execute(
                "UPDATE transactions SET position_id = $1 WHERE tx_hash = $2",
                position_id,
                tx_hash
            )
            print(f"✅ Linked transaction to position")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(create_position())
