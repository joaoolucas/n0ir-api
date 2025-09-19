"""Pydantic models for CDP SQL API responses."""

from typing import List, Dict, Any, Optional
from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel, Field


class CDPQueryResponse(BaseModel):
    """Response from CDP SQL API query."""
    result: List[Dict[str, Any]] = Field(default_factory=list)
    result_schema: Optional[Dict[str, Any]] = Field(None, alias="schema")
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        populate_by_name = True  # Allow both 'schema' and 'result_schema'


class TransactionData(BaseModel):
    """Blockchain transaction data from CDP SQL API."""
    transaction_hash: str
    block_number: int
    block_timestamp: datetime
    from_address: str
    to_address: Optional[str] = None
    value: str  # Wei value as string
    gas_used: Optional[int] = None
    gas_price: Optional[str] = None  # Wei as string
    gas_cost_eth: Optional[Decimal] = None
    tx_type: str = "transaction"
    
    class Config:
        json_encoders = {
            Decimal: str,
            datetime: lambda v: v.isoformat()
        }


class TransferData(BaseModel):
    """Token transfer data from CDP SQL API."""
    transaction_hash: str
    block_number: int
    block_timestamp: datetime
    from_address: str
    to_address: str
    token_address: str
    value: str  # Token amount as string
    tx_type: str = "transfer"
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class EventData(BaseModel):
    """Smart contract event data from CDP SQL API."""
    transaction_hash: str
    block_number: int
    block_timestamp: datetime
    log_index: int
    event_signature: str
    contract_address: str
    topics: List[str] = Field(default_factory=list)
    data: Optional[str] = None
    decoded_params: Optional[Dict[str, Any]] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class WalletMetrics(BaseModel):
    """Aggregated wallet metrics from CDP SQL API."""
    wallet_address: str
    transaction_count: int = 0
    total_gas_eth: Decimal = Decimal(0)
    total_gas_usdc: Decimal = Decimal(0)
    usdc_in: Decimal = Decimal(0)
    usdc_out: Decimal = Decimal(0)
    net_usdc_flow: Decimal = Decimal(0)
    first_tx_timestamp: Optional[datetime] = None
    last_tx_timestamp: Optional[datetime] = None
    transactions: List[TransactionData] = Field(default_factory=list)
    transfers: List[TransferData] = Field(default_factory=list)
    
    class Config:
        json_encoders = {
            Decimal: str,
            datetime: lambda v: v.isoformat() if v else None
        }


class LiquidityEventMetrics(BaseModel):
    """Liquidity manager event metrics from CDP SQL API."""
    positions_created: int = 0
    positions_closed: int = 0
    total_liquidity_provided: Decimal = Decimal(0)
    total_liquidity_removed: Decimal = Decimal(0)
    total_fees_collected: Decimal = Decimal(0)
    events: List[EventData] = Field(default_factory=list)
    
    class Config:
        json_encoders = {
            Decimal: str
        }