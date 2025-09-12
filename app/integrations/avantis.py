"""Avantis protocol integration for hedge position management."""

import json
from typing import Dict, Optional, Any, Tuple
from decimal import Decimal
from web3 import Web3
from web3.contract import Contract
from app.core.config import settings
from app.core.logger import logger


class AvantisClient:
    """Client for interacting with Avantis perp trading protocol."""
    
    # Contract addresses on Base Mainnet
    AVANTIS_TRADING = "0x44914408af82bC9983bbb330e3578E1105e11d4e"
    AVANTIS_REFERRAL = "0x6Cd67cfb2F7184D82fE1d67444d488E88E38e5e5"
    
    # Chainlink price feeds
    ETH_USD_FEED = "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70"
    BTC_USD_FEED = "0x64c911996D3c6aC71f9b455B1E8E7266BcbD848F"
    
    # Trading pairs
    PAIR_ETH_USD = 0
    PAIR_BTC_USD = 1
    
    # Constants
    MIN_HEDGE_SIZE = 10 * 10**6  # 10 USDC minimum
    MAX_LEVERAGE = 100
    DEFAULT_LEVERAGE = 3
    
    def __init__(self):
        """Initialize the Avantis client."""
        self._w3: Optional[Web3] = None
        self._trading_contract: Optional[Contract] = None
        self._referral_contract: Optional[Contract] = None
        
    def _get_w3(self) -> Web3:
        """Get or create Web3 instance."""
        if self._w3 is None:
            self._w3 = Web3(Web3.HTTPProvider(settings.rpc_url))
            if not self._w3.is_connected():
                raise Exception(f"Failed to connect to RPC endpoint: {settings.rpc_url}")
        return self._w3
    
    def _get_trading_abi(self) -> list:
        """Get simplified Avantis trading ABI."""
        return [
            {
                "inputs": [
                    {"internalType": "uint256", "name": "pairIndex", "type": "uint256"},
                    {"internalType": "uint256", "name": "posId", "type": "uint256"}
                ],
                "name": "getPosition",
                "outputs": [
                    {
                        "components": [
                            {"internalType": "address", "name": "trader", "type": "address"},
                            {"internalType": "uint256", "name": "pairIndex", "type": "uint256"},
                            {"internalType": "uint256", "name": "index", "type": "uint256"},
                            {"internalType": "uint256", "name": "initialPosUSDC", "type": "uint256"},
                            {"internalType": "uint256", "name": "openPrice", "type": "uint256"},
                            {"internalType": "bool", "name": "buy", "type": "bool"},
                            {"internalType": "uint256", "name": "leverage", "type": "uint256"},
                            {"internalType": "uint256", "name": "tp", "type": "uint256"},
                            {"internalType": "uint256", "name": "sl", "type": "uint256"}
                        ],
                        "internalType": "struct Trade",
                        "name": "",
                        "type": "tuple"
                    }
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "pairIndex", "type": "uint256"}
                ],
                "name": "getCurrentPrice",
                "outputs": [
                    {"internalType": "uint256", "name": "", "type": "uint256"}
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "pairIndex", "type": "uint256"},
                    {"internalType": "uint256", "name": "posId", "type": "uint256"}
                ],
                "name": "getPositionPnL",
                "outputs": [
                    {"internalType": "int256", "name": "pnl", "type": "int256"},
                    {"internalType": "uint256", "name": "fundingFee", "type": "uint256"}
                ],
                "stateMutability": "view",
                "type": "function"
            }
        ]
    
    def _get_trading_contract(self) -> Contract:
        """Get or create Avantis trading contract instance."""
        if self._trading_contract is None:
            w3 = self._get_w3()
            self._trading_contract = w3.eth.contract(
                address=Web3.to_checksum_address(self.AVANTIS_TRADING),
                abi=self._get_trading_abi()
            )
        return self._trading_contract
    
    async def get_position_status(self, hedge_id: int, pair_index: int) -> Dict[str, Any]:
        """
        Get current status of a hedge position.
        
        Args:
            hedge_id: Avantis position ID
            pair_index: Trading pair index (0 for ETH/USD, 1 for BTC/USD)
            
        Returns:
            Dictionary with position status including current price and P&L
        """
        try:
            contract = self._get_trading_contract()
            
            # Get position details
            position = contract.functions.getPosition(pair_index, hedge_id).call()
            
            # Get current price
            current_price = contract.functions.getCurrentPrice(pair_index).call()
            
            # Get P&L and funding
            pnl_data = contract.functions.getPositionPnL(pair_index, hedge_id).call()
            pnl_wei = pnl_data[0]
            funding_wei = pnl_data[1]
            
            # Convert from wei to USDC (6 decimals)
            pnl_usdc = Decimal(pnl_wei) / Decimal(10**6)
            funding_usdc = Decimal(funding_wei) / Decimal(10**6)
            price_decimal = Decimal(current_price) / Decimal(10**8)  # Price has 8 decimals
            
            return {
                "hedge_id": hedge_id,
                "pair_index": pair_index,
                "trader": position[0],
                "initial_size_usdc": Decimal(position[3]) / Decimal(10**6),
                "entry_price": Decimal(position[4]) / Decimal(10**8),
                "is_long": position[5],
                "leverage": position[6],
                "current_price": price_decimal,
                "pnl": pnl_usdc,
                "funding_paid": funding_usdc,
                "net_pnl": pnl_usdc - funding_usdc,
                "status": "active"
            }
            
        except Exception as e:
            logger.error(f"Error fetching Avantis position {hedge_id}: {e}")
            raise
    
    async def calculate_hedge_size(
        self,
        lp_position_value_usd: Decimal,
        token_exposure: str,
        hedge_ratio: Decimal = Decimal("0.5")
    ) -> Tuple[Decimal, int]:
        """
        Calculate optimal hedge size for delta-neutral position.
        
        Args:
            lp_position_value_usd: Total value of LP position in USD
            token_exposure: Which token to hedge ('ETH' or 'BTC')
            hedge_ratio: Percentage of exposure to hedge (default 50%)
            
        Returns:
            Tuple of (hedge_size_usdc, pair_index)
        """
        # Calculate exposure to hedge
        exposure_to_hedge = lp_position_value_usd * hedge_ratio
        
        # Determine pair index
        pair_index = self.PAIR_ETH_USD if token_exposure.upper() == 'ETH' else self.PAIR_BTC_USD
        
        # Apply minimum size constraint
        hedge_size = max(exposure_to_hedge, Decimal(self.MIN_HEDGE_SIZE) / Decimal(10**6))
        
        return (hedge_size, pair_index)
    
    async def get_funding_rate(self, pair_index: int) -> Decimal:
        """
        Get current funding rate for a trading pair.
        
        Args:
            pair_index: Trading pair index
            
        Returns:
            Current funding rate as decimal
        """
        try:
            # This would typically call a contract function to get funding rate
            # For now, return a placeholder
            return Decimal("0.0001")  # 0.01% funding rate
            
        except Exception as e:
            logger.error(f"Error fetching funding rate for pair {pair_index}: {e}")
            return Decimal("0")
    
    async def estimate_liquidation_price(
        self,
        entry_price: Decimal,
        is_long: bool,
        leverage: int
    ) -> Decimal:
        """
        Estimate liquidation price for a position.
        
        Args:
            entry_price: Entry price of the position
            is_long: Whether position is long
            leverage: Position leverage
            
        Returns:
            Estimated liquidation price
        """
        # Liquidation occurs when losses reach ~80% of collateral
        # With leverage, this happens at price movement of 0.8/leverage
        liquidation_threshold = Decimal("0.8") / Decimal(leverage)
        
        if is_long:
            # Long positions liquidate when price drops
            liquidation_price = entry_price * (Decimal("1") - liquidation_threshold)
        else:
            # Short positions liquidate when price rises
            liquidation_price = entry_price * (Decimal("1") + liquidation_threshold)
            
        return liquidation_price
    
    def get_market_name(self, pair_index: int) -> str:
        """Get human-readable market name from pair index."""
        if pair_index == self.PAIR_ETH_USD:
            return "ETH-USD"
        elif pair_index == self.PAIR_BTC_USD:
            return "BTC-USD"
        else:
            return f"UNKNOWN-{pair_index}"