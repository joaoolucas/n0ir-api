#!/usr/bin/env python3
"""Create all database tables from SQLAlchemy models."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from sqlalchemy import create_engine
from app.core.config import settings
from app.database.base import Base
from app.database.models import User, Transaction, Position

def create_tables():
    """Create all tables from models."""
    engine = create_engine(settings.database_url or settings.get_database_url())

    print("Creating all tables from models...")
    Base.metadata.create_all(bind=engine)
    print("✅ All tables created successfully!")

    return True

if __name__ == "__main__":
    if create_tables():
        sys.exit(0)
    else:
        sys.exit(1)
