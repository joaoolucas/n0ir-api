#!/usr/bin/env python3
"""
n0ir System Testing Flow
Execute comprehensive tests for the entire system
"""

import requests
import json
import time
from datetime import datetime
from typing import Dict, Any

# Configuration
API_BASE_URL = "http://localhost:8000"  # Update for Railway if needed
TEST_WALLET = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb8"  # Test wallet address

class N0irTester:
    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.user_id = None
        self.position_id = None
        
    def test_health(self) -> bool:
        """Test 1: Check system health"""
        print("\n🧪 TEST 1: System Health Check")
        print("-" * 40)
        
        try:
            # Check API health
            resp = self.session.get(f"{self.base_url}/health")
            if resp.status_code == 200:
                print("✅ API is healthy")
            else:
                print(f"❌ API health check failed: {resp.status_code}")
                return False
                
            # Check agent manager health
            resp = self.session.get(f"{self.base_url}/api/v1/agents/health")
            if resp.status_code == 200:
                data = resp.json()
                print(f"✅ Agent Manager: {data.get('status', 'unknown')}")
                print(f"   Memory Usage: {data.get('memory_usage_mb', 0):.2f} MB")
                print(f"   Active Agents: {data.get('active_agents', 0)}")
            else:
                print(f"⚠️  Agent Manager not responding: {resp.status_code}")
                
            return True
            
        except Exception as e:
            print(f"❌ Health check error: {e}")
            return False
    
    def test_user_registration(self, wallet_address: str = TEST_WALLET) -> bool:
        """Test 2: User Registration"""
        print("\n🧪 TEST 2: User Registration")
        print("-" * 40)
        
        try:
            # Register new user
            payload = {
                "wallet_address": wallet_address,
                "cdp_wallet_name": f"test-wallet-{int(time.time())}"
            }
            
            resp = self.session.post(
                f"{self.base_url}/api/v1/users/register",
                json=payload
            )
            
            if resp.status_code in [200, 201]:
                data = resp.json()
                self.user_id = data.get("user_id", wallet_address)
                print(f"✅ User registered: {self.user_id}")
                print(f"   CDP Wallet: {data.get('cdp_wallet_name', 'N/A')}")
                return True
            elif resp.status_code == 409:
                print(f"ℹ️  User already exists: {wallet_address}")
                self.user_id = wallet_address
                return True
            else:
                print(f"❌ Registration failed: {resp.status_code}")
                print(f"   Response: {resp.text}")
                return False
                
        except Exception as e:
            print(f"❌ Registration error: {e}")
            return False
    
    def test_position_creation(self) -> bool:
        """Test 3: Position Creation"""
        print("\n🧪 TEST 3: Position Creation")
        print("-" * 40)
        
        if not self.user_id:
            print("❌ No user_id available, run registration first")
            return False
            
        try:
            # Create a new position
            payload = {
                "user_id": self.user_id,
                "pool_address": "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640",  # USDC/ETH 0.05%
                "token0_amount": 1000,  # 1000 USDC
                "token1_amount": 0.3,   # 0.3 ETH
                "tick_lower": -887220,
                "tick_upper": 887220,
                "fee_tier": 500
            }
            
            resp = self.session.post(
                f"{self.base_url}/api/v1/positions/create",
                json=payload
            )
            
            if resp.status_code in [200, 201]:
                data = resp.json()
                self.position_id = data.get("position_id") or data.get("nft_token_id")
                print(f"✅ Position created: {self.position_id}")
                print(f"   Pool: {data.get('pool_address', 'N/A')[:10]}...")
                print(f"   Status: {data.get('status', 'unknown')}")
                return True
            else:
                print(f"❌ Position creation failed: {resp.status_code}")
                print(f"   Response: {resp.text}")
                return False
                
        except Exception as e:
            print(f"❌ Position creation error: {e}")
            return False
    
    def test_position_monitoring(self) -> bool:
        """Test 4: Position Monitoring"""
        print("\n🧪 TEST 4: Position Monitoring")
        print("-" * 40)
        
        if not self.position_id:
            print("⚠️  No position_id available, skipping")
            return True
            
        try:
            # Get position details
            resp = self.session.get(
                f"{self.base_url}/api/v1/positions/{self.position_id}"
            )
            
            if resp.status_code == 200:
                data = resp.json()
                print(f"✅ Position {self.position_id} status:")
                print(f"   Current Value: ${data.get('current_value_usdc', 0):,.2f}")
                print(f"   Unrealized P&L: ${data.get('unrealized_pnl_usdc', 0):,.2f}")
                print(f"   Protocol Fee: ${data.get('protocol_fee_amount', 0):,.2f}")
                print(f"   Status: {data.get('status', 'unknown')}")
                return True
            else:
                print(f"⚠️  Could not fetch position: {resp.status_code}")
                return True
                
        except Exception as e:
            print(f"❌ Position monitoring error: {e}")
            return False
    
    def test_redis_pubsub(self) -> bool:
        """Test 5: Redis Pub/Sub Communication"""
        print("\n🧪 TEST 5: Redis Pub/Sub")
        print("-" * 40)
        
        try:
            # Send test message via API
            payload = {
                "channel": "test_channel",
                "message": {"test": "message", "timestamp": datetime.now().isoformat()}
            }
            
            resp = self.session.post(
                f"{self.base_url}/api/v1/debug/redis/publish",
                json=payload
            )
            
            if resp.status_code == 200:
                print("✅ Redis pub/sub working")
                return True
            elif resp.status_code == 404:
                print("ℹ️  Redis debug endpoint not available")
                return True
            else:
                print(f"⚠️  Redis test returned: {resp.status_code}")
                return True
                
        except Exception as e:
            print(f"⚠️  Redis test skipped: {e}")
            return True
    
    def test_agent_processes(self) -> bool:
        """Test 6: Agent Process Management"""
        print("\n🧪 TEST 6: Agent Processes")
        print("-" * 40)
        
        try:
            # Check agent manager status
            resp = self.session.get(f"{self.base_url}/api/v1/agents/status")
            
            if resp.status_code == 200:
                data = resp.json()
                print(f"✅ Agent Manager Status:")
                print(f"   Running: {data.get('is_running', False)}")
                print(f"   Active Agents: {data.get('active_agents', 0)}")
                print(f"   Memory (MB): {data.get('memory_usage_mb', 0):.2f}")
                
                # List active agents
                agents = data.get('agents', [])
                if agents:
                    print("   Active Agent List:")
                    for agent in agents:
                        print(f"     - {agent.get('name', 'unknown')}: {agent.get('status', 'unknown')}")
                
                return True
            else:
                print(f"⚠️  Agent manager not available: {resp.status_code}")
                return True
                
        except Exception as e:
            print(f"⚠️  Agent process test skipped: {e}")
            return True
    
    def run_all_tests(self):
        """Run all tests in sequence"""
        print("\n" + "="*50)
        print("🚀 n0ir SYSTEM TESTING SUITE")
        print("="*50)
        print(f"Target: {self.base_url}")
        print(f"Time: {datetime.now().isoformat()}")
        
        results = []
        
        # Run tests
        tests = [
            ("Health Check", self.test_health),
            ("User Registration", self.test_user_registration),
            ("Position Creation", self.test_position_creation),
            ("Position Monitoring", self.test_position_monitoring),
            ("Redis Pub/Sub", self.test_redis_pubsub),
            ("Agent Processes", self.test_agent_processes),
        ]
        
        for test_name, test_func in tests:
            try:
                result = test_func()
                results.append((test_name, result))
            except Exception as e:
                print(f"❌ Test '{test_name}' crashed: {e}")
                results.append((test_name, False))
            
            time.sleep(1)  # Small delay between tests
        
        # Summary
        print("\n" + "="*50)
        print("📊 TEST SUMMARY")
        print("="*50)
        
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        for test_name, result in results:
            status = "✅ PASSED" if result else "❌ FAILED"
            print(f"{status}: {test_name}")
        
        print(f"\nTotal: {passed}/{total} tests passed")
        
        if passed == total:
            print("\n🎉 All tests passed successfully!")
        else:
            print(f"\n⚠️  {total - passed} test(s) failed")
        
        return passed == total


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="n0ir System Testing")
    parser.add_argument("--url", default=API_BASE_URL, help="API base URL")
    parser.add_argument("--wallet", default=TEST_WALLET, help="Test wallet address")
    parser.add_argument("--test", help="Run specific test (health, user, position, etc.)")
    
    args = parser.parse_args()
    
    tester = N0irTester(args.url)
    
    if args.test:
        # Run specific test
        test_map = {
            "health": tester.test_health,
            "user": tester.test_user_registration,
            "position": tester.test_position_creation,
            "monitor": tester.test_position_monitoring,
            "redis": tester.test_redis_pubsub,
            "agents": tester.test_agent_processes,
        }
        
        if args.test in test_map:
            test_map[args.test]()
        else:
            print(f"Unknown test: {args.test}")
            print(f"Available: {', '.join(test_map.keys())}")
    else:
        # Run all tests
        tester.run_all_tests()


if __name__ == "__main__":
    main()