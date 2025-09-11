#!/usr/bin/env python3
"""Clear stuck Redis stream messages in staging."""

import redis
import os

# Connect to staging Redis
REDIS_URL = "redis://default:w7XCMpFupNqWPLsFdSkRnKCYxXCsJXnF@n0ir-redis-staging.up.railway.app:3010"

def clear_stuck_messages():
    """Clear stuck messages from Redis streams."""
    
    # Connect to Redis
    r = redis.from_url(REDIS_URL)
    
    print("Connected to Redis")
    
    # The stuck message ID
    stuck_message_id = "1756090229871-0"
    stream_name = "agent:commands:stream"
    group_name = "agent-manager-group"
    
    try:
        # First, check pending messages
        pending = r.xpending(stream_name, group_name)
        print(f"Pending messages summary: {pending}")
        
        if pending and pending['pending'] > 0:
            # Get detailed info about pending messages
            detailed = r.xpending_range(stream_name, group_name, "-", "+", 10)
            print(f"Detailed pending messages: {detailed}")
            
            for msg in detailed:
                msg_id = msg['message_id'].decode() if isinstance(msg['message_id'], bytes) else msg['message_id']
                consumer = msg['consumer'].decode() if isinstance(msg['consumer'], bytes) else msg['consumer']
                idle_time = msg['time_since_delivered']
                
                print(f"\nFound pending message: {msg_id}")
                print(f"  Consumer: {consumer}")
                print(f"  Idle time: {idle_time}ms")
                
                if msg_id == stuck_message_id:
                    print(f"\nThis is our stuck message! Attempting to fix...")
                    
                    # Method 1: Try to ACK it directly
                    try:
                        ack_result = r.xack(stream_name, group_name, stuck_message_id)
                        print(f"  ACK attempt: {ack_result}")
                        if ack_result > 0:
                            print(f"  ✓ Successfully acknowledged message")
                            return
                    except Exception as e:
                        print(f"  ✗ ACK failed: {e}")
                    
                    # Method 2: Try to claim it first
                    try:
                        # Claim with a new consumer
                        claim_result = r.xclaim(
                            stream_name,
                            group_name,
                            "cleanup-consumer",
                            min_idle_time=0,
                            message_ids=[stuck_message_id]
                        )
                        print(f"  CLAIM attempt: {claim_result}")
                        
                        # Now ACK it
                        ack_result = r.xack(stream_name, group_name, stuck_message_id)
                        print(f"  ACK after claim: {ack_result}")
                        if ack_result > 0:
                            print(f"  ✓ Successfully claimed and acknowledged message")
                            return
                    except Exception as e:
                        print(f"  ✗ Claim failed: {e}")
                    
                    # Method 3: Delete the message entirely
                    try:
                        del_result = r.xdel(stream_name, stuck_message_id)
                        print(f"  DELETE attempt: {del_result}")
                        if del_result > 0:
                            print(f"  ✓ Successfully deleted message")
                            return
                    except Exception as e:
                        print(f"  ✗ Delete failed: {e}")
                    
                    # Method 4: Try to read and manually remove from PEL
                    try:
                        # Read the message first
                        messages = r.xrange(stream_name, stuck_message_id, stuck_message_id)
                        print(f"  Message content: {messages}")
                        
                        # Force acknowledge
                        r.execute_command('XACK', stream_name, group_name, stuck_message_id)
                        print(f"  ✓ Force acknowledged via raw command")
                    except Exception as e:
                        print(f"  ✗ Force ACK failed: {e}")
        
        # Check if message still exists in stream
        try:
            messages = r.xrange(stream_name, stuck_message_id, stuck_message_id)
            if messages:
                print(f"\nMessage {stuck_message_id} still exists in stream")
                print(f"Content: {messages}")
                
                # Try to delete it from the stream
                del_result = r.xdel(stream_name, stuck_message_id)
                print(f"Final delete attempt: {del_result}")
            else:
                print(f"\nMessage {stuck_message_id} no longer exists in stream")
        except Exception as e:
            print(f"Error checking message existence: {e}")
            
        # Final check of pending messages
        pending_after = r.xpending(stream_name, group_name)
        print(f"\nFinal pending messages: {pending_after}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        r.close()
        print("\nRedis connection closed")

if __name__ == "__main__":
    print("=== Clearing Stuck Redis Messages ===\n")
    clear_stuck_messages()
    print("\n=== Complete ===")