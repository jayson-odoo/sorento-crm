import uuid
import pytest
from sqlalchemy import Column, String, create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.schemas.lookup import LookupSetCreate, LookupOptionCreate, LookupBindingCreate
from app.services.lookup_set_service import LookupSetService
from app.services.lookup_option_service import LookupOptionService
from app.services.lookup_binding_service import LookupBindingService
from app.services.lookup_eligibility import _REGISTRY, register_lookup_eligible
from app.services.lookup_write_listener import register_lookup_write_listeners
from app.services.lookup_validator import _cache_clear
from app.services.error_handler import AppException


class FakeLookupTarget(Base):
    __tablename__ = "fake_lookup_target"
    id = Column(String, primary_key=True)
    status = Column(String, nullable=True)


@pytest.fixture
def db_session():
    from app.models.lookup import LookupSet, LookupOption, LookupOptionKeyword, LookupBinding
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, connection_record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(
        engine,
        tables=[
            LookupSet.__table__, LookupOption.__table__,
            LookupOptionKeyword.__table__, LookupBinding.__table__,
            FakeLookupTarget.__table__,
        ],
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _setup():
    _REGISTRY.clear()
    register_lookup_eligible(model=FakeLookupTarget, column="status",
                             table_label="Fake", column_label="Status")
    _cache_clear()
    register_lookup_write_listeners()
    yield


def test_listener_rejects_unknown(db_session):
    s = LookupSetService(db_session).create(LookupSetCreate(set_key="fs", name="F"))
    LookupOptionService(db_session).create(s.id, LookupOptionCreate(value="open", label="Open"))
    LookupBindingService(db_session).create(s.id, LookupBindingCreate(
        table_name="fake_lookup_target", column_name="status"))
    bad = FakeLookupTarget(id=str(uuid.uuid4()), status="closed")
    db_session.add(bad)
    with pytest.raises(AppException) as e:
        db_session.flush()
    assert e.value.status_code == 422


def test_listener_allows_known(db_session):
    s = LookupSetService(db_session).create(LookupSetCreate(set_key="fs", name="F"))
    LookupOptionService(db_session).create(s.id, LookupOptionCreate(value="open", label="Open"))
    LookupBindingService(db_session).create(s.id, LookupBindingCreate(
        table_name="fake_lookup_target", column_name="status"))
    good = FakeLookupTarget(id=str(uuid.uuid4()), status="open")
    db_session.add(good)
    db_session.flush()  # should not raise
