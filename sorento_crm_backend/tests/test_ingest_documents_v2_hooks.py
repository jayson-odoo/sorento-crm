"""Group V5 - post-write hooks and committed demand (PLAN section 2.6, D6/D7).

  AC-V5-1   a non-dry sales-order batch runs `plan_exception_service.snapshot`
            before / `generate_batch` after over the touched products,
            `source_documents` = the batch's SO numbers; a hook failure is
            logged, never fails the batch
  AC-V5-2   a non-dry purchase-order batch supersedes (closes) the matching
            active `scm_recommendation` PO line/header exactly as the upload's
            `_supersede_crm_raised_pos` does, and
            `ProjectOrderInquiryService.relink_to_matching_lines` runs with the
            written header ids and `trigger="autocount_ingest"`
  AC-V5-3   a canonical `partial` sales order is stored `open` (D6a); read-back
            reports `open`; the other four canonical words are unchanged;
            `scm.committed_v` counts the open line's outstanding quantity
  AC-V5-4   none of the hooks run on a dry run
  AC-V5-5   `planning_change_service.build_batch` is NOT run by ingest in v2 -
            this is a guard and PASSES TODAY (nothing calls it yet either);
            it stays green through S5 and would only turn red if some future
            change wired it in by mistake

None of the hooks in this group exist on the ingest route yet (`app/api/v1/
external/ingest.py` calls only `service.ingest(...)` then `db.commit()`), so
the ACTIVE half of AC-V5-1 and AC-V5-2 is RED: no hook is ever called, on a
dry run or not. AC-V5-4's dry-run tests use that SAME absence to assert "zero
calls" and so PASS TODAY, trivially, since there is nothing to skip yet - they
turn into a real guard only once the hooks exist. AC-V5-3 is RED because
`SALES_ORDER_STATUS_MAP["partial"]` still maps to `partially_delivered` today
(D6a is not applied); its "the other four words are unchanged" parametrize and
AC-V5-5's guard both PASS TODAY, on purpose - they are regression pins, not
tests of the new behaviour.

Substrate reused byte for byte from `test_ingest_documents` per the tester
brief (`env`, `_Env`, `_ref`, the record builders) - no new fixture. Every row
this file seeds directly (the CRM-raised PO, its line) is dropped under the
`MARKER` prefix or inside the same rolled-back scratch-schema transaction as
everything else `env` seeds.
"""
from __future__ import annotations

import importlib.util
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.services.project_order_inquiry_service import ProjectOrderInquiryService
from app.services.scm import plan_exception_service

import tests._pg_fixture as pg_fixture
from tests.test_ingest_documents import (
    INGEST_PO,
    INGEST_SO,
    MARKER,
    READ_SO,
    _po_line,
    _po_record,
    _ref,
    _so_line,
    _so_record,
    env,  # noqa: F401 - pytest fixture, imported for reuse per the tester brief
)

__all__ = ["env"]


# ------------------------------------------------------------------ seed helpers
def _crm_raised_po(env, *, supplier_id: str, product_id: str, qty_ordered="20") -> tuple[
    PurchaseOrder, PurchaseOrderLine
]:
    """A purchase order + line the CRM itself raised from a reorder-plan
    `bulk_confirm` - the exact `source_system`/`status` shape
    `outstanding_import_service._supersede_crm_raised_pos` already retires for
    the xlsx upload (`tests/scm/test_outstanding_supersedes_crm_po.py`)."""
    po = PurchaseOrder(
        po_number=f"{MARKER}-CRMPO-{uuid.uuid4().hex[:8]}".upper(),
        supplier_id=supplier_id,
        status="active",
        source_system="scm_recommendation",
        source_ref="scm",
        company_id=env.company_a,
    )
    env.db.add(po)
    env.db.flush()
    line = PurchaseOrderLine(
        purchase_order_id=po.id,
        product_id=product_id,
        qty_ordered=Decimal(str(qty_ordered)),
        qty_received=Decimal("0"),
        line_status="open",
        source_system="scm_recommendation",
        source_ref=f"{MARKER}-rec-{uuid.uuid4().hex[:8]}",
        company_id=env.company_a,
    )
    env.db.add(line)
    env.db.flush()
    env.db.commit()  # survive the dry-run rollback tests the same way `_Env` does
    return po, line


def _po_line_status(env, line_id: str) -> str:
    return env.db.execute(
        text("SELECT line_status FROM purchase_order_lines WHERE id = :i"), {"i": line_id}
    ).scalar()


