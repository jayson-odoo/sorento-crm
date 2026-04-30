import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.schemas.lookup import LookupSetCreate, LookupOptionCreate, LookupKeywordIn
from app.services.lookup_set_service import LookupSetService
from app.services.lookup_option_service import LookupOptionService
from app.services.lookup_resolver import LookupResolverService
from app.services.error_handler import AppException


@pytest.fixture
def db_session():
    from app.database import Base
    from app.models.lookup import LookupSet, LookupOption, LookupOptionKeyword, LookupBinding
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(
        engine,
        tables=[
            LookupSet.__table__, LookupOption.__table__,
            LookupOptionKeyword.__table__, LookupBinding.__table__,
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def seeded(db_session):
    s = LookupSetService(db_session).create(LookupSetCreate(set_key="region", name="Region"))
    LookupOptionService(db_session).create(s.id, LookupOptionCreate(
        value="north", label="North",
        keywords=[LookupKeywordIn(keyword="up north"), LookupKeywordIn(keyword="northern")]
    ))
    LookupOptionService(db_session).create(s.id, LookupOptionCreate(
        value="south", label="South"))
    return s


def test_exact_value_match(db_session, seeded):
    r = LookupResolverService(db_session).resolve("region", "north")
    assert r.value == "north" and r.match_type == "exact_value"


def test_exact_label_case_insensitive(db_session, seeded):
    r = LookupResolverService(db_session).resolve("region", "SOUTH")
    assert r.value == "south" and r.match_type == "exact_label"


def test_keyword_match(db_session, seeded):
    r = LookupResolverService(db_session).resolve("region", "Up North")
    assert r.value == "north" and r.match_type == "exact_keyword"


def test_normalized_match(db_session, seeded):
    r = LookupResolverService(db_session).resolve("region", "  northern!  ")
    assert r.value == "north"
    assert r.match_type in ("exact_keyword", "normalized")


def test_unresolved_raises_404(db_session, seeded):
    with pytest.raises(AppException) as e:
        LookupResolverService(db_session).resolve("region", "moon")
    assert e.value.status_code == 404
