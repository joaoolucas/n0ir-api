"""Models for tracking blockchain data synchronization."""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, DateTime, Integer, Numeric, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid
from app.database.base import Base


class BlockchainSync(Base):
    """Track blockchain sync status for different data types."""
    __tablename__ = "blockchain_sync"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Sync identification
    sync_type = Column(String(50), nullable=False, unique=True)
    # Types: WALLET_HISTORY, LIQUIDITY_EVENTS, USDC_TRANSFERS
    
    # Last synced position
    last_block_number = Column(Integer, nullable=True)
    last_timestamp = Column(DateTime(timezone=True), nullable=True)
    
    # Sync metadata
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    next_sync_at = Column(DateTime(timezone=True), nullable=True)
    sync_status = Column(String(20), default="IDLE")
    # Status: IDLE, SYNCING, FAILED, COMPLETED
    
    # Error tracking
    last_error = Column(String(500), nullable=True)
    error_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        Index('idx_blockchain_sync_type', 'sync_type'),
        Index('idx_blockchain_sync_status', 'sync_status'),
    )


class WalletTransaction(Base):
    """Store wallet transaction history from CDP SQL API."""
    __tablename__ = "wallet_transactions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Transaction identification
    transaction_hash = Column(String(66), unique=True, nullable=False, index=True)
    block_number = Column(Integer, nullable=False, index=True)
    
    # Addresses
    from_address = Column(String(42), nullable=False, index=True)
    to_address = Column(String(42), nullable=True, index=True)
    
    # Transaction data
    value = Column(String(78), nullable=True)  # Wei value as string
    gas = Column(Integer, nullable=True)
    gas_price = Column(Integer, nullable=True)
    gas_cost_eth = Column(Numeric(precision=20, scale=18), nullable=True)
    
    # Timestamps
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    fetched_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    # Metadata
    is_agent_wallet = Column(Boolean, default=False)
    user_id = Column(String(42), nullable=True, index=True)
    
    # Indexes
    __table_args__ = (
        Index('idx_wallet_tx_addresses', 'from_address', 'to_address'),
        Index('idx_wallet_tx_timestamp', 'timestamp'),
        Index('idx_wallet_tx_user', 'user_id'),
    )


class LiquidityEvent(Base):
    """Store liquidity manager events from CDP SQL API."""
    __tablename__ = "liquidity_events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Event identification
    transaction_hash = Column(String(66), nullable=False, index=True)
    block_number = Column(Integer, nullable=False, index=True)
    log_index = Column(Integer, nullable=False)
    
    # Event data
    event_signature = Column(String(255), nullable=False, index=True)
    event_name = Column(String(100), nullable=True)
    contract_address = Column(String(42), nullable=False, index=True)
    
    # Event parameters (stored as JSON)
    parameters = Column(JSONB, nullable=True)
    topics = Column(JSONB, nullable=True)
    
    # Decoded data for our use case
    token_id = Column(Integer, nullable=True, index=True)  # Position NFT ID
    owner_address = Column(String(42), nullable=True, index=True)
    pool_address = Column(String(42), nullable=True)
    
    # Timestamps
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    fetched_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    # Link to our data
    position_id = Column(Integer, nullable=True, index=True)  # Link to positions.token_id
    user_id = Column(String(42), nullable=True, index=True)
    
    # Unique constraint
    __table_args__ = (
        Index('idx_liquidity_event_unique', 'transaction_hash', 'log_index', unique=True),
        Index('idx_liquidity_event_token', 'token_id'),
        Index('idx_liquidity_event_owner', 'owner_address'),
        Index('idx_liquidity_event_timestamp', 'timestamp'),
    )