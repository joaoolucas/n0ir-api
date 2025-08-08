from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class TokenInfoResponse(BaseModel):
    address: str = Field(..., description="Token contract address")
    symbol: str = Field(..., description="Token symbol")
    decimals: int = Field(..., description="Token decimals")
    name: str = Field(..., description="Token name")
    price_usd: float = Field(0, description="Token price in USD")
    logo_uri: Optional[str] = Field(None, description="Token logo URI")


class TokenPricesRequest(BaseModel):
    addresses: List[str] = Field(..., description="List of token addresses", min_items=1, max_items=100)
    
    @field_validator("addresses")
    def validate_addresses(cls, v):
        # Validate that all addresses are valid Ethereum addresses
        for addr in v:
            if not addr.startswith("0x") or len(addr) != 42:
                raise ValueError(f"Invalid address format: {addr}")
        return v


class TokenPricesResponse(BaseModel):
    prices: Dict[str, float] = Field(..., description="Map of token addresses to prices in USD")