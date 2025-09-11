# N0ir Strategy Module - Quantitative Analysis

## Core Components

### 1. Quantitative Scoring Model
**Location**: `app/core/strategy_calculator.py:55-96`

The strategy uses a **multi-factor composite scoring model**:

```
Score = w₁·F + w₂·V + w₃·L + w₄·C + w₅·E
```

**Factor Weights:**
- **Fee Efficiency (F)**: 30% - APR vs fee tier optimization
- **Volume Consistency (V)**: 25% - Volume/TVL ratio analysis  
- **Liquidity Depth (L)**: 20% - TVL-based liquidity scoring
- **Correlation Benefit (C)**: 15% - Portfolio diversification
- **Execution Quality (E)**: 10% - Tick spacing & slippage

### 2. Risk-Adjusted Position Sizing

**Risk Profiles** (`strategy_calculator.py:31-53`):
- **Conservative**: Max 10% per position, min $1M TVL
- **Balanced**: Max 20% per position, min $500K TVL  
- **Aggressive**: Max 30% per position, min $250K TVL

**Dynamic Allocation** (`strategy_orchestrator.py:289-297`):
- < $250: 95% in single position
- $250-500: 45% per position (2 positions)
- $500-1000: 30% per position (3 positions)
- > $1000: Square root rule, max 10 positions

### 3. Rebalancing Thresholds (UPDATED)

**Entry Criteria for Existing Portfolios** (`rebalancing_config.py:149-170`):
- **Confidence**: ≥ 75%
- **APR Uplift**: ≥ 35% 
- **Net Benefit**: ≥ max($20, 10 bps of NAV)
- **Position Size**: ≥ $50-$100 (5% of NAV, capped)

**NAV-Based Decision Logic**:
```python
min_benefit = max(20.0, nav * 0.001)  # 10 basis points
min_position = max(50.0, min(100.0, nav * 0.05))  # 5% of NAV
```

### 4. Exit Signal Generation

**Exit Triggers** (`strategy_orchestrator.py:416-421`):
- **Critical**: Out-of-range positions
- **High**: Significant underperformance
- **Rebalance**: Performance-based optimization

### 5. APR Scoring Function

**Non-linear APR mapping** (`strategy_calculator.py:103-114`):
- 50% APR → Score 40
- 100% APR → Score 60
- 200% APR → Score 80
- 500%+ APR → Score 100

### 6. Liquidity Depth Scoring

**TVL-based tiering** (`strategy_calculator.py:137-150`):
- < $100K: Linear scaling 0-30
- $100K-500K: Score 30-50
- $500K-1M: Score 50-65
- $1M-2M: Score 65-80
- > $10M: Score 100

### 7. Portfolio Risk Management

**Risk Alerts** (`strategy_orchestrator.py:502-548`):
- Concentration risk: >95% capital deployed
- Portfolio health: Multiple urgent exits
- Over-diversification: >15 positions
- Capital fragmentation: Insufficient for diversification

### 8. Execution Timing

**Agent Manager Integration** (`executor/src/strategy/manager.py`):
- Minimum holding period: 10 minutes
- Position switch cooldown tracking
- Cache TTL: 30 seconds for monitor responses

## Quantitative Edge

1. **Multi-factor optimization** prevents single-metric bias
2. **Dynamic position sizing** adapts to capital constraints
3. **Gas-aware thresholds** ensure profitability on L2
4. **Non-linear scoring** captures diminishing returns
5. **Risk-adjusted rebalancing** minimizes unnecessary churn
6. **NAV-based benefit requirements** ensure meaningful portfolio improvements

## User Flow Examples

### Example 1: New User with $500 Capital

**Request:**
```python
POST /api/v1/strategy/comprehensive-screen
{
  "executor_address": "0xuser123...",
  "available_capital": 500.0
}
```

**Strategy Process:**
1. **Pool Discovery**: Fetches whitelisted pools (WETH/USDC, cbBTC/USDC)
2. **Scoring**: Each pool scored on 5 factors:
   - WETH/USDC: APR 150% → Fee score: 70, Volume/TVL: 0.3 → Score: 55
   - cbBTC/USDC: APR 200% → Fee score: 80, Volume/TVL: 0.2 → Score: 45
3. **Position Sizing**: With $500, allocates 45% per position ($225 each)
4. **Entry Analysis**: Parallel checks for both pools
5. **Decision Matrix**: 
   ```json
   {
     "immediate_actions": [
       {
         "type": "entry",
         "pool": "0xb2cc224c...",  // WETH/USDC
         "allocation": 225,
         "confidence": 78,
         "expected_apr": 150
       },
       {
         "type": "entry", 
         "pool": "0x4e962bb3...",  // cbBTC/USDC
         "allocation": 225,
         "confidence": 76,
         "expected_apr": 200
       }
     ]
   }
   ```

