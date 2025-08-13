# Database Setup Guide

## Overview
The n0ir API uses PostgreSQL for persistent storage of user data, positions, transactions, and protocol fees. The database layer is built with SQLAlchemy (async) and Alembic for migrations.

## Local Development Setup

### 1. Install PostgreSQL
```bash
# Ubuntu/Debian
sudo apt-get install postgresql postgresql-contrib

# macOS with Homebrew
brew install postgresql
brew services start postgresql

# Docker
docker run --name n0ir-postgres -e POSTGRES_PASSWORD=mysecretpassword -p 5432:5432 -d postgres
```

### 2. Create Database
```bash
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE n0ir_dev;

# Create user (optional)
CREATE USER n0ir_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE n0ir_dev TO n0ir_user;
```

### 3. Set Environment Variables
```bash
# Add to your .env file
DATABASE_URL=postgresql+asyncpg://n0ir_user:your_password@localhost/n0ir_dev
```

### 4. Run Migrations
```bash
# Create initial migration (first time only)
alembic revision --autogenerate -m "Initial database schema"

# Apply migrations
alembic upgrade head
```

## Railway Deployment

### 1. Add PostgreSQL Service
In your Railway project:
1. Click "Add Service" → "Database" → "PostgreSQL"
2. Railway will automatically provision a PostgreSQL instance
3. The connection details will be available as environment variables

### 2. Environment Variables
Railway automatically provides these variables:
- `DATABASE_URL` - Standard connection string
- `DATABASE_PRIVATE_URL` - Internal connection (faster, free)
- `DATABASE_PUBLIC_URL` - External connection

The API automatically uses `DATABASE_PRIVATE_URL` when available for better performance.

### 3. Migrations
Migrations run automatically on deploy via the Railway configuration:
```json
{
  "deploy": {
    "startCommand": "alembic upgrade head && uvicorn app.main:app --host :: --port $PORT"
  }
}
```

## Database Schema

### Users Table
- Stores user accounts with CDP wallet information
- Links to transactions, positions, and protocol fees

### Transactions Table
- Records all financial transactions (deposits, withdrawals, position entries/exits)
- Tracks blockchain transaction details and status

### Positions Table
- Manages Aerodrome liquidity positions
- Tracks performance metrics (PnL, fees, rewards)
- Links to protocol fees for profitable positions

### Protocol Fees Table
- Records 5% protocol fee on profitable positions
- Tracks collection status and transaction hashes

## Common Commands

### Alembic Migrations
```bash
# Create new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history

# Show current revision
alembic current
```

### Database Inspection
```bash
# Connect to database
psql $DATABASE_URL

# List tables
\dt

# Describe table structure
\d users
\d positions
\d transactions
\d protocol_fees

# View indexes
\di
```

## Troubleshooting

### Migration Issues
1. **"Can't connect to database"**: Check DATABASE_URL is set correctly
2. **"Table already exists"**: Database may be out of sync with migrations
   - Solution: `alembic stamp head` to mark current state as up-to-date
3. **"Import error"**: Ensure all models are imported in `migrations/env.py`

### Connection Issues
1. **"Connection refused"**: PostgreSQL service may not be running
2. **"Authentication failed"**: Check username/password in DATABASE_URL
3. **"Database does not exist"**: Create the database first

### Performance Tips
1. Use connection pooling (configured by default)
2. Create appropriate indexes for frequently queried fields
3. Use `DATABASE_PRIVATE_URL` in Railway for internal connections
4. Monitor slow queries with `DATABASE_ECHO=True` in development

## API Endpoints

The database enables these user management endpoints:

### User Management
- `POST /api/v1/users` - Create user with CDP wallet
- `GET /api/v1/users/{user_id}` - Get user profile
- `PUT /api/v1/users/{user_id}` - Update user settings

### Wallet Operations
- `POST /api/v1/users/{user_id}/deposit` - Deposit USDC
- `POST /api/v1/users/{user_id}/withdraw` - Withdraw USDC
- `GET /api/v1/users/{user_id}/balance` - Get balance

### Position Management
- `POST /api/v1/users/{user_id}/positions` - Create position
- `GET /api/v1/users/{user_id}/positions` - List positions
- `DELETE /api/v1/users/{user_id}/positions/{id}` - Exit position

### Performance Analytics
- `GET /api/v1/users/{user_id}/pnl` - PnL breakdown
- `GET /api/v1/users/{user_id}/performance` - Complete metrics
- `GET /api/v1/users/{user_id}/fees` - Protocol fees

## Security Considerations

1. **Never commit secrets**: Keep DATABASE_URL and CDP keys out of version control
2. **Use SSL connections**: Required for production databases
3. **Validate inputs**: All user inputs are validated via Pydantic schemas
4. **SQL injection protection**: SQLAlchemy ORM prevents SQL injection
5. **Connection pooling**: Prevents connection exhaustion attacks