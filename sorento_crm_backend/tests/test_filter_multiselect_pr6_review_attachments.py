"""FILTER-MULTISELECT PR6 review round: attachments, several companies that are BOTH in the caller's scope
(scope {Sorento, Mocha}, a row in each): picking both returns both, picking one returns one, on the list and the
drive routes. Postgres only; rows seeded by the sibling resources fixtures.
"""
from __future__ import annotations

import pytest

from app.services.user_service import UserPermissionService
from tests._multi_filter_client import SORENTO, get, open_client
from tests.test_resources_multi_filters import DRIVE, LIST, MOCHA, db, world  # noqa: F401  (fixtures)


@pytest.fixture
def client(db, monkeypatch):
    with open_client(db, monkeypatch, scope=frozenset({SORENTO, MOCHA})) as (c, _a):
        monkeypatch.setattr(
            UserPermissionService,
            "get_user_permission_slugs",
            lambda self, uid: ["resource.attachments.view", "resource.attachment_directories.view"],
        )
        yield c


def _ids(client, url, pairs):
    resp = get(client, url, [("limit", 200), *pairs])
    assert resp.status_code == 200, resp.text
    return {r["id"] for r in resp.json()["data"] if r.get("kind", "file") == "file"}


@pytest.mark.parametrize("url", [LIST, DRIVE])
def test_two_companies_both_in_scope_union(client, world, url):
    s = world
    assert _ids(client, url, [("company", f"{SORENTO},{MOCHA}")]) & {s["a"].id, s["c"].id, s["d"].id} == {s["a"].id, s["c"].id, s["d"].id}
    assert _ids(client, url, [("company", SORENTO), ("company", MOCHA)]) & {s["a"].id, s["c"].id, s["d"].id} == {s["a"].id, s["c"].id, s["d"].id}


@pytest.mark.parametrize("url", [LIST, DRIVE])
def test_picking_one_company_returns_only_its_rows(client, world, url):
    s = world
    ours = {s["a"].id, s["b"].id, s["c"].id, s["d"].id}
    assert _ids(client, url, [("company", MOCHA)]) & ours == {s["c"].id}
    assert _ids(client, url, [("company", SORENTO)]) & ours == {s["a"].id, s["d"].id}
