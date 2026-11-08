"""PUT /accessories/{id}/colours locks the accessory row before it deletes and re-inserts the list."""
from __future__ import annotations

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.services.company_scope import register_company_scope_listeners
from tests._pg_fixture import blank_session
from tests.test_accessories import EDIT, VIEW, _accessory, _caller, _name  # noqa: F401


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


def test_put_colours_reads_the_accessory_for_update(db, monkeypatch):
    from sqlalchemy.orm import Query

    client = _caller(db, {VIEW, EDIT}, monkeypatch)
    row = _accessory(db, _name("LOCKED"))
    locked = []
    real = Query.with_for_update

    def spy(self, *args, **kwargs):
        locked.append(1)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Query, "with_for_update", spy)
    response = client.put(
        f"/api/v1/master-data/accessories/{row.id}/colours", json={"colours": [{"hex": "#1f2937"}]}
    )
    assert response.status_code == 200, response.text
    assert locked
