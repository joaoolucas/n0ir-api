# Removed Strategy Endpoint

## Summary
The POST `/api/v1/users/{user_id}/strategy` endpoint and all related code has been completely removed from the codebase.

## Files Removed
1. `app/core/delta_neutral_service.py` - Service for delta-neutral strategy generation
2. `app/core/gpt_strategy_service.py` - GPT-powered strategy service
3. `app/core/moonwell_service.py` - Moonwell lending protocol integration
4. `test_delta_neutral.py` - Test file for strategy endpoint
5. `DEPRECATED_PERPS.md` - Documentation for deprecated perps code

## Code Removed from Existing Files

### `app/api/v1/endpoints/core.py`
- Removed the `get_delta_neutral_strategy` endpoint function
- Removed imports for strategy-related services

### `app/schemas/users.py`
- Removed `LPAllocation` class
- Removed `Hedge` class (legacy perps)
- Removed `MoonwellHedge` class and related schemas
- Removed `DeltaNeutralStrategyRequest` class
- Removed `DeltaNeutralStrategyResponse` class

## Remaining Endpoints
The core API now only has these endpoints:
- `POST /users/{user_id}/create` - Create user and CDP wallet
- `POST /users/{user_id}/activate` - Activate trading agent
- `POST /users/{user_id}/deactivate` - Deactivate trading agent

## Note
The perps-related code (`app/core/perps_service.py`, `app/schemas/perps.py`) remains in the codebase but is marked as deprecated for backward compatibility.