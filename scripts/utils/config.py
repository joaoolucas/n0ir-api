"""Shared configuration utilities for scripts."""
import os
from typing import Optional
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
root_dir = Path(__file__).parent.parent.parent
env_path = root_dir / '.env'
load_dotenv(env_path)

def get_database_url() -> str:
    """Get database URL from environment variables.
    
    Returns:
        Database URL string
        
    Raises:
        ValueError: If no database URL is configured
    """
    # Try different database URL environment variables in order of preference
    db_url = (
        os.getenv('DATABASE_URL') or
        os.getenv('DATABASE_PRIVATE_URL') or
        os.getenv('DATABASE_PUBLIC_URL')
    )
    
    if not db_url:
        raise ValueError(
            "No database URL configured. Please set DATABASE_URL in your .env file.\n"
            "Example: DATABASE_URL=postgresql://user:password@host:port/database"
        )
    
    return db_url

def get_async_database_url() -> str:
    """Get async database URL from environment variables.
    
    Returns:
        Async database URL string with asyncpg driver
    """
    db_url = get_database_url()
    
    # Convert to asyncpg format if needed
    if db_url.startswith('postgresql://'):
        return db_url.replace('postgresql://', 'postgresql+asyncpg://')
    return db_url

def get_rpc_url() -> str:
    """Get RPC URL from environment variables.
    
    Returns:
        RPC URL string
    """
    rpc_url = os.getenv('RPC_URL')
    if not rpc_url:
        raise ValueError("RPC_URL not configured in environment variables")
    return rpc_url

def get_redis_url() -> Optional[str]:
    """Get Redis URL from environment variables.
    
    Returns:
        Redis URL string or None if not configured
    """
    return os.getenv('REDIS_URL')

# Common configuration values
BASE_CHAIN_ID = int(os.getenv('BASE_CHAIN_ID', '8453'))
ETHERSCAN_API_KEY = os.getenv('ETHERSCAN_API_KEY')

# Contract addresses
LIQUIDITY_MANAGER_ADDRESS = os.getenv(
    'LIQUIDITY_MANAGER_ADDRESS',
    '0xA933aAa8222De2f85E7A904E3E3e940652FBFdFD'
)
SUGAR_CONTRACT_ADDRESS = os.getenv(
    'SUGAR_CONTRACT_ADDRESS',
    '0x27fc745390d1f4BaF8D184FBd97748340f786634'
)

# Token addresses
USDC_ADDRESS = os.getenv(
    'USDC_ADDRESS',
    '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'
)
WETH_ADDRESS = os.getenv(
    'WETH_ADDRESS',
    '0x4200000000000000000000000000000000000006'
)
AERO_TOKEN_ADDRESS = os.getenv(
    'AERO_TOKEN_ADDRESS',
    '0x940181a94A35A4569E4529A3CDfB74e38FD98631'
)