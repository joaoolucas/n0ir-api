import asyncio
import redis.asyncio as redis
import json
from datetime import datetime

async def trigger_balance_event():
    # Connect to Redis
    redis_url = "redis://default:oqqCbIhdjpNzhvlEBTXYXgfVGaxujADn@n0ir-redis.railway.internal:6379"
    client = redis.from_url(redis_url)
    
    user_id = "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51"
    balance = 15.0
    
    # Store balance in hash for balance monitor to find
    await client.hset("users:balances", user_id, str(balance))
    print(f"Stored balance in users:balances: {user_id} -> {balance}")
    
    # Publish balance event
    event_data = {
        'user_id': user_id,
        'balance': str(balance),
        'old_balance': '0',
        'event_type': 'manual_trigger',
        'timestamp': datetime.utcnow().isoformat()
    }
    
    await client.publish('user:balance:changed', json.dumps(event_data))
    print(f"Published balance event for {user_id}: {balance} USDC")
    
    await client.close()

if __name__ == "__main__":
    asyncio.run(trigger_balance_event())
