import uuid
import pytest
from sqlalchemy import Column, String

from app.database import Base
from app.schemas.lookup import LookupSetCreate, LookupOptionCreate, LookupBindingCreate
from app.services.lookup_set_service import LookupSetService
from app.services.lookup_option_service import LookupOptionService
from app.services.lookup_binding_service import LookupBindingService
from app.services.lookup_eligibility import _REGISTRY, register_lookup_eligible
from app.services.lookup_write_listener import register_lookup_write_listeners
from app.services.lookup_validator import _cache_clear
from app.services.error_handler import AppException
from tests._pg_fixture import blank_session


class FakeLookupTarget(Base):
    __tablename__ = "fake_lookup_target"
    id = Column(String, primary_key=True)
    status = Column(String, nullable=True)
    note = Column(String, nullable=True)


@pytest.fixture
def db_session():
    """Empty Postgres schema over the full real DDL.

    FakeLookupTarget is declared in this module, so whether the shared blank
    schema already carries it depends on import ordering. Creating it here with
    checkfirst is order-independent: a no-op when collection registered it in
    time, and the DDL otherwise. It is transactional either way, so the outer
    rollback discards it.
    """
    with blank_session() as session:
        FakeLookupTarget.__table__.create(session.get_bind(), checkfirst=True)
        yield session


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


def test_update_of_unrelated_column_does_not_revalidate_legacy_value(db_session):
    """Regression: updating an unrelated column must NOT re-validate an unchanged
    lookup column that holds a legacy value predating its binding."""
    s = LookupSetService(db_session).create(LookupSetCreate(set_key="fs", name="F"))
    LookupOptionService(db_session).create(s.id, LookupOptionCreate(value="open", label="Open"))
    LookupBindingService(db_session).create(s.id, LookupBindingCreate(
        table_name="fake_lookup_target", column_name="status"))

    # Seed a row with an invalid (legacy) status, bypassing the listener --
    # which is a mapper-level ORM hook, so a Core insert sidesteps it just as
    # the raw SQL string this replaced did. Expressed as a Table insert rather
    # than text() because the blank schema is reached via schema_translate_map,
    # and that rewrites Table constructs only, never a literal SQL string.
    rid = str(uuid.uuid4())
    db_session.execute(
        FakeLookupTarget.__table__.insert().values(id=rid, status="legacy_bad", note=None)
    )
    db_session.commit()

    row = db_session.query(FakeLookupTarget).filter(FakeLookupTarget.id == rid).first()
    row.note = "touched"  # change an unrelated column only
    db_session.flush()  # must NOT raise despite status='legacy_bad'
    assert row.note == "touched"


def test_update_of_bound_column_to_invalid_still_rejected(db_session):
    """The bound column is still enforced when it IS the one being changed."""
    s = LookupSetService(db_session).create(LookupSetCreate(set_key="fs", name="F"))
    LookupOptionService(db_session).create(s.id, LookupOptionCreate(value="open", label="Open"))
    LookupBindingService(db_session).create(s.id, LookupBindingCreate(
        table_name="fake_lookup_target", column_name="status"))
    good = FakeLookupTarget(id=str(uuid.uuid4()), status="open")
    db_session.add(good)
    db_session.flush()

    good.status = "nope"  # change the bound column to an invalid value
    with pytest.raises(AppException) as e:
        db_session.flush()
    assert e.value.status_code == 422
