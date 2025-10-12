#!/bin/bash
# Startup script for n0ir API

echo "🚀 Starting n0ir API..."

# Run database migrations
echo "📦 Running database migrations..."

# Clean up migration issues: remove orphaned migrations and fix alembic_version
python -c "
import os
from sqlalchemy import create_engine, text
db_url = os.environ.get('DATABASE_URL')
if db_url:
    engine = create_engine(db_url)
    with engine.connect() as conn:
        # Check current state
        result = conn.execute(text(\"SELECT version_num FROM alembic_version\"))
        versions = [row[0] for row in result]

        # Remove orphaned migration 036
        if '036_refactor_to_hybrid_strategy' in versions:
            conn.execute(text(\"DELETE FROM alembic_version WHERE version_num = '036_refactor_to_hybrid_strategy'\"))
            print('Removed orphaned migration 036')

        # If 037 exists but 035 doesn't, we need to fix the chain
        if '037_add_effective_apr_stable' in versions and '035_add_user_strategies' not in versions:
            # Set to 035 so that both 035 and 037 can run
            conn.execute(text(\"UPDATE alembic_version SET version_num = '035_add_user_strategies' WHERE version_num = '037_add_effective_apr_stable'\"))
            print('Fixed migration chain to run from 035')

        conn.commit()
    print('🧹 Cleaned up migration records')
" 2>/dev/null || true

alembic upgrade head || echo "⚠️ Migrations failed"

# Start the application
echo "✅ Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}