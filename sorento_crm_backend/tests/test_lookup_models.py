import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.models.lookup import LookupSet, LookupOption, LookupOptionKeyword, LookupBinding


@pytest.fixture
def db_session():
    """In-memory SQLite session scoped to the lookup tables only.

    We deliberately avoid importing the full models registry because other
    models use JSONB/PostgreSQL-specific types that SQLite cannot compile.
    The lookup models only use standard ANSI types, so SQLite works fine.
    """
    from app.database import Base

    # Importing the lookup models above already registered their mappers;
    # we only create their tables so SQLite doesn't choke on PG-specific types.
    tables = [
        LookupSet.__table__,
        LookupOption.__table__,
        LookupOptionKeyword.__table__,
        LookupBinding.__table__,
    ]
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=tables)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_models_construct(db_session):
    s = LookupSet(id=str(uuid.uuid4()), set_key="region", name="Region")
    db_session.add(s)
    db_session.flush()
    o = LookupOption(id=str(uuid.uuid4()), set_id=s.id, value="north", label="North")
    db_session.add(o)
    db_session.flush()
    k = LookupOptionKeyword(id=str(uuid.uuid4()), option_id=o.id, keyword="up north")
    b = LookupBinding(id=str(uuid.uuid4()), set_id=s.id, table_name="customers", column_name="region")
    db_session.add_all([k, b])
    db_session.flush()
    assert o.set is s
    assert k.option is o
    assert b.set is s
