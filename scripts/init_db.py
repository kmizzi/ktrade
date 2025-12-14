"""
Initialize the database.
Creates all tables and sets up initial schema.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.session import init_db
from src.utils.logger import setup_logging
import structlog

# Setup logging
logger = setup_logging()


def main():
    """Initialize database"""
    try:
        logger.info("initializing_database")

        # Create all tables
        init_db()

        logger.info("database_initialized_successfully")

    except Exception as e:
        logger.error("database_initialization_failed", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
