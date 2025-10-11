# Per-Strategy Capital Allocation Implementation Guide

## Overview

This guide outlines the changes needed to implement per-strategy capital allocation, allowing users to designate specific amounts of capital to each strategy while tracking deployed vs. available capital in real-time.

---

## Problem Statement

Currently, when an agent is activated, all available USDC in the wallet can be used by any strategy. This creates issues:

- No control over capital distribution across strategies
- Risk of one strategy consuming all available capital
- Difficult to rebalance or adjust strategy allocations
- No visibility into how much capital each strategy has deployed

---

## Solution Architecture

### Capital Tracking Flow

1. **User Configuration**: User sets allocated capital per strategy (e.g., s1: $100, s2: $50)
2. **API Enforcement**: Strategy endpoint respects allocation limits when returning recommendations
3. **Agent Execution**: Agent opens positions within allocation constraints
4. **Event Reporting**: Agent reports position lifecycle events (opened/closed) to API
5. **State Updates**: API updates deployed capital tracking in real-time

### Key Principles

- **Allocated Capital**: Maximum amount user wants to deploy to a strategy
- **Deployed Capital**: Currently active capital in open positions
- **Available Capital**: `allocated - deployed` (what can still be deployed)
- **Constraint**: `max_deployable = min(available_capital, wallet_balance)`

---

## Database Schema Changes

### 1. Update `active_strategies` Field

The `active_strategies` JSONB field in the users table needs additional fields:

**Current Structure:**
```
{
  "s1": {
    "status": "active",
    "strategy_type": "stable_eurc_usdc",
    "created_at": "2025-10-11T17:14:26",
    "updated_at": "2025-10-11T17:14:26"
  }
}
```

**New Structure:**
```
{
  "s1": {
    "status": "active",
    "strategy_type": "stable_eurc_usdc",
    "allocated_capital_usd": 100.0,    // NEW: Max capital for this strategy
    "deployed_capital_usd": 0.0,       // NEW: Currently active capital
    "created_at": "2025-10-11T17:14:26",
    "updated_at": "2025-10-11T17:14:26"
  }
}
```

### 2. Migration Considerations

- Set default `allocated_capital_usd` based on existing wallet balance or business rules
- Initialize `deployed_capital_usd` to 0.0 for existing strategies
- Update all existing records during migration

---

## API Endpoint Changes

### 1. Strategy Recommendation Endpoint

**Endpoint**: `POST /api/v1/users/{user_id}/strategy?strategy_type={strategy_code}`

**Current Behavior**: Returns recommendations without considering per-strategy limits

**New Behavior**: Must calculate and enforce capital constraints

**Required Changes**:

1. **Fetch User Configuration**
   - Get user's `active_strategies` with allocation info
   - Verify requested strategy is active and has allocation

2. **Calculate Available Capital**
   - Extract `allocated_capital_usd` and `deployed_capital_usd` for the strategy
   - Compute `available_allocation = allocated - deployed`
   - Fetch actual wallet USDC balance
   - Determine `max_deployable = min(available_allocation, wallet_balance)`

3. **Return Appropriate Action**
   - If `max_deployable <= 0`: Return `action: "no_action"` with reason
   - If `max_deployable > 0`: Return `action: "open"` with constrained amount

4. **Enhanced Response Structure**
   - Add `capital` object with detailed breakdown:
     - `total_usd`: Amount agent can deploy now
     - `allocated_for_strategy`: Total allocation for this strategy
     - `already_deployed`: Capital currently in positions
     - `available_to_deploy`: Remaining allocation (`allocated - deployed`)
     - `wallet_balance`: Actual USDC in wallet
     - `reason`: (optional) Why action is limited/blocked

**Response Examples**:

*When capital is available:*
```
{
  "action": "open",
  "capital": {
    "total_usd": "70.0",
    "allocated_for_strategy": "100.0",
    "already_deployed": "30.0",
    "available_to_deploy": "70.0",
    "wallet_balance": "150.0"
  },
  "contract_params": {
    "usdc_amount": "70.0",
    ...
  }
}
```

*When allocation exhausted:*
```
{
  "action": "no_action",
  "capital": {
    "total_usd": "0.0",
    "allocated_for_strategy": "100.0",
    "already_deployed": "100.0",
    "available_to_deploy": "0.0",
    "wallet_balance": "80.0",
    "reason": "allocation_exhausted"
  }
}
```

*When wallet balance is limiting factor:*
```
{
  "action": "open",
  "capital": {
    "total_usd": "20.0",
    "allocated_for_strategy": "100.0",
    "already_deployed": "0.0",
    "available_to_deploy": "100.0",
    "wallet_balance": "20.0"
  },
  "contract_params": {
    "usdc_amount": "20.0",
    ...
  }
}
```