### Example 2: Existing User with Out-of-Range Position

**Current State:**
- 3 active positions worth $2,000
- Position #42 in WETH/USDC out of range
- $100 available capital

**Strategy Response:**
```python
{
  "exit_recommendations": [{
    "token_id": 42,
    "urgency": "critical",
    "reason": "range_break",
    "expected_proceeds": 650,
    "slippage_estimate": 0.5
  }],
  "entry_analyses": [],  // No entries due to low capital
  "risk_alerts": [{
    "type": "portfolio_health",
    "message": "Position #42 requires urgent rebalancing",
    "severity": "high"
  }]
}
```

### Example 3: Portfolio Rebalancing Trigger

**Scenario:** User has $5,000 across 5 positions, one underperforming

**Switch Analysis:**
```python
{
  "switch_recommendations": [{
    "from_token_id": 127,
    "from_pool": "Low APR Pool (50%)",
    "to_pool_address": "0xb2cc224c...",
    "to_pool_name": "WETH/USDC",
    "apr_improvement": 100,  // 50% → 150%
    "net_benefit_after_costs": 750,  // After gas costs
    "confidence": 82
  }]
}
```

**Decision Logic:**
- APR improvement (100%) > threshold (35%) ✓
- Net benefit ($750) > minimum ($500) ✓
- Confidence (82%) > minimum (70%) ✓
- **Action**: Schedule switch for next cycle

### Example 4: Small Balance Optimization

**Request:** $50 available capital (no existing positions)

**Strategy Adaptation:**
```python
{
  "capital_allocation": {
    "recommended_positions": 1,  // Single position for gas efficiency
    "allocation_per_position": 47.5  // 95% of capital
  },
  "opportunities": [{
    "pool_address": "0xb2cc224c...",
    "recommended_allocation": 47.5,
    "safety_score": 85,
    "warnings": ["Gas costs ~1% of position size"]
  }]
}
```

### Example 5: Edge Case - $25 Free Capital with Existing Position (UPDATED)

**Current State:**
- 1 active position worth $275
- $25 available capital  
- NAV: $300 (positions + available)

**NEW Strategy Behavior with NAV-based Rules:**

1. **Position Sizing Logic** (`strategy_orchestrator.py:290-291`):
   - Since available_capital ($25) < $250
   - Proposed allocation = $25 * 0.95 = $23.75

2. **NAV-Based Entry Criteria** (`rebalancing_config.py:149-170`):
   - Has existing positions: YES ✓
   - Min position size = max($50, min($100, $300 * 0.05)) = $50
   - **FAILS**: $23.75 < $50 minimum for portfolio addition
   
3. **Benefit Analysis (if it had $50+)**:
   - Min benefit = max($20, $300 * 0.001) = $20
   - With 150% APR on $50: 30-day benefit = $50 * 1.5 * (30/365) = $6.16
   - **WOULD FAIL**: $6.16 < $20 minimum benefit

4. **Actual Response:**
```python
{
  "opportunities": [],  // No opportunities due to insufficient capital
  "decision_matrix": {
    "immediate_actions": [],  // No new entries recommended
    "capital_allocation": {
      "recommended_positions": 1,
      "allocation_per_position": 50,  // Minimum for portfolio addition
      "active_positions": 1
    }
  },
  "risk_alerts": [{
    "type": "capital_fragmentation",
    "message": "Available capital too small for optimal portfolio addition (need $50+)",
    "severity": "low"
  }]
}
```

**Key Points:**
- **NEW RULE**: With existing positions, minimum new position = $50-$100
- **NAV BENEFIT**: Must generate max($20, 10bps of NAV) in 30-day benefit
- **APR THRESHOLD**: Must exceed 35% APR for portfolio additions
- **RESULT**: User should wait until they have at least $50 available
- **RECOMMENDATION**: System suggests waiting to accumulate more capital

### Example 6: Risk Alert Generation

**Portfolio State:**
- 18 active positions
- $10,000 total value
- $9,800 deployed (98%)

**Risk Alerts:**
```python
{
  "risk_alerts": [
    {
      "type": "concentration",
      "message": "Over 95% of capital is deployed",
      "severity": "medium"
    },
    {
      "type": "over_diversification", 
      "message": "Portfolio has too many positions, consider consolidation",
      "severity": "medium"
    }
  ]
}
```

## Performance Metrics

- Decision latency: <100ms (parallel analysis)
- Cache efficiency: 5-10 second TTLs
- Position limit: 10 concurrent (optimal diversification)
- Rebalance frequency: Controlled by 35% APR threshold
- NAV-based benefit: 10 bps minimum for portfolio additions