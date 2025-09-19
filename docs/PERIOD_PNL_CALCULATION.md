# Period-Based PNL Calculation Architecture

## Problem Statement

The original PNL calculation for time periods (24h, 7d, 30d) was producing impossible results such as:
- Showing -109% loss while the user still has positive balance
- Calculating percentages that exceed 100% in unrealistic ways
- Providing metrics that don't align with user expectations

### Root Cause

The fundamental issue was a **mismatched comparison base**:
1. PNL was calculated using ALL positions (regardless of when they were created)
2. But the percentage was calculated using only net deposits for the specific period
3. This created nonsensical results when dividing total portfolio PNL by period-specific deposits

## Solution: Industry-Standard Approach

### 1. SimplePeriodPnLCalculator (Recommended for MVP)

Located in: `/app/services/period_pnl_calculator.py`

This calculator uses a pragmatic approach that provides meaningful metrics:

#### Key Concepts:
- **Active Positions During Period**: Includes ALL positions that were active at any point during the period
- **Average Invested Capital**: Uses average capital as the denominator for percentage calculations
- **Proper Position Attribution**: Correctly attributes PNL to the period when it occurred

#### Calculation Method:

```python
# For each period:
1. Get all positions active during the period (not just opened/closed)
2. Calculate realized PNL from positions closed in the period
3. Calculate unrealized PNL from positions still active
4. Use average invested capital as denominator:
   - Current balance + (net deposits during period / 2)
   - This approximates the average amount at risk
5. PNL % = Total PNL / Average Invested Capital
```

#### Benefits:
- Percentages stay within reasonable bounds
- Results are intuitive and explainable to users
- Handles edge cases gracefully (no deposits, all withdrawals, etc.)

### 2. PeriodPnLCalculator (Full Time-Weighted Return)

Also in the same file, this implements a more sophisticated approach following the Modified Dietz method:

#### Key Concepts:
- **Starting Portfolio Value**: Value at the beginning of the period
- **Ending Portfolio Value**: Current value at the end of the period
- **Time-Weighted Returns**: Accounts for when cash flows occurred

#### Calculation Method:

```python
# Period PNL = Ending Value - Starting Value - Net Deposits
# Period Return % = Period PNL / Starting Value (or net deposits if no starting value)
```

This approach is more accurate but requires:
- Historical position valuations (or approximations)
- Transaction replay to calculate balances at specific points in time
- More complex logic for handling edge cases

## Implementation Details

### API Endpoint Changes

The `/users/{user_id}/pnl` endpoint now:
1. Uses `SimplePeriodPnLCalculator` for period-based calculations
2. Maintains backwards compatibility with existing response format
3. Provides additional metrics for debugging/transparency

### Key Improvements:

1. **Correct Position Filtering**:
   - Old: Only counted positions opened/closed IN the period
   - New: Counts all positions ACTIVE DURING the period

2. **Meaningful Denominator**:
   - Old: Used net deposits for period (could be zero or negative)
   - New: Uses average invested capital (always positive and meaningful)

3. **Edge Case Handling**:
   - Zero deposits: Uses current balance as base
   - All withdrawals: Still calculates meaningful percentages
   - No activity: Returns zero PNL with clear reasoning

## Usage Examples

### 24-Hour PNL
```
User has:
- $1000 balance at start of day
- Deposited $100 during the day
- Position gained $50 in value

Old calculation: $50 / $100 = 50% (misleading - seems like huge gain)
New calculation: $50 / $1050 (avg invested) = 4.76% (realistic daily return)
```

### With Withdrawals
```
User has:
- $5000 balance at start
- Withdrew $4000 during period
- Positions lost $100

Old calculation: -$100 / -$4000 = 2.5% (nonsensical)
New calculation: -$100 / $3000 (avg invested) = -3.33% (meaningful loss percentage)
```

## Migration Path

1. **Phase 1** (Current):
   - New calculator deployed alongside old code
   - Can switch between implementations via feature flag

2. **Phase 2**:
   - Monitor metrics to ensure accuracy
   - Gather user feedback on new percentages
   - Remove old implementation

3. **Phase 3** (Future):
   - Implement periodic portfolio snapshots
   - Enable full time-weighted return calculations
   - Add more sophisticated performance metrics

## Testing Considerations

### Test Cases to Validate:

1. **No deposits in period**: Should use existing capital as base
2. **Only withdrawals**: Should still show meaningful percentages
3. **Mixed positions**: Correctly attributes PNL to period
4. **New user**: Handles zero starting balance gracefully
5. **Large deposits**: Doesn't artificially inflate percentages

### Expected Behavior:

- Percentages should rarely exceed ±50% for daily returns
- Weekly/monthly returns should be proportionally reasonable
- All-time returns can be large but should match actual portfolio performance

## Future Enhancements

1. **Portfolio Snapshots**: Store periodic valuations for accurate historical calculations
2. **XIRR Calculations**: Implement money-weighted returns for more sophisticated analysis
3. **Benchmark Comparisons**: Compare performance against market indices
4. **Risk-Adjusted Returns**: Calculate Sharpe ratios and other risk metrics

## Conclusion

The new period-based PNL calculation provides:
- **Accurate** percentages that reflect true performance
- **Intuitive** results that users can understand
- **Robust** handling of edge cases
- **Industry-standard** methodology that aligns with financial best practices

This ensures users see meaningful performance metrics that help them make informed decisions about their portfolio.