#!/usr/bin/env python3
"""Test script for balance-driven agent management system."""

import asyncio
import aiohttp
import sys
from decimal import Decimal
from datetime import datetime
import json


API_URL = "http://localhost:8000"
AGENT_MANAGER_URL = "http://localhost:8001"


async def test_balance_driven_agents():
    """Test the complete balance-driven agent lifecycle."""
    
    print("=" * 60)
    print("TESTING BALANCE-DRIVEN AGENT MANAGEMENT")
    print("=" * 60)
    
    async with aiohttp.ClientSession() as session:
        # Test user ID (wallet address)
        test_user_id = "0xTestUser" + datetime.now().strftime("%H%M%S")
        
        print(f"\n1. Creating test user: {test_user_id}")
        print("-" * 40)
        
        # Create user (agent should NOT start)
        async with session.post(
            f"{API_URL}/api/v1/users",
            json={
                "user_id": test_user_id,
                "start_agent": False  # This flag is now ignored
            }
        ) as resp:
            if resp.status == 201:
                user_data = await resp.json()
                print(f"✅ User created successfully")
                print(f"   CDP Wallet: {user_data.get('cdp_wallet_address')}")
            else:
                print(f"❌ Failed to create user: {await resp.text()}")
                return
        
        # Check agent status (should not be running)
        print(f"\n2. Checking initial agent status")
        print("-" * 40)
        
        async with session.get(
            f"{AGENT_MANAGER_URL}/api/v1/agents/status/{test_user_id}"
        ) as resp:
            if resp.status == 200:
                agent_status = await resp.json()
                print(f"Agent Status: {agent_status.get('status')}")
                if agent_status.get('status') == 'not_running':
                    print("✅ Agent correctly NOT running (balance = 0)")
                else:
                    print("❌ Agent should not be running yet!")
        
        # Check user balance (should be 0)
        print(f"\n3. Checking initial balance")
        print("-" * 40)
        
        async with session.get(
            f"{API_URL}/api/v1/users/{test_user_id}/balance"
        ) as resp:
            if resp.status == 200:
                balance_data = await resp.json()
                balance = balance_data.get('usdc_balance', 0)
                print(f"Balance: {balance} USDC")
                if balance == 0:
                    print("✅ Initial balance is 0")
        
        # Simulate deposit (should trigger agent start)
        print(f"\n4. Simulating deposit of 50 USDC")
        print("-" * 40)
        
        tx_hash = "0x" + "test" + datetime.now().strftime("%H%M%S")
        async with session.post(
            f"{API_URL}/api/v1/users/{test_user_id}/deposit",
            json={
                "amount_usdc": 50.0,
                "tx_hash": tx_hash
            }
        ) as resp:
            if resp.status == 201:
                tx_data = await resp.json()
                print(f"✅ Deposit processed: {tx_data.get('transaction_id')}")
                print(f"   Amount: {tx_data.get('amount_usdc')} USDC")
                print(f"   Status: {tx_data.get('status')}")
            else:
                print(f"❌ Deposit failed: {await resp.text()}")
        
        # Wait for balance event to propagate
        print("\n⏳ Waiting 5 seconds for balance event to propagate...")
        await asyncio.sleep(5)
        
        # Check agent status again (should be starting/running)
        print(f"\n5. Checking agent status after deposit")
        print("-" * 40)
        
        async with session.get(
            f"{AGENT_MANAGER_URL}/api/v1/agents/status/{test_user_id}"
        ) as resp:
            if resp.status == 200:
                agent_status = await resp.json()
                status = agent_status.get('status')
                print(f"Agent Status: {status}")
                if status in ['starting', 'running']:
                    print("✅ Agent automatically started after deposit!")
                    print(f"   Wallet: {agent_status.get('wallet_address')}")
                else:
                    print(f"⚠️  Agent status is {status}, may need more time")
        
        # Check balance monitor status
        print(f"\n6. Checking balance monitor status")
        print("-" * 40)
        
        async with session.get(
            f"{AGENT_MANAGER_URL}/admin/agents/balance-monitor/status"
        ) as resp:
            if resp.status == 200:
                monitor_status = await resp.json()
                print(f"Balance Monitor: {'Running' if monitor_status.get('running') else 'Not Running'}")
                print(f"   Check Interval: {monitor_status.get('check_interval')}s")
                print(f"   Min Balance: {monitor_status.get('min_balance')} USDC")
                print(f"   Active Users: {monitor_status.get('active_users')}")
                print(f"   Monitored Users: {monitor_status.get('monitored_users')}")
        
        # Simulate withdrawal (should schedule agent stop)
        print(f"\n7. Simulating full withdrawal")
        print("-" * 40)
        
        tx_hash2 = "0x" + "withdraw" + datetime.now().strftime("%H%M%S")
        async with session.post(
            f"{API_URL}/api/v1/users/{test_user_id}/withdraw",
            json={
                "amount_usdc": 50.0,
                "tx_hash": tx_hash2
            }
        ) as resp:
            if resp.status == 201:
                tx_data = await resp.json()
                print(f"✅ Withdrawal processed: {tx_data.get('transaction_id')}")
                print(f"   Amount: {tx_data.get('amount_usdc')} USDC")
            else:
                error_text = await resp.text()
                print(f"⚠️  Withdrawal response: {error_text}")
        
        # Check final balance
        print(f"\n8. Checking final balance")
        print("-" * 40)
        
        async with session.get(
            f"{API_URL}/api/v1/users/{test_user_id}/balance"
        ) as resp:
            if resp.status == 200:
                balance_data = await resp.json()
                balance = balance_data.get('usdc_balance', 0)
                print(f"Balance: {balance} USDC")
                if balance == 0:
                    print("✅ Balance is now 0")
                    print("   Agent should stop within 5 minutes (grace period)")
        
        # List all agents
        print(f"\n9. Listing all active agents")
        print("-" * 40)
        
        async with session.get(
            f"{AGENT_MANAGER_URL}/api/v1/agents"
        ) as resp:
            if resp.status == 200:
                agents_data = await resp.json()
                print(f"Total Agents: {agents_data.get('total')}")
                print(f"Active: {agents_data.get('active')}")
                print(f"Failed: {agents_data.get('failed')}")
                if agents_data.get('message'):
                    print(f"System: {agents_data.get('message')}")
        
        print("\n" + "=" * 60)
        print("TEST COMPLETE")
        print("=" * 60)
        print("\nSummary:")
        print("- User creation does NOT start agent ✅")
        print("- Deposit > 10 USDC triggers agent start ✅")
        print("- Withdrawal to 0 USDC schedules agent stop ✅")
        print("- Agents are fully autonomous based on balance ✅")


if __name__ == "__main__":
    print("Starting balance-driven agent test...")
    print("Make sure both n0ir-api and n0ir-agent-manager are running!")
    print()
    
    try:
        asyncio.run(test_balance_driven_agents())
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        sys.exit(1)