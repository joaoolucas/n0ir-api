"""Service for managing perpetual futures (perps) positions."""

from typing import List, Dict, Any, Optional
from avantis_trader_sdk import TraderClient, FeedClient
from app.core.logger import logger
from app.schemas.perps import PerpsPosition, PerpsPositionListResponse


class PerpsService:
    """Service for fetching and analyzing perpetual positions."""

    def __init__(self):
        """Initialize the Perps service."""
        self.provider_url = "https://mainnet.base.org"
        self.trader_client = None
        self.feed_client = None

    async def _ensure_clients(self):
        """Ensure trader and feed clients are initialized."""
        if not self.trader_client:
            self.trader_client = TraderClient(self.provider_url)
            self.feed_client = FeedClient(pair_fetcher=self.trader_client.pairs_cache.get_pairs_info)
            logger.info("Initialized Avantis SDK clients")

    async def get_current_prices(self, pairs: List[str]) -> Dict[str, float]:
        """Get current prices for given pairs."""
        try:
            price_data = await self.feed_client.get_latest_price_updates(pairs)
            prices = {}
            for i, pair in enumerate(pairs):
                if i < len(price_data.parsed):
                    prices[pair] = float(price_data.parsed[i].converted_price)
                else:
                    logger.warning(f"No price data for {pair}")
            return prices
        except Exception as e:
            logger.error(f"Error fetching prices: {e}")
            return {}

    async def get_positions_by_wallet(self, wallet_address: str) -> PerpsPositionListResponse:
        """
        Get all perpetual positions for a given wallet address.

        Args:
            wallet_address: The wallet address to query

        Returns:
            PerpsPositionListResponse with all positions and statistics
        """
        await self._ensure_clients()

        try:
            # Fetch trades from Avantis
            logger.info(f"Fetching perps positions for wallet: {wallet_address}")
            trades, pending_orders = await self.trader_client.trade.get_trades(wallet_address)

            if not trades:
                logger.info(f"No open positions found for wallet: {wallet_address}")
                return PerpsPositionListResponse(
                    wallet_address=wallet_address,
                    positions=[],
                    total_positions=0,
                    total_collateral_usdc=0.0,
                    total_notional_usdc=0.0,
                    total_pnl_usdc=0.0,
                    short_positions_count=0,
                    long_positions_count=0
                )

            # Get current prices for all unique pairs
            pair_mapping = {
                0: "BTC/USD",
                1: "BTC/USD",  # Based on the price level in our data
                2: "ETH/USD",
                3: "SOL/USD",
                4: "ARB/USD",
                5: "AVAX/USD",
                6: "MATIC/USD"
            }

            unique_pairs = set()
            for trade in trades:
                if hasattr(trade, 'trade'):
                    pair_index = getattr(trade.trade, 'pair_index', 1)
                    pair = pair_mapping.get(pair_index, "BTC/USD")
                    unique_pairs.add(pair)

            # Fetch current prices
            current_prices = await self.get_current_prices(list(unique_pairs))

            # Parse positions
            positions = []
            total_collateral = 0.0
            total_notional = 0.0
            total_pnl = 0.0
            short_count = 0
            long_count = 0

            for trade in trades:
                if hasattr(trade, 'trade'):
                    t = trade.trade
                    info = getattr(trade, 'additional_info', None)

                    # Extract trade data
                    pair_index = getattr(t, 'pair_index', 1)
                    pair = pair_mapping.get(pair_index, "BTC/USD")
                    is_long = getattr(t, 'is_long', False)
                    collateral = float(getattr(t, 'open_collateral', 0))
                    leverage = float(getattr(t, 'leverage', 0))
                    entry_price = float(getattr(t, 'open_price', 0))

                    # Get current price
                    current_price = current_prices.get(pair, entry_price)

                    # Calculate position details
                    notional = collateral * leverage
                    position_size = notional / entry_price if entry_price > 0 else 0

                    # Calculate P&L
                    if is_long:
                        pnl = (current_price - entry_price) * position_size
                        long_count += 1
                    else:
                        pnl = (entry_price - current_price) * position_size
                        short_count += 1

                    pnl_pct = (pnl / collateral * 100) if collateral > 0 else 0

                    # Get additional fields
                    liquidation_price = float(getattr(trade, 'liquidation_price', 0))
                    margin_fee = float(getattr(trade, 'margin_fee', 0))
                    tp = float(getattr(t, 'tp', 0))
                    sl = float(getattr(t, 'sl', 0))
                    timestamp = int(getattr(t, 'timestamp', 0))

                    # Open interest from additional info
                    open_interest = None
                    if info:
                        open_interest = float(getattr(info, 'open_interest_usdc', 0))

                    # Create position object
                    position = PerpsPosition(
                        pair=pair,
                        pair_index=pair_index,
                        is_long=is_long,
                        collateral_usdc=collateral,
                        leverage=leverage,
                        notional_value_usdc=notional,
                        position_size=position_size,
                        entry_price=entry_price,
                        current_price=current_price,
                        liquidation_price=liquidation_price,
                        pnl_usdc=pnl,
                        pnl_percentage=pnl_pct,
                        take_profit=tp if tp > 0 else None,
                        stop_loss=sl if sl > 0 else None,
                        margin_fee=margin_fee if margin_fee > 0 else None,
                        open_interest_usdc=open_interest,
                        timestamp=timestamp if timestamp > 0 else None
                    )

                    positions.append(position)

                    # Update totals
                    total_collateral += collateral
                    total_notional += notional
                    total_pnl += pnl

            logger.info(f"Found {len(positions)} positions for wallet {wallet_address}")

            return PerpsPositionListResponse(
                wallet_address=wallet_address,
                positions=positions,
                total_positions=len(positions),
                total_collateral_usdc=total_collateral,
                total_notional_usdc=total_notional,
                total_pnl_usdc=total_pnl,
                short_positions_count=short_count,
                long_positions_count=long_count
            )

        except Exception as e:
            logger.error(f"Error fetching perps positions for {wallet_address}: {e}", exc_info=True)
            raise ValueError(f"Failed to fetch positions: {str(e)}")


# Singleton instance
perps_service = PerpsService()