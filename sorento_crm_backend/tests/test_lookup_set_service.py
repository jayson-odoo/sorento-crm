import pytest

from app.schemas.lookup import LookupSetCreate, LookupSetUpdate
from app.services.lookup_set_service import LookupSetService
from app.services.error_handler import AppException
from tests._pg_fixture import blank_session


@pytest.fixture
def db_session():
    """Empty Postgres schema, mirrors test_lookup_models.py pattern.

    Blank rather than the live database because test_list_paginated asserts an
    absolute row total, which only holds on an empty slate.
    """
    with blank_session() as session:
        yield session


def test_create_and_get(db_session):
    svc = LookupSetService(db_session)
    s = svc.create(LookupSetCreate(set_key="region", name="Region"))
    assert s.set_key == "region"
    got = svc.get(s.id)
    assert got.id == s.id


def test_duplicate_set_key_conflict(db_session):
    svc = LookupSetService(db_session)
    svc.create(LookupSetCreate(set_key="region", name="Region"))
    with pytest.raises(AppException) as e:
        svc.create(LookupSetCreate(set_key="region", name="Region 2"))
    assert e.value.status_code == 409


def test_list_paginated(db_session):
    svc = LookupSetService(db_session)
    for i in range(3):
        svc.create(LookupSetCreate(set_key=f"k{i}", name=f"K{i}"))
    res = svc.list(page=1, limit=2, query=None)
    assert res["pagination"]["total"] == 3
    assert len(res["data"]) == 2


def test_update_and_delete(db_session):
    svc = LookupSetService(db_session)
    s = svc.create(LookupSetCreate(set_key="region", name="Region"))
    svc.update(s.id, LookupSetUpdate(name="Regions"))
    assert svc.get(s.id).name == "Regions"
    svc.delete(s.id)
    with pytest.raises(AppException):
        svc.get(s.id)
