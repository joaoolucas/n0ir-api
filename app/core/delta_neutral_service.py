"""
Delta-Neutral Strategy Service.
Coordinates LP positions with hedging for market-neutral returns.
"""
from typing import Dict, List, Optional, Any
from decimal import Decimal
from loguru import logger

from app.core.gpt_strategy_service import gpt_strategy_service
from app.core.blockchain_service import blockchain_service
from app.core.positions_service import positions_service
from app.core.pools_service import pools_service
from app.schemas.users import (
    DeltaNeutralStrategyResponse,
    LPAllocation,
    Hedge
)
from app.database.session import get_db
from app.database.models import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


# Whitelisted pools
WHITELISTED_POOLS = {
    "WETH/USDC": "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59",
    "cbBTC/USDC": "0x4e962bb3889bf030368f56810a9c96b83cb3e778",
}


class DeltaNeutralService:
    """Service for managing delta-neutral strategies."""

    def __init__(self):
        """Initialize service dependencies."""
        self.gpt_service = gpt_strategy_service
        self.blockchain = blockchain_service
        self.positions = positions_service
        self.pools = pools_service

    async def analyze_user_portfolio(
        self,
        user_id: str,
        db: AsyncSession
    ) -> DeltaNeutralStrategyResponse:
        """
        Analyze user portfolio and generate delta-neutral strategy.

        Args:
            user_id: User identifier
            db: Database session

        Returns:
            Delta-neutral strategy recommendations
        """
        try:
            # Get user and CDP wallet
            user_data = await self._get_user_and_wallet(user_id, db)
            if not user_data:
                raise ValueError(f"User {user_id} not found")

            wallet_address = user_data['cdp_wallet']
            if not wallet_address:
                raise ValueError(f"User {user_id} has no CDP wallet configured")

            # Fetch balance and positions in parallel
            balance, positions = await self._fetch_portfolio_data(wallet_address)

            # Get pool data for decision making
            pool_data = await self._fetch_pool_data()

            # Check if we have positions out of range
            out_of_range_positions = self._check_out_of_range_positions(positions)

            if out_of_range_positions:
                # Handle range break scenario
                return await self._handle_range_break(
                    out_of_range_positions[0],  # Handle first out of range position
                    balance,
                    pool_data,
                    positions,
                    out_of_range_positions
                )
            elif positions:
                # Have positions but all are in range - return maintain action
                return self._build_maintain_response(balance, positions)
            else:
                # No positions - generate initial strategy using GPT
                strategy = self.gpt_service.generate_initial_strategy(
                    balance=balance,
                    existing_positions=[],
                    pool_data=pool_data
                )

                # Convert to response format for initial allocation
                return self._build_initial_strategy_response(strategy, balance)

        except Exception as e:
            logger.error(f"Error analyzing portfolio for user {user_id}: {e}")
            # Return error strategy
            return DeltaNeutralStrategyResponse(
                action="error",
                notes=f"Error generating strategy: {str(e)}",
                total_capital_deployed=Decimal(0),
                remaining_balance=Decimal(balance) if balance else Decimal(0)
            )

    async def _get_user_and_wallet(
        self,
        user_id: str,
        db: AsyncSession
    ) -> Optional[Dict]:
        """Get user and CDP wallet address."""
        result = await db.execute(
            select(User).where(
                (User.user_id == user_id) |
                (User.user_id == user_id.lower())
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            return None

        return {
            'user_id': user.user_id,
            'cdp_wallet': user.cdp_wallet_address
        }

    async def _fetch_portfolio_data(
        self,
        wallet_address: str
    ) -> tuple[float, List[Any]]:
        """Fetch wallet balance and positions."""
        # Get USDC balance
        balance = await self.blockchain.get_usdc_balance(wallet_address)

        # Get active positions
        positions = await self.positions.get_positions_by_owner(wallet_address)

        logger.info(f"Wallet {wallet_address}: Balance ${balance:.2f}, {len(positions)} positions")

        return balance, positions

    async def _fetch_pool_data(self) -> Dict[str, Any]:
        """Fetch pool APRs and market data."""
        pool_data = {}

        # Fetch data for whitelisted pools
        for pool_name, pool_address in WHITELISTED_POOLS.items():
            try:
                pool_info = await self.pools.get_pool(pool_address)
                if pool_info:
                    pool_data[pool_name] = {
                        "address": pool_address,
                        "apr": pool_info.get("apr_7d", 100),  # Default 100% APR
                        "tvl": pool_info.get("tvl_usd", 0),
                        "volume_24h": pool_info.get("volume_24h_usd", 0)
                    }
            except Exception as e:
                logger.warning(f"Could not fetch data for {pool_name}: {e}")
                pool_data[pool_name] = {
                    "address": pool_address,
                    "apr": 100 if "WETH" in pool_name else 80,  # Default APRs
                    "tvl": 1000000,
                    "volume_24h": 500000
                }

        # Add market prices (simplified - would fetch from oracle in production)
        pool_data["eth_price"] = 3500
        pool_data["btc_price"] = 65000
        pool_data["eth_funding"] = -0.02  # Negative funding = shorts earn
        pool_data["btc_funding"] = -0.01

        return pool_data

    def _format_positions(self, positions: List[Any]) -> List[Dict]:
        """Format positions for GPT consumption."""
        formatted = []
        for pos in positions:
            formatted.append({
                "token_id": pos.id if hasattr(pos, 'id') else pos.get('id'),
                "pool_name": getattr(pos, 'pool_name', 'Unknown'),
                "current_value": float(getattr(pos, 'current_value_usd', 0)),
                "in_range": getattr(pos, 'in_range', True),
                "apr": float(getattr(pos, 'current_apr', 0))
            })
        return formatted

    def _check_out_of_range_positions(self, positions: List[Any]) -> List[Any]:
        """Check for positions that are out of range."""
        out_of_range = []
        for pos in positions:
            # Check if position has range status
            if hasattr(pos, 'in_range') and not pos.in_range:
                out_of_range.append(pos)
            elif hasattr(pos, 'range_status') and pos.range_status and not pos.range_status.in_range:
                out_of_range.append(pos)

        return out_of_range

    async def _handle_range_break(
        self,
        position: Any,
        balance: float,
        pool_data: Dict,
        all_positions: List[Any],
        out_of_range_positions: List[Any]
    ) -> DeltaNeutralStrategyResponse:
        """Handle position that's out of range."""

        # Prepare position data for GPT
        position_data = {
            "pool_name": getattr(position, 'pool_name', 'WETH/USDC'),
            "current_value": float(getattr(position, 'current_value_usd', 0)),
            "time_out_of_range": 6,  # Would calculate from events in production
            "apr_in_range": float(getattr(position, 'current_apr', 100))
        }

        # Simplified market data
        market_data = {
            "current_price": pool_data.get("eth_price", 3500),
            "price_change_24h": 2.5,  # Would fetch from price feed
            "volatility": "medium",
            "trend": "bullish"
        }

        # Get GPT recommendation
        action = self.gpt_service.evaluate_range_break(
            position_data=position_data,
            market_data=market_data,
            current_balance=balance
        )

        # Extract position IDs that are out of range
        out_of_range_ids = [getattr(p, 'id', None) for p in out_of_range_positions if hasattr(p, 'id')]

        # Build response based on action type
        lp_allocations = []
        hedges = []
        total_deployed = Decimal(0)

        if action.get("action") == "close_and_reopen" and action.get("new_lp_allocation"):
            lp = action["new_lp_allocation"]
            lp_allocations.append(
                LPAllocation(
                    pair=lp["pair"],
                    amount_usd=Decimal(str(lp["amount_usd"])),
                    range_pct=lp["range_pct"],
                    pool_address=WHITELISTED_POOLS.get(lp["pair"])
                )
            )
            total_deployed += Decimal(str(lp["amount_usd"]))

        if action.get("hedge"):
            hedge = action["hedge"]
            hedges.append(
                Hedge(
                    asset=hedge["asset"],
                    side=hedge["side"],
                    collateral_usd=Decimal(str(hedge["collateral_usd"])),
                    leverage=hedge["leverage"],
                    notional_exposure_usd=Decimal(str(hedge["notional_exposure_usd"]))
                )
            )
            total_deployed += Decimal(str(hedge["collateral_usd"]))

        return DeltaNeutralStrategyResponse(
            action=action.get("action", "wait"),
            notes=action.get("reason", "Range break detected"),
            lp_allocations=lp_allocations,
            hedges=hedges,
            total_capital_deployed=total_deployed,
            remaining_balance=Decimal(balance) - total_deployed,
            current_positions=self._format_positions(all_positions),
            out_of_range_positions=out_of_range_ids,
            position_id=getattr(position, 'id', None),
            reason=action.get("reason")
        )

    def _build_initial_strategy_response(
        self,
        strategy: Dict[str, Any],
        balance: float
    ) -> DeltaNeutralStrategyResponse:
        """Build initial strategy response from GPT output."""

        lp_allocations = []
        total_lp = Decimal(0)

        for lp in strategy.get("lp_allocations", []):
            allocation = LPAllocation(
                pair=lp["pair"],
                amount_usd=Decimal(str(lp["amount_usd"])),
                range_pct=lp.get("range_pct", 5),
                pool_address=WHITELISTED_POOLS.get(lp["pair"])
            )
            lp_allocations.append(allocation)
            total_lp += allocation.amount_usd

        hedges = []
        total_hedge = Decimal(0)

        for hedge in strategy.get("hedges", []):
            h = Hedge(
                asset=hedge["asset"],
                side=hedge.get("side", "short"),
                collateral_usd=Decimal(str(hedge["collateral_usd"])),
                leverage=hedge.get("leverage", 5),
                notional_exposure_usd=Decimal(str(hedge["notional_exposure_usd"]))
            )
            hedges.append(h)
            total_hedge += h.collateral_usd

        total_deployed = total_lp + total_hedge
        remaining = Decimal(str(balance)) - total_deployed

        return DeltaNeutralStrategyResponse(
            action="initial_allocation",
            notes=strategy.get("notes", "Delta-neutral strategy generated"),
            lp_allocations=lp_allocations,
            hedges=hedges,
            total_capital_deployed=total_deployed,
            remaining_balance=max(Decimal(0), remaining),
            current_positions=None
        )

    def _build_maintain_response(
        self,
        balance: float,
        positions: List[Any]
    ) -> DeltaNeutralStrategyResponse:
        """Build response when all positions are in range - maintain current strategy."""

        # Calculate total value in positions
        total_position_value = sum(
            float(getattr(p, 'current_value_usd', 0)) for p in positions
        )

        return DeltaNeutralStrategyResponse(
            action="maintain",
            notes=f"All {len(positions)} positions are in range and performing well. Maintain current strategy.",
            lp_allocations=[],
            hedges=[],
            total_capital_deployed=Decimal(str(total_position_value)),
            remaining_balance=Decimal(str(balance)),
            current_positions=self._format_positions(positions),
            out_of_range_positions=[]
        )



# Singleton instance
delta_neutral_service = DeltaNeutralService()