def _po_status(env, po_id: str) -> str:
    return env.db.execute(
        text("SELECT status FROM purchase_orders WHERE id = :i"), {"i": po_id}
    ).scalar()


def _plan_exception_batches_for(env, so_number: str) -> list[dict]:
    """Every `plan_exception_batch` row naming `so_number` in its `source_documents`.

    Bare table name, not `scm.plan_exception_batch`: the scratch fixture's
    `search_path` is what routes an unqualified name into the translated
    scratch schema (`tests/_pg_fixture.py`); a literal `scm.` prefix would
    instead hit the real `scm` schema outside the sandbox
    (`test_ingest_documents_v2_links.py` documents the same convention for
    `order_link_claim`).
    """
    rows = (
        env.db.execute(
            text(
                "SELECT id, source_documents FROM plan_exception_batch "
                "WHERE source_documents ? :so"
            ),
            {"so": so_number},
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


_MIGRATION_428 = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "428_order_inquiry_ack_state.py"
)


def _committed_v_available() -> bool:
    """Whether the migration whose body this file replays for the scratch schema
    is even present in this checkout - a defensive guard, not part of the AC."""
    return _MIGRATION_428.exists()


def _create_committed_v_in_scratch_schema(env) -> None:
    """Recreate `scm.committed_v` (migration 428's body) inside THIS test's own
    scratch schema.

    `blank_session` builds its schema from `Base.metadata.create_all` - ORM
    tables only. `committed_v` is a hand-written VIEW a migration creates with
    raw SQL, so it does not exist there unless a test creates it. The
    migration's literal `scm.` / `projects.` qualifiers are rewritten to this
    run's translated scratch-schema names first, or `CREATE OR REPLACE VIEW
    scm.committed_v` would silently target the REAL `scm` schema outside the
    sandbox rather than the isolated one this test reads and writes.
    `scm.committed_v` becomes the bare `committed_v` (created in, and then
    queried from, the scratch run's default schema - first on `search_path`
    either way); `projects.` becomes the translated `{name}_projects` schema,
    which is where the projects-schema tables this view joins actually live.
    """
    spec = importlib.util.spec_from_file_location(
        "_ac_v2_migration_428_committed_v", _MIGRATION_428
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    sql = module._AS_OF_428

    name = pg_fixture._BLANK["name"]
    sql = sql.replace("scm.committed_v", "committed_v")
    sql = sql.replace("projects.", f'"{name}_projects".')
    env.db.execute(text(sql))


def _committed_for_product(env, product_id: str) -> float:
    return float(
        env.db.execute(
            text("SELECT COALESCE(SUM(committed), 0) FROM committed_v WHERE product_id = :p"),
            {"p": product_id},
        ).scalar()
    )


# ================================================================== AC-V5-1
class TestPlanExceptionHook:
    def test_a_non_dry_sales_order_batch_writes_a_plan_exception_batch_row(self, env):
        """AC-V5-1. `plan_exception_service.generate_batch` must actually run,
        over the product the pushed line names, and record the SO number that
        triggered it - the same way a confirmed reorder-plan restatement does.
        """
        so_number = f"{MARKER}-SO-{uuid.uuid4().hex[:8]}"
        record = _so_record(env, number=so_number)

        res = env.post(INGEST_SO, [record])

        assert res.json()["summary"]["created"] == 1, res.text
        batches = _plan_exception_batches_for(env, so_number)
        assert len(batches) == 1, (
            "AC-V5-1: no plan_exception_batch row was generated after a "
            "non-dry sales-order ingest - the post-write hook "
            "(plan_exception_service.snapshot before / generate_batch after) "
            "is not wired into ingest.py yet"
        )

    def test_the_hook_actually_runs_and_a_failure_inside_it_never_fails_the_batch(
        self, env, monkeypatch
    ):
        """AC-V5-1, second half. `generate_batch` failing must be logged, never
        surface as a failed record - but that guarantee is only worth anything
        once the hook is proven to run at all, which is what the call-count
        assertion pins."""
        calls: list[dict] = []

        def _boom(db, **kwargs):
            calls.append(kwargs)
            raise RuntimeError("boom: simulated plan-exception failure")

        monkeypatch.setattr(plan_exception_service, "generate_batch", _boom)

        record = _so_record(env)
        res = env.post(INGEST_SO, [record])

        assert res.status_code == 200, res.text
        assert res.json()["records"][0]["outcome"] == "created", res.text
        assert len(calls) == 1, (
            "AC-V5-1: plan_exception_service.generate_batch was never called by "
            "the ingest route - the hook does not exist yet"
        )


# ================================================================== AC-V5-2
class TestSupersedeAndRelinkHook:
    def test_a_non_dry_po_batch_supersedes_the_matching_crm_raised_po_line(self, env):
        """AC-V5-2, supersede half. Mirrors the upload's own proof in
        `tests/scm/test_outstanding_supersedes_crm_po.py`: an active,
        CRM-raised (`scm_recommendation`) PO line for the SAME (product,
        supplier) is closed once AutoCount confirms the same physical order,
        and an emptied header closes with it."""
        supplier_id = env.refs.resolve(entity_type="suppliers", source_ref=env.supplier_ref)
        product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)
        crm_po, crm_line = _crm_raised_po(env, supplier_id=supplier_id, product_id=product_id)

        record = _po_record(
            env,
            supplier_ref=env.supplier_ref,
            lines=[_po_line(env, product_ref=env.product_ref, qty_ordered=5)],
        )

        res = env.post(INGEST_PO, [record])

        assert res.json()["records"][0]["outcome"] == "created", res.text
        assert _po_line_status(env, crm_line.id) == "closed", (
            "AC-V5-2: the CRM-raised PO line was not superseded by the "
            "AutoCount push - the supersede hook is not wired into ingest.py "
            "yet"
        )
        assert _po_status(env, crm_po.id) == "closed", (
            "the CRM PO's only line closed, so the header must close with it"
        )

    def test_a_non_dry_po_batch_relinks_placements_with_the_autocount_trigger(
        self, env, monkeypatch
    ):
        """AC-V5-2, relink half. `ProjectOrderInquiryService.relink_to_matching_lines`
        must run over the header(s) this batch just wrote, tagged
        `trigger="autocount_ingest"` so the relink audit can tell an AutoCount
        push apart from the xlsx upload / PO-history import that also call it."""
        calls: list[dict] = []

        def _fake_relink(self, po_ids, *, actor_user_id=None, trigger=None):
            calls.append(
                {"po_ids": [str(i) for i in po_ids], "actor_user_id": actor_user_id,
                 "trigger": trigger}
            )
            return 0

        monkeypatch.setattr(
            ProjectOrderInquiryService, "relink_to_matching_lines", _fake_relink
        )

        record = _po_record(env, supplier_ref=env.supplier_ref)
        res = env.post(INGEST_PO, [record])
        assert res.json()["records"][0]["outcome"] == "created", res.text

        header = env.header("purchase_orders", record["source_ref"])
        assert len(calls) == 1, (
            "AC-V5-2: ProjectOrderInquiryService.relink_to_matching_lines was "
            "never called by the ingest route - the relink hook does not "
            "exist yet"
        )
        assert calls[0]["po_ids"] == [str(header["id"])]
        assert calls[0]["trigger"] == "autocount_ingest"


# ================================================================== AC-V5-3
class TestPartialSalesOrderIsCommittedDemand:
    def test_a_partial_sales_order_is_stored_open_not_partially_delivered(self, env):
        """AC-V5-3 / D6a. `partial` maps to stored `open`; the per-line
        `qty_delivered` already carries the partial fact, so nothing else has
        to widen to admit it as committed demand."""
        record = _so_record(
            env,
            status="partial",
            lines=[_so_line(env, warehouse_ref=env.warehouse_ref, qty_ordered=10,
                             qty_delivered=4)],
        )

        res = env.post(INGEST_SO, [record])

        assert res.json()["records"][0]["outcome"] == "created", res.text
        header = env.header("sales_orders", record["source_ref"])
        assert header["status"] == "open", (
            "AC-V5-3: a canonical 'partial' sales order must be stored 'open' "
            "(D6a) - today it is stored 'partially_delivered'"
        )

    def test_read_back_reports_open_for_a_partial_sales_order(self, env):
        record = _so_record(env, status="partial")

        env.post(INGEST_SO, [record])
        back = env.read(READ_SO, [record["source_ref"]]).json()["records"][0]

        assert back["status"] == "open", (
            "AC-V5-3: read-back of a canonical 'partial' sales order must "
            "report 'open', not 'partially_delivered' or 'partial'"
        )

    @pytest.mark.parametrize("canonical", ["open", "fulfilled", "closed", "cancelled"])
    def test_the_other_four_canonical_words_are_unchanged(self, env, canonical):
        """The other four canonical words must not move - only `partial` is a
        v2 deviation (D6a)."""
        record = _so_record(env, status=canonical)

        res = env.post(INGEST_SO, [record])

        assert res.json()["records"][0]["outcome"] == "created", res.text
        back = env.read(READ_SO, [record["source_ref"]]).json()["records"][0]
        assert back["status"] == canonical

    @pytest.mark.skipif(
        not _committed_v_available(),
        reason="migration 428_order_inquiry_ack_state.py is absent from this checkout",
    )
    def test_a_partial_sales_order_counts_as_committed_demand_in_committed_v(self, env):
        """AC-V5-3, the pinning half. `scm.committed_v`'s book leg admits
        `so.status = 'open' AND sol.line_status = 'open'` - a partial order
        with an open line (10 ordered, 4 delivered) must show 6 units of
        committed demand for that product, the same as any other open line.
        The view is not part of the ORM-built scratch schema, so this test
        recreates migration 428's body inside its own sandbox first."""
        _create_committed_v_in_scratch_schema(env)
        product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)

        record = _so_record(
            env,
            status="partial",
            lines=[_so_line(env, product_ref=env.product_ref, qty_ordered=10,
                             qty_delivered=4)],
        )
        res = env.post(INGEST_SO, [record])
        assert res.json()["records"][0]["outcome"] == "created", res.text

        assert _committed_for_product(env, product_id) == 6.0, (
            "AC-V5-3: a partial SO's open line (10 ordered, 4 delivered) must "
            "count as 6 units of committed demand in scm.committed_v - it "
            "does not while 'partial' is still stored as 'partially_delivered' "
            "(committed_v's book leg only admits so.status = 'open')"
        )


# ================================================================== AC-V5-4
class TestHooksNeverRunOnADryRun:
    def test_a_dry_run_sales_order_batch_writes_no_plan_exception_batch(
        self, env, monkeypatch
    ):
        calls: list[dict] = []

        def _record_call(db, **kwargs):
            calls.append(kwargs)
            return None

        monkeypatch.setattr(plan_exception_service, "generate_batch", _record_call)

        so_number = f"{MARKER}-SO-{uuid.uuid4().hex[:8]}"
        record = _so_record(env, number=so_number)

        res = env.post(INGEST_SO, [record], dry_run=True)

        assert res.json()["dry_run"] is True
        assert len(calls) == 0, "AC-V5-4: generate_batch must never run on a dry run"
        assert _plan_exception_batches_for(env, so_number) == []

    def test_a_dry_run_purchase_order_batch_supersedes_and_relinks_nothing(
        self, env, monkeypatch
    ):
        supplier_id = env.refs.resolve(entity_type="suppliers", source_ref=env.supplier_ref)
        product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)
        crm_po, crm_line = _crm_raised_po(env, supplier_id=supplier_id, product_id=product_id)

        calls: list[dict] = []

        def _fake_relink(self, po_ids, *, actor_user_id=None, trigger=None):
            calls.append({"po_ids": list(po_ids), "trigger": trigger})
            return 0

        monkeypatch.setattr(
            ProjectOrderInquiryService, "relink_to_matching_lines", _fake_relink
        )

        record = _po_record(
            env,
            supplier_ref=env.supplier_ref,
            lines=[_po_line(env, product_ref=env.product_ref, qty_ordered=5)],
        )

        res = env.post(INGEST_PO, [record], dry_run=True)

        assert res.json()["dry_run"] is True
        assert len(calls) == 0, "AC-V5-4: relink_to_matching_lines must never run on a dry run"
        assert _po_line_status(env, crm_line.id) == "open", (
            "AC-V5-4: the CRM-raised PO line must not be superseded on a dry run"
        )
        assert _po_status(env, crm_po.id) == "active"


# ================================================================== AC-V5-5
class TestPlanningChangeIsNotRunByIngest:
    def test_planning_change_service_build_batch_is_never_called(self, env, monkeypatch):
        """AC-V5-5. A guard, not a feature: `planning_change_service.build_batch`
        needs the upload's own `Diff` of `Line`s, which the ingest route has no
        equivalent for, and D7 explicitly defers it to the backlog ("the
        captain asks why an ingested SO changed the plan and there is no
        change batch to show"). This PASSES TODAY - nothing calls it either
        way - and must stay green through S5; it exists so a future change
        that wires ingest into planning_change_service without a deliberate
        decision trips a test instead of shipping silently.
        """
        from app.services import planning_change_service

        calls: list[dict] = []
        monkeypatch.setattr(
            planning_change_service, "build_batch", lambda *a, **kw: calls.append(kw)
        )

        record = _so_record(env)
        res = env.post(INGEST_SO, [record])

        assert res.json()["records"][0]["outcome"] == "created", res.text
        assert calls == [], (
            "AC-V5-5: planning_change_service.build_batch must not be called "
            "by document ingest in v2 (deferred by D7)"
        )
