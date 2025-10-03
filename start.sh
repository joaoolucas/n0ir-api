#!/bin/bash
# Startup script for n0ir API

echo "🚀 Starting n0ir API..."

# Run Alembic migrations to create/update tables
echo "📦 Running Alembic migrations..."
alembic upgrade head || echo "⚠️ Alembic migration failed"

# Start the application
echo "✅ Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}