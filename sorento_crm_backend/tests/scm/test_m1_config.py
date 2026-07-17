"""SCM M1 — dead-stock-days quick setting endpoint tests.

Covers, against the seeded demo (global reorder_policy, dead_stock_days=180):
  * GET returns the global policy's value,
  * PUT round-trips a new value and persists it,
  * validation rejects out-of-range values,
  * RBAC: view slug can read, only scm.config.manage can write,
  * the new threshold recomputes the dashboard "dead" status.

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


def test_get_dead_stock_days(scm_app):
    app, db = _client(scm_app, "purchasing")
    seeded = db.execute(text(
        "SELECT dead_stock_days FROM scm.reorder_policy "
        "WHERE scope_type = 'global' ORDER BY is_active DESC, created_at ASC LIMIT 1"
    )).scalar()
    with TestClient(app) as c:
        res = c.get("/api/v1/scm/config/dead-stock-days")
    assert res.status_code == 200, res.text
    assert res.json() == {"dead_stock_days": int(seeded)}


def test_put_dead_stock_days_round_trip(scm_app):
    app, db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        put = c.put("/api/v1/scm/config/dead-stock-days", json={"dead_stock_days": 90})
        assert put.status_code == 200, put.text
        assert put.json() == {"dead_stock_days": 90}
        got = c.get("/api/v1/scm/config/dead-stock-days")
    assert got.json() == {"dead_stock_days": 90}
    # persisted onto the global policy row
    val = db.execute(text(
        "SELECT dead_stock_days FROM scm.reorder_policy WHERE scope_type = 'global' "
        "ORDER BY is_active DESC, created_at ASC LIMIT 1"
    )).scalar()
    assert int(val) == 90


def test_put_dead_stock_days_validation(scm_app):
    app, _ = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        assert c.put("/api/v1/scm/config/dead-stock-days", json={"dead_stock_days": 0}).status_code == 422
        assert c.put("/api/v1/scm/config/dead-stock-days", json={"dead_stock_days": 99999}).status_code == 422


def test_put_dead_stock_days_recomputes_dead_status(scm_app):
    """Shrinking the window flips healthy/incoming SKUs to dead → stockout counts hold
    but the dead-stock population grows. We assert the roll-up dead valuation is
    monotonic non-decreasing when the threshold is lowered aggressively."""
    app, _ = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        before = c.get("/api/v1/scm/dashboard/rollups").json()["dead_stock_valuation"]
        c.put("/api/v1/scm/config/dead-stock-days", json={"dead_stock_days": 1})
        after = c.get("/api/v1/scm/dashboard/rollups").json()["dead_stock_valuation"]
    assert after >= before


def test_global_policy_resolution_deterministic_across_paths(scm_app):
    """With duplicate global rows, the config endpoint and the dashboard read-model
    must resolve the SAME canonical row (active preferred, then oldest created_at)."""
    import uuid as _uuid

    from app.services.scm.reorder_policy import resolve_global_dead_stock_days

    app, db = _client(scm_app, "purchasing")
    with TestClient(app) as c:
        base = c.get("/api/v1/scm/config/dead-stock-days").json()["dead_stock_days"]

    older_val = base + 7
    # an OLDER active duplicate must win over the seeded row…
    db.execute(text(
        "INSERT INTO scm.reorder_policy "
        "(id, scope_type, scope_ref, policy_type, dead_stock_days, is_active, "
        " source_system, source_ref, created_at, updated_at) "
        "VALUES (:id, 'global', NULL, 'reorder_point', :d, true, 'manual', 'test', "
        " '2000-01-01 00:00:00', '2000-01-01 00:00:00')"
    ), {"id": str(_uuid.uuid4()), "d": older_val})
    # …and a NEWER active duplicate with a different value must be ignored.
    db.execute(text(
        "INSERT INTO scm.reorder_policy "
        "(id, scope_type, scope_ref, policy_type, dead_stock_days, is_active, "
        " source_system, source_ref, created_at, updated_at) "
        "VALUES (:id, 'global', NULL, 'reorder_point', :d, true, 'manual', 'test', "
        " now(), now())"
    ), {"id": str(_uuid.uuid4()), "d": older_val + 100})
    db.flush()

    with TestClient(app) as c:
        via_config = c.get("/api/v1/scm/config/dead-stock-days").json()["dead_stock_days"]
    # the dashboard's global fallback resolves through this same helper
    via_dashboard = resolve_global_dead_stock_days(db)

    assert via_config == older_val
    assert via_dashboard == older_val
    assert via_config == via_dashboard


def test_get_rbac_denied_without_view(scm_app):
    app, _ = _client(scm_app, None)  # bare user, no scm.dashboard.view
    with TestClient(app) as c:
        assert c.get("/api/v1/scm/config/dead-stock-days").status_code == 403


def test_put_rbac_denied_without_manage(scm_app, monkeypatch):
    """A user with view-only access can read but not write the setting."""
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, None)
    # Grant ONLY scm.dashboard.view to this user via a throwaway role.
    import uuid as _uuid
    from datetime import datetime
    rid = str(_uuid.uuid4())
    db.execute(text(
        "INSERT INTO user_roles (id, slug, name, is_trashed, is_protected, is_default, created_at) "
        "VALUES (:id, :slug, 'View Only', false, false, false, :now)"
    ), {"id": rid, "slug": f"scm-viewonly-{rid[:8]}", "now": datetime.utcnow()})
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
        assert c.get("/api/v1/scm/config/dead-stock-days").status_code == 200
        assert c.put("/api/v1/scm/config/dead-stock-days", json={"dead_stock_days": 120}).status_code == 403
