"""
Hedge Service for calculating Moonwell positions and account health.
"""
from typing import Dict, List, Any
from decimal import Decimal
from datetime import datetime
from loguru import logger

from app.integrations.moonwell_client import moonwell_client
from app.schemas.hedge import (
    HedgePositionResponse,
    SupplyPosition,
    BorrowPosition,
    AccountLiquidity,
    AccountHealth,
    PositionSummary
)


class HedgeService:
    """Service for managing hedge positions and calculations."""

    # Default prices for assets (in production, fetch from oracle)
    DEFAULT_PRICES = {
        "USDC": 1.0,
        "WETH": 4000.0,
        "cbBTC": 100000.0
    }

    # Collateral factors for Moonwell markets (default values)
    COLLATERAL_FACTORS = {
        "mUSDC": 0.75,  # 75% LTV
        "mWETH": 0.75,  # 75% LTV
        "mcbBTC": 0.70  # 70% LTV
    }

    async def get_asset_prices(self) -> Dict[str, float]:
        """
        Get current asset prices.
        In production, this would fetch from a price oracle.
        """
        # TODO: Integrate with actual price oracle
        return self.DEFAULT_PRICES

    async def get_hedge_position(self, wallet_address: str) -> HedgePositionResponse:
        """
        Get complete hedge position for a wallet including:
        - Supply positions
        - Borrow positions
        - Account health metrics
        - Position summary

        Args:
            wallet_address: Wallet address to check

        Returns:
            Complete hedge position response
        """
        try:
            # Get asset prices
            prices = await self.get_asset_prices()

            # Get all positions from Moonwell
            positions = await moonwell_client.get_all_positions(wallet_address)

            # Get account liquidity
            liquidity_data = await moonwell_client.get_account_liquidity(wallet_address)

            # Process supply positions
            supply_positions = []
            total_supply_usd = Decimal(0)
            total_supply_weighted_apy = Decimal(0)

            for supply in positions.get("supplies", []):
                # Calculate USD value
                underlying_asset = supply["underlying_asset"]
                price = prices.get(underlying_asset, 1.0)
                usd_value = Decimal(str(supply["underlying_balance"])) * Decimal(str(price))

                supply_position = SupplyPosition(
                    market=supply["market"],
                    underlying_asset=underlying_asset,
                    mtoken_balance=Decimal(str(supply["mtoken_balance"])),
                    exchange_rate=Decimal(str(supply["exchange_rate"])),
                    underlying_balance=Decimal(str(supply["underlying_balance"])),
                    underlying_balance_usd=usd_value,
                    supply_apy=Decimal(str(supply["supply_apy"]))
                )
                supply_positions.append(supply_position)

                total_supply_usd += usd_value
                total_supply_weighted_apy += usd_value * Decimal(str(supply["supply_apy"]))

            # Process borrow positions
            borrow_positions = []
            total_borrow_usd = Decimal(0)
            total_borrow_weighted_apy = Decimal(0)

            for borrow in positions.get("borrows", []):
                # Calculate USD value
                underlying_asset = borrow["underlying_asset"]
                price = prices.get(underlying_asset, 1.0)
                usd_value = Decimal(str(borrow["borrow_balance"])) * Decimal(str(price))

                borrow_position = BorrowPosition(
                    market=borrow["market"],
                    underlying_asset=underlying_asset,
                    borrow_balance=Decimal(str(borrow["borrow_balance"])),
                    borrow_balance_usd=usd_value,
                    borrow_apy=Decimal(str(borrow["borrow_apy"]))
                )
                borrow_positions.append(borrow_position)

                total_borrow_usd += usd_value
                total_borrow_weighted_apy += usd_value * Decimal(str(borrow["borrow_apy"]))

            # Calculate net APY
            net_apy = Decimal(0)
            if total_supply_usd > 0:
                supply_apy_contribution = total_supply_weighted_apy / total_supply_usd
                borrow_apy_contribution = Decimal(0)
                if total_borrow_usd > 0:
                    borrow_apy_contribution = total_borrow_weighted_apy / total_borrow_usd

                # Net APY = (Supply APY * Supply Value - Borrow APY * Borrow Value) / Net Value
                net_value = total_supply_usd - total_borrow_usd
                if net_value > 0:
                    net_apy = ((supply_apy_contribution * total_supply_usd) -
                              (borrow_apy_contribution * total_borrow_usd)) / net_value

            # Calculate health metrics
            health_factor = Decimal(0)
            ltv = Decimal(0)
            max_ltv = Decimal(0.75)  # Default 75%

            if total_supply_usd > 0:
                # Calculate weighted collateral value
                total_collateral_value = Decimal(0)
                for supply in supply_positions:
                    collateral_factor = Decimal(str(self.COLLATERAL_FACTORS.get(supply.market, 0.75)))
                    total_collateral_value += supply.underlying_balance_usd * collateral_factor

                if total_borrow_usd > 0:
                    ltv = total_borrow_usd / total_supply_usd
                    health_factor = total_collateral_value / total_borrow_usd
                else:
                    health_factor = Decimal(999)  # Very high if no borrows

            # Build response
            return HedgePositionResponse(
                wallet=wallet_address,
                supply_positions=supply_positions,
                borrow_positions=borrow_positions,
                summary=PositionSummary(
                    total_supply_usd=total_supply_usd,
                    total_borrow_usd=total_borrow_usd,
                    net_value_usd=total_supply_usd - total_borrow_usd,
                    net_apy=net_apy
                ),
                liquidity=AccountLiquidity(
                    available_to_borrow_usd=Decimal(str(liquidity_data["liquidity"])),
                    shortfall_usd=Decimal(str(liquidity_data["shortfall"])),
                    is_liquidatable=liquidity_data["is_liquidatable"]
                ),
                health=AccountHealth(
                    health_factor=health_factor,
                    ltv=ltv,
                    max_ltv=max_ltv,
                    liquidation_threshold=max_ltv
                ),
                timestamp=datetime.utcnow().isoformat() + "Z"
            )

        except Exception as e:
            logger.error(f"Error getting hedge position for {wallet_address}: {e}")
            # Return empty position on error
            return HedgePositionResponse(
                wallet=wallet_address,
                supply_positions=[],
                borrow_positions=[],
                summary=PositionSummary(
                    total_supply_usd=Decimal(0),
                    total_borrow_usd=Decimal(0),
                    net_value_usd=Decimal(0),
                    net_apy=Decimal(0)
                ),
                liquidity=AccountLiquidity(
                    available_to_borrow_usd=Decimal(0),
                    shortfall_usd=Decimal(0),
                    is_liquidatable=False
                ),
                health=AccountHealth(
                    health_factor=Decimal(0),
                    ltv=Decimal(0),
                    max_ltv=Decimal(0.75),
                    liquidation_threshold=Decimal(0.75)
                ),
                timestamp=datetime.utcnow().isoformat() + "Z"
            )


# Singleton instance
hedge_service = HedgeService()