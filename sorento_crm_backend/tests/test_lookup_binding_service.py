import pytest
from sqlalchemy import Column, String

from app.database import Base
from tests._pg_fixture import blank_session
from app.schemas.lookup import LookupSetCreate, LookupOptionCreate, LookupBindingCreate
from app.services.lookup_set_service import LookupSetService
from app.services.lookup_option_service import LookupOptionService
from app.services.lookup_binding_service import LookupBindingService
from app.services.lookup_eligibility import _REGISTRY, register_lookup_eligible
from app.services.error_handler import AppException


class _M:
    __tablename__ = "fake_orders"


class _DemoWidget(Base):
    """Real metadata-backed table so the distinct-values Core query path
    (not the ``_REGISTRY`` short-circuit) can be exercised against seeded rows.

    String ``status`` column: non-blacklisted table/column, nullable, no FK/PK
    constraints → eligible via ``_eligibility_from_metadata`` when ``_REGISTRY``
    is empty.
    """
    __tablename__ = "demo_widgets"
    id = Column(String, primary_key=True)
    status = Column(String, nullable=True)


@pytest.fixture
def db_session():
    """A blank Postgres schema, rolled back after the test.

    Was in-memory sqlite with a PRAGMA to switch foreign keys on -- Postgres
    enforces them natively, and ``_DemoWidget`` rides along because it is
    declared on ``Base`` at import time, so the blank schema's create_all
    picks it up with everything else.
    """
    with blank_session() as session:
        yield session


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


def test_reject_injection_style_identifier(db_session):
    """An injection-style table/column never reaches SQL — eligibility
    validation rejects it first (unchanged behaviour, defense-in-depth)."""
    s = LookupSetService(db_session).create(LookupSetCreate(set_key="op", name="x"))
    svc = LookupBindingService(db_session)
    with pytest.raises(AppException) as e:
        svc.create(s.id, LookupBindingCreate(
            table_name="fake_orders", column_name="priority; DROP TABLE users"))
    assert e.value.status_code in (400, 422)
    # The malicious column is not eligible, so no DISTINCT query was ever built.
    with pytest.raises(AppException) as e2:
        svc.create(s.id, LookupBindingCreate(
            table_name="users; DROP TABLE lookup_sets", column_name="priority"))
    assert e2.value.status_code in (400, 422)


def test_distinct_values_core_blocks_out_of_set(db_session):
    """Core ``select(col).where(col.isnot(None)).distinct()`` reads the same
    rows as the old f-string: a seeded out-of-options value is detected and the
    binding is rejected. Uses the metadata path (empty ``_REGISTRY``)."""
    _REGISTRY.clear()  # force metadata-driven eligibility, not the test override
    db_session.execute(
        _DemoWidget.__table__.insert().values(id="1", status="archived"))
    db_session.commit()
    s = LookupSetService(db_session).create(
        LookupSetCreate(set_key="ws", name="Widget Status"))
    LookupOptionService(db_session).create(
        s.id, LookupOptionCreate(value="active", label="Active"))
    svc = LookupBindingService(db_session)
    with pytest.raises(AppException) as e:
        svc.create(s.id, LookupBindingCreate(table_name="demo_widgets", column_name="status"))
    assert e.value.status_code in (400, 422)
    assert "archived" in str(e.value.detail.get("message"))


def test_distinct_values_core_allows_in_set(db_session):
    """When every existing distinct value is in the set's options, the Core
    query path permits the binding (behaviour-identical to before)."""
    _REGISTRY.clear()  # force metadata-driven eligibility
    db_session.execute(
        _DemoWidget.__table__.insert().values(id="2", status="active"))
    db_session.commit()
    s = LookupSetService(db_session).create(
        LookupSetCreate(set_key="ws", name="Widget Status"))
    LookupOptionService(db_session).create(
        s.id, LookupOptionCreate(value="active", label="Active"))
    svc = LookupBindingService(db_session)
    b = svc.create(s.id, LookupBindingCreate(table_name="demo_widgets", column_name="status"))
    assert b.table_name == "demo_widgets"
    assert b.column_name == "status"