### 2. New Position Event Tracking Endpoint

**Endpoint**: `POST /api/v1/users/{user_id}/strategies/{strategy_code}/positions/events`

**Purpose**: Receive position lifecycle events from agent to track deployed capital

**Request Body**:
```
{
  "type": "opened" | "closed" | "rebalanced",
  "timestamp": "2025-10-11T17:20:00Z",
  "token_id": 28460398,
  "tx_hash": "0xabc...",

  // For "opened" events:
  "capital_deployed_usd": 50.0,

  // For "closed" events:
  "capital_returned_usd": 52.5,
  "pnl_usd": 2.5,

  // For "rebalanced" events:
  "capital_change_usd": 10.0  // Positive = added, Negative = removed
}
```

**Response**:
```
{
  "success": true,
  "strategy_code": "s1",
  "deployed_capital_usd": 50.0,
  "available_capital_usd": 50.0
}
```

**Required Logic**:

1. **Validate Request**
   - User exists and strategy is active
   - Token ID matches expected format
   - Event type is valid

2. **Update Deployed Capital**
   - `opened`: Increase `deployed_capital_usd` by `capital_deployed_usd`
   - `closed`: Decrease `deployed_capital_usd` by `capital_returned_usd`
   - `rebalanced`: Adjust by `capital_change_usd` (can be positive or negative)

3. **Update Timestamp**
   - Set `updated_at` to current timestamp

4. **Persist Changes**
   - Save updated `active_strategies` to database
   - Consider transaction safety for concurrent updates

5. **Return Updated State**
   - Confirm success and return current deployed/available amounts

**Important Considerations**:

- **Idempotency**: Handle duplicate events (same tx_hash) gracefully
- **Negative Balance Prevention**: Don't allow `deployed_capital_usd < 0`
- **Concurrency**: Use database transactions or optimistic locking
- **Audit Trail**: Consider logging all events for reconciliation

### 3. New Allocation Management Endpoint

**Endpoint**: `POST /api/v1/users/{user_id}/strategies/{strategy_code}/allocation`

**Purpose**: Allow updating allocated capital for a strategy

**Request Body**:
```
{
  "allocated_capital_usd": 150.0
}
```

**Response**:
```
{
  "success": true,
  "strategy_code": "s1",
  "allocated_capital_usd": 150.0,
  "deployed_capital_usd": 30.0,
  "available_capital_usd": 120.0
}
```

**Required Logic**:

1. **Validation**
   - Strategy exists and is active for user
   - New allocation is positive
   - **Critical**: New allocation >= currently deployed capital
     - Prevent reducing allocation below deployed amount
     - Return error if violated: "Cannot set allocation to $X when $Y is already deployed"

2. **Update Allocation**
   - Set `allocated_capital_usd` to new value
   - Update `updated_at` timestamp
   - Persist to database

3. **Return Updated State**
   - Show new allocation and available amounts

**Business Rules**:

- Cannot reduce allocation below deployed capital (user must close positions first)
- Can increase allocation freely (up to reasonable limits)
- Changes take effect immediately for next strategy call

### 4. Enhanced User Info Endpoint

**Endpoint**: `GET /api/v1/users?user_id={user_id}`

**Current Behavior**: Returns `active_strategies` with basic info

**Required Changes**:

- Ensure `allocated_capital_usd` and `deployed_capital_usd` are included
- Consider adding computed field: `available_capital_usd` for convenience
- Maintain backward compatibility for agent manager

**Example Response**:
```
{
  "user_id": "0x123...",
  "wallet_address": "0xabc...",
  "active_strategies": {
    "s1": {
      "status": "active",
      "strategy_type": "stable_eurc_usdc",
      "allocated_capital_usd": 100.0,
      "deployed_capital_usd": 30.0,
      "created_at": "2025-10-11T17:14:26",
      "updated_at": "2025-10-11T17:20:00"
    }
  }
}
```

---

## Implementation Sequence

### Phase 1: Database & Schema (Day 1)

1. Update database schema to add new fields
2. Create migration script with default values
3. Test migration on staging database
4. Update ORM models/schemas

### Phase 2: Core API Logic (Day 2-3)

1. Update strategy recommendation endpoint
   - Add capital calculation logic
   - Modify response structure
   - Handle edge cases (no allocation, no balance)

2. Implement position event endpoint
   - Create route and handler
   - Add deployed capital update logic
   - Implement idempotency and validation

3. Implement allocation management endpoint
   - Create route for setting allocations
   - Add validation rules
   - Test increase/decrease scenarios

### Phase 3: Testing (Day 4)

