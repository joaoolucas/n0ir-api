#!/usr/bin/env python3
"""Script to manually trigger agent startup for a user with balance."""

import asyncio
import sys
from decimal import Decimal
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, '/home/mortiee/projects/n0ir/n0ir-api')

from app.services.agent_management_service import get_agent_service
from app.services.user_service import UserService
from app.database.session import get_db
from app.core.logger import logger


async def trigger_agent_for_user(user_id: str):
    """Trigger agent startup for a specific user."""
    
    try:
        # Get services
        agent_service = get_agent_service()
        
        if not agent_service.redis_client:
            logger.error("Redis not available")
            return False
        
        # Get user's balance
        async for db in get_db():
            user_service = UserService(db)
            balance = await user_service.get_user_balance(user_id)
            
            if not balance:
                logger.error(f"Could not get balance for {user_id}")
                return False
            
            logger.info(f"User {user_id} has balance: {balance} USDC")
            
            # Publish balance event to trigger agent startup
            success = await agent_service.publish_balance_event(
                user_id=user_id,
                balance=float(balance),
                event_type='manual_trigger'
            )
            
            if success:
                logger.info(f"Successfully published balance event for {user_id}")
                logger.info("Agent should start within a few seconds if balance >= 10 USDC")
                
                # Wait a bit to see if agent starts
                await asyncio.sleep(5)
                
                # Check agent status
                status = await agent_service.get_agent_status(user_id)
                if status:
                    logger.info(f"Agent status: {status}")
                else:
                    logger.warning("Could not get agent status (agent may still be starting)")
                
                return True
            else:
                logger.error(f"Failed to publish balance event for {user_id}")
                return False
            
            break  # Exit after first db session
            
    except Exception as e:
        logger.error(f"Error triggering agent: {e}")
        return False


async def main():
    user_id = "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51"
    logger.info(f"Triggering agent startup for user: {user_id}")
    
    success = await trigger_agent_for_user(user_id)
    
    if success:
        logger.info("Agent trigger completed successfully")
        logger.info("Now you can try the withdrawal again")
    else:
        logger.error("Failed to trigger agent startup")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())