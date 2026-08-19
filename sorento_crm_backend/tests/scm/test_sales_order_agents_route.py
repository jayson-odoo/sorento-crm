"""`GET /scm/sales-orders/agents` over HTTP - RBAC + shape.

Added because the Agent filter/select on the SCM sales-orders screens was, until now, fed
by the sales-agents master's own `GET /master-data/sales-agents/` - gated on
`master_data.sales_agents.view`. On the stack DB only Admin + integration roles hold that
slug; a Purchasing role (this route's own `purchasing` fixture role) holds
`scm.dashboard.view`, the sales-order read permission, and nothing else, so the select 403'd
for exactly the role that needs it. This endpoint is served under the SO read gate instead.

Declared before `/sales-orders/{so_id}` in the router, so `GET /sales-orders/agents` never
gets swallowed as a `so_id` lookup - covered implicitly by every 200 here returning the
agents shape, never a 404 `SO not found`.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.scm.conftest import as_user, requires_pg, seed_user

pytestmark = requires_pg

MARKER = "ZZTSOAGTRT"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


def _client(scm_app, role_slug):
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, role_slug)
    as_user(app, gcu, gcuak, uid)
    return app, db


def _world(db):
    from app.models.sales_agent import SalesAgent

    active_a = SalesAgent(id=_u(), sales_agent=_code("AGT"), person_label="Route Jeremy",
                          is_active=True)
    active_b = SalesAgent(id=_u(), sales_agent=_code("AGT"), person_label="Route Cindy",
                          is_active=True)
    inactive = SalesAgent(id=_u(), sales_agent=_code("AGT"), person_label="Route Retired",
                          is_active=False)
    db.add_all([active_a, active_b, inactive])
    db.flush()
    return {"active_a": active_a, "active_b": active_b, "inactive": inactive}


def test_a_purchasing_user_reads_the_active_agents(scm_app):
    """The route this whole file exists for: `scm.dashboard.view` is enough, not the
    sales-agents master's own CRUD permission."""
    app, db = _client(scm_app, "purchasing")
    world = _world(db)

    with TestClient(app) as c:
        res = c.get("/api/v1/scm/sales-orders/agents")

    assert res.status_code == 200, res.text
    by_id = {row["id"]: row for row in res.json()}

    assert world["active_a"].id in by_id
    assert by_id[world["active_a"].id]["sales_agent"] == world["active_a"].sales_agent
    assert by_id[world["active_a"].id]["person_label"] == "Route Jeremy"
    assert world["active_b"].id in by_id
    assert world["inactive"].id not in by_id


def test_q_narrows_by_code_or_label_substring(scm_app):
    app, db = _client(scm_app, "purchasing")
    world = _world(db)

    with TestClient(app) as c:
        res = c.get("/api/v1/scm/sales-orders/agents", params={"q": "Route Cindy"})

    assert res.status_code == 200, res.text
    ids = {row["id"] for row in res.json()}

    assert ids == {world["active_b"].id}


def test_denied_without_dashboard_view(scm_app):
    app, _ = _client(scm_app, None)

    with TestClient(app) as c:
        res = c.get("/api/v1/scm/sales-orders/agents")

    assert res.status_code == 403
