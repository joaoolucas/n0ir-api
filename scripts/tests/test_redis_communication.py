#!/usr/bin/env python3
"""Test Redis pub/sub communication between API and Agent Manager."""

import redis
import json
import time
import asyncio
from datetime import datetime

# Railway Redis URL
REDIS_URL = "redis://default:JupjBvrNSfMYfNNaYZtkivGAiTgPSqKm@centerbeam.proxy.rlwy.net:42947"

def test_redis_connection():
    """Test basic Redis connection."""
    print("Testing Redis connection...")
    try:
        r = redis.from_url(REDIS_URL, decode_responses=True)
        r.ping()
        print("✅ Redis connection successful")
        return r
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        return None

def listen_to_channels(r):
    """Listen to both agent_commands and wallet_created channels."""
    print("\nListening to Redis channels...")
    print("Channels: agent_commands, wallet_created")
    print("-" * 50)
    
    pubsub = r.pubsub()
    pubsub.subscribe('agent_commands', 'wallet_created')
    
    print("Waiting for messages (press Ctrl+C to stop)...\n")
    
    for message in pubsub.listen():
        if message['type'] == 'message':
            timestamp = datetime.now().strftime("%H:%M:%S")
            channel = message['channel']
            
            try:
                data = json.loads(message['data'])
                print(f"[{timestamp}] {channel}:")
                print(f"  {json.dumps(data, indent=2)}")
            except:
                print(f"[{timestamp}] {channel}: {message['data']}")
            print("-" * 50)

def send_test_command(r):
    """Send a test agent command."""
    print("\nSending test agent command...")
    
    command = {
        'action': 'start',
        'user_id': '0xTEST123',
        'wait_for_wallet': True,
        'timestamp': datetime.utcnow().isoformat()
    }
    
    r.publish('agent_commands', json.dumps(command))
    print(f"✅ Sent: {json.dumps(command, indent=2)}")

def check_agent_manager_keys(r):
    """Check if agent-manager is storing any status keys."""
    print("\nChecking for agent status keys...")
    
    # Look for agent status keys
    keys = r.keys('agent:*:status')
    if keys:
        print(f"Found {len(keys)} agent status keys:")
        for key in keys[:5]:  # Show first 5
            status = r.get(key)
            print(f"  {key}: {status}")
    else:
        print("No agent status keys found")
    
    # Check for any wallet-related keys
    wallet_keys = r.keys('*wallet*')
    if wallet_keys:
        print(f"\nFound {len(wallet_keys)} wallet-related keys:")
        for key in wallet_keys[:5]:
            print(f"  {key}")

def main():
    r = test_redis_connection()
    if not r:
        return
    
    print("\nOptions:")
    print("1. Listen to channels (see live messages)")
    print("2. Send test command")
    print("3. Check agent status keys")
    print("4. Test full flow (send and wait)")
    
    choice = input("\nSelect option (1-4): ").strip()
    
    if choice == '1':
        listen_to_channels(r)
    elif choice == '2':
        send_test_command(r)
    elif choice == '3':
        check_agent_manager_keys(r)
    elif choice == '4':
        print("\nTesting full flow...")
        
        # Start listening in a thread
        import threading
        messages = []
        
        def listener():
            pubsub = r.pubsub()
            pubsub.subscribe('agent_commands', 'wallet_created')
            
            start_time = time.time()
            while time.time() - start_time < 10:  # Listen for 10 seconds
                message = pubsub.get_message(timeout=1)
                if message and message['type'] == 'message':
                    messages.append(message)
        
        thread = threading.Thread(target=listener)
        thread.daemon = True
        thread.start()
        
        time.sleep(1)  # Let listener start
        
        # Send command
        send_test_command(r)
        
        # Wait for responses
        print("Waiting 10 seconds for responses...")
        thread.join()
        
        print(f"\nReceived {len(messages)} messages:")
        for msg in messages:
            print(f"  Channel: {msg['channel']}")
            try:
                data = json.loads(msg['data'])
                print(f"  Data: {json.dumps(data, indent=4)}")
            except:
                print(f"  Data: {msg['data']}")
    else:
        print("Invalid option")

if __name__ == "__main__":
    main()