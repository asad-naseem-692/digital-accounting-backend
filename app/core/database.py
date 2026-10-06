from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # reconnect gracefully after idle disconnects
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


def get_db():
    """
    FastAPI dependency that yields a database session and ensures it is
    closed after the request, even if an exception occurs.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
