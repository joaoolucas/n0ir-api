# Fix Summary: Out-of-Range Position Recommendations

## Problem
Out-of-range positions were showing `recommended_action: "hold"` when they should recommend exiting the position and finding new opportunities through the screening endpoint.

## Solution Implemented

### 1. Updated Position Recommendation Logic (strategy_service.py:795-828)
- Changed out-of-range positions to recommend `"exit"` instead of `"hold"`
- Added `next_step` guidance pointing users to `/api/v1/strategy/screen` endpoint
- Applied to three scenarios:
  - Unstaked positions
  - Out-of-range positions  
  - Severe range breaks (>85% severity)

### 2. Updated Range Break Handler (strategy_service.py:1010-1015)
- Changed severe downward breaks to recommend `"exit"` instead of `"rebalance"`
- Consistent with the position monitoring logic

### 3. Updated Portfolio Analyzer (portfolio_analyzer.py:457)
- Changed underperforming position recommendations from `"close"` to `"exit"`
- Ensures consistency across all recommendation sources

## Key Changes

**Before:**
- Out-of-range: `recommended_action: "hold"`
- Conflicting recommendations between position and range_breaks

**After:**
- Out-of-range: `recommended_action: "exit"`
- Includes `next_step: "Use /api/v1/strategy/screen endpoint to find better opportunities"`
- Consistent recommendations across all analysis components

## Testing
The fix should now properly return:
```json
{
  "recommended_action": "exit",
  "action_details": {
    "urgency": "high",
    "reason": "Position is out of range - exit and find new opportunities",
    "next_step": "Use /api/v1/strategy/screen endpoint to find better opportunities"
  }
}
```

For out-of-range positions instead of `"hold"`.