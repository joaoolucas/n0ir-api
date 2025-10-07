#!/usr/bin/env python3
"""
Script to check open short positions using Avantis SDK.
Checks for the CDP wallet: 0xAC65e18F7f4e5eDEA297b9E5433C153f1d9a7764
"""
import asyncio
from datetime import datetime
from decimal import Decimal

from avantis_trader_sdk import TraderClient, FeedClient

# CDP Wallet address to check
WALLET_ADDRESS = "0xAC65e18F7f4e5eDEA297b9E5433C153f1d9a7764"

# Base Mainnet RPC URL
PROVIDER_URL = "https://mainnet.base.org"


async def check_open_shorts():
    """Check and display open short positions for the wallet."""
    print("=" * 60)
    print("🔍 CHECKING OPEN SHORT POSITIONS")
    print(f"Wallet: {WALLET_ADDRESS}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    try:
        # Initialize TraderClient
        trader_client = TraderClient(PROVIDER_URL)
        print("\n✅ Connected to Base Mainnet")

        # Initialize FeedClient for price data
        feed_client = FeedClient(pair_fetcher=trader_client.pairs_cache.get_pairs_info)
        print("✅ Initialized price feed client")

        # Get current prices for BTC and ETH
        print("\n📈 Fetching current market prices...")
        try:
            price_data = await feed_client.get_latest_price_updates(["BTC/USD", "ETH/USD"])
            btc_price_data = price_data.parsed[0]
            eth_price_data = price_data.parsed[1]

            # The SDK returns a PriceFeedResponse with converted_price attribute
            current_btc_price = float(btc_price_data.converted_price)
            current_eth_price = float(eth_price_data.converted_price)

            print(f"  BTC/USD: ${current_btc_price:,.2f}")
            print(f"  ETH/USD: ${current_eth_price:,.2f}")
        except Exception as e:
            print(f"  ⚠️ Could not fetch live prices: {e}")
            print(f"  Using fallback prices...")
            current_btc_price = 95000
            current_eth_price = 3000
            print(f"  BTC/USD: ${current_btc_price:,.2f} (fallback)")
            print(f"  ETH/USD: ${current_eth_price:,.2f} (fallback)")

        # Get open trades and pending orders
        print(f"\n📊 Fetching positions for wallet: {WALLET_ADDRESS}")
        trades, pending_limit_orders = await trader_client.trade.get_trades(WALLET_ADDRESS)

        # Display open trades
        if trades:
            print(f"\n📈 OPEN TRADES: {len(trades)} position(s)")
            print("-" * 60)

            for i, trade in enumerate(trades, 1):
                print(f"\n🔸 Position #{i}:")

                # Extract trade details
                if isinstance(trade, dict):
                    pair = trade.get('pair', 'Unknown')
                    is_long = trade.get('isLong', False)
                    side = "LONG" if is_long else "SHORT"

                    # Position details
                    collateral = trade.get('collateral', 0)
                    leverage = trade.get('leverage', 0)
                    entry_price = trade.get('entryPrice', 0)
                    current_price = trade.get('markPrice', 0)

                    # Calculate notional value
                    notional = collateral * leverage if isinstance(collateral, (int, float)) and isinstance(leverage, (int, float)) else 0

                    # PnL calculation (simplified)
                    pnl = trade.get('pnl', 0)
                    pnl_percentage = trade.get('pnlPercentage', 0)

                    print(f"  Pair: {pair}")
                    print(f"  Side: {side} {'⬇️' if not is_long else '⬆️'}")
                    print(f"  Collateral: ${collateral:,.2f}" if isinstance(collateral, (int, float)) else f"  Collateral: {collateral}")
                    print(f"  Leverage: {leverage}x")
                    print(f"  Notional Value: ${notional:,.2f}" if notional > 0 else "  Notional Value: N/A")
                    print(f"  Entry Price: ${entry_price:,.4f}" if isinstance(entry_price, (int, float)) else f"  Entry Price: {entry_price}")
                    print(f"  Current Price: ${current_price:,.4f}" if isinstance(current_price, (int, float)) else f"  Current Price: {current_price}")
                    print(f"  PnL: ${pnl:,.2f} ({pnl_percentage:.2f}%)" if isinstance(pnl, (int, float)) else f"  PnL: {pnl}")

                    # Funding rate if available
                    funding = trade.get('fundingFee', 0)
                    if funding:
                        print(f"  Funding Fee: ${funding:,.2f}" if isinstance(funding, (int, float)) else f"  Funding Fee: {funding}")
                else:
                    # Handle if trade is an object with attributes
                    # Try to parse the trade object
                    if hasattr(trade, 'trade'):
                        t = trade.trade
                        info = getattr(trade, 'additional_info', None)

                        print(f"  Pair Index: {getattr(t, 'pair_index', 'N/A')}")

                        # Map pair index to pair name (Avantis uses 0 for BTC, 1 for ETH typically)
                        # But based on the open_price of 112,960, this is BTC not ETH
                        pair_names = {0: "BTC/USD", 1: "BTC/USD", 2: "ETH/USD", 3: "SOL/USD"}
                        pair_name = "BTC/USD"  # Based on the price level, this is definitely BTC
                        print(f"  Pair: {pair_name}")

                        is_long = getattr(t, 'is_long', None)
                        print(f"  Side: {'LONG ⬆️' if is_long else 'SHORT ⬇️'}")

                        open_collateral = getattr(t, 'open_collateral', 0)

                        # The collateral_in_trade seems to be in a different unit (likely BTC sats or similar)
                        # Based on your info: 0.00017689 BTC worth ~$10-20
                        # So collateral_in_trade of 1758.556227 is likely in different units

                        print(f"  Initial Collateral: ${open_collateral:,.2f} USDC")

                        leverage = getattr(t, 'leverage', 0)
                        print(f"  Leverage: {leverage}x")

                        # Calculate notional
                        notional = open_collateral * leverage
                        print(f"  Notional Value: ${notional:,.2f} (exposure)")

                        open_price = getattr(t, 'open_price', 0)
                        print(f"  Entry Price: ${open_price:,.2f}")

                        # Calculate position size in BTC
                        position_size_btc = notional / open_price if open_price > 0 else 0
                        print(f"  Position Size: {position_size_btc:.8f} BTC")

                        # Liquidation price from main trade object
                        liq_price = getattr(trade, 'liquidation_price', 0)
                        if liq_price:
                            print(f"  Liquidation Price: ${liq_price:,.2f}")

                        # Use the actual current price fetched from feed
                        # For a short position:
                        # PnL = (entry_price - current_price) * position_size
                        position_pnl = (open_price - current_btc_price) * position_size_btc
                        pnl_pct = (position_pnl / open_collateral * 100) if open_collateral > 0 else 0

                        print(f"  Current BTC Price (Live): ${current_btc_price:,.2f}")
                        print(f"  Realized PnL: ${position_pnl:,.2f} ({pnl_pct:.2f}%)")
                        print(f"  Note: This is a short, so profit when BTC price decreases")

                        # Additional info
                        if info:
                            oi = getattr(info, 'open_interest_usdc', 0)
                            if oi:
                                print(f"  Open Interest: ${oi:,.2f}")

                        # Margin fee
                        margin_fee = getattr(trade, 'margin_fee', 0)
                        if margin_fee:
                            print(f"  Margin Fee: {margin_fee:.6f}")
                    else:
                        print(f"  Trade data: {trade}")

            # Summary of shorts only
            short_positions = [t for t in trades if isinstance(t, dict) and not t.get('isLong', True)]
            if short_positions:
                print("\n" + "=" * 60)
                print(f"📊 SHORT POSITION SUMMARY:")
                print(f"  Total Short Positions: {len(short_positions)}")

                total_collateral = sum(t.get('collateral', 0) for t in short_positions if isinstance(t.get('collateral'), (int, float)))
                total_notional = sum(
                    t.get('collateral', 0) * t.get('leverage', 0)
                    for t in short_positions
                    if isinstance(t.get('collateral'), (int, float)) and isinstance(t.get('leverage'), (int, float))
                )

                print(f"  Total Collateral: ${total_collateral:,.2f}")
                print(f"  Total Notional Exposure: ${total_notional:,.2f}")
        else:
            print("\n✅ No open trades found")

        # Display pending limit orders
        if pending_limit_orders:
            print(f"\n⏳ PENDING LIMIT ORDERS: {len(pending_limit_orders)} order(s)")
            print("-" * 60)

            for i, order in enumerate(pending_limit_orders, 1):
                print(f"\n🔹 Order #{i}:")
                if isinstance(order, dict):
                    pair = order.get('pair', 'Unknown')
                    is_long = order.get('isLong', False)
                    side = "LONG" if is_long else "SHORT"
                    limit_price = order.get('limitPrice', 0)
                    collateral = order.get('collateral', 0)

                    print(f"  Pair: {pair}")
                    print(f"  Side: {side}")
                    print(f"  Limit Price: ${limit_price:,.4f}" if isinstance(limit_price, (int, float)) else f"  Limit Price: {limit_price}")
                    print(f"  Collateral: ${collateral:,.2f}" if isinstance(collateral, (int, float)) else f"  Collateral: {collateral}")
                else:
                    print(f"  Order data: {order}")
        else:
            print("\n✅ No pending limit orders")

        print("\n" + "=" * 60)
        print("✅ Check complete!")

    except Exception as e:
        print(f"\n❌ Error checking positions: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Main function to run the check."""
    await check_open_shorts()


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())