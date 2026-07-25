import pytest

from app.schemas.lookup import LookupSetCreate, LookupOptionCreate, LookupBindingCreate
from app.services.lookup_set_service import LookupSetService
from app.services.lookup_option_service import LookupOptionService
from app.services.lookup_binding_service import LookupBindingService
from app.services.lookup_eligibility import _REGISTRY, register_lookup_eligible
from app.services.lookup_validator import validate_lookup_value, _cache_clear
from app.services.error_handler import AppException
from tests._pg_fixture import blank_session


class _M:
    __tablename__ = "fake_t"


@pytest.fixture
def db_session():
    """Empty Postgres schema over the full real DDL.

    Blank rather than the live database because a live binding on the same
    table/column would change which values validate. ``_M`` needs no table of
    its own -- the validator resolves bindings by table-name string.
    """
    with blank_session() as session:
        yield session


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
