"""Test withdrawal endpoint that simulates USDC transfer."""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.services.user_service import UserService
from app.core.logger import logger
from datetime import datetime
import asyncio

router = APIRouter()


from pydantic import BaseModel

class TestWithdrawRequest(BaseModel):
    amount_usdc: float

@router.post("/{user_id}/test-withdraw")
async def test_withdraw(
    user_id: str,
    request: TestWithdrawRequest,
    db: AsyncSession = Depends(get_db)
):
    """Test withdrawal endpoint that simulates sending USDC.
    
    This bypasses the agent-manager and simulates a successful withdrawal.
    """
    try:
        amount_usdc = request.amount_usdc
        logger.info(f"[TEST-WITHDRAW] Starting test withdrawal for {user_id}: {amount_usdc} USDC")
        
        # Get user service
        user_service = UserService(db)
        
        # Get user
        user = await user_service.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get user balance
        balance = await user_service.get_user_balance(user_id)
        logger.info(f"[TEST-WITHDRAW] User balance: {balance} USDC")
        logger.info(f"[TEST-WITHDRAW] CDP wallet: {user.cdp_wallet_address if hasattr(user, 'cdp_wallet_address') else 'N/A'}")
        
        # Simulate position closing if needed
        positions_to_close = []
        if balance < amount_usdc:
            logger.info(f"[TEST-WITHDRAW] Need to close positions")
            positions = await user_service.get_user_positions(user_id, status="ACTIVE")
            
            total_recovered = 0
            for position in positions:
                if total_recovered >= amount_usdc:
                    break
                positions_to_close.append(position.nft_token_id)
                total_recovered += float(position.current_value_usd or 0)
                logger.info(f"[TEST-WITHDRAW] Would close position {position.nft_token_id} for ~{position.current_value_usd} USD")
        
        # Simulate the withdrawal transaction
        logger.info(f"[TEST-WITHDRAW] Simulating transfer of {amount_usdc} USDC to {user_id}")
        
        # Wait to simulate blockchain transaction
        await asyncio.sleep(2)
        
        # Generate mock transaction hash
        import hashlib
        import json
        tx_data = json.dumps({
            "from": user.cdp_wallet_address if hasattr(user, 'cdp_wallet_address') else "0xa449F944aD033D8083564556Fd918C45B716f79c",
            "to": user_id,
            "amount": amount_usdc,
            "timestamp": datetime.utcnow().isoformat()
        })
        tx_hash = "0x" + hashlib.sha256(tx_data.encode()).hexdigest()
        
        logger.info(f"[TEST-WITHDRAW] Mock transaction successful: {tx_hash}")
        
        # Return success response
        return {
            "success": True,
            "message": "Test withdrawal successful (simulated)",
            "amount_usdc": amount_usdc,
            "to_address": user_id,
            "from_address": user.cdp_wallet_address if hasattr(user, 'cdp_wallet_address') else "0xa449F944aD033D8083564556Fd918C45B716f79c",
            "tx_hash": tx_hash,
            "positions_closed": positions_to_close,
            "note": "This is a simulated withdrawal for testing. In production, the agent-manager would handle the actual blockchain transaction."
        }
        
    except Exception as e:
        logger.error(f"[TEST-WITHDRAW] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))