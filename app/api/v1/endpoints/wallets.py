"""Wallet Registry API endpoints."""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Path, Body, Request, Query
from app.schemas.wallet_registry import (
    WalletAddress,
    WalletRegistrationResponse,
    WalletRemovalResponse,
    WalletStatusResponse
)
from app.schemas.common import ErrorResponse
from app.core.wallet_registry_service import wallet_registry_service
from app.core.logger import logger
from app.core.config import settings
from web3 import Web3

router = APIRouter()


@router.post(
    "/wallets/register",
    response_model=WalletRegistrationResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Unauthorized operator"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def register_wallet(
    request: Request,
    wallet: WalletAddress
):
    """
    Register a single wallet in the registry.
    
    This endpoint adds a wallet address to the on-chain registry.
    Only authorized operators can register wallets.
    
    Returns:
    - Transaction details if successful
    - Error message if wallet is already registered or operation fails
    """
    logger.info(f"POST /wallets/register - IP: {request.client.host}, Address: {wallet.address}")
    
    try:
        # Validate address
        try:
            normalized_address = Web3.to_checksum_address(wallet.address)
        except Exception:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "INVALID_ADDRESS",
                        "message": f"Invalid Ethereum address: {wallet.address}",
                        "details": {"address": wallet.address}
                    }
                }
            )
        
        # Check operator authorization
        is_authorized = await wallet_registry_service.is_authorized_operator()
        if not is_authorized:
            logger.error("Operator not authorized")
            raise HTTPException(
                status_code=401,
                detail={
                    "error": {
                        "code": "UNAUTHORIZED_OPERATOR",
                        "message": "The configured operator is not authorized to perform this action",
                        "details": {}
                    }
                }
            )
        
        # Check if already registered
        is_registered = await wallet_registry_service.is_wallet_registered(normalized_address)
        if is_registered:
            logger.warning(f"Wallet {normalized_address} is already registered")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "WALLET_ALREADY_REGISTERED",
                        "message": f"Wallet {normalized_address} is already registered",
                        "details": {"address": normalized_address}
                    }
                }
            )
        
        # Register the wallet
        result = await wallet_registry_service.register_wallet(normalized_address)
        
        if not result['success']:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": {
                        "code": "REGISTRATION_FAILED",
                        "message": result.get('error', 'Failed to register wallet'),
                        "details": {"address": normalized_address}
                    }
                }
            )
        
        logger.info(f"Successfully registered wallet {normalized_address}")
        return WalletRegistrationResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to register wallet {wallet.address}: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": str(e),
                    "details": {}
                }
            }
        )


@router.delete(
    "/wallets/{address}",
    response_model=WalletRemovalResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Unauthorized operator"},
        404: {"model": ErrorResponse, "description": "Wallet not found"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def remove_wallet(
    request: Request,
    address: str = Path(..., description="Wallet address to remove")
):
    """
    Remove a wallet from the registry.
    
    This endpoint removes a wallet address from the on-chain registry.
    Only authorized operators can remove wallets.
    
    Returns:
    - Transaction details if successful
    - Error message if wallet is not registered or operation fails
    """
    logger.info(f"DELETE /wallets/{address} - IP: {request.client.host}")
    
    try:
        # Validate address
        try:
            normalized_address = Web3.to_checksum_address(address)
        except Exception:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "INVALID_ADDRESS",
                        "message": f"Invalid Ethereum address: {address}",
                        "details": {"address": address}
                    }
                }
            )
        
        # Check operator authorization
        is_authorized = await wallet_registry_service.is_authorized_operator()
        if not is_authorized:
            logger.error("Operator not authorized")
            raise HTTPException(
                status_code=401,
                detail={
                    "error": {
                        "code": "UNAUTHORIZED_OPERATOR",
                        "message": "The configured operator is not authorized to perform this action",
                        "details": {}
                    }
                }
            )
        
        # Check if wallet is registered
        is_registered = await wallet_registry_service.is_wallet_registered(normalized_address)
        if not is_registered:
            logger.warning(f"Wallet {normalized_address} is not registered")
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "WALLET_NOT_REGISTERED",
                        "message": f"Wallet {normalized_address} is not registered",
                        "details": {"address": normalized_address}
                    }
                }
            )
        
        # Remove the wallet
        result = await wallet_registry_service.remove_wallet(normalized_address)
        
        if not result['success']:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": {
                        "code": "REMOVAL_FAILED",
                        "message": result.get('error', 'Failed to remove wallet'),
                        "details": {"address": normalized_address}
                    }
                }
            )
        
        logger.info(f"Successfully removed wallet {normalized_address}")
        return WalletRemovalResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to remove wallet {address}: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": str(e),
                    "details": {}
                }
            }
        )


@router.get(
    "/wallets/{address}/status",
    response_model=WalletStatusResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid address"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def get_wallet_status(
    request: Request,
    address: str = Path(..., description="Wallet address to check")
):
    """
    Check if a wallet is registered in the registry.
    
    This endpoint queries the on-chain registry to check if a wallet
    address is currently registered.
    
    Returns:
    - Address and registration status (true/false)
    """
    logger.info(f"GET /wallets/{address}/status - IP: {request.client.host}")
    
    try:
        # Validate address
        try:
            normalized_address = Web3.to_checksum_address(address)
        except Exception:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "INVALID_ADDRESS",
                        "message": f"Invalid Ethereum address: {address}",
                        "details": {"address": address}
                    }
                }
            )
        
        is_registered = await wallet_registry_service.is_wallet_registered(normalized_address)
        
        logger.info(f"Wallet {normalized_address} registration status: {is_registered}")
        return WalletStatusResponse(
            address=normalized_address,
            registered=is_registered
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to check wallet status {address}: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": str(e),
                    "details": {}
                }
            }
        )