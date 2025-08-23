#!/usr/bin/env python3
"""Direct withdrawal script that bypasses agent-manager."""

import asyncio
import sys
import os
from decimal import Decimal
from datetime import datetime
from loguru import logger

# Add parent directory to path
sys.path.insert(0, '/home/mortiee/projects/n0ir/n0ir-api')

from app.database.session import get_db
from app.services.user_service import UserService
from app.core.config import settings

# CDP imports
from cdp import Cdp, Wallet, WalletData
from cdp.errors import ApiError


async def direct_withdraw(user_id: str, amount_usdc: float):
    """Perform direct withdrawal for a user.
    
    This bypasses the agent-manager and directly sends USDC to the user.
    """
    logger.info(f"Starting direct withdrawal for {user_id}: {amount_usdc} USDC")
    
    try:
        # Initialize CDP SDK
        logger.info("Initializing CDP SDK...")
        Cdp.configure(
            api_key_name=os.getenv("CDP_API_KEY_ID"),
            api_key_private_key=os.getenv("CDP_API_KEY_SECRET").replace('\\n', '\n')
        )
        
        # Get user's CDP wallet data from database
        async for db in get_db():
            user_service = UserService(db)
            
            # Get user info
            user = await user_service.get_user(user_id)
            if not user:
                logger.error(f"User {user_id} not found")
                return False
            
            logger.info(f"User balance: {user.balance_usdc} USDC")
            
            # Check if user has CDP wallet
            wallet_data = await db.execute(
                "SELECT wallet_data FROM user_wallets WHERE user_id = :user_id",
                {"user_id": user_id}
            )
            wallet_record = wallet_data.fetchone()
            
            if not wallet_record or not wallet_record[0]:
                logger.error(f"No CDP wallet found for user {user_id}")
                
                # Try to get wallet from agent's stored data
                import redis.asyncio as aioredis
                redis_url = os.getenv("REDIS_URL", settings.redis_url)
                if redis_url:
                    redis_client = await aioredis.from_url(redis_url, decode_responses=False)
                    wallet_data_bytes = await redis_client.hget("user_wallets", user_id)
                    if wallet_data_bytes:
                        logger.info("Found wallet data in Redis")
                        wallet_data_str = wallet_data_bytes.decode('utf-8') if isinstance(wallet_data_bytes, bytes) else wallet_data_bytes
                    else:
                        logger.error("No wallet data in Redis either")
                        return False
                else:
                    logger.error("Redis not available")
                    return False
            else:
                wallet_data_str = wallet_record[0]
            
            logger.info(f"Loading CDP wallet for {user_id}...")
            
            # Import the wallet
            wallet = Wallet.import_data(WalletData.from_json(wallet_data_str))
            wallet_address = wallet.default_address.address_id
            logger.info(f"CDP wallet loaded: {wallet_address}")
            
            # Get USDC balance in wallet
            usdc_address = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # USDC on Base
            try:
                balance = await asyncio.to_thread(
                    wallet.balance,
                    usdc_address
                )
                balance_decimal = Decimal(str(balance))
                logger.info(f"CDP wallet USDC balance: {balance_decimal}")
                
                if balance_decimal < Decimal(str(amount_usdc)):
                    logger.error(f"Insufficient balance in CDP wallet: {balance_decimal} < {amount_usdc}")
                    # Don't fail - we might have positions to close
                    
            except Exception as e:
                logger.warning(f"Could not get wallet balance: {e}")
                balance_decimal = Decimal("0")
            
            # Close positions if needed to get USDC
            positions_closed = []
            if user.balance_usdc < amount_usdc:
                logger.info(f"Need to close positions to get {amount_usdc} USDC")
                
                # Get active positions
                positions = await user_service.get_user_positions(user_id, status="ACTIVE")
                total_value = Decimal("0")
                
                for position in positions:
                    if total_value >= Decimal(str(amount_usdc)):
                        break
                    
                    logger.info(f"Would close position {position.nft_token_id} (value: {position.current_value_usd} USD)")
                    positions_closed.append(position.nft_token_id)
                    total_value += Decimal(str(position.current_value_usd or 0))
                
                logger.info(f"Positions to close: {positions_closed}")
                logger.warning("NOTE: Position closing not implemented in this script - would need executor")
            
            # Perform the transfer
            logger.info(f"Transferring {amount_usdc} USDC to {user_id}...")
            
            try:
                # Create transfer
                transfer = await asyncio.to_thread(
                    wallet.transfer,
                    amount=amount_usdc,
                    asset_id=usdc_address,
                    destination=user_id,  # Send to user's EOA
                    gasless=False  # Use standard gas
                )
                
                # Wait for confirmation
                logger.info(f"Transfer initiated: {transfer.transaction_hash}")
                logger.info("Waiting for confirmation...")
                
                result = await asyncio.to_thread(transfer.wait)
                
                if result.status == "complete":
                    logger.info(f"✅ Transfer successful! TX: {result.transaction_hash}")
                    logger.info(f"Sent {amount_usdc} USDC to {user_id}")
                    
                    # Update user balance in database
                    await user_service.update_user_balance(
                        user_id,
                        float(user.balance_usdc) - amount_usdc
                    )
                    
                    return True
                else:
                    logger.error(f"Transfer failed: {result.status}")
                    return False
                    
            except ApiError as e:
                logger.error(f"CDP API error: {e}")
                logger.error(f"Error details: {e.message}")
                return False
            except Exception as e:
                logger.error(f"Transfer failed: {e}")
                return False
            
            break  # Exit after first db session
            
    except Exception as e:
        logger.error(f"Direct withdrawal failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main entry point."""
    user_id = "0xdBE4e3bcb15B221324B776Db6F0CbFf24918Ea51"
    amount_usdc = 10.0
    
    logger.info(f"Direct withdrawal for {user_id}: {amount_usdc} USDC")
    
    success = await direct_withdraw(user_id, amount_usdc)
    
    if success:
        logger.info("✅ Withdrawal successful!")
    else:
        logger.error("❌ Withdrawal failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())