# Executor Migration Guide: Portfolio Endpoint Removal

## Overview
The portfolio endpoint has been removed and its functionality has been integrated into the `analyze` endpoint with `action: "switch"`. This consolidation reduces redundancy and simplifies the API.

## Changes Made

### 1. Enhanced Analyze Endpoint
The `/strategy/analyze` endpoint with `action: "switch"` now returns a comprehensive portfolio summary along with switch recommendations.

### 2. New Response Structure

#### Previous (Separate Portfolio Endpoint)
```json
GET /portfolio/{wallet}/summary
Response: {
  "total_value": 1000,
  "positions": [...],
  "metrics": {...}
}
```

#### New (Integrated into Analyze)
```json
POST /strategy/analyze
{
  "action": "switch",
  "switch_data": {
    "user_address": "0x...",
    "token_ids": [1, 2, 3]
  }
}

Response: {
  "action": "switch",
  "switch_response": {
    "portfolio_summary": {
      "total_value_usd": 1000,
      "total_positions": 3,
      "total_pnl_usd": 100,
      "total_pnl_percentage": 10,
      "weighted_apr": 75.5,
      "total_emissions_value_usd": 50,
      "risk_score": 45,
      "concentration_risk": {
        "WETH": 35.5,
        "USDC": 30.2,
        "AERO": 34.3
      },
      "top_performers": [...],
      "underperformers": [...]
    },
    "recommendations": [...],
    "total_positions_analyzed": 3,
    "positions_recommended_for_switch": 2,
    "total_expected_apr_improvement": 25.5,
    "estimated_total_gas_cost": 200
  }
}
```

## Migration Steps for Executor

### 1. Update API Calls
Replace any calls to portfolio endpoints with the analyze endpoint:

```python
# OLD
response = await http_client.get(f"/portfolio/{wallet}/summary")

# NEW
response = await http_client.post("/strategy/analyze", json={
    "action": "switch",
    "switch_data": {
        "user_address": wallet,
        "token_ids": position_ids  # Get from positions endpoint if needed
    }
})
portfolio_data = response.json()["switch_response"]["portfolio_summary"]
```

### 2. Get All User Positions
If you need all positions for a wallet without specific token_ids:

```python
# First, get all positions
positions = await http_client.get(f"/positions/owner/{wallet}")
token_ids = [p["id"] for p in positions]

# Then analyze with portfolio summary
response = await http_client.post("/strategy/analyze", json={
    "action": "switch",
    "switch_data": {
        "user_address": wallet,
        "token_ids": token_ids
    }
})
```

### 3. Access Portfolio Metrics
The portfolio summary now includes:
- `total_value_usd`: Total portfolio value
- `total_pnl_usd` & `total_pnl_percentage`: Profit/Loss metrics
- `weighted_apr`: Portfolio-weighted average APR
- `risk_score`: Overall risk assessment (0-100)
- `concentration_risk`: Token exposure percentages
- `top_performers` & `underperformers`: Best and worst positions

### 4. Handle Switch Recommendations
The same response includes switch recommendations, so you get both portfolio overview AND actionable insights in one call:

```python
portfolio_summary = response["switch_response"]["portfolio_summary"]
switch_recommendations = response["switch_response"]["recommendations"]

# Display portfolio metrics
print(f"Portfolio Value: ${portfolio_summary['total_value_usd']}")
print(f"Risk Score: {portfolio_summary['risk_score']}")

# Process switch recommendations
for rec in switch_recommendations:
    if rec["should_switch"]:
        print(f"Switch position {rec['token_id']} to {rec['target_pool_symbol']}")
```

## Benefits of This Change

1. **Single API Call**: Get portfolio overview + recommendations in one request
2. **Reduced Latency**: No need for multiple sequential calls
3. **Consistent Data**: Portfolio metrics and recommendations use the same data snapshot
4. **Simplified Codebase**: Less endpoints to maintain and document

## Backwards Compatibility

There is no backwards compatibility - the portfolio endpoints have been completely removed. All integrations must migrate to use the analyze endpoint.

## Support

For questions or issues during migration, please refer to the updated API documentation or contact the development team.