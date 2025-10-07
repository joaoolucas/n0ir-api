#!/bin/bash
# Startup script for n0ir API

echo "🚀 Starting n0ir API..."

# Run database migrations
echo "📦 Running database migrations..."
alembic upgrade head || echo "⚠️ Migrations failed"

# Start the application
echo "✅ Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}