"""
Hedge Service for calculating vault hedge positions and account health.
"""
from typing import Dict, List, Any
from decimal import Decimal
from datetime import datetime
from loguru import logger

from app.integrations.vault_contract import vault_contract
from app.schemas.hedge import (
    HedgePositionResponse,
    VaultPositionInfo,
    GlobalHealthMetrics
)


class HedgeService:
    """Service for managing hedge positions and calculations."""

    # Default prices for assets (in production, fetch from oracle)
    DEFAULT_PRICES = {
        "USDC": 1.0,
        "WETH": 4000.0,
        "cbBTC": 100000.0
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
        Get complete hedge position for a wallet from vault contract.

        Args:
            wallet_address: Wallet address to check

        Returns:
            Complete hedge position response
        """
        try:
            # Get asset prices
            prices = await self.get_asset_prices()

            # Get all position token IDs for user
            token_ids = vault_contract.get_user_positions(wallet_address)

            # Get global health metrics
            global_metrics = vault_contract.get_global_health_metrics()
            is_at_risk, current_hf, min_safe_hf = vault_contract.is_protocol_at_risk()

            # Process each position
            positions = []
            total_collateral_usd = Decimal(0)
            total_debt_usd = Decimal(0)

            for token_id in token_ids:
                try:
                    hedge_info = vault_contract.get_position_hedge_info(token_id)

                    # Get asset symbol
                    asset_symbol = vault_contract.get_token_symbol(hedge_info['hedged_asset'])

                    # Calculate debt in USD (need to determine decimals based on asset)
                    if asset_symbol == "WETH":
                        debt_amount = hedge_info['debt'] / 1e18
                        debt_usd = debt_amount * prices.get("WETH", 4000)
                    elif asset_symbol == "cbBTC":
                        debt_amount = hedge_info['debt'] / 1e8
                        debt_usd = debt_amount * prices.get("cbBTC", 100000)
                    else:
                        debt_amount = hedge_info['debt'] / 1e18  # Default to 18 decimals
                        debt_usd = 0

                    collateral_usdc = Decimal(str(hedge_info['collateral']))

                    position_info = VaultPositionInfo(
                        token_id=token_id,
                        collateral_usdc=collateral_usdc,
                        debt_amount=Decimal(str(debt_amount)),
                        debt_usd=Decimal(str(debt_usd)),
                        hedged_asset=hedge_info['hedged_asset'],
                        hedged_asset_symbol=asset_symbol,
                        is_hedged=hedge_info['is_hedged'],
                        exposure_usd=None,  # Would need LP position data to calculate
                        net_delta_usd=None  # Would need exposure to calculate
                    )

                    positions.append(position_info)
                    total_collateral_usd += collateral_usdc
                    total_debt_usd += Decimal(str(debt_usd))

                except Exception as e:
                    logger.error(f"Error processing position {token_id}: {e}")
                    continue

            # Build global health metrics response
            global_health = GlobalHealthMetrics(
                total_collateral_usd=Decimal(str(global_metrics['total_collateral'])),
                total_debt_weth=Decimal(str(global_metrics['total_debt_weth'])),
                total_debt_btc=Decimal(str(global_metrics['total_debt_btc'])),
                health_factor=Decimal(str(global_metrics['health_factor'])),
                available_borrows_usd=Decimal(str(global_metrics['available_borrows_usd'])),
                is_at_risk=is_at_risk
            )

            # Build response
            response = HedgePositionResponse(
                wallet=wallet_address,
                positions=positions,
                global_health=global_health,
                total_positions=len(positions),
                total_collateral_usd=total_collateral_usd,
                total_debt_usd=total_debt_usd,
                net_value_usd=total_collateral_usd - total_debt_usd,
                timestamp=datetime.utcnow().isoformat() + "Z"
            )

            return response

        except Exception as e:
            logger.error(f"Error getting hedge position for {wallet_address}: {e}")
            # Return empty position on error
            return HedgePositionResponse(
                wallet=wallet_address,
                positions=[],
                global_health=GlobalHealthMetrics(
                    total_collateral_usd=Decimal(0),
                    total_debt_weth=Decimal(0),
                    total_debt_btc=Decimal(0),
                    health_factor=Decimal(0),
                    available_borrows_usd=Decimal(0),
                    is_at_risk=False
                ),
                total_positions=0,
                total_collateral_usd=Decimal(0),
                total_debt_usd=Decimal(0),
                net_value_usd=Decimal(0),
                timestamp=datetime.utcnow().isoformat() + "Z"
            )

    async def get_hedge_position_by_token_id(self, token_id: int) -> HedgePositionResponse:
        """
        Get hedge position for a specific token ID using LiquidityManager.

        Args:
            token_id: NFT token ID

        Returns:
            Complete hedge position response for single position
        """
        try:
            # Get asset prices
            prices = await self.get_asset_prices()

            # Get global health metrics
            global_metrics = vault_contract.get_global_health_metrics()
            is_at_risk, current_hf, min_safe_hf = vault_contract.is_protocol_at_risk()

            # Get hedge info for this specific position
            hedge_info = vault_contract.get_position_hedge_info(token_id)

            # Get asset symbol
            asset_symbol = vault_contract.get_token_symbol(hedge_info['hedged_asset'])

            # Calculate debt in USD (need to determine decimals based on asset)
            if asset_symbol == "WETH":
                debt_amount = hedge_info['debt'] / 1e18
                debt_usd = debt_amount * prices.get("WETH", 4000)
            elif asset_symbol == "cbBTC":
                debt_amount = hedge_info['debt'] / 1e8
                debt_usd = debt_amount * prices.get("cbBTC", 100000)
            else:
                debt_amount = hedge_info['debt'] / 1e18  # Default to 18 decimals
                debt_usd = 0

            collateral_usdc = Decimal(str(hedge_info['collateral']))

            position_info = VaultPositionInfo(
                token_id=token_id,
                collateral_usdc=collateral_usdc,
                debt_amount=Decimal(str(debt_amount)),
                debt_usd=Decimal(str(debt_usd)),
                hedged_asset=hedge_info['hedged_asset'],
                hedged_asset_symbol=asset_symbol,
                is_hedged=hedge_info['is_hedged'],
                exposure_usd=None,
                net_delta_usd=None
            )

            # Build global health metrics response
            global_health = GlobalHealthMetrics(
                total_collateral_usd=Decimal(str(global_metrics['total_collateral'])),
                total_debt_weth=Decimal(str(global_metrics['total_debt_weth'])),
                total_debt_btc=Decimal(str(global_metrics['total_debt_btc'])),
                health_factor=Decimal(str(global_metrics['health_factor'])),
                available_borrows_usd=Decimal(str(global_metrics['available_borrows_usd'])),
                is_at_risk=is_at_risk
            )

            # Build response
            response = HedgePositionResponse(
                wallet=f"token_{token_id}",  # Use token_id as identifier
                positions=[position_info],
                global_health=global_health,
                total_positions=1,
                total_collateral_usd=collateral_usdc,
                total_debt_usd=Decimal(str(debt_usd)),
                net_value_usd=collateral_usdc - Decimal(str(debt_usd)),
                timestamp=datetime.utcnow().isoformat() + "Z"
            )

            return response

        except Exception as e:
            logger.error(f"Error getting hedge position for token {token_id}: {e}")
            # Return empty position on error
            return HedgePositionResponse(
                wallet=f"token_{token_id}",
                positions=[],
                global_health=GlobalHealthMetrics(
                    total_collateral_usd=Decimal(0),
                    total_debt_weth=Decimal(0),
                    total_debt_btc=Decimal(0),
                    health_factor=Decimal(0),
                    available_borrows_usd=Decimal(0),
                    is_at_risk=False
                ),
                total_positions=0,
                total_collateral_usd=Decimal(0),
                total_debt_usd=Decimal(0),
                net_value_usd=Decimal(0),
                timestamp=datetime.utcnow().isoformat() + "Z"
            )


# Singleton instance
hedge_service = HedgeService()