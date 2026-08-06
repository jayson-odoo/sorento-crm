"""Database configuration and session management."""
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings

# Create database engine with connection pooling
# Set timezone to UTC so all timestamps are stored and interpreted in UTC
# Pool sizing is deliberately conservative and env-tunable: see `db_pool_size` in
# app/config.py. Until the API stopped blocking its event loop, a worker could
# only ever run ONE request at a time, so the pool was never actually exercised
# and its oversubscription (4 workers x 30 = 120 against max_connections=100)
# stayed hidden. Now that requests run concurrently in the threadpool, the pool
# is real and has to fit inside the server's connection budget.
engine = create_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
    pool_pre_ping=True,  # Verify connections before using
    echo=settings.debug,
    connect_args={
        "options": "-c timezone=utc"
    }
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency function to get database session.
    Yields a database session and ensures it's closed after use.
    """
    db = SessionLocal()
    # Multi-company isolation: default the session to the fail-closed UNSET scope.
    # A later slice wires the real resolver (JWT active_company_id / X-API-Key
    # contact) at request entry; until then owned-table reads are fail-closed and
    # owned-table writes are rejected (no company to stamp). See
    # app/services/company_scope.py + PLAN-multi-company-isolation.md.
    from app.models.base import UNSET, set_company_scope
    set_company_scope(db, UNSET)
    try:
        yield db
    finally:
        db.close()
