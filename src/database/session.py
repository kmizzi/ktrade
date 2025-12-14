"""
Database session management.
Provides session factory and connection handling.
"""

from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from config.settings import settings
from src.database.models import Base


# Create engine
engine = create_engine(
    settings.database_url,
    echo=settings.log_level == "DEBUG",
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {}
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """
    Initialize the database by creating all tables.
    Should be called once at application startup.
    """
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    Get database session.
    Use as a context manager or with dependency injection.

    Example:
        with get_db() as db:
            positions = db.query(Position).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session() -> Session:
    """
    Get a database session directly.
    Caller is responsible for closing the session.

    Returns:
        SQLAlchemy Session
    """
    return SessionLocal()
