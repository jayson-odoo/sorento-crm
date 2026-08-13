"""SCM S1 - universal planning-mode quick setting endpoint tests (UAC A).

Covers, against a MARKER global policy row this suite seeds itself:
  * GET derives auto|manual from the global row's policy_type,
  * PUT flips policy_type ONLY (every other column on the row is untouched),
  * RBAC: view slug can read, only scm.config.manage can write,
  * an unrecognised/legacy policy_type still reads as auto (never crashes).

`_seed_global_policy` upserts the singleton GLOBAL row (`scm.reorder_policy`,
`scope_type='global'`, partial-unique-indexed by migration 353) to known marker
values inside the test's own rolled-back savepoint - never a bare `LIMIT 1` borrow
of whatever the live/prod-copy database happens to hold (repo rule, CLAUDE.md):
that pattern returns `None` on an empty CI database (`TypeError` unpacking the row)
and, even when it does return something, asserts against data the test never wrote.
Every test here asserts only against values it seeded or wrote itself.

Everything runs inside the rolled-back savepoint, so writes never escape.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.scm.conftest import as_user, requires_pg, seed_user

pytestmark = requires_pg


def _client(scm_app, role_slug):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db


def _seed_global_policy(
    db,
    *,
    policy_type: str = "reorder_point",
    dead_stock_days: int = 181,
    overstock_days: int = 121,
    safety_days: float = 8.25,
):
    """Upsert the singleton GLOBAL row to known marker values.

    Works whether a global row already exists (the local prod-copy database
    always has one) or not (a freshly bootstrapped CI database has none): it is
    the SAME atomic upsert the route itself uses (`upsert_global_policy`), so
    seeding can never race the uniqueness constraint it seeds under.
    """
    from app.services.scm.reorder_policy import upsert_global_policy

    upsert_global_policy(
        db,
        policy_type=policy_type,
        dead_stock_days=dead_stock_days,
        overstock_days=overstock_days,
        safety_days=safety_days,
    )
    db.flush()


def _global_row(db):
    """Read back the (now-singleton) global row THIS test seeded or wrote."""
    return db.execute(text(
        "SELECT id, policy_type, dead_stock_days, overstock_days, safety_days "
        "FROM scm.reorder_policy WHERE scope_type = 'global'"
    )).fetchone()


def test_get_planning_mode_derives_from_policy_type(scm_app):
    app, db = _client(scm_app, "purchasing")
    _seed_global_policy(db, policy_type="reorder_level")
    with TestClient(app) as c:
        res = c.get("/api/v1/scm/config/planning-mode")
    assert res.status_code == 200, res.text
    assert res.json() == {"mode": "manual"}


def test_put_planning_mode_round_trip_manual_then_auto(scm_app):
    app, db = _client(scm_app, "purchasing")
    _seed_global_policy(db, policy_type="reorder_point")
    with TestClient(app) as c:
        put = c.put("/api/v1/scm/config/planning-mode", json={"mode": "manual"})
        assert put.status_code == 200, put.text
        assert put.json() == {"mode": "manual"}
        got = c.get("/api/v1/scm/config/planning-mode")
        assert got.json() == {"mode": "manual"}

        back = c.put("/api/v1/scm/config/planning-mode", json={"mode": "auto"})
        assert back.status_code == 200, back.text
        assert back.json() == {"mode": "auto"}

    row = _global_row(db)
    assert row[1] == "reorder_point"


def test_put_planning_mode_touches_only_policy_type(scm_app):
    """The rest of the global row (dead_stock_days, overstock_days, safety_days, ...)
    must survive the flip untouched - AC-A1."""
    app, db = _client(scm_app, "purchasing")
    _seed_global_policy(
        db, policy_type="reorder_point",
        dead_stock_days=181, overstock_days=121, safety_days=8.25,
    )
    before = _global_row(db)
    before_dead, before_over, before_safety = before[2], before[3], before[4]

    with TestClient(app) as c:
        assert c.put(
            "/api/v1/scm/config/planning-mode", json={"mode": "manual"}
        ).status_code == 200

    after = _global_row(db)
    assert after[1] == "reorder_level"
    assert after[2] == before_dead
    assert after[3] == before_over
    assert after[4] == before_safety


def test_planning_mode_unrecognised_policy_type_reads_as_auto(scm_app):
    """A legacy/periodic_review row is auto, never manual and never a crash."""
    app, db = _client(scm_app, "purchasing")
    _seed_global_policy(db, policy_type="reorder_point")
    row = _global_row(db)
    db.execute(
        text("UPDATE scm.reorder_policy SET policy_type = 'periodic_review' WHERE id = :id"),
        {"id": row[0]},
    )
    db.flush()
    with TestClient(app) as c:
        res = c.get("/api/v1/scm/config/planning-mode")
    assert res.status_code == 200, res.text
    assert res.json() == {"mode": "auto"}


def test_get_planning_mode_rbac_denied_without_view(scm_app):
    app, _ = _client(scm_app, None)  # bare user, no scm.dashboard.view
    with TestClient(app) as c:
        assert c.get("/api/v1/scm/config/planning-mode").status_code == 403


def test_put_planning_mode_rbac_denied_without_manage(scm_app):
    """A user with view-only access can read but not write the setting."""
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, None)
    import uuid as _uuid
    from datetime import datetime
    rid = str(_uuid.uuid4())
    db.execute(text(
        "INSERT INTO user_roles (id, slug, name, is_trashed, is_protected, is_default, created_at) "
        "VALUES (:id, :slug, 'View Only', false, false, false, :now)"
    ), {"id": rid, "slug": f"scm-viewonly-pm-{rid[:8]}", "now": datetime.utcnow()})
    pid = db.execute(text("SELECT id FROM user_permissions WHERE slug = 'scm.dashboard.view'")).scalar()
    db.execute(text(
        "INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at) "
        "VALUES (:id, :r, :p, :now)"
    ), {"id": str(_uuid.uuid4()), "r": rid, "p": pid, "now": datetime.utcnow()})
    from app.models.user import UserRoleAssignment
    db.add(UserRoleAssignment(user_id=uid, role_id=rid))
    db.flush()
    as_user(app, gcu, gcuak, uid)
    with TestClient(app) as c:
        assert c.get("/api/v1/scm/config/planning-mode").status_code == 200
        assert c.put(
            "/api/v1/scm/config/planning-mode", json={"mode": "manual"}
        ).status_code == 403
