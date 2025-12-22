"""
FastAPI dependencies for database sessions and common utilities.
"""

from typing import Generator
from sqlalchemy.orm import Session

from src.database.session import SessionLocal


def get_db_session() -> Generator[Session, None, None]:
    """
    Dependency that provides a database session.
    Automatically closes the session when the request is complete.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db():
    """Alias for get_db_session for compatibility."""
    return get_db_session()
