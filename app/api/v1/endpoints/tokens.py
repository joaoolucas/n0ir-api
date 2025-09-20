from fastapi import APIRouter, HTTPException, Path, Request
from app.schemas.tokens import (
    TokenInfoResponse,
    TokenPricesResponse
)
from app.schemas.common import ErrorResponse
from app.core.pools_service import pools_service
from app.core.logger import logger

router = APIRouter()


@router.get(
    "/tokens/{address}",
    response_model=TokenInfoResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Token not found"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def get_token_info(
    request: Request,
    address: str = Path(..., description="Token contract address", pattern="^0x[a-fA-F0-9]{40}$")
):
    """
    Get information about a specific token.
    
    Returns token metadata including symbol, decimals, name, and current price.
    """
    logger.info(f"GET /tokens/{address} - IP: {request.client.host}")
    try:
        token_info = await pools_service.get_token_info(address)
        logger.info(f"Successfully fetched token info for {address}")
        return token_info
        
    except Exception as e:
        if "not found" in str(e).lower():
            logger.warning(f"Token not found: {address}")
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "TOKEN_NOT_FOUND",
                        "message": f"Token with address {address} not found",
                        "details": {}
                    }
                }
            )
        logger.error(f"Error fetching token info for {address}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to fetch token information",
                    "details": {"error": str(e)}
                }
            }
        )


# POST /tokens/prices endpoint removed - use GET /tokens/prices/<address> instead