1. Unit tests for capital calculations
2. Integration tests for event tracking
3. End-to-end tests with agent manager
4. Edge case testing:
   - Zero allocation
   - Over-allocation attempts
   - Concurrent position events
   - Insufficient wallet balance

### Phase 4: Agent Manager Integration (Day 5)

1. Deploy API changes to staging
2. Update agent manager to use new response structure
3. Implement event reporting in agent manager
4. Test full flow on staging

### Phase 5: Production Deployment (Day 6)

1. Run migration on production database
2. Deploy API changes
3. Deploy agent manager changes
4. Monitor for issues

---

## Data Flow Examples

### Example 1: Initial Setup

**User Configuration**:
- Wallet Balance: $200 USDC
- Strategy s1 Allocation: $100
- Strategy s2 Allocation: $50
- Strategy h3 Allocation: $50

**Initial State**:
```
s1: allocated=$100, deployed=$0, available=$100
s2: allocated=$50, deployed=$0, available=$50
h3: allocated=$50, deployed=$0, available=$50
```

### Example 2: Agent Opens Position for s1

**Agent Request**: `POST /strategy?strategy_type=s1`

**API Response**:
```
{
  "action": "open",
  "capital": {
    "total_usd": "100.0",
    "allocated_for_strategy": "100.0",
    "already_deployed": "0.0",
    "available_to_deploy": "100.0",
    "wallet_balance": "200.0"
  },
  "contract_params": {
    "usdc_amount": "100.0",
    "pool": "0x...",
    ...
  }
}
```

**Agent Opens Position**: Creates position with $100

**Agent Reports**: `POST /strategies/s1/positions/events`
```
{
  "type": "opened",
  "capital_deployed_usd": 100.0,
  "token_id": 28460500,
  "tx_hash": "0x..."
}
```

**Updated State**:
```
s1: allocated=$100, deployed=$100, available=$0
Wallet Balance: $100 USDC
```

### Example 3: Agent Tries to Open Another s1 Position

**Agent Request**: `POST /strategy?strategy_type=s1`

**API Response**:
```
{
  "action": "no_action",
  "capital": {
    "total_usd": "0.0",
    "allocated_for_strategy": "100.0",
    "already_deployed": "100.0",
    "available_to_deploy": "0.0",
    "wallet_balance": "100.0",
    "reason": "allocation_exhausted"
  }
}
```

**Agent Behavior**: Skips s1, continues to next strategy (s2)

### Example 4: Agent Opens Position for s2

**Agent Request**: `POST /strategy?strategy_type=s2`

**API Response**:
```
{
  "action": "open",
  "capital": {
    "total_usd": "50.0",
    "allocated_for_strategy": "50.0",
    "already_deployed": "0.0",
    "available_to_deploy": "50.0",
    "wallet_balance": "100.0"
  },
  "contract_params": {
    "usdc_amount": "50.0",
    ...
  }
}
```

**Updated State After Reporting**:
```
s1: allocated=$100, deployed=$100, available=$0
s2: allocated=$50, deployed=$50, available=$0
Wallet Balance: $50 USDC
```

### Example 5: Position Closes with Profit

**Agent Closes s1 Position**: Returns $105 (5% profit)

**Agent Reports**: `POST /strategies/s1/positions/events`
```
{
  "type": "closed",
  "capital_returned_usd": 105.0,
  "pnl_usd": 5.0,
  "token_id": 28460500,
  "tx_hash": "0x..."
}
```

**Updated State**:
```
s1: allocated=$100, deployed=$0, available=$100
s2: allocated=$50, deployed=$50, available=$0
Wallet Balance: $155 USDC
```

### Example 6: Insufficient Wallet Balance

**Current State**:
```
s1: allocated=$100, deployed=$0, available=$100
Wallet Balance: $30 USDC
```

**Agent Request**: `POST /strategy?strategy_type=s1`

**API Response**:
```
{
  "action": "open",
  "capital": {
    "total_usd": "30.0",           // Limited by wallet!
    "allocated_for_strategy": "100.0",
    "already_deployed": "0.0",
    "available_to_deploy": "100.0",
    "wallet_balance": "30.0"       // Limiting factor
  },
  "contract_params": {
    "usdc_amount": "30.0",
    ...
  }
}
```

**Agent Behavior**: Opens position with only $30 (all available wallet balance)

---

## Error Handling

### 1. Strategy Not Found
**Scenario**: Agent requests strategy not in user's `active_strategies`

**Response**: 404 with clear error message

### 2. Strategy Inactive
**Scenario**: Strategy exists but `status != "active"`

**Response**: 400 with "Strategy is not active"

