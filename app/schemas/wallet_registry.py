"""Schemas for wallet registry operations."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
from web3 import Web3


class WalletAddress(BaseModel):
    """Single wallet address."""
    address: str = Field(..., description="Ethereum wallet address")
    
    @field_validator('address')
    @classmethod
    def validate_address(cls, v: str) -> str:
        """Validate and normalize Ethereum address."""
        try:
            return Web3.to_checksum_address(v)
        except Exception:
            raise ValueError(f"Invalid Ethereum address: {v}")


class WalletAddressList(BaseModel):
    """List of wallet addresses."""
    addresses: List[str] = Field(..., description="List of Ethereum wallet addresses", min_length=1, max_length=100)
    
    @field_validator('addresses')
    @classmethod
    def validate_addresses(cls, v: List[str]) -> List[str]:
        """Validate and normalize all addresses."""
        validated = []
        for addr in v:
            try:
                validated.append(Web3.to_checksum_address(addr))
            except Exception:
                raise ValueError(f"Invalid Ethereum address: {addr}")
        return validated


class WalletRegistrationResponse(BaseModel):
    """Response for wallet registration operation."""
    success: bool = Field(..., description="Whether the operation was successful")
    address: str = Field(..., description="The wallet address that was registered")
    tx_hash: Optional[str] = Field(None, description="Transaction hash if successful")
    error: Optional[str] = Field(None, description="Error message if failed")
    gas_used: Optional[int] = Field(None, description="Gas used for the transaction")
    block_number: Optional[int] = Field(None, description="Block number where transaction was mined")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb5",
                "tx_hash": "0x123456789abcdef...",
                "gas_used": 45000,
                "block_number": 12345678
            }
        }


class WalletBatchRegistrationResponse(BaseModel):
    """Response for batch wallet registration operation."""
    success: bool = Field(..., description="Whether the operation was successful")
    registered: List[str] = Field(..., description="Addresses that were successfully registered")
    already_registered: List[str] = Field(..., description="Addresses that were already registered")
    tx_hash: Optional[str] = Field(None, description="Transaction hash if successful")
    error: Optional[str] = Field(None, description="Error message if failed")
    gas_used: Optional[int] = Field(None, description="Gas used for the transaction")
    message: Optional[str] = Field(None, description="Additional message")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "registered": ["0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb5"],
                "already_registered": ["0x123..."],
                "tx_hash": "0x123456789abcdef...",
                "gas_used": 120000
            }
        }


class WalletRemovalResponse(BaseModel):
    """Response for wallet removal operation."""
    success: bool = Field(..., description="Whether the operation was successful")
    address: str = Field(..., description="The wallet address that was removed")
    tx_hash: Optional[str] = Field(None, description="Transaction hash if successful")
    error: Optional[str] = Field(None, description="Error message if failed")
    gas_used: Optional[int] = Field(None, description="Gas used for the transaction")
    block_number: Optional[int] = Field(None, description="Block number where transaction was mined")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb5",
                "tx_hash": "0x123456789abcdef...",
                "gas_used": 45000,
                "block_number": 12345678
            }
        }


class WalletBatchRemovalResponse(BaseModel):
    """Response for batch wallet removal operation."""
    success: bool = Field(..., description="Whether the operation was successful")
    removed: List[str] = Field(..., description="Addresses that were successfully removed")
    not_registered: List[str] = Field(..., description="Addresses that were not registered")
    tx_hash: Optional[str] = Field(None, description="Transaction hash if successful")
    error: Optional[str] = Field(None, description="Error message if failed")
    gas_used: Optional[int] = Field(None, description="Gas used for the transaction")
    message: Optional[str] = Field(None, description="Additional message")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "removed": ["0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb5"],
                "not_registered": ["0x123..."],
                "tx_hash": "0x123456789abcdef...",
                "gas_used": 120000
            }
        }


class WalletStatusResponse(BaseModel):
    """Response for wallet registration status check."""
    address: str = Field(..., description="The wallet address")
    registered: bool = Field(..., description="Whether the wallet is registered")
    
    class Config:
        json_schema_extra = {
            "example": {
                "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb5",
                "registered": True
            }
        }


class WalletBatchStatusResponse(BaseModel):
    """Response for batch wallet status check."""
    statuses: List[WalletStatusResponse] = Field(..., description="Registration status for each wallet")
    
    class Config:
        json_schema_extra = {
            "example": {
                "statuses": [
                    {
                        "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb5",
                        "registered": True
                    },
                    {
                        "address": "0x123...",
                        "registered": False
                    }
                ]
            }
        }


class RegistryStatsResponse(BaseModel):
    """Response for registry statistics."""
    wallet_count: int = Field(..., description="Total number of registered wallets")
    operator_count: int = Field(..., description="Total number of authorized operators")
    contract_address: str = Field(..., description="Wallet registry contract address")
    operator_address: str = Field(..., description="Current operator address")
    
    class Config:
        json_schema_extra = {
            "example": {
                "wallet_count": 150,
                "operator_count": 3,
                "contract_address": "0xB693920F2ea642020491420dc8Fb03cFbA2f412C",
                "operator_address": "0x27f4f543c35ee533A7566663C0207Eb179FbA656"
            }
        }