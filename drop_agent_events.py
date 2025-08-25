import asyncio
import asyncpg

async def drop_agent_events():
    conn = await asyncpg.connect(
        "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@shuttle.proxy.rlwy.net:17669/railway"
    )
    
    print("Connected to Railway database")
    
    # Check if agent_events table exists
    exists = await conn.fetchval("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_name = 'agent_events'
        )
    """)
    
    if exists:
        print("Dropping agent_events table...")
        await conn.execute("DROP TABLE IF EXISTS agent_events CASCADE")
        print("✅ agent_events table dropped successfully")
    else:
        print("ℹ️ agent_events table doesn't exist")
    
    # Also remove the model file since it's not used
    print("\nNote: You should also delete app/database/models/agent_event.py")
    
    await conn.close()
    print("\nCleanup completed!")

asyncio.run(drop_agent_events())