#!/bin/bash
# Startup script for n0ir API

echo "🚀 Starting n0ir API..."

# Create tables from SQLAlchemy models
echo "📦 Creating database tables..."
python create_tables.py || echo "⚠️ Table creation failed"

# Start the application
echo "✅ Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}