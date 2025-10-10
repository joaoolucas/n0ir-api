# Moonwell Strategy Endpoint

## Summary
The strategy endpoint has been reimplemented with Moonwell-based hedging, replacing the previous perps-based approach.

## Current Endpoint

### `POST /api/v1/users/{user_id}/strategy`
Generates a Moonwell-based delta-neutral strategy with the following structure:

**Request:** No body required (user_id in path)

**Response Format:**
```json
{
  "user_id": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb7",
  "strategy_type": "delta_neutral",
  "timestamp": "2025-01-25T12:00:00Z",
  "action": "open",

  "capital": {
    "total_usd": 1000,
    "base_asset": "USDC"
  },

  "allocations": {
    "moonwell": {
      "protocol": "moonwell",
      "collateral": {
        "market": "mUSDC",
        "amount_usdc": 1000
      },
      "borrow": {
        "market": "mWETH",
        "amount_weth": 0.1125,
        "amount_usd": 450,
        "post_borrow_action": "swap_to_usdc"
      }
    },
    "aerodrome_lp": {
      "protocol": "aerodrome",
      "pool": "WETH-USDC",
      "amount_usdc": 447.75,
      "range_percentage": 5
    }
  },

  "monitoring": {
    "range_break": {
      "trigger": "price_outside_tick_bounds",
      "suggested_action": "close_and_rebalance"
    }
  }
}
```

## Strategy Flow

1. **Collateral**: User deposits 100% of capital as USDC collateral in Moonwell
2. **Borrow**: Borrow WETH at 45% LTV (safe ratio)
3. **Swap**: Convert borrowed WETH to USDC
4. **LP**: Deploy USDC to Aerodrome LP pool
5. **Monitor**: Check for range breaks in existing positions

## Files Added

### New Services:
1. `app/core/moonwell_service.py` - Moonwell calculations and risk management
2. `app/core/moonwell_strategy_service.py` - Strategy generation service

### Updated Files:
1. `app/schemas/users.py` - Added Moonwell strategy schemas
2. `app/api/v1/endpoints/core.py` - Added strategy endpoint

## Risk Parameters

- **Target LTV**: 45% (conservative)
- **Max LTV**: 75% (Moonwell's limit)
- **Health Factor Target**: >1.5
- **LP Range**: 5% around current price

## Non-Custodial Design

The strategy is non-custodial:
- User's wallet manages Moonwell position directly
- Agent only manages Aerodrome LP
- Clear separation of concerns

## Previous Implementation (Removed)

The previous implementation using perpetual futures (perps) has been completely removed:
- Removed all perps-related services and schemas
- Removed Avantis integration
- Removed GPT strategy service
- Clean removal with no backward compatibility