### 3. Negative Capital Attempt
**Scenario**: Event would make `deployed_capital_usd < 0`

**Response**: 400 with "Invalid capital amount"

### 4. Allocation Below Deployed
**Scenario**: User tries to set allocation to $50 when $80 is deployed

**Response**: 400 with "Cannot reduce allocation below deployed capital ($80)"

### 5. Concurrent Updates
**Scenario**: Two position events arrive simultaneously

**Solution**: Use database transactions or row-level locking

---

## Monitoring & Observability

### Key Metrics to Track

1. **Per-Strategy Metrics**
   - Allocated capital
   - Deployed capital
   - Utilization rate (deployed/allocated)
   - Number of active positions

2. **System-Wide Metrics**
   - Total allocated capital across all users/strategies
   - Total deployed capital
   - Position event success/failure rates
   - Capital constraint violations (attempts to over-allocate)

3. **Alerts**
   - Deployed capital exceeds allocated (should never happen)
   - Negative deployed capital (should never happen)
   - High failure rate on position events
   - Frequent allocation exhaustion (might indicate need for rebalancing)

### Logging Requirements

1. **Log all capital-affecting operations**:
   - Strategy allocation changes
   - Position events received
   - Deployed capital updates
   - Capital calculation decisions

2. **Include context**:
   - User ID
   - Strategy code
   - Amounts (before/after)
   - Timestamps
   - Related transaction hashes

---

## Reconciliation & Data Integrity

### Periodic Reconciliation

Implement a background job to verify consistency:

1. **Compare deployed capital to actual positions**
   - Query blockchain for user's open positions
   - Sum up actual capital in positions
   - Compare to `deployed_capital_usd` in database
   - Alert on mismatches

2. **Reconciliation Frequency**
   - Run every hour
   - Run on-demand for specific users
   - Run after system recovery/restart

3. **Handling Mismatches**
   - Log detailed discrepancy information
   - Create alerts for manual review
   - Consider auto-correction for small differences
   - Require manual approval for large corrections

### Event Idempotency

- Store processed transaction hashes to prevent double-counting
- Return success for duplicate events without modifying state
- Consider event replay for recovery scenarios

---

## Backward Compatibility

### During Migration

1. **Default Values**
   - Set `allocated_capital_usd` = wallet balance for existing strategies
   - Set `deployed_capital_usd` = 0.0 initially
   - Alternatively, calculate from existing positions if available

2. **Gradual Rollout**
   - Phase 1: Add fields but don't enforce limits (log only)
   - Phase 2: Enforce limits for new users
   - Phase 3: Enforce limits for all users

3. **Fallback Behavior**
   - If `allocated_capital_usd` is missing/null, use wallet balance as limit
   - If `deployed_capital_usd` is missing/null, treat as 0.0

---

## Security Considerations

1. **Authorization**
   - Only authenticated users can update their own allocations
   - Admin endpoints for support team to make corrections
   - Audit log for all allocation changes

2. **Rate Limiting**
   - Limit allocation changes per user per time period
   - Prevent abuse of position event endpoint

3. **Validation**
   - Sanitize all numeric inputs
   - Prevent negative values
   - Enforce reasonable maximums (e.g., $1M per strategy)

---

## Success Criteria

Implementation is successful when:

1. ✅ Users can set per-strategy capital allocations
2. ✅ Strategy endpoint respects allocation limits
3. ✅ Deployed capital is tracked accurately in real-time
4. ✅ Agent manager receives and respects capital constraints
5. ✅ Position events update deployed capital correctly
6. ✅ No over-allocation occurs (deployed > allocated)
7. ✅ System handles wallet balance constraints gracefully
8. ✅ Reconciliation confirms data accuracy
9. ✅ Monitoring shows expected metrics
10. ✅ End-to-end tests pass

---

## Next Steps

1. **Review this guide** with API team and get approval
2. **Prioritize implementation** based on business needs
3. **Create detailed tickets** for each phase
4. **Set up staging environment** for testing
5. **Coordinate with agent manager team** for integration timing
6. **Plan rollout strategy** (gradual vs. full)
7. **Prepare rollback plan** in case of issues

---

## Questions for Discussion

1. What should default `allocated_capital_usd` be for new strategies?
2. Should we allow fractional USDC amounts or round to integers?
3. How do we handle positions that are worth more/less when closed due to market movements?
4. Should there be a global capital limit across all strategies for a user?
5. Do we want to support pausing a strategy without closing positions?
6. Should allocation changes require confirmation or take effect immediately?
7. What's the reconciliation strategy for mismatches between deployed capital and actual positions?

---

## Contact

For questions or clarifications on this implementation guide, contact the agent manager team.
