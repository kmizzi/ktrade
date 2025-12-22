#!/usr/bin/env python3
"""
Database migration script to add new tables.
Run this to upgrade the database with new models.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.session import engine, SessionLocal
from src.database.models import Base


def migrate():
    """Create all new tables in the database."""
    print("Starting database migration...")

    # Create all tables that don't exist
    # SQLAlchemy's create_all() only creates tables that don't already exist
    Base.metadata.create_all(bind=engine)

    print("Migration complete!")

    # Print table names
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"\nDatabase now has {len(tables)} tables:")
    for table in sorted(tables):
        print(f"  - {table}")


if __name__ == "__main__":
    migrate()
