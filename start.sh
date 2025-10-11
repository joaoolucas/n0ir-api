#!/bin/bash
# Startup script for n0ir API

echo "🚀 Starting n0ir API..."

# Run database migrations
echo "📦 Running database migrations..."

# Clean up migration issues: remove orphaned migrations and ensure single head
python -c "
import os
from sqlalchemy import create_engine, text
db_url = os.environ.get('DATABASE_URL')
if db_url:
    engine = create_engine(db_url)
    with engine.connect() as conn:
        # Remove orphaned migration 036
        conn.execute(text(\"DELETE FROM alembic_version WHERE version_num = '036_refactor_to_hybrid_strategy'\"))
        # If there are multiple heads (both 035 and 037), keep only 035 so 037 can run
        result = conn.execute(text(\"SELECT version_num FROM alembic_version\"))
        versions = [row[0] for row in result]
        if '037_add_effective_apr_stable' in versions:
            conn.execute(text(\"DELETE FROM alembic_version WHERE version_num = '037_add_effective_apr_stable'\"))
        conn.commit()
    print('🧹 Cleaned up migration records')
" 2>/dev/null || true

alembic upgrade head || echo "⚠️ Migrations failed"

# Start the application
echo "✅ Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}