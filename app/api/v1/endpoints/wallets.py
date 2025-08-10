"""Wallet Registry API endpoints."""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Path, Body, Request, Query
from app.schemas.wallet_registry import (
    WalletAddress,
    WalletAddressList,
    WalletRegistrationResponse,
    WalletBatchRegistrationResponse,
    WalletRemovalResponse,
    WalletBatchRemovalResponse,
    WalletStatusResponse,
    WalletBatchStatusResponse,
    RegistryStatsResponse
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
        
        result = await wallet_registry_service.register_wallet(wallet.address)
        
        if not result['success']:
            if 'already registered' in result.get('error', '').lower():
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": {
                            "code": "WALLET_ALREADY_REGISTERED",
                            "message": f"Wallet {wallet.address} is already registered",
                            "details": {"address": wallet.address}
                        }
                    }
                )
            else:
                raise HTTPException(
                    status_code=500,
                    detail={
                        "error": {
                            "code": "REGISTRATION_FAILED",
                            "message": result.get('error', 'Failed to register wallet'),
                            "details": {"address": wallet.address}
                        }
                    }
                )
        
        logger.info(f"Successfully registered wallet {wallet.address}")
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


@router.post(
    "/wallets/register/batch",
    response_model=WalletBatchRegistrationResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Unauthorized operator"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def register_wallets_batch(
    request: Request,
    wallets: WalletAddressList
):
    """
    Register multiple wallets in the registry in a single transaction.
    
    This endpoint adds multiple wallet addresses to the on-chain registry
    in a batch operation, which is more gas-efficient than individual registrations.
    
    Limits:
    - Maximum 100 addresses per batch
    
    Returns:
    - List of successfully registered addresses
    - List of already registered addresses
    - Transaction details if successful
    """
    logger.info(f"POST /wallets/register/batch - IP: {request.client.host}, Count: {len(wallets.addresses)}")
    
    try:
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
        
        result = await wallet_registry_service.register_wallets_batch(wallets.addresses)
        
        if not result['success']:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": {
                        "code": "BATCH_REGISTRATION_FAILED",
                        "message": result.get('error', 'Failed to register wallets'),
                        "details": {"attempted": len(wallets.addresses)}
                    }
                }
            )
        
        logger.info(f"Successfully registered {len(result.get('registered', []))} wallets")
        return WalletBatchRegistrationResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to register wallets batch: {e}")
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
    address: str = Path(..., description="Wallet address to remove from registry")
):
    """
    Remove a single wallet from the registry.
    
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
        
        result = await wallet_registry_service.remove_wallet(normalized_address)
        
        if not result['success']:
            if 'not registered' in result.get('error', '').lower():
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
            else:
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


@router.post(
    "/wallets/remove/batch",
    response_model=WalletBatchRemovalResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Unauthorized operator"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def remove_wallets_batch(
    request: Request,
    wallets: WalletAddressList
):
    """
    Remove multiple wallets from the registry in a single transaction.
    
    This endpoint removes multiple wallet addresses from the on-chain registry
    in a batch operation, which is more gas-efficient than individual removals.
    
    Limits:
    - Maximum 100 addresses per batch
    
    Returns:
    - List of successfully removed addresses
    - List of addresses that were not registered
    - Transaction details if successful
    """
    logger.info(f"POST /wallets/remove/batch - IP: {request.client.host}, Count: {len(wallets.addresses)}")
    
    try:
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
        
        result = await wallet_registry_service.remove_wallets_batch(wallets.addresses)
        
        if not result['success']:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": {
                        "code": "BATCH_REMOVAL_FAILED",
                        "message": result.get('error', 'Failed to remove wallets'),
                        "details": {"attempted": len(wallets.addresses)}
                    }
                }
            )
        
        logger.info(f"Successfully removed {len(result.get('removed', []))} wallets")
        return WalletBatchRemovalResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to remove wallets batch: {e}")
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


@router.post(
    "/wallets/status/batch",
    response_model=WalletBatchStatusResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def check_wallets_status_batch(
    request: Request,
    wallets: WalletAddressList
):
    """
    Check registration status for multiple wallets.
    
    This endpoint queries the on-chain registry to check if multiple
    wallet addresses are currently registered.
    
    Limits:
    - Maximum 100 addresses per query
    
    Returns:
    - List of addresses with their registration status
    """
    logger.info(f"POST /wallets/status/batch - IP: {request.client.host}, Count: {len(wallets.addresses)}")
    
    try:
        statuses = await wallet_registry_service.check_wallets_batch(wallets.addresses)
        
        response_statuses = [
            WalletStatusResponse(address=addr, registered=status)
            for addr, status in zip(wallets.addresses, statuses)
        ]
        
        logger.info(f"Checked status for {len(wallets.addresses)} wallets")
        return WalletBatchStatusResponse(statuses=response_statuses)
        
    except Exception as e:
        logger.error(f"Failed to check wallets status batch: {e}")
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
    "/operator/status",
    response_model=Dict[str, Any],
    responses={
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def check_operator_status(
    request: Request,
    address: Optional[str] = Query(None, description="Operator address to check (uses configured operator if not provided)")
):
    """
    Check if an operator is authorized.
    
    This endpoint checks whether an operator address is authorized to perform
    wallet registration operations on the contract.
    
    Args:
    - address: Optional operator address to check (uses configured operator if not provided)
    
    Returns:
    - Operator address
    - Authorization status
    """
    logger.info(f"GET /wallets/operator/status - IP: {request.client.host}, Address: {address}")
    
    try:
        # Get the address to check
        if address:
            checked_address = address
        else:
            # Get the configured operator address from settings
            checked_address = settings.wallet_registry_operator_address
        
        is_authorized = await wallet_registry_service.is_operator_authorized(checked_address)
        
        logger.info(f"Operator {checked_address} authorization status: {is_authorized}")
        return {
            "operator": checked_address,
            "authorized": is_authorized,
            "contract": settings.wallet_registry_contract_address
        }
        
    except Exception as e:
        logger.error(f"Failed to check operator status: {e}")
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
    "/wallets/stats",
    response_model=RegistryStatsResponse,
    responses={
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)
async def get_registry_stats(request: Request):
    """
    Get wallet registry statistics.
    
    This endpoint returns current statistics about the wallet registry,
    including total number of registered wallets and authorized operators.
    
    Returns:
    - Total wallet count
    - Total operator count
    - Contract address
    - Current operator address
    """
    logger.info(f"GET /wallets/stats - IP: {request.client.host}")
    
    try:
        stats = await wallet_registry_service.get_registry_stats()
        
        logger.info(f"Registry stats: {stats['wallet_count']} wallets, {stats['operator_count']} operators")
        return RegistryStatsResponse(**stats)
        
    except Exception as e:
        logger.error(f"Failed to get registry stats: {e}")
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