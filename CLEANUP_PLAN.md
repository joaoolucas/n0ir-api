# n0ir-api Cleanup and Optimization Plan

## Overview
This document outlines the comprehensive cleanup and optimization plan for the n0ir-api, focusing on removing redundant fields, simplifying response models, and improving overall performance.

## Key Problems Identified

### 1. Database Model Issues
- **Redundant Fields**: Many fields duplicate data already stored in JSONB columns
- **Backward Compatibility Cruft**: 70+ properties that exist only for compatibility
- **Confusing Naming**: Mix of USD/USDC, multiple PnL field names
- **Unused Features**: Hedge-related properties (78 lines) that always return None

### 2. API Response Issues
- **Over-fetching**: Returning too much data per request
- **Complex Enrichment**: 100+ line functions to enrich responses
- **Redundant Fields**: Multiple fields representing the same data
- **No Pagination**: Some endpoints return all data without limits

### 3. Performance Issues
- **Unnecessary Blockchain Calls**: Fetching on-chain data for closed positions
- **No Caching**: Pool names and token info fetched repeatedly
- **Complex Queries**: Multiple database round-trips for single endpoints
- **Large Response Payloads**: Including all metadata and computed fields

## Implementation Plan

### Phase 1: Database Cleanup (Week 1)
1. **Run Migration**: Execute `cleanup_redundant_fields.sql`
   - Remove agent fields from users table
   - Remove protocol fee fields from positions
   - Standardize transaction types to 4 core types
   - Create optimized indexes

2. **Update Models**: 
   - Remove backward compatibility properties from User model
   - Remove hedge-related properties from Position model
   - Simplify Transaction model computed properties

### Phase 2: Schema Simplification (Week 1)
1. **Implement Simplified Schemas**: Use new schemas from `app/schemas/simplified.py`
   - SimplifiedUserResponse
   - SimplifiedPositionResponse
   - SimplifiedTransactionResponse
   - SimplifiedBalanceResponse

2. **Benefits**:
   - 60% reduction in response payload size
   - Clear, non-redundant field names
   - Consistent naming conventions

### Phase 3: Service Layer Optimization (Week 2)
1. **Deploy Optimized Service**: Use `app/services/optimized_user_service.py`
   - Single-query aggregations
   - Efficient pagination
   - Pool name caching
   - Batch operations

2. **Performance Improvements**:
   - 70% reduction in database queries
   - 50% faster response times
   - Better memory usage

### Phase 4: API Endpoint Updates (Week 2)
1. **Create V2 Endpoints**: Parallel deployment strategy
   - `/api/v2/users` - Uses simplified schemas
   - Keep v1 endpoints for backward compatibility
   - Gradual migration of clients

2. **Endpoint Optimizations**:
   - Proper pagination on all list endpoints
   - Optional field selection with query parameters
   - Response compression

## Migration Strategy

### Step 1: Parallel Deployment
```python
# In app/api/v2/endpoints/users.py
from app.services.optimized_user_service import optimized_user_service

@router.get("/{user_id}", response_model=SimplifiedUserResponse)
async def get_user_v2(user_id: str, db: AsyncSession = Depends(get_db)):
    return await optimized_user_service.get_user_summary(user_id, db)
```

### Step 2: Client Migration
1. Document v2 API changes
2. Provide migration guide for clients
3. Set deprecation timeline for v1
4. Monitor usage metrics

### Step 3: Cleanup Old Code
After successful migration:
1. Remove v1 endpoints
2. Delete old schemas
3. Remove compatibility properties from models
4. Archive old service code

## Metrics to Track

### Performance Metrics
- Average response time (target: < 100ms)
- Database query count per request (target: < 3)
- Response payload size (target: 50% reduction)
- Memory usage (target: 30% reduction)

### Business Metrics
- API error rate (target: < 0.1%)
- Client migration progress
- Feature parity validation
- User experience feedback

## Specific Field Removals

### User Model
```python
# REMOVE:
- agent_started_at
- agent_stopped_at  
- last_balance_check
- agent_metadata
- unrealized_pnl_usdc (property)
- realized_pnl_usdc (property)
- unrealized_pnl_percentage (property)
- realized_pnl_percentage (property)
```

### Position Model
```python
# REMOVE:
- protocol_fee_amount
- protocol_fee_collected
- protocol_fee_tx_hash
- position_data (property)
- blockchain_data (property)
- All 78 hedge-related properties
- Multiple PnL alias properties
```

### Transaction Model
```python
# SIMPLIFY:
- tx_type to 4 core types only
- Remove complex type mappings
- Remove computed properties
```

## Expected Benefits

### Performance
- **50% faster API response times**
- **60% smaller response payloads**
- **70% fewer database queries**
- **Better resource utilization**

### Maintainability
- **Cleaner codebase** (remove ~500 lines of redundant code)
- **Clearer data model**
- **Easier debugging**
- **Simpler testing**

### Developer Experience
- **Clear API documentation**
- **Consistent field naming**
- **Predictable responses**
- **Better error messages**

## Risk Mitigation

### Backward Compatibility
- Keep v1 endpoints during transition
- Provide compatibility layer if needed
- Clear migration documentation
- Gradual rollout with feature flags

### Data Integrity
- Run migration in transaction
- Create backup before migration
- Validate data after migration
- Keep rollback plan ready

### Testing Strategy
- Unit tests for new schemas
- Integration tests for new endpoints
- Performance testing
- Load testing

## Timeline

### Week 1
- Day 1-2: Database migration and testing
- Day 3-4: Deploy simplified schemas
- Day 5: Testing and validation

### Week 2
- Day 1-2: Deploy optimized service layer
- Day 3-4: Create v2 endpoints
- Day 5: Documentation and client communication

### Week 3
- Monitor metrics
- Address issues
- Begin client migration
- Performance tuning

### Week 4
- Complete client migration
- Deprecate v1 endpoints
- Final cleanup
- Post-mortem

## Success Criteria

1. **All tests passing** with new schemas
2. **Performance targets met** (< 100ms p95 latency)
3. **No data loss** during migration
4. **Client migrations successful**
5. **Reduced operational costs** (lower CPU/memory usage)

## Next Steps

1. **Review and approve** this plan with the team
2. **Create feature branch** for implementation
3. **Set up monitoring** for migration metrics
4. **Schedule migration** during low-traffic period
5. **Prepare rollback plan** and test it

## Contact

For questions or concerns about this cleanup plan, please reach out to the API team.