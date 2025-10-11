#!/bin/bash
# Startup script for n0ir API

echo "🚀 Starting n0ir API..."

# Run database migrations
echo "📦 Running database migrations..."

# Remove orphaned migration 036 from alembic_version if it exists
python -c "
import os
from sqlalchemy import create_engine, text
db_url = os.environ.get('DATABASE_URL')
if db_url:
    engine = create_engine(db_url)
    with engine.connect() as conn:
        conn.execute(text(\"DELETE FROM alembic_version WHERE version_num = '036_refactor_to_hybrid_strategy'\"))
        conn.commit()
    print('🧹 Cleaned up orphaned migration 036')
" 2>/dev/null || true

alembic upgrade head || echo "⚠️ Migrations failed"

# Start the application
echo "✅ Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}