from typing import List, Union, Optional
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
    
    # Contract Addresses
    sugar_contract_address: str = Field(
        default="0x27fc745390d1f4BaF8D184FBd97748340f786634",
        env="SUGAR_CONTRACT_ADDRESS"
    )
    liquidity_manager_address: str = Field(
        default="0xA933aAa8222De2f85E7A904E3E3e940652FBFdFD",
        env="LIQUIDITY_MANAGER_ADDRESS"
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
    
    # Gas Configuration
    max_gas_price_gwei: int = Field(default=50, env="MAX_GAS_PRICE_GWEI")
    gas_multiplier: float = Field(default=1.2, env="GAS_MULTIPLIER")
    
    # Transaction Configuration
    transaction_timeout: int = Field(default=300, env="TRANSACTION_TIMEOUT")
    max_retry_attempts: int = Field(default=3, env="MAX_RETRY_ATTEMPTS")
    
    # Tick Spacings
    stable_tick_spacings: List[int] = [1, 10, 50]
    volatile_tick_spacings: List[int] = [100, 200, 2000]
    
    # Strategy Configuration
    strategy_min_tvl: float = Field(default=500_000, env="STRATEGY_MIN_TVL")
    strategy_min_volume_24h: float = Field(default=100_000, env="STRATEGY_MIN_VOLUME_24H")
    strategy_min_apr: float = Field(default=80, env="STRATEGY_MIN_APR")
    strategy_max_pool_concentration: float = Field(default=0.25, env="STRATEGY_MAX_POOL_CONCENTRATION")
    strategy_max_token_concentration: float = Field(default=0.40, env="STRATEGY_MAX_TOKEN_CONCENTRATION")
    strategy_max_var_1d: float = Field(default=0.05, env="STRATEGY_MAX_VAR_1D")
    strategy_max_var_7d: float = Field(default=0.10, env="STRATEGY_MAX_VAR_7D")
    strategy_circuit_breaker_threshold: float = Field(default=0.08, env="STRATEGY_CIRCUIT_BREAKER_THRESHOLD")
    strategy_upward_break_reversal_prob: float = Field(default=0.70, env="STRATEGY_UPWARD_BREAK_REVERSAL_PROB")
    strategy_cache_ttl_opportunities: int = Field(default=300, env="STRATEGY_CACHE_TTL_OPPORTUNITIES")
    strategy_cache_ttl_analysis: int = Field(default=60, env="STRATEGY_CACHE_TTL_ANALYSIS")
    
    # Database Configuration
    database_url: Optional[str] = Field(default=None, env="DATABASE_URL")
    database_private_url: Optional[str] = Field(default=None, env="DATABASE_PRIVATE_URL")
    database_public_url: Optional[str] = Field(default=None, env="DATABASE_PUBLIC_URL")
    database_pool_size: int = Field(default=20, env="DATABASE_POOL_SIZE")
    database_pool_overflow: int = Field(default=0, env="DATABASE_POOL_OVERFLOW")
    database_echo: bool = Field(default=False, env="DATABASE_ECHO")
    
    # CDP Integration Configuration
    cdp_api_key_id: Optional[str] = Field(default=None, env="CDP_API_KEY_ID")
    cdp_api_key_secret: Optional[str] = Field(default=None, env="CDP_API_KEY_SECRET")
    cdp_wallet_secret: Optional[str] = Field(default=None, env="CDP_WALLET_SECRET")
    
    # CDP SQL API Configuration
    cdp_client_api_key: Optional[str] = Field(
        default=None,
        env="CDP_CLIENT_API_KEY"
    )
    cdp_sql_api_url: str = Field(
        default="https://api.cdp.coinbase.com/platform/v2/data/query/run",
        env="CDP_SQL_API_URL"
    )
    cdp_sql_cache_ttl: int = Field(default=60, env="CDP_SQL_CACHE_TTL")
    cdp_sql_max_retries: int = Field(default=3, env="CDP_SQL_MAX_RETRIES")
    
    # Etherscan API Configuration
    etherscan_api_key: Optional[str] = Field(default=None, env="ETHERSCAN_API_KEY")
    base_chain_id: int = Field(default=8453, env="BASE_CHAIN_ID")  # Base mainnet chain ID
    
    # Agent Manager Configuration
    agent_manager_url: str = Field(
        default="http://localhost:8001",
        env="AGENT_MANAGER_URL"
    )
    
    # Redis Configuration
    redis_url: str = Field(
        default="redis://localhost:6379",
        env="REDIS_URL"
    )
    
    # API Authentication
    api_bearer_token: Optional[str] = Field(
        default=None,
        env="API_BEARER_TOKEN"
    )
    
    @property
    def get_database_url(self) -> Optional[str]:
        """Get the appropriate database URL for Railway."""
        # Use private URL for internal Railway connections (faster, free)
        return self.database_private_url or self.database_url
    
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