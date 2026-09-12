"""AC-N7 - the loading plan's sales-order cut-off becomes a window (From/To), like reorder
planning's own.

`PLAN-scm-loading-plan-lines-feedback-12sep.md`, AC-N7. `plan_horizon_date` has always been
end-only ("Sales order cut-off": a line needed after it is not counted, an undated line
always is). This adds the start-side twin, `plan_horizon_start`, the same column and the same
reading `scm.reorder_run.plan_horizon_start` (migration 499) already gave the reorder engine -
`container_request_service.build` already threads a `plan_horizon_start` kwarg into
`_open_need` / `_project_open_need` for that reason, but nothing on the loading plan's own
lifecycle (the model column, `create_record`, the two routes, `record_dict`,
`build_for_plan`) reads or writes it yet.

TEST-FIRST: `scm.loading_plan` carries no `plan_horizon_start` column and
`loading_plan_service.create_record` takes no such keyword when this file is written, so
every test below fails immediately - a `TypeError` on the missing keyword/column, or a wrong
HTTP status where a validator does not exist yet - never an import error.

Postgres, marker-prefixed, every chain seeded here (CI's database is empty).
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi.testclient import TestClient

from app.models.order import SalesOrder, SalesOrderLine
from app.models.scm import LoadingPlan
from app.services.scm import container_request_service as build_svc
from app.services.scm import loading_plan_service as plan_svc
from tests._pg_fixture import pg_session
from tests.scm.conftest import requires_pg
from tests.scm.test_loading_plan import World
from tests.scm.test_loading_plan_record import PLANS_URL, _create, _world
from tests.scm.test_outstanding_import_routes import as_company_user
from tests.scm.test_plan_owned_statement import World as StatementWorld
from tests.scm.test_plan_owned_statement import MARKER as STATEMENT_MARKER
from tests.scm.test_plan_owned_statement import _row

pytestmark = requires_pg


def _retail_need_by(db, w: "StatementWorld", key: str, qty: float, *, required=None) -> None:
    """Open retail demand due on a stated date, or none - the window's own predicate."""
    so = SalesOrder(
        id=str(uuid.uuid4()),
        so_number=f"{STATEMENT_MARKER}-SO-{uuid.uuid4().hex[:8]}",
        status="open",
        demand_class="retail",
        order_date=date(2026, 1, 1),
    )
    db.add(so)
    db.flush()
    db.add(
        SalesOrderLine(
            id=str(uuid.uuid4()),
            sales_order_id=so.id,
            product_id=w.product(key).id,
            qty_ordered=qty,
            qty_delivered=0,
            line_status="open",
            purchasing_status="not_reviewed",
            required_date=required,
        )
    )
    db.flush()


# --------------------------------------------------------------------------- #
# (a) create_record persists and echoes the window
# --------------------------------------------------------------------------- #


def test_create_record_persists_and_echoes_the_window():
    with pg_session() as db:
        w = StatementWorld(db)

        plan = plan_svc.create_record(
            db,
            supplier_id=str(w.supplier.id),
            plan_horizon_start=date(2026, 10, 1),
            plan_horizon_date=date(2026, 10, 31),
            document_kind="none",
            source_attachment_id=None,
            actor="Ms Tee",
        )

        assert plan.plan_horizon_start == date(2026, 10, 1)
        assert plan.plan_horizon_date == date(2026, 10, 31)

        out = plan_svc.record_dict(db, plan)
        assert out["plan_horizon_start"] == "2026-10-01"
        assert out["plan_horizon_date"] == "2026-10-31"


# --------------------------------------------------------------------------- #
# (b) build_for_plan reads the window off the plan row
# --------------------------------------------------------------------------- #


def test_build_for_plan_excludes_demand_needed_before_the_window_start():
    """A line due before From is not counted; one due within it, and one carrying no
    required date at all, both are (the same reading the end date already gives it)."""
    with pg_session() as db:
        w = StatementWorld(db)
        # `LoadingPlan(...)` directly, not `create_record` (this half of the test is about
        # the BUILD reading the column off the row, not about the service that writes it -
        # AC-N7's (a) already pins that). A model missing the column raises here immediately.
        plan = LoadingPlan(
            id=str(uuid.uuid4()),
            supplier_id=w.supplier.id,
            status="planning",
            plan_horizon_date=date(2026, 10, 31),
            plan_horizon_start=date(2026, 10, 1),
            document_kind="stock_list",
            line_edits={},
        )
        db.add(plan)
        db.flush()

        w.stock_row("A", packed=5, plan_id=str(plan.id))
        w.link("A")
        _retail_need_by(db, w, "A", 10, required=date(2026, 9, 15))  # before From: excluded
        _retail_need_by(db, w, "A", 20, required=date(2026, 10, 15))  # inside the window
        _retail_need_by(db, w, "A", 5, required=None)  # undated: always counted

        out = build_svc.build_for_plan(db, plan_id=str(plan.id))

        row = _row(out, w.code("A"))
        assert row["open_so_need"] == 25.0


# --------------------------------------------------------------------------- #
# (c) the routes: validated, and persisted
# --------------------------------------------------------------------------- #


def test_creating_a_plan_with_a_start_after_the_end_is_refused(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)

    r = _create(
        TestClient(app),
        str(w.supplier.id),
        plan_horizon_start="2026-10-31",
        plan_horizon_date="2026-10-01",
    )

    assert r.status_code == 422, r.text


def test_changing_the_cut_off_with_a_start_after_the_end_is_refused(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    client = TestClient(app)
    plan = _create(client, str(w.supplier.id)).json()

    r = client.patch(
        f"{PLANS_URL}/{plan['id']}",
        json={"plan_horizon_start": "2026-10-31", "plan_horizon_date": "2026-10-01"},
    )

    assert r.status_code == 422, r.text


def test_a_valid_window_is_created_and_then_changed(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    client = TestClient(app)

    created = _create(
        client,
        str(w.supplier.id),
        plan_horizon_start="2026-10-01",
        plan_horizon_date="2026-10-31",
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["plan_horizon_start"] == "2026-10-01"
    assert body["plan_horizon_date"] == "2026-10-31"

    changed = client.patch(
        f"{PLANS_URL}/{body['id']}",
        json={"plan_horizon_start": "2026-11-01", "plan_horizon_date": "2026-11-30"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["plan_horizon_start"] == "2026-11-01"
    assert changed.json()["plan_horizon_date"] == "2026-11-30"
