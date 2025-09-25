# Removed Strategy and Perps Endpoints

## Summary
The strategy and perps endpoints have been completely removed from the codebase.

## Endpoints Removed
1. `POST /api/v1/users/{user_id}/strategy` - Strategy generation endpoint
2. `GET /api/v1/blockchain/perps/{address}` - Perps positions endpoint

## Files Removed

### Strategy-related:
1. `app/core/delta_neutral_service.py` - Service for delta-neutral strategy generation
2. `app/core/gpt_strategy_service.py` - GPT-powered strategy service
3. `app/core/moonwell_service.py` - Moonwell lending protocol integration
4. `test_delta_neutral.py` - Test file for strategy endpoint
5. `DEPRECATED_PERPS.md` - Documentation for deprecated perps code

### Perps-related:
1. `app/core/perps_service.py` - Service for fetching perps positions
2. `app/schemas/perps.py` - Perps position schemas
3. `app/integrations/avantis.py` - Avantis SDK integration
4. `scripts/test_perps_endpoint.py` - Test script for perps endpoint

## Code Removed from Existing Files

### `app/api/v1/endpoints/core.py`
- Removed the `get_delta_neutral_strategy` endpoint function
- Removed imports for strategy-related services

### `app/api/v1/endpoints/blockchain.py`
- Removed the `get_perps_positions` endpoint function
- Removed imports for perps service and schemas

### `app/schemas/users.py`
- Removed `LPAllocation` class
- Removed `Hedge` class (legacy perps)
- Removed `MoonwellHedge` class and related schemas
- Removed `DeltaNeutralStrategyRequest` class
- Removed `DeltaNeutralStrategyResponse` class

## Remaining Core Endpoints
The core API now only has these endpoints:
- `POST /users/{user_id}/create` - Create user and CDP wallet
- `POST /users/{user_id}/activate` - Activate trading agent
- `POST /users/{user_id}/deactivate` - Deactivate trading agent

## Note
All perps and strategy-related functionality has been completely removed from the codebase.