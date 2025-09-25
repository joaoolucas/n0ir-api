"""
Moonwell Service for borrow-based hedging.
Manages collateral and borrow calculations for delta-neutral strategies.
"""
from typing import Dict, Optional
from decimal import Decimal
from loguru import logger


class MoonwellService:
    """Service for Moonwell borrow calculations."""

    def __init__(self):
        """Initialize Moonwell service."""
        # Moonwell markets on Base
        self.markets = {
            "mUSDC": {
                "address": "0xEdc817A28E8B93B03976FBd4a3dDBc9f7D176c22",
                "decimals": 6,
                "type": "collateral",
                "collateral_factor": 0.75  # 75% max LTV
            },
            "mWETH": {
                "address": "0x628ff693426583D9a7FB391E54366292F509D457",
                "decimals": 18,
                "type": "borrow",
                "borrow_apy": 4.2  # Default APY
            },
            "mWBTC": {
                "address": "0xF877ACaFA28c19b96727966690b2f44d35aD5976",
                "decimals": 8,
                "type": "borrow",
                "borrow_apy": 3.8  # Default APY
            }
        }

        # Default rates
        self.default_rates = {
            "mUSDC": {"supply_apy": 2.5},
            "mWETH": {"borrow_apy": 4.2},
            "mWBTC": {"borrow_apy": 3.8}
        }

    def calculate_hedge_position(
        self,
        total_capital: float,
        weth_price: float = 4000,
        wbtc_price: float = 100000
    ) -> Dict:
        """
        Calculate optimal Moonwell hedge position.

        For Moonwell strategy:
        1. Supply all capital as USDC collateral
        2. Borrow WETH based on safe LTV (45%)
        3. Swap borrowed WETH to USDC for Aerodrome LP

        Args:
            total_capital: Total USDC available
            weth_price: Current WETH price
            wbtc_price: Current WBTC price

        Returns:
            Hedge position details
        """
        # All capital goes to Moonwell as collateral
        collateral_usdc = total_capital

        # Calculate safe borrow amount (45% LTV for safety)
        max_borrow_usd = collateral_usdc * 0.45

        # Calculate WETH to borrow
        weth_to_borrow = max_borrow_usd / weth_price

        # Expected USDC after swap (0.5% slippage)
        expected_usdc_from_swap = max_borrow_usd * 0.995

        return {
            "moonwell": {
                "protocol": "moonwell",
                "collateral": {
                    "market": "mUSDC",
                    "amount_usdc": collateral_usdc
                },
                "borrow": {
                    "market": "mWETH",
                    "amount_weth": round(weth_to_borrow, 4),
                    "amount_usd": max_borrow_usd,
                    "post_borrow_action": "swap_to_usdc"
                }
            },
            "aerodrome_lp": {
                "protocol": "aerodrome",
                "pool": "WETH-USDC",
                "amount_usdc": expected_usdc_from_swap,
                "range_percentage": 5
            }
        }

    def calculate_ltv(self, collateral_usd: float, borrow_usd: float) -> float:
        """Calculate loan-to-value ratio."""
        if collateral_usd == 0:
            return 0
        return borrow_usd / collateral_usd

    def calculate_health_factor(
        self,
        collateral_usd: float,
        borrow_usd: float,
        collateral_factor: float = 0.75
    ) -> float:
        """
        Calculate health factor.
        Health factor > 1 = safe, < 1 = liquidation risk
        """
        if borrow_usd == 0:
            return float('inf')
        return (collateral_usd * collateral_factor) / borrow_usd

    def check_range_break(
        self,
        current_price: float,
        tick_lower: int,
        tick_upper: int,
        tick_spacing: int = 10
    ) -> Dict:
        """
        Check if position is out of range.

        Args:
            current_price: Current price
            tick_lower: Lower tick bound
            tick_upper: Upper tick bound
            tick_spacing: Tick spacing for the pool

        Returns:
            Range break monitoring info
        """
        # Convert ticks to prices (simplified)
        price_lower = 1.0001 ** tick_lower
        price_upper = 1.0001 ** tick_upper

        if current_price < price_lower or current_price > price_upper:
            return {
                "range_break": {
                    "trigger": "price_outside_tick_bounds",
                    "suggested_action": "close_and_rebalance",
                    "current_price": current_price,
                    "price_range": {
                        "lower": price_lower,
                        "upper": price_upper
                    }
                }
            }
        return {}


# Singleton instance
moonwell_service = MoonwellService()