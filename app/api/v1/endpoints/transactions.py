from fastapi import APIRouter, HTTPException, Query, Path, Depends
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.services.transaction_service import transaction_service
from app.database.session import get_db
from app.database.models.transaction import Transaction
from app.database.models.user import User
from app.core.logger import logger

router = APIRouter()


@router.get("/status/{tx_hash}")
async def get_transaction_status(
    tx_hash: str,
    detailed: bool = Query(False, description="Include full transaction details")
) -> Dict[str, Any]:
    """
    Get transaction status from Etherscan API.
    
    Args:
        tx_hash: The transaction hash to check
        detailed: If True, returns full transaction details along with status
        
    Returns:
        Transaction status information including:
        - tx_hash: The transaction hash
        - status: 0 for failed, 1 for success, None if unknown
        - status_text: Human-readable status ("Success", "Failed", or "Unknown")
        - message: API response message
        - details: Full transaction details (if detailed=True)
    """
    try:
        # Validate tx_hash format (basic check)
        if not tx_hash.startswith("0x") or len(tx_hash) != 66:
            raise HTTPException(
                status_code=400,
                detail="Invalid transaction hash format. Must be a 66-character hex string starting with '0x'"
            )
        
        # Get transaction status
        result = await transaction_service.get_transaction_status(tx_hash)
        
        # If detailed flag is set, also fetch full transaction details
        if detailed:
            try:
                details = await transaction_service.get_transaction_details(tx_hash)
                result["details"] = details.get("details")
            except Exception as e:
                logger.warning(f"Failed to fetch transaction details: {str(e)}")
                result["details"] = None
                result["details_error"] = str(e)
        
        return result
        
    except ValueError as e:
        # Handle missing API key
        raise HTTPException(
            status_code=503,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error fetching transaction status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch transaction status: {str(e)}"
        )


@router.get("/details/{tx_hash}")
async def get_transaction_details(tx_hash: str) -> Dict[str, Any]:
    """
    Get full transaction details from Etherscan API.
    
    Args:
        tx_hash: The transaction hash to check
        
    Returns:
        Full transaction details including block number, gas used, value, etc.
    """
    try:
        # Validate tx_hash format
        if not tx_hash.startswith("0x") or len(tx_hash) != 66:
            raise HTTPException(
                status_code=400,
                detail="Invalid transaction hash format. Must be a 66-character hex string starting with '0x'"
            )
        
        result = await transaction_service.get_transaction_details(tx_hash)
        
        if result.get("error"):
            raise HTTPException(
                status_code=404,
                detail=result["error"]
            )
        
        return result
        
    except ValueError as e:
        # Handle missing API key
        raise HTTPException(
            status_code=503,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching transaction details: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch transaction details: {str(e)}"
        )


@router.get("/by-address/{address}")
async def get_transactions_by_address(
    address: str = Path(..., description="Wallet address to get transactions for"),
    limit: int = Query(100, ge=1, le=1000, description="Number of results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get all transactions for a given wallet address.
    
    This endpoint retrieves transactions associated with a user by their wallet address.
    
    Args:
        address: The wallet address to query transactions for
        limit: Maximum number of transactions to return (default: 100, max: 1000)
        offset: Number of transactions to skip for pagination (default: 0)
        
    Returns:
        Dictionary containing:
        - transactions: List of transaction records
        - total: Total number of transactions for this address
        - offset: The offset used in the query
        - limit: The limit used in the query
        - address: The queried wallet address
    """
    try:
        # Validate address format (basic check)
        if not address.startswith("0x") or len(address) != 42:
            raise HTTPException(
                status_code=400,
                detail="Invalid wallet address format. Must be a 42-character hex string starting with '0x'"
            )
        
        # First, find the user by wallet address
        stmt = select(User).where(User.wallet_address == address)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            # If no user found with this wallet address, return empty result
            logger.info(f"No user found for wallet address: {address}")
            return {
                "transactions": [],
                "total": 0,
                "offset": offset,
                "limit": limit,
                "address": address,
                "message": "No user found with this wallet address"
            }
        
        # Get transactions for this user
        # Count total transactions
        count_stmt = select(func.count()).select_from(Transaction).where(Transaction.user_id == user.user_id)
        count_result = await db.execute(count_stmt)
        total_count = count_result.scalar_one()
        
        # Get paginated transactions
        stmt = (
            select(Transaction)
            .where(Transaction.user_id == user.user_id)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(stmt)
        transactions = result.scalars().all()
        
        # Format transactions for response
        formatted_transactions = []
        for tx in transactions:
            formatted_tx = {
                "transaction_id": str(tx.transaction_id),
                "user_id": tx.user_id,
                "transaction_type": tx.transaction_type.value if tx.transaction_type else None,
                "amount_usdc": float(tx.amount_usdc) if tx.amount_usdc else 0,
                "tx_hash": tx.tx_hash,
                "block_number": tx.block_number,
                "gas_used": tx.gas_used,
                "gas_price": float(tx.gas_price) if tx.gas_price else None,
                "status": tx.status.value if tx.status else None,
                "metadata": tx.tx_metadata,
                "created_at": tx.created_at.isoformat() if tx.created_at else None,
                "confirmed_at": tx.confirmed_at.isoformat() if tx.confirmed_at else None
            }
            formatted_transactions.append(formatted_tx)
        
        logger.info(f"Successfully fetched {len(transactions)} transactions for address {address}")
        
        return {
            "transactions": formatted_transactions,
            "total": total_count,
            "offset": offset,
            "limit": limit,
            "address": address,
            "user_id": user.user_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching transactions for address {address}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch transactions for address: {str(e)}"
        )