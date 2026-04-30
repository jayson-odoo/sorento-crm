import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.schemas.lookup import LookupSetCreate, LookupOptionCreate, LookupOptionUpdate, LookupKeywordIn
from app.services.lookup_set_service import LookupSetService
from app.services.lookup_option_service import LookupOptionService
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


def _set(db_session, key="region"):
    return LookupSetService(db_session).create(LookupSetCreate(set_key=key, name="x"))


def test_create_with_keywords(db_session):
    s = _set(db_session)
    svc = LookupOptionService(db_session)
    o = svc.create(s.id, LookupOptionCreate(value="north", label="North",
        keywords=[LookupKeywordIn(keyword="up north"), LookupKeywordIn(keyword="northern")]))
    assert len(o.keywords) == 2


def test_duplicate_value_case_insensitive(db_session):
    s = _set(db_session)
    svc = LookupOptionService(db_session)
    svc.create(s.id, LookupOptionCreate(value="North", label="North"))
    with pytest.raises(AppException) as e:
        svc.create(s.id, LookupOptionCreate(value="north", label="x"))
    assert e.value.status_code == 409


def test_update_replaces_keywords(db_session):
    s = _set(db_session)
    svc = LookupOptionService(db_session)
    o = svc.create(s.id, LookupOptionCreate(value="n", label="N",
        keywords=[LookupKeywordIn(keyword="a")]))
    svc.update(o.id, LookupOptionUpdate(keywords=[LookupKeywordIn(keyword="b")]))
    db_session.refresh(o)
    assert {k.keyword for k in o.keywords} == {"b"}


def test_delete_cascades_keywords(db_session):
    from app.models.lookup import LookupOptionKeyword
    s = _set(db_session)
    svc = LookupOptionService(db_session)
    o = svc.create(s.id, LookupOptionCreate(value="n", label="N",
        keywords=[LookupKeywordIn(keyword="a")]))
    svc.delete(o.id)
    assert db_session.query(LookupOptionKeyword).filter_by(option_id=o.id).count() == 0
