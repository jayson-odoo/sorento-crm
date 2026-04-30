import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.schemas.lookup import LookupSetCreate, LookupOptionCreate, LookupBindingCreate
from app.services.lookup_set_service import LookupSetService
from app.services.lookup_option_service import LookupOptionService
from app.services.lookup_binding_service import LookupBindingService
from app.services.lookup_eligibility import _REGISTRY, register_lookup_eligible
from app.services.error_handler import AppException


class _M:
    __tablename__ = "fake_orders"


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
    register_lookup_eligible(model=_M, column="priority",
                             table_label="Order", column_label="Priority")


def test_create_binding(db_session):
    s = LookupSetService(db_session).create(LookupSetCreate(set_key="op", name="Order Priority"))
    LookupOptionService(db_session).create(s.id, LookupOptionCreate(value="high", label="High"))
    svc = LookupBindingService(db_session)
    b = svc.create(s.id, LookupBindingCreate(table_name="fake_orders", column_name="priority"))
    assert b.table_name == "fake_orders"


def test_reject_unknown_eligibility(db_session):
    s = LookupSetService(db_session).create(LookupSetCreate(set_key="op", name="x"))
    svc = LookupBindingService(db_session)
    with pytest.raises(AppException) as e:
        svc.create(s.id, LookupBindingCreate(table_name="fake_orders", column_name="ghost"))
    assert e.value.status_code == 422 or e.value.status_code == 400


def test_reject_duplicate_binding(db_session):
    s = LookupSetService(db_session).create(LookupSetCreate(set_key="op", name="x"))
    LookupOptionService(db_session).create(s.id, LookupOptionCreate(value="h", label="H"))
    svc = LookupBindingService(db_session)
    svc.create(s.id, LookupBindingCreate(table_name="fake_orders", column_name="priority"))
    with pytest.raises(AppException) as e:
        svc.create(s.id, LookupBindingCreate(table_name="fake_orders", column_name="priority"))
    assert e.value.status_code == 409
