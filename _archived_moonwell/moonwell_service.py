"""
Moonwell Service for borrow-based hedging.
Manages collateral and borrow calculations for delta-neutral strategies.
"""
from typing import Dict, Optional
from decimal import Decimal
from loguru import logger
from app.integrations.liquidity_manager import LiquidityManagerClient


class MoonwellService:
    """Service for Moonwell borrow calculations."""

    def __init__(self):
        """Initialize Moonwell service."""
        self.liquidity_manager = LiquidityManagerClient()

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

    def calculate_optimal_range_from_pool_metrics(
        self,
        apr: float,
        volume_24h: float,
        tvl: float,
        is_stable: bool = False
    ) -> int:
        """
        Calculate optimal range percentage based on pool metrics.

        Args:
            apr: Pool's base APR
            volume_24h: 24-hour volume in USD
            tvl: Total value locked in USD
            is_stable: Whether this is a stable pool

        Returns:
            Suggested range percentage (e.g., 10 for ±5%)
        """
        # Calculate volume/TVL ratio (turnover)
        turnover = volume_24h / tvl if tvl > 0 else 0

        # Stable pools should have very tight ranges
        if is_stable:
            return 2  # ±1% for stable pools

        # High APR and high turnover: moderately tight range to capture fees
        if apr > 50 and turnover > 0.5:
            return 10  # ±5% (was 5%, too narrow for volatile pairs)

        # Medium APR or medium turnover: standard range
        elif apr > 20 or turnover > 0.2:
            return 20  # ±10% (was 10%, increased for better stability)

        # Low APR and low turnover: wider range for safety
        else:
            return 30  # ±15% (was 20%, increased for safety)

    def calculate_effective_apr(
        self,
        base_apr: float,
        range_percentage: int
    ) -> float:
        """
        Calculate effective APR based on range width.
        Narrower ranges capture more fees but have higher IL risk.

        Args:
            base_apr: Base APR of the pool
            range_percentage: Range width as percentage

        Returns:
            Effective APR adjusted for range
        """
        # Range effectiveness multipliers (adjusted for wider ranges)
        if range_percentage <= 5:
            # Very narrow: 4x fees but very high IL risk (rare for volatile pairs)
            multiplier = 4.0
        elif range_percentage <= 10:
            # Tight: 2.5x fees, high concentration
            multiplier = 2.5
        elif range_percentage <= 20:
            # Standard: 1.8x fees, balanced risk
            multiplier = 1.8
        elif range_percentage <= 30:
            # Wide: 1.4x fees, lower risk
            multiplier = 1.4
        else:
            # Very wide: close to base APR
            multiplier = 1.2

        return base_apr * multiplier

    def calculate_optimal_borrow_amount(
        self,
        total_capital: float,
        target_lp_allocation: float,
        max_ltv: float = 0.45
    ) -> Dict:
        """
        Calculate optimal borrow amount based on target LP allocation.

        Args:
            total_capital: User's total USDC capital
            target_lp_allocation: Target USDC amount for LP
            max_ltv: Maximum safe loan-to-value ratio (default 45%)

        Returns:
            Dictionary with borrow calculations
        """
        # Maximum we can borrow based on LTV
        max_borrow_usd = total_capital * max_ltv

        # If target LP allocation is less than max borrow, use it
        if target_lp_allocation <= max_borrow_usd:
            borrow_amount = target_lp_allocation
        else:
            # Can't achieve target with safe LTV, use max safe amount
            borrow_amount = max_borrow_usd
            logger.warning(f"Target LP allocation {target_lp_allocation} exceeds safe borrow limit {max_borrow_usd}")

        return {
            "collateral_usdc": total_capital,
            "borrow_usd": borrow_amount,
            "actual_lp_allocation": borrow_amount * 0.995,  # Account for swap slippage
            "ltv": borrow_amount / total_capital if total_capital > 0 else 0,
            "health_factor": (total_capital * 0.75) / borrow_amount if borrow_amount > 0 else float('inf')
        }

    def calculate_hedge_position(
        self,
        total_capital: float,
        pool_address: str,
        pool_metrics: Optional[Dict] = None,
        weth_price: float = 4000,
        wbtc_price: float = 100000
    ) -> Dict:
        """
        Calculate optimal Moonwell hedge position using pool metrics.

        For Moonwell strategy:
        1. Determine optimal range based on pool metrics
        2. Calculate optimal USDC allocation using liquidity manager
        3. Supply all capital as USDC collateral
        4. Borrow WETH based on safe LTV and optimal allocation
        5. Swap borrowed WETH to USDC for Aerodrome LP

        Args:
            total_capital: Total USDC available
            pool_address: Address of the target pool
            pool_metrics: Pool metrics (APR, volume, TVL, etc.)
            weth_price: Current WETH price
            wbtc_price: Current WBTC price

        Returns:
            Hedge position details with optimal allocations
        """
        # Calculate optimal range based on pool metrics
        if pool_metrics:
            suggested_range = self.calculate_optimal_range_from_pool_metrics(
                apr=pool_metrics.get('apr', 20),
                volume_24h=pool_metrics.get('volume_24h', 0),
                tvl=pool_metrics.get('tvl_usd', 0),
                is_stable=pool_metrics.get('is_stable', False)
            )
            effective_apr = self.calculate_effective_apr(
                pool_metrics.get('apr', 20),
                suggested_range
            )
        else:
            suggested_range = 20  # Default to 20% range (±10%) for volatile pairs
            effective_apr = 40  # Default APR

        # Calculate optimal USDC allocation
        # For now, use the full amount we can safely borrow
        # In production, this would call the liquidity manager contract
        target_lp_allocation = total_capital * 0.45

        # Calculate borrow amounts based on optimal allocation
        borrow_calculations = self.calculate_optimal_borrow_amount(
            total_capital=total_capital,
            target_lp_allocation=target_lp_allocation,
            max_ltv=0.45
        )

        # All capital goes to Moonwell as collateral
        collateral_usdc = total_capital

        # Calculate WETH to borrow
        weth_to_borrow = borrow_calculations['borrow_usd'] / weth_price

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
                    "amount_usd": borrow_calculations['borrow_usd'],
                    "post_borrow_action": "swap_to_usdc"
                }
            },
            "aerodrome_lp": {
                "protocol": "aerodrome",
                "pool": pool_metrics.get('symbol', 'WETH-USDC') if pool_metrics else "WETH-USDC",
                "pool_address": pool_address,
                "amount_usdc": borrow_calculations['actual_lp_allocation'],
                "range_percentage": suggested_range,
                "effective_apr": effective_apr
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