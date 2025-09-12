# Emergency Database Fix Instructions

## Problem
The database has old column names that need to be renamed:
- `unrealized_pnl_usd` → `pnl_usdc`
- `unrealized_pnl_pct` → `pnl_pct`
- `realized_pnl_usd` → `realized_pnl_usdc`

## Solution Options

### Option 1: Using Railway CLI (Recommended)
```bash
# Connect to the database
railway connect postgres

# Once connected, run the SQL from manual_fix.sql
\i manual_fix.sql
```

### Option 2: Using Railway Database Dashboard
1. Go to Railway dashboard
2. Click on the database service (n0ir-db)
3. Go to the "Data" tab
4. Click "Query"
5. Copy and paste the contents of `manual_fix.sql`
6. Run the query

### Option 3: Direct psql connection
```bash
# Get the database URL from Railway
railway variables -s n0ir-db

# Connect using psql
psql "postgresql://postgres:pXmVJczPuWPIauAWXFUKwUdaYGTKqBdX@postgres.railway.internal:5432/railway"

# Run the fix
\i manual_fix.sql
```

### Option 4: Using pgAdmin or DBeaver
1. Get connection details from Railway
2. Connect to the database
3. Run the SQL from `manual_fix.sql`

## Quick Fix Commands
If you just want to copy/paste the essential fix:

```sql
ALTER TABLE positions RENAME COLUMN unrealized_pnl_usd TO pnl_usdc;
ALTER TABLE positions RENAME COLUMN unrealized_pnl_pct TO pnl_pct;
ALTER TABLE positions RENAME COLUMN realized_pnl_usd TO realized_pnl_usdc;
```

## Verification
After running the fix, the application should work without column errors.

You can verify by checking:
1. Railway deployment logs should no longer show "column positions.pnl_usdc does not exist"
2. API endpoints should work properly
3. The miniapp should load data correctly