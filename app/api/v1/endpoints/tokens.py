from fastapi import APIRouter, HTTPException, Path
from app.schemas.tokens import (
    TokenInfoResponse,
    TokenPricesRequest,
    TokenPricesResponse
)
from app.schemas.common import ErrorResponse
from app.core.pools_service import pools_service

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
    address: str = Path(..., description="Token contract address", pattern="^0x[a-fA-F0-9]{40}$")
):
    """
    Get information about a specific token.
    
    Returns token metadata including symbol, decimals, name, and current price.
    """
    try:
        token_info = await pools_service.get_token_info(address)
        return token_info
        
    except Exception as e:
        if "not found" in str(e).lower():
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


@router.post(
    "/tokens/prices",
    response_model=TokenPricesResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Bad Request"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def get_token_prices(request: TokenPricesRequest):
    """
    Get current USD prices for multiple tokens.
    
    Returns a map of token addresses to their current USD prices.
    Tokens without available price data will have a price of 0.
    """
    try:
        prices = await pools_service.get_token_prices(request.addresses)
        return prices
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to fetch token prices",
                    "details": {"error": str(e)}
                }
            }
        )