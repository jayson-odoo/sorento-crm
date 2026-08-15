"""Where "use stock" may draw from before buying - the global quick setting (AC-3.2).

> "why am I allowed to use stock from other locations? It is either I use stock from BRW,
>  or buy."

Same shape and gates as the planning-mode switch it sits beside: read on the dashboard view
slug (the setting is shown next to the plan it changes), write on `scm.config.manage`, and
the value lives on the singleton GLOBAL `scm.reorder_policy` row.

Every test seeds the global row itself through the SAME atomic upsert the route uses, never
a bare `LIMIT 1` borrow off whatever the database happens to hold. Everything runs inside the
rolled-back savepoint, so writes never escape.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.scm.conftest import as_user, requires_pg, seed_user

pytestmark = requires_pg

URL = "/api/v1/scm/config/cover-scope"


def _client(scm_app, role_slug):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db


def _seed_global_policy(db, **updates):
    from app.services.scm.reorder_policy import upsert_global_policy

    upsert_global_policy(db, **updates)
    db.flush()


def _global_row(db):
    return db.execute(text(
        "SELECT policy_type, dead_stock_days, cover_scope FROM scm.reorder_policy "
        "WHERE scope_type = 'global'"
    )).fetchone()


def test_get_reads_the_global_rows_value(scm_app):
    app, db = _client(scm_app, "purchasing")
    _seed_global_policy(db, cover_scope="all_locations")
    with TestClient(app) as c:
        res = c.get(URL)
    assert res.status_code == 200, res.text
    assert res.json() == {"cover_scope": "all_locations"}


def test_an_unset_value_reads_as_own_pool(scm_app):
    """The captain's answer is the default: a row that predates the column, or a value
    nobody ever set, means "my own site", not "anywhere"."""
    app, db = _client(scm_app, "purchasing")
    _seed_global_policy(db, policy_type="reorder_point")
    db.execute(text("UPDATE scm.reorder_policy SET cover_scope = NULL WHERE scope_type = 'global'"))
    db.flush()
    with TestClient(app) as c:
        res = c.get(URL)
    assert res.json() == {"cover_scope": "own_pool"}


def test_put_round_trips_both_ways(scm_app):
    app, db = _client(scm_app, "purchasing")
    _seed_global_policy(db, cover_scope="own_pool")
    with TestClient(app) as c:
        put = c.put(URL, json={"cover_scope": "all_locations"})
        assert put.status_code == 200, put.text
        assert put.json() == {"cover_scope": "all_locations"}
        assert c.get(URL).json() == {"cover_scope": "all_locations"}

        back = c.put(URL, json={"cover_scope": "own_pool"})
        assert back.status_code == 200, back.text
        assert c.get(URL).json() == {"cover_scope": "own_pool"}


def test_put_touches_only_cover_scope(scm_app):
    """The rest of the global row survives the save - same rule as the planning-mode flip."""
    app, db = _client(scm_app, "purchasing")
    _seed_global_policy(db, policy_type="reorder_level", dead_stock_days=181,
                        cover_scope="own_pool")
    with TestClient(app) as c:
        assert c.put(URL, json={"cover_scope": "all_locations"}).status_code == 200

    row = _global_row(db)
    assert row[0] == "reorder_level"
    assert int(row[1]) == 181
    assert row[2] == "all_locations"


def test_an_unknown_value_is_rejected(scm_app):
    app, db = _client(scm_app, "purchasing")
    _seed_global_policy(db, cover_scope="own_pool")
    with TestClient(app) as c:
        assert c.put(URL, json={"cover_scope": "anywhere_i_like"}).status_code == 422
        assert c.put(URL, json={}).status_code == 422
    assert _global_row(db)[2] == "own_pool"


def test_get_rbac_denied_without_view(scm_app):
    app, _ = _client(scm_app, None)  # bare user, no scm.dashboard.view
    with TestClient(app) as c:
        assert c.get(URL).status_code == 403


def test_put_rbac_denied_without_manage(scm_app):
    """A view-only user reads the setting but cannot move it."""
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, None)
    rid = str(_uuid.uuid4())
    db.execute(text(
        "INSERT INTO user_roles (id, slug, name, is_trashed, is_protected, is_default, created_at) "
        "VALUES (:id, :slug, 'View Only', false, false, false, :now)"
    ), {"id": rid, "slug": f"scm-viewonly-cs-{rid[:8]}", "now": datetime.utcnow()})
    pid = db.execute(text(
        "SELECT id FROM user_permissions WHERE slug = 'scm.dashboard.view'"
    )).scalar()
    db.execute(text(
        "INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at) "
        "VALUES (:id, :r, :p, :now)"
    ), {"id": str(_uuid.uuid4()), "r": rid, "p": pid, "now": datetime.utcnow()})
    from app.models.user import UserRoleAssignment
    db.add(UserRoleAssignment(user_id=uid, role_id=rid))
    db.flush()
    as_user(app, gcu, gcuak, uid)
    with TestClient(app) as c:
        assert c.get(URL).status_code == 200
        assert c.put(URL, json={"cover_scope": "all_locations"}).status_code == 403


def test_the_engine_reads_the_same_column(scm_app):
    """`load_policies` feeds the resolver, so the knob has to reach it - a value the plan
    cannot see is a setting that does nothing."""
    from app.services.scm.reorder_engine import load_policies

    app, db = _client(scm_app, "purchasing")
    _seed_global_policy(db, cover_scope="all_locations")
    rows = [p for p in load_policies(db) if p["scope_type"] == "global"]
    assert rows and all("cover_scope" in p for p in rows)
    assert any(p["cover_scope"] == "all_locations" for p in rows)


def test_seeded_defaults_start_at_own_pool(scm_app):
    """A brand new install gets the captain's answer, not the old behaviour."""
    from app.services.scm.reorder_engine import ensure_reorder_policy_defaults

    app, db = _client(scm_app, "purchasing")
    db.execute(text("DELETE FROM scm.reorder_policy WHERE scope_type = 'global'"))
    db.flush()
    ensure_reorder_policy_defaults(db)
    db.flush()
    assert _global_row(db)[2] == "own_pool"
