from typing import Optional
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error: dict = Field(..., description="Error details")
    
    class Config:
        json_schema_extra = {
            "example": {
                "error": {
                    "code": "POOL_NOT_FOUND",
                    "message": "Pool with address 0x... not found",
                    "details": {}
                }
            }
        }


class PaginationInfo(BaseModel):
    total: int = Field(..., description="Total number of items")
    limit: int = Field(..., description="Maximum items per page")
    offset: int = Field(..., description="Number of items skipped")
    has_more: bool = Field(..., description="Whether more items are available")


class HealthResponse(BaseModel):
    status: str = Field(..., description="Service health status")
    network: str = Field(..., description="Blockchain network")
    block_number: Optional[int] = Field(None, description="Current block number")
    sugar_contract: str = Field(..., description="Sugar contract address")
    last_update: Optional[int] = Field(None, description="Last update timestamp")
    error: Optional[str] = Field(None, description="Error message if unhealthy")