# n0ir API

FastAPI-based REST API for accessing Aerodrome Finance Concentrated Liquidity pool data on Base network.

## Features

- Pool discovery with filters (type, TVL, volume, APR)
- Single pool information
- Batch pool fetching
- Token information and prices
- Pool statistics
- Health check endpoint

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Copy the environment configuration:
```bash
cp .env.example .env
```

3. Update `.env` file with your configuration (optional, defaults are provided)

## Running the API

### Development mode:
```bash
python run.py
```

Or using uvicorn directly:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Production mode:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## API Documentation

Once the server is running, you can access:
- Interactive API docs: http://localhost:8000/docs
- Alternative API docs: http://localhost:8000/redoc
- OpenAPI schema: http://localhost:8000/openapi.json

## API Endpoints

### Pools
- `GET /api/v1/pools` - Get pools with filters
- `GET /api/v1/pools/{address}` - Get single pool details
- `POST /api/v1/pools/batch` - Get multiple pools by addresses
- `GET /api/v1/pools/{address}/stats` - Get pool statistics

### Tokens
- `GET /api/v1/tokens/{address}` - Get token information
- `POST /api/v1/tokens/prices` - Get token prices in batch

### Health
- `GET /api/v1/health` - Service health check

## Query Parameters for Pool Discovery

- `type`: Pool type filter (stable/volatile/all)
- `min_tvl`: Minimum TVL in USD (default: 1000)
- `min_volume_24h`: Minimum 24h volume in USD (default: 10000)
- `min_apr`: Minimum APR percentage (default: 0)
- `blacklist`: Comma-separated token addresses to exclude
- `limit`: Maximum results (default: 100, max: 500)
- `offset`: Pagination offset (default: 0)
- `sort_by`: Sort field (apr/tvl/volume, default: apr)
- `sort_order`: Sort order (desc/asc, default: desc)

## Configuration

Configuration is managed through environment variables in the `.env` file:

- `RPC_URL`: Base network RPC endpoint
- `CACHE_TTL_*`: Cache TTL settings for different data types
- `HOST`: Server host (default: 0.0.0.0)
- `PORT`: Server port (default: 8000)
- `CORS_*`: CORS configuration

## Architecture

The API is built with:
- **FastAPI**: Modern async web framework
- **n0ir SDK**: Core blockchain interaction logic
- **In-memory cache**: Fast data caching with TTL
- **Pydantic**: Data validation and serialization

## Project Structure

```
n0ir-api/
├── app/
│   ├── api/v1/          # API endpoints
│   ├── core/            # Core services and configuration
│   ├── schemas/         # Pydantic models
│   └── main.py          # FastAPI application
├── requirements.txt     # Python dependencies
├── .env.example        # Environment template
├── .env                # Environment configuration
└── run.py              # Application runner
```