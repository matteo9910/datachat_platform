"""
System Database connection management.

Provides engine, session factory, and FastAPI dependency for the System DB
(Neon PostgreSQL). This is completely separate from the client DB connection
in dependencies.py — system tables are NEVER created on the client DB.
"""

import logging
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System DB engine & session factory
# ---------------------------------------------------------------------------
# Lazy-initialized: engine is created on first call to get_system_engine().

_system_engine = None
_SystemSessionLocal = None


def get_system_engine():
    """
    Return the SQLAlchemy engine for the System Database.

    Raises RuntimeError if SYSTEM_DATABASE_URL is not configured.
    """
    global _system_engine
    if _system_engine is not None:
        return _system_engine

    url = settings.system_database_url
    if not url:
        raise RuntimeError(
            "SYSTEM_DATABASE_URL is not configured. "
            "Set it in .env to point to your Neon PostgreSQL instance."
        )

    # Pool settings only apply to PostgreSQL; SQLite uses different defaults
    engine_kwargs = {"echo": False}
    if url.startswith("postgresql"):
        engine_kwargs.update({
            "pool_size": 5,
            "max_overflow": 10,
            "pool_pre_ping": True,
        })

    _system_engine = create_engine(url, **engine_kwargs)
    logger.info("System DB engine created")
    return _system_engine


def get_system_session_factory():
    """Return a sessionmaker bound to the system engine."""
    global _SystemSessionLocal
    if _SystemSessionLocal is not None:
        return _SystemSessionLocal

    engine = get_system_engine()
    _SystemSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )
    return _SystemSessionLocal


def get_system_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a System DB session.

    Usage::

        @router.get("/endpoint")
        def endpoint(db: Session = Depends(get_system_db)):
            ...
    """
    SessionLocal = get_system_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def reset_system_engine():
    """Reset the cached engine (useful for testing)."""
    global _system_engine, _SystemSessionLocal
    if _system_engine is not None:
        _system_engine.dispose()
    _system_engine = None
    _SystemSessionLocal = None
