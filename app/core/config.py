from typing import List, Union
from pydantic_settings import BaseSettings
from pydantic import Field
import json


class Settings(BaseSettings):
    # API Configuration
    api_title: str = Field(default="n0ir API", env="API_TITLE")
    api_version: str = Field(default="1.0.0", env="API_VERSION")
    api_prefix: str = Field(default="/api/v1", env="API_PREFIX")
    
    # RPC Configuration
    rpc_url: str = Field(
        default="https://base-mainnet.g.alchemy.com/v2/PbEIlFPXdZpA6ld_nxViZD73mlaupBrY",
        env="RPC_URL"
    )
    
    # Cache Configuration (seconds)
    cache_ttl_token_info: int = Field(default=3600, env="CACHE_TTL_TOKEN_INFO")
    cache_ttl_token_prices: int = Field(default=60, env="CACHE_TTL_TOKEN_PRICES")
    cache_ttl_pool_data: int = Field(default=300, env="CACHE_TTL_POOL_DATA")
    cache_ttl_pool_list: int = Field(default=60, env="CACHE_TTL_POOL_LIST")
    
    # Server Configuration
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")
    reload: bool = Field(default=False, env="RELOAD")
    
    # Logging Configuration
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    enable_file_logging: bool = Field(default=True, env="ENABLE_FILE_LOGGING")
    log_dir: str = Field(default="logs", env="LOG_DIR")
    
    # CORS Configuration
    cors_origins: List[str] = Field(default=["*"], env="CORS_ORIGINS")
    cors_allow_credentials: bool = Field(default=True, env="CORS_ALLOW_CREDENTIALS")
    cors_allow_methods: List[str] = Field(default=["*"], env="CORS_ALLOW_METHODS")
    cors_allow_headers: List[str] = Field(default=["*"], env="CORS_ALLOW_HEADERS")
    
    # Sugar Contract Configuration
    sugar_contract_address: str = Field(
        default="0x27fc745390d1f4BaF8D184FBd97748340f786634",
        env="SUGAR_CONTRACT_ADDRESS"
    )
    
    # Common Token Addresses
    aero_token_address: str = Field(
        default="0x940181a94A35A4569E4529A3CDfB74e38FD98631",
        env="AERO_TOKEN_ADDRESS"
    )
    usdc_address: str = Field(
        default="0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        env="USDC_ADDRESS"
    )
    weth_address: str = Field(
        default="0x4200000000000000000000000000000000000006",
        env="WETH_ADDRESS"
    )
    
    # Wallet Registry Configuration
    wallet_registry_contract_address: str = Field(
        default="0xBd221C9A75f44dBcF33e8F872daD001f2C0B6f26",
        env="WALLET_REGISTRY_CONTRACT_ADDRESS"
    )
    wallet_registry_operator_address: str = Field(
        default="0x27f4f543c35ee533A7566663C0207Eb179FbA656",
        env="WALLET_REGISTRY_OPERATOR_ADDRESS"
    )
    wallet_registry_operator_private_key: str = Field(
        default="",
        env="WALLET_REGISTRY_OPERATOR_PRIVATE_KEY"
    )
    
    # Gas Configuration
    max_gas_price_gwei: int = Field(default=50, env="MAX_GAS_PRICE_GWEI")
    gas_multiplier: float = Field(default=1.2, env="GAS_MULTIPLIER")
    
    # Transaction Configuration
    transaction_timeout: int = Field(default=300, env="TRANSACTION_TIMEOUT")
    max_retry_attempts: int = Field(default=3, env="MAX_RETRY_ATTEMPTS")
    
    # Tick Spacings
    stable_tick_spacings: List[int] = [1, 10, 50]
    volatile_tick_spacings: List[int] = [100, 200, 2000]
    
    # Wallet Registry Configuration
    wallet_registry_contract_address: str = Field(
        default="0xB693920F2ea642020491420dc8Fb03cFbA2f412C",
        env="WALLET_REGISTRY_CONTRACT_ADDRESS"
    )
    wallet_registry_operator_address: str = Field(
        default="0x27f4f543c35ee533A7566663C0207Eb179FbA656",
        env="WALLET_REGISTRY_OPERATOR_ADDRESS"
    )
    wallet_registry_operator_private_key: str = Field(
        default="",
        env="WALLET_REGISTRY_OPERATOR_PRIVATE_KEY"
    )
    
    # Transaction Configuration
    max_gas_price_gwei: int = Field(default=50, env="MAX_GAS_PRICE_GWEI")
    gas_multiplier: float = Field(default=1.2, env="GAS_MULTIPLIER")
    transaction_timeout: int = Field(default=300, env="TRANSACTION_TIMEOUT")
    max_retry_attempts: int = Field(default=3, env="MAX_RETRY_ATTEMPTS")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        
        @classmethod
        def parse_env_var(cls, field_name: str, raw_val: str) -> Union[str, List[str], bool, int]:
            # Parse JSON strings for list fields
            if field_name in ["cors_origins", "cors_allow_methods", "cors_allow_headers"]:
                try:
                    return json.loads(raw_val)
                except (json.JSONDecodeError, TypeError):
                    # If it's not valid JSON, treat it as a single string
                    return [raw_val] if raw_val else []
            return raw_val


# Create a singleton instance
settings = Settings()