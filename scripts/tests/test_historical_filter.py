#!/usr/bin/env python3
"""Test script for historical filter in performance and PnL endpoints."""

import asyncio
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from app.database.session import AsyncSessionLocal
from app.services.user_service import UserService
from app.schemas.users import TimePeriod
from app.core.logger import logger


async def test_historical_filters():
    """Test the historical filter implementation."""
    async with AsyncSessionLocal() as db:
        service = UserService(db)
        
        # Test user ID - you may need to change this to an existing user
        test_user_id = "0x1234567890123456789012345678901234567890"
        
        logger.info("Testing historical filter implementation...")
        
        # Test each time period
        periods = [
            TimePeriod.DAY_1,
            TimePeriod.DAY_7,
            TimePeriod.DAY_30,
            TimePeriod.ALL_TIME
        ]
        
        for period in periods:
            logger.info(f"\n{'='*50}")
            logger.info(f"Testing period: {period.value}")
            logger.info(f"{'='*50}")
            
            try:
                # Test the service method directly
                pnl_data = await service.recalculate_user_pnl_for_period(test_user_id, period)
                
                if pnl_data:
                    logger.info(f"Period: {pnl_data.get('period', 'N/A')}")
                    logger.info(f"Realized PnL: ${pnl_data.get('realized_pnl_usdc', 0):.2f}")
                    logger.info(f"Unrealized PnL: ${pnl_data.get('unrealized_pnl_usdc', 0):.2f}")
                    logger.info(f"Total PnL: ${pnl_data.get('total_pnl_usdc', 0):.2f}")
                    logger.info(f"Active Positions: {pnl_data.get('active_positions_count', 0)}")
                    logger.info(f"Closed Positions: {pnl_data.get('closed_positions_count', 0)}")
                    logger.info(f"Fees Earned: ${pnl_data.get('fees_earned_usdc', 0):.2f}")
                    logger.info(f"Rewards Earned: ${pnl_data.get('rewards_earned_usdc', 0):.2f}")
                else:
                    logger.warning(f"No data returned for period {period.value}")
                    
            except Exception as e:
                logger.error(f"Error testing period {period.value}: {e}")
        
        logger.info("\n✅ Historical filter testing complete!")


async def test_api_endpoints():
    """Test the API endpoints with historical filters."""
    import httpx
    
    # Base URL for the API (adjust if needed)
    base_url = "http://localhost:8000/api/v1"
    
    # Test user ID - you may need to change this to an existing user
    test_user_id = "0x1234567890123456789012345678901234567890"
    
    logger.info("Testing API endpoints with historical filters...")
    
    async with httpx.AsyncClient() as client:
        # Test each time period
        periods = ["24h", "7d", "30d", "all", None]  # None tests default behavior
        
        for period in periods:
            logger.info(f"\n{'='*50}")
            logger.info(f"Testing API with period: {period or 'default (all)'}")
            logger.info(f"{'='*50}")
            
            # Build query params
            params = {"period": period} if period else {}
            
            # Test /pnl endpoint
            try:
                response = await client.get(
                    f"{base_url}/users/{test_user_id}/pnl",
                    params=params
                )
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"PnL endpoint response:")
                    logger.info(f"  Realized PnL: ${data.get('realized_pnl_usdc', 0)}")
                    logger.info(f"  Unrealized PnL: ${data.get('unrealized_pnl_usdc', 0)}")
                    logger.info(f"  Total PnL: ${data.get('total_pnl_usdc', 0)}")
                elif response.status_code == 404:
                    logger.warning(f"User not found: {test_user_id}")
                else:
                    logger.error(f"PnL endpoint failed: {response.status_code} - {response.text}")
            except Exception as e:
                logger.error(f"Error calling PnL endpoint: {e}")
            
            # Test /performance endpoint
            try:
                response = await client.get(
                    f"{base_url}/users/{test_user_id}/performance",
                    params=params
                )
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"Performance endpoint response:")
                    logger.info(f"  Balance: ${data.get('balance', 0)}")
                    logger.info(f"  PnL USDC: ${data.get('pnl_usdc', 0)}")
                    logger.info(f"  PnL %: {data.get('pnl_pct', 0)}%")
                    logger.info(f"  Active Positions: {data.get('active_positions', 0)}")
                    logger.info(f"  APR: {data.get('apr', 0)}%")
                elif response.status_code == 404:
                    logger.warning(f"User not found: {test_user_id}")
                else:
                    logger.error(f"Performance endpoint failed: {response.status_code} - {response.text}")
            except Exception as e:
                logger.error(f"Error calling Performance endpoint: {e}")
    
    logger.info("\n✅ API endpoint testing complete!")


async def main():
    """Main test function."""
    logger.info("Starting historical filter tests...")
    
    # Test the service methods directly
    await test_historical_filters()
    
    # Uncomment to test API endpoints (requires running server)
    # await test_api_endpoints()
    
    logger.info("\n🎉 All tests complete!")


if __name__ == "__main__":
    asyncio.run(main())