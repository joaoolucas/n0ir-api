from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Dict, Any
from app.services.transaction_service import transaction_service
import logging

logger = logging.getLogger(__name__)

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