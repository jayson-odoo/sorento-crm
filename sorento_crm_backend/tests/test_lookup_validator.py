import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.schemas.lookup import LookupSetCreate, LookupOptionCreate, LookupBindingCreate
from app.services.lookup_set_service import LookupSetService
from app.services.lookup_option_service import LookupOptionService
from app.services.lookup_binding_service import LookupBindingService
from app.services.lookup_eligibility import _REGISTRY, register_lookup_eligible
from app.services.lookup_validator import validate_lookup_value, _cache_clear
from app.services.error_handler import AppException


class _M:
    __tablename__ = "fake_t"


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


def setup_function(_):
    _REGISTRY.clear()
    register_lookup_eligible(model=_M, column="status", table_label="F", column_label="S")
    _cache_clear()


def test_value_in_active_options_passes(db_session):
    s = LookupSetService(db_session).create(LookupSetCreate(set_key="fs", name="x"))
    LookupOptionService(db_session).create(s.id, LookupOptionCreate(value="open", label="Open"))
    LookupBindingService(db_session).create(s.id, LookupBindingCreate(table_name="fake_t", column_name="status"))
    validate_lookup_value(db_session, table="fake_t", column="status", value="open")


def test_unknown_value_raises_422(db_session):
    s = LookupSetService(db_session).create(LookupSetCreate(set_key="fs", name="x"))
    LookupOptionService(db_session).create(s.id, LookupOptionCreate(value="open", label="Open"))
    LookupBindingService(db_session).create(s.id, LookupBindingCreate(table_name="fake_t", column_name="status"))
    with pytest.raises(AppException) as e:
        validate_lookup_value(db_session, table="fake_t", column="status", value="closed")
    assert e.value.status_code == 422


def test_unbound_column_skipped(db_session):
    validate_lookup_value(db_session, table="fake_t", column="status", value="anything")
