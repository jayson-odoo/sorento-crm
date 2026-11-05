"""PO-LINK-HISTORY, red tests: when and how a PO line got its S/O link.

Plan: documentation/plans/procurement/PLAN-po-link-history-04nov.md (behaviour card 1-5,
crew answers 4 Nov: all five (a)).

Owner, 4 Nov 2026, on a purchase order's Lines tab: "can i see the audit trails of when is
this linked in the UI?" The S/O column is `purchase_order_lines.from_so_line_ref`, written
only by the AutoCount PO ingest, and the line table is audit-skipped. These tests pin:

1. the ingest writes ONE named audit event per S/O link change it writes (changed ref, a
   NEW line born with a ref, an explicit clear), and none on a re-push that changes nothing;
2. the PO detail serializer serves each line's latest link event (`book_so_link`);
3. a user with Purchase Orders view reads that PO's History tab, a user without it cannot;
4. the start-time backfill (no longer the migration) seeds one "first seen" event per
   linked line, one commit per batch, idempotently, behind an advisory lock;
5. the Placed popup's order-inquiry rows carry who linked them and when.

Driven through the real HTTP ingest route (the `env` fixture of
tests/test_ingest_documents.py). Postgres only. Every test seeds its own chain.
"""
from __future__ import annotations

import importlib.util
import logging
import uuid
from datetime import date, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.models.audit import AuditLog
from app.models.order import SalesOrder

from .test_ingest_documents import (
    INGEST_PO,
    _po_line,
    _po_record,
    env,  # noqa: F401 - pytest fixture, imported for reuse
)

__all__ = ["env"]

CHANGE = "scm.po_line.book_so_change"
SEEN = "scm.po_line.book_so_seen"


# --------------------------------------------------------------------------- helpers
def _held_so(env, number: str) -> str:
    """A sales order this CRM holds; returns its AutoCount doc key (line refs hang off it)."""
    doc_key = f"ZZT_PLH:{uuid.uuid4().hex[:8]}"
    env.db.add(
        SalesOrder(
            id=str(uuid.uuid4()), company_id=env.company_a, so_number=number,
            order_date=date(2026, 9, 1), demand_class="project", source_ref=doc_key,
        )
    )
    env.db.commit()
    return doc_key


def _push(env, record) -> None:
    res = env.post(INGEST_PO, [record])
    assert res.status_code == 200, res.text
    assert res.json()["records"][0]["outcome"] in ("created", "updated", "unchanged"), res.text
    env.db.expire_all()


def _line_ids(env, record) -> dict[str, str]:
    header = env.header("purchase_orders", record["source_ref"])
    return {l["source_ref"]: str(l["id"]) for l in env.po_lines(header["id"])}


def _events(env, line_id: str, event: str = CHANGE) -> list[AuditLog]:
    env.db.expire_all()
    return (
        env.db.query(AuditLog)
        .filter(
            AuditLog.entity_type == "purchase_order_lines",
            AuditLog.entity_id == line_id,
            AuditLog.event == event,
        )
        .order_by(AuditLog.changed_at.asc())
        .all()
    )


# ============================================================== 1. the ingest event
class TestIngestWritesTheEvent:
    def test_a_new_line_born_with_an_so_writes_one_event_from_none(self, env):
        key = _held_so(env, "ZZTPLH-SO-1")
        line = _po_line(env, from_so_line_ref=f"{key}:1")
        record = _po_record(env, lines=[line])

        _push(env, record)

        line_id = _line_ids(env, record)[line["source_ref"]]
        events = _events(env, line_id)
        assert len(events) == 1
        ev = events[0]
        assert ev.action == "EVENT"
        assert ev.old_values["from_so_line_ref"] is None
        assert ev.new_values["from_so_line_ref"] == f"{key}:1"
        assert ev.new_values["so_number"] == "ZZTPLH-SO-1"
        header = env.header("purchase_orders", record["source_ref"])
        # Rolls up to the PO, so the PO's History tab shows it.
        assert ev.root_entity_type == "purchase_orders"
        assert ev.root_entity_id == str(header["id"])
        assert str(ev.company_id) == env.company_a
        # What the History tab prints: item code, before, after. No machine ref.
        assert "ZZTPLH-SO-1" in ev.description
        assert key not in ev.description

    def test_a_new_line_without_an_so_writes_nothing(self, env):
        line = _po_line(env)
        record = _po_record(env, lines=[line])

        _push(env, record)

        assert _events(env, _line_ids(env, record)[line["source_ref"]]) == []

    def test_a_changed_so_writes_one_event_with_old_and_new(self, env):
        key1 = _held_so(env, "ZZTPLH-SO-A")
        key2 = _held_so(env, "ZZTPLH-SO-B")
        line = _po_line(env, from_so_line_ref=f"{key1}:1")
        record = _po_record(env, lines=[line])
        _push(env, record)
        line_id = _line_ids(env, record)[line["source_ref"]]

        _push(env, dict(record, lines=[dict(line, from_so_line_ref=f"{key2}:7")]))

        events = _events(env, line_id)
        assert len(events) == 2
        last = events[-1]
        assert last.old_values == {"from_so_line_ref": f"{key1}:1", "so_number": "ZZTPLH-SO-A"}
        assert last.new_values == {"from_so_line_ref": f"{key2}:7", "so_number": "ZZTPLH-SO-B"}
        assert "ZZTPLH-SO-A" in last.description and "ZZTPLH-SO-B" in last.description

    def test_a_re_push_with_the_same_so_writes_nothing_more(self, env):
        key = _held_so(env, "ZZTPLH-SO-S")
        line = _po_line(env, from_so_line_ref=f"{key}:1")
        record = _po_record(env, lines=[line])
        _push(env, record)
        line_id = _line_ids(env, record)[line["source_ref"]]

        _push(env, dict(record, lines=[dict(line, qty_ordered=9)]))
        # An omitted field leaves the stored ref alone: also no event.
        omitted = {k: v for k, v in line.items() if k != "from_so_line_ref"}
        _push(env, dict(record, lines=[omitted]))

        assert len(_events(env, line_id)) == 1

    def test_an_explicit_clear_writes_an_event_to_none(self, env):
        key = _held_so(env, "ZZTPLH-SO-C")
        line = _po_line(env, from_so_line_ref=f"{key}:1")
        record = _po_record(env, lines=[line])
        _push(env, record)
        line_id = _line_ids(env, record)[line["source_ref"]]

        _push(env, dict(record, lines=[dict(line, from_so_line_ref=None)]))

        last = _events(env, line_id)[-1]
        assert last.new_values["from_so_line_ref"] is None
        assert last.old_values["so_number"] == "ZZTPLH-SO-C"

    def test_an_so_this_crm_does_not_hold_is_recorded_without_a_number(self, env):
        line = _po_line(env, from_so_line_ref="ZZT_NOT_HELD:1:2")
        record = _po_record(env, lines=[line])

        _push(env, record)

        ev = _events(env, _line_ids(env, record)[line["source_ref"]])[0]
        assert ev.new_values == {"from_so_line_ref": "ZZT_NOT_HELD:1:2", "so_number": None}
        assert "ZZT_NOT_HELD" not in ev.description

    def test_an_adopted_import_line_records_its_link_move(self, env):
        """The third write site: a ref-less line an earlier extract import wrote is ADOPTED
        by the first AutoCount push of its order (`_adopt_lines`), and the push's S/O ref
        overwrites whatever the import left there."""
        from app.models.procurement import PurchaseOrder, PurchaseOrderLine

        key_old = _held_so(env, "ZZTPLH-SO-IMP")
        key_new = _held_so(env, "ZZTPLH-SO-ADP")
        number = f"ZZTDOC-PO-{uuid.uuid4().hex[:8]}"
        header = PurchaseOrder(
            id=str(uuid.uuid4()), po_number=number, status="draft", company_id=env.company_a
        )
        env.db.add(header)
        env.db.flush()
        pushed = _po_line(env, qty_ordered=4, from_so_line_ref=f"{key_new}:1")
        product_id = env.refs.resolve(entity_type="products", source_ref=pushed["product_ref"])
        legacy = PurchaseOrderLine(
            id=str(uuid.uuid4()), purchase_order_id=header.id, product_id=str(product_id),
            qty_ordered=4, qty_received=0, line_status="open", company_id=env.company_a,
            from_so_line_ref=f"{key_old}:1",
        )
        env.db.add(legacy)
        env.db.commit()

        _push(env, _po_record(env, number=number, lines=[pushed]))

        events = _events(env, str(legacy.id))
        assert len(events) == 1, "the adopted line keeps its id and records the move"
        assert events[0].old_values["so_number"] == "ZZTPLH-SO-IMP"
        assert events[0].new_values["so_number"] == "ZZTPLH-SO-ADP"

    def test_a_record_that_fails_after_its_lines_leaves_no_event(self, env, monkeypatch):
        """The events live inside the record's savepoint: a record that fails after its
        lines were written rolls them back with everything else."""
        from app.services.document_ingest_service import DocumentIngestService

        def _boom(self, header, payload):
            raise RuntimeError("ZZT forced failure after the lines")

        monkeypatch.setattr(DocumentIngestService, "_write_order_link_claims", _boom)
        key = _held_so(env, "ZZTPLH-SO-F")
        record = _po_record(env, lines=[_po_line(env, from_so_line_ref=f"{key}:1")])
        before = env.db.query(AuditLog).filter(AuditLog.event == CHANGE).count()

        res = env.post(INGEST_PO, [record])

        assert res.status_code == 200, res.text
        assert res.json()["records"][0]["outcome"] == "failed", res.text
        env.db.expire_all()
        assert env.db.query(AuditLog).filter(AuditLog.event == CHANGE).count() == before

    def test_a_dry_run_writes_no_event(self, env):
        key = _held_so(env, "ZZTPLH-SO-D")
        record = _po_record(env, lines=[_po_line(env, from_so_line_ref=f"{key}:1")])
        before = env.db.query(AuditLog).filter(AuditLog.event == CHANGE).count()

        res = env.post(INGEST_PO, [record], dry_run=True)

        assert res.status_code == 200, res.text
        env.db.expire_all()
        assert env.db.query(AuditLog).filter(AuditLog.event == CHANGE).count() == before


# ============================================================== 2. the detail serializer
def _detail_lines(env, record) -> dict[str, dict]:
    from app.services.scm.purchase_order_service import PurchaseOrderService

    env.db.expire_all()
    header = env.header("purchase_orders", record["source_ref"])
    po = PurchaseOrderService(env.db).get_one(str(header["id"]))
    return {str(l["id"]): l for l in po["lines"]}


class TestDetailServesTheLatestEvent:
    def test_a_line_with_no_event_serves_none(self, env):
        line = _po_line(env)
        record = _po_record(env, lines=[line])
        _push(env, record)

        line_id = _line_ids(env, record)[line["source_ref"]]
        assert _detail_lines(env, record)[line_id]["book_so_link"] is None

    def test_a_changed_line_serves_when_and_the_previous_so(self, env):
        key1 = _held_so(env, "ZZTPLH-SO-P1")
        key2 = _held_so(env, "ZZTPLH-SO-P2")
        line = _po_line(env, from_so_line_ref=f"{key1}:1")
        record = _po_record(env, lines=[line])
        _push(env, record)
        _push(env, dict(record, lines=[dict(line, from_so_line_ref=f"{key2}:1")]))
        line_id = _line_ids(env, record)[line["source_ref"]]

        link = _detail_lines(env, record)[line_id]["book_so_link"]

        latest = _events(env, line_id)[-1]
        # `response_model` drops an undeclared field: the route's schema must carry it.
        from app.schemas.scm_orders import PurchaseOrder as PurchaseOrderSchema

        header = env.header("purchase_orders", record["source_ref"])
        from app.services.scm.purchase_order_service import PurchaseOrderService

        served = PurchaseOrderSchema.model_validate(
            PurchaseOrderService(env.db).get_one(str(header["id"]))
        ).model_dump(mode="json")
        served_line = next(l for l in served["lines"] if str(l["id"]) == line_id)
        assert served_line["book_so_link"]["previous_so_number"] == "ZZTPLH-SO-P1"
        assert link == {
            "changed_at": latest.changed_at.isoformat(),
            "estimated": False,
            "previous_linked": True,
            "previous_so_number": "ZZTPLH-SO-P1",
        }

    def test_a_line_born_linked_serves_previous_not_linked(self, env):
        key = _held_so(env, "ZZTPLH-SO-N")
        line = _po_line(env, from_so_line_ref=f"{key}:1")
        record = _po_record(env, lines=[line])
        _push(env, record)
        line_id = _line_ids(env, record)[line["source_ref"]]

        link = _detail_lines(env, record)[line_id]["book_so_link"]

        assert link["previous_linked"] is False
        assert link["previous_so_number"] is None
        assert link["estimated"] is False

    def test_a_backfilled_line_serves_estimated(self, env):
        line = _po_line(env)
        record = _po_record(env, lines=[line])
        _push(env, record)
        line_id = _line_ids(env, record)[line["source_ref"]]
        header = env.header("purchase_orders", record["source_ref"])
        env.db.add(AuditLog(
            id=str(uuid.uuid4()), entity_type="purchase_order_lines", entity_id=line_id,
            action="EVENT", event=SEEN, new_values={"from_so_line_ref": "X:1:2"},
            root_entity_type="purchase_orders", root_entity_id=str(header["id"]),
            changed_at=datetime(2026, 9, 3, 10, 0),
        ))
        env.db.commit()

        link = _detail_lines(env, record)[line_id]["book_so_link"]

        assert link == {
            "changed_at": "2026-09-03T10:00:00",
            "estimated": True,
            "previous_linked": None,
            "previous_so_number": None,
        }


# ============================================================== 3. History tab permission
@pytest.fixture
def history_env():
    """A PO in company A and one in company B, each with a link event; callers by role.

    Crew ruling (4 Nov, second): the PO history is gated on EXACTLY the permission that opens
    the PO detail page, `scm.dashboard.view` (`app/api/v1/scm/purchase_orders.py:36`, the
    `GET /purchase-orders/{po_id}` route's `_READ`); always inside the PO's company; never
    for an X-API-Key principal."""
    from fastapi.testclient import TestClient

    import app.database as app_database
    from app.dependencies import get_current_user_or_api_key
    from app.main import app
    from app.models.base import set_company_scope
    from app.models.company import Company
    from app.models.procurement import PurchaseOrder
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from app.services.company_scope_resolver import apply_company_scope
    from tests._pg_fixture import blank_session
    from tests.test_audit_read_gate import _role, _user

    with blank_session() as db:
        other_company = str(uuid.uuid4())
        db.add(Company(id=other_company, name="ZZT PLH B", code=f"ZP{uuid.uuid4().hex[:6]}"))
        db.flush()
        ids = {
            "buyer": _user(db, "buyer", _role(db, "zz_po_page", ["scm.dashboard.view"])),
            "esb_slug": _user(db, "esb", _role(db, "zz_esb_slug", ["scm.purchase_orders.view"])),
            "plain": _user(db, "plain", _role(db, "zz_nothing", [])),
            "admin": _user(db, "admin", _role(db, "admin")),
        }
        pos = {}
        for key, company in (("a", DEFAULT_COMPANY_ID), ("b", other_company)):
            po = PurchaseOrder(
                id=str(uuid.uuid4()), po_number=f"ZZT-PLH-{key}-{uuid.uuid4().hex[:6]}",
                status="active", company_id=company,
            )
            db.add(po)
            db.flush()
            db.add(AuditLog(
                id=str(uuid.uuid4()), entity_type="purchase_order_lines",
                entity_id=str(uuid.uuid4()), action="EVENT", event=CHANGE,
                description="ZZT: S/O none → ZZT-SO", root_entity_type="purchase_orders",
                root_entity_id=str(po.id), company_id=company, ip_address="10.9.8.7",
            ))
            pos[key] = str(po.id)
        db.commit()
        caller = {"user": None, "scope": frozenset({DEFAULT_COMPANY_ID})}

        def _override_db():
            yield db

        async def _override_scope():
            set_company_scope(db, caller["scope"])
            return caller["scope"]

        app.dependency_overrides[app_database.get_db] = _override_db
        app.dependency_overrides[apply_company_scope] = _override_scope
        app.dependency_overrides[get_current_user_or_api_key] = lambda: caller["user"]

        def get(who, po_key="a", *, api_key=False, scope=None):
            user = {"id": ids[who]}
            if api_key:
                # What `resolve_integration_principal` returns for an X-API-Key call.
                user.update(integration_id=str(uuid.uuid4()), integration_name="ZZT ESB",
                            auth_method="integration_api_key")
            caller["user"] = user
            caller["scope"] = scope if scope is not None else frozenset({DEFAULT_COMPANY_ID})
            return TestClient(app).get(
                "/api/v1/audit/logs/?entity_type=purchase_orders"
                f"&entity_id={pos[po_key]}&include_children=true"
            )

        try:
            yield get
        finally:
            app.dependency_overrides.clear()


class TestPoHistoryRead:
    def test_a_buyer_who_can_open_the_po_reads_its_history_without_ip(self, history_env):
        r = history_env("buyer")
        assert r.status_code == 200, r.text
        rows = r.json()["data"]
        # The line's link event, beside the PO's own creation row the seed wrote.
        assert CHANGE in [row["event"] for row in rows]
        assert all(row["ip_address"] is None for row in rows)

    @pytest.mark.parametrize("who", ["plain", "esb_slug"])
    def test_a_user_without_po_page_access_gets_403(self, history_env, who):
        # `scm.purchase_orders.view` is the ESB's slug; it does not open the PO page.
        assert history_env(who).status_code == 403

    @pytest.mark.parametrize("who", ["buyer", "admin"])
    def test_an_api_key_principal_gets_403(self, history_env, who):
        # Never the open all-companies scope an X-API-Key call otherwise runs with.
        assert history_env(who, api_key=True, scope=frozenset()).status_code == 403
        assert history_env(who, api_key=True).status_code == 403

    @pytest.mark.parametrize("who", ["buyer", "admin"])
    def test_another_companys_po_gets_403(self, history_env, who):
        assert history_env(who, "b").status_code == 403

    def test_an_admin_reads_their_own_companys_po(self, history_env):
        assert history_env("admin").status_code == 200


# ============================================================== 4. the backfill (after start)
# POLH-BACKFILL-ASYNC (5 Nov): inside the deploy migration the backfill took ~19 s a batch on
# the prod clone, blue never got healthy inside 240 s and the whole release rolled back. It
# now runs after the backend starts (`scripts/backfill_po_link_seen.py`, from `start.sh`).
BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "alembic" / "versions" / "polh_0001_seen_backfill.py"


def _run_migration(db) -> None:
    spec = importlib.util.spec_from_file_location("polh_0001", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        module.upgrade()


def _run_backfill(db, batch: int | None = None) -> int:
    from app.services.scm import po_link_history

    if batch is None:
        return po_link_history.backfill_seen(db)
    return po_link_history.backfill_seen(db, batch=batch)  # walk the keyset loop


def _pre_history_lines(env, refs: list[str | None], *, created_at: datetime):
    """PO lines linked before history began: pushed with no ref (the ingest writes no event
    for a line born unlinked), then given their ref the way pre-release rows carry one. No
    audit row is deleted: `audit_logs` is append-only to a non-maintainer role."""
    lines = [_po_line(env) for _ in refs]
    record = _po_record(env, lines=lines)
    _push(env, record)
    by_ref = _line_ids(env, record)
    ids = [by_ref[line["source_ref"]] for line in lines]
    for line_id, ref in zip(ids, refs):
        env.db.execute(
            text(
                "UPDATE purchase_order_lines SET from_so_line_ref = :ref, created_at = :at "
                "WHERE id = CAST(:id AS uuid)"
            ),
            {"ref": ref, "at": created_at, "id": line_id},
        )
    env.db.commit()
    return record, ids


class TestBackfill:
    def test_seeds_one_seen_event_per_linked_line_and_reruns_as_a_no_op(self, env):
        from app.models.scm import OrderLinkClaim

        record, (linked, claimed, bare) = _pre_history_lines(
            env, ["ZZT_BF:1:1", "ZZT_BF:1:2", None], created_at=datetime(2026, 9, 10, 8, 0)
        )
        header = env.header("purchase_orders", record["source_ref"])
        assert _events(env, linked, SEEN) == [] and _events(env, linked) == []
        env.db.add(OrderLinkClaim(
            id=str(uuid.uuid4()), company_id=env.company_a, so_number="ZZT-SO",
            po_number=record["po_number"], source="autocount",
            claimed_at=datetime(2026, 9, 2, 9, 30),  # MYT wall time, as `_now()` stamps it
            po_line_id=claimed,
        ))
        env.db.commit()

        assert _run_backfill(env.db, batch=1) == 2

        env.db.expire_all()
        seen_linked = _events(env, linked, SEEN)
        seen_claimed = _events(env, claimed, SEEN)
        assert _events(env, bare, SEEN) == []
        assert len(seen_linked) == 1 and len(seen_claimed) == 1
        assert seen_linked[0].changed_at == datetime(2026, 9, 10, 8, 0)
        # The earliest AutoCount claim beats the line's own created_at. `claimed_at` is
        # Malaysian wall time (`order_link_service._now`) and `changed_at` is UTC, so
        # 09:30 MYT on 2 Sep lands as 01:30 UTC (crew pass on 2339d063: 22,248 rows 8 h late).
        assert seen_claimed[0].changed_at == datetime(2026, 9, 2, 1, 30)
        ev = seen_linked[0]
        assert ev.action == "EVENT"
        assert ev.actor_type == "system"
        assert ev.new_values == {"from_so_line_ref": "ZZT_BF:1:1"}
        assert ev.description.endswith(": S/O an S/O not held here first seen (linked on or before this date)")
        assert ev.root_entity_type == "purchase_orders"
        assert ev.root_entity_id == str(header["id"])
        assert str(ev.company_id) == env.company_a

        assert _run_backfill(env.db) == 0

        assert len(_events(env, linked, SEEN)) == 1

    def test_a_line_that_already_has_a_change_event_is_skipped(self, env):
        key = _held_so(env, "ZZTPLH-SO-BF")
        line = _po_line(env, from_so_line_ref=f"{key}:1")
        record = _po_record(env, lines=[line])
        _push(env, record)
        line_id = _line_ids(env, record)[line["source_ref"]]

        assert _run_backfill(env.db) == 0

        assert _events(env, line_id, SEEN) == []

    def test_the_earliest_autocount_claim_dates_the_line_and_other_sources_do_not(self, env):
        # A line can carry several claims (identity is company + S/O + PO + item,
        # `order_link_service.py:355`): ONE seen row, dated by the earliest AUTOCOUNT claim; a
        # still earlier claim from another source never counts.
        from app.models.scm import OrderLinkClaim

        record, (line_id,) = _pre_history_lines(env, ["ZZT_BF:4:1"], created_at=datetime(2026, 9, 20))
        for so_number, source, at in (
            ("ZZT-SO-LATE", "autocount", datetime(2026, 9, 8, 9, 0)),
            ("ZZT-SO-EARLY", "autocount", datetime(2026, 9, 5, 9, 0)),
            ("ZZT-SO-HIST", "po_history", datetime(2026, 9, 1, 9, 0)),
        ):
            env.db.add(OrderLinkClaim(
                id=str(uuid.uuid4()), company_id=env.company_a, so_number=so_number,
                po_number=record["po_number"], source=source, claimed_at=at, po_line_id=line_id,
            ))
        env.db.commit()

        assert _run_backfill(env.db) == 1

        seen = _events(env, line_id, SEEN)
        assert len(seen) == 1
        assert seen[0].changed_at == datetime(2026, 9, 5, 1, 0)  # 09:00 MYT on 5 Sep, as UTC

    def test_rows_the_old_inline_migration_wrote_make_a_start_time_run_a_no_op(self, env):
        # DEPLOY-MIGRATE-STEP: prod ran polh_0001 at 42d1a56c, when the migration still seeded
        # the rows itself; start.sh now runs this backfill on EVERY start. A row in that
        # migration's exact shape (its INSERT ... SELECT columns and literals) must count as
        # "already seen", so the first start-time run on prod inserts nothing for that line.
        _, (seeded, fresh) = _pre_history_lines(
            env, ["ZZT_BF:5:1", "ZZT_BF:5:2"], created_at=datetime(2026, 9, 10)
        )
        env.db.execute(
            text(
                "INSERT INTO audit_logs (id, entity_type, entity_id, action, event, actor_type, "
                "changed_at, new_values, description, company_id, root_entity_type, root_entity_id) "
                "SELECT gen_random_uuid(), 'purchase_order_lines', CAST(l.id AS text), 'EVENT', "
                ":event, 'system', l.created_at, "
                "jsonb_build_object('from_so_line_ref', l.from_so_line_ref), "
                "'Line: S/O an S/O not held here first seen (linked on or before this date)', "
                "l.company_id, 'purchase_orders', CAST(l.purchase_order_id AS text) "
                "FROM purchase_order_lines l WHERE l.id = CAST(:id AS uuid)"
            ),
            {"event": SEEN, "id": seeded},
        )
        env.db.commit()

        assert _run_backfill(env.db) == 1  # only the line the old migration never reached

        assert len(_events(env, seeded, SEEN)) == 1
        assert len(_events(env, fresh, SEEN)) == 1
        assert _run_backfill(env.db) == 0

    def test_the_migration_no_longer_writes_the_backfill(self, env):
        # The deploy runs every pending revision in ONE transaction inside the 240 s health
        # wait: polh_0001 stays in the chain but seeds nothing.
        _, (line_id,) = _pre_history_lines(env, ["ZZT_BF:2:1"], created_at=datetime(2026, 9, 10))

        _run_migration(env.db)

        assert _events(env, line_id, SEEN) == []

    def test_each_batch_commits_on_its_own_so_a_killed_run_resumes(self, env, monkeypatch):
        _, ids = _pre_history_lines(env, ["ZZT_BF:3:1", "ZZT_BF:3:2"], created_at=datetime(2026, 9, 10))
        real_commit = env.db.commit
        commits: list[int] = []

        def dying_commit():
            commits.append(1)
            if len(commits) == 2:
                raise RuntimeError("backend stopped mid-backfill")
            real_commit()

        monkeypatch.setattr(env.db, "commit", dying_commit)
        with pytest.raises(RuntimeError):
            _run_backfill(env.db, batch=1)
        monkeypatch.undo()
        env.db.rollback()

        # The first batch survived the kill; the second was never committed.
        assert sum(len(_events(env, i, SEEN)) for i in ids) == 1
        assert _run_backfill(env.db, batch=1) == 1
        assert [len(_events(env, i, SEEN)) for i in ids] == [1, 1]


# ------------------------------------------------- the start-time script that runs it
def _linked_lines_in(engine) -> int:
    from app.models.procurement import PurchaseOrderLine

    with engine.connect() as conn:
        return conn.execute(
            sa.select(sa.func.count()).select_from(PurchaseOrderLine.__table__).where(
                PurchaseOrderLine.__table__.c.from_so_line_ref.isnot(None)
            )
        ).scalar()


def _advisory_held(engine, key: int) -> int:
    """Sessions holding advisory lock `key` (a key below 2**31: classid 0, objid = key)."""
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
                 "AND classid = 0 AND objid = :k AND granted"),
            {"k": key},
        ).scalar()


@pytest.fixture
def lock_key(monkeypatch):
    """A per-test key, so a held lock can never block another test or a real backend."""
    from scripts import backfill_po_link_seen as script

    key = 0x10000000 + uuid.uuid4().int % 0x0FFFFFFF
    monkeypatch.setattr(script, "ADVISORY_LOCK_KEY", key)
    return key


def test_the_script_backfills_and_releases_its_lock(lock_key):
    from scripts import backfill_po_link_seen as script

    from ._pg_fixture import blank_schema_engine

    engine = blank_schema_engine()
    # Honest only on an empty scratch schema: the script commits for real.
    assert _linked_lines_in(engine) == 0
    assert script.run(engine) == 0
    # pg_locks, not a second try-lock: a pooled engine may hand back the very connection that
    # still holds it, and a session re-acquires its own lock.
    assert _advisory_held(engine, lock_key) == 0


def test_the_script_leaves_it_to_a_backend_already_backfilling(lock_key):
    # Blue and green starting together: the one that does not get the lock does nothing.
    from scripts import backfill_po_link_seen as script

    from ._pg_fixture import blank_schema_engine

    engine = blank_schema_engine()
    with engine.connect() as other:
        key = {"k": lock_key}
        # try, never a blocking pg_advisory_lock: a leaked lock must fail this test, not hang it.
        assert other.execute(text("SELECT pg_try_advisory_lock(:k)"), key).scalar() is True
        try:
            assert script.run(engine) is None
        finally:
            other.execute(text("SELECT pg_advisory_unlock(:k)"), key)


def test_the_script_never_fails_the_container(monkeypatch, caplog):
    # gunicorn reaps it like a worker after start.sh execs: a non-zero exit reads as a crash.
    from scripts import backfill_po_link_seen as script

    def broken(engine):
        raise RuntimeError("database unreachable")

    monkeypatch.setattr(script, "run", broken)
    caplog.set_level(logging.WARNING)
    script.main()
    assert "database unreachable" in caplog.text


def test_start_sh_runs_the_backfill_in_the_background_after_migrating():
    start = (BACKEND / "start.sh").read_text()
    upgrade = start.index("alembic upgrade head")
    backfill = start.index("python -m scripts.backfill_po_link_seen &")
    assert upgrade < backfill < start.index("exec python -m gunicorn")


def test_start_sh_runs_the_backfill_on_every_start_whatever_skip_migrations_says():
    # DEPLOY-MIGRATE-STEP: prod deploys now start the colour with SKIP_MIGRATIONS=1 (the deploy
    # migrates as its own step), so the post-start jobs must sit outside the flag's if-block.
    start = (BACKEND / "start.sh").read_text()
    gate = start.index('if [ "${SKIP_MIGRATIONS:-0}" != "1" ]; then')
    gate_end = start.index("\nfi\n", gate)
    for job in ("python -m scripts.backfill_po_link_seen &", "python -m scripts.ensure_goods_chain_indexes &"):
        assert start.index(job) > gate_end, job


# ============================================================== 5. Placed popup who/when
def test_placed_inquiry_rows_carry_who_linked_and_when(env):
    from app.services.scm.purchase_order_service import PurchaseOrderService

    from .test_ac_removed_lines_ingest import PoWorld, _oi_row_on

    line_a = _po_line(env, qty_ordered=10)
    line_b = _po_line(env, qty_ordered=10)
    record = _po_record(env, lines=[line_a, line_b])
    _push(env, record)
    w = PoWorld(env, record, line_a, line_b)
    _oi_row_on(env, w)
    from app.models.project_so import OrderInquiryLink

    # ORM, not a schema-qualified UPDATE: the blank session's scratch schema holds the rows.
    links = env.db.query(OrderInquiryLink).filter(OrderInquiryLink.po_line_id == w.line_a).all()
    assert links
    for link in links:
        link.linked_by = "5b8b9c10-1111-4222-8333-4444555566d1"
        link.auto = False
        link.linked_at = datetime(2026, 9, 4, 14, 5)
    env.db.commit()
    env.db.expire_all()

    po = PurchaseOrderService(env.db).get_one(w.header_id)

    by_line = {str(a["line_id"]): a for a in po["allocations"]}
    placement = next(p for p in by_line[w.line_a]["placements"] if p["kind"] == "inquiry")
    assert placement["linked_at"] == "2026-09-04T14:05:00"
    assert placement["linked_by_name"] == "ZZTDOC admin"
    assert placement["auto"] is False
    # `response_model` drops an undeclared field: the route's schema must carry all three.
    from app.schemas.scm_orders import PurchaseOrder as PurchaseOrderSchema

    served = PurchaseOrderSchema.model_validate(po).model_dump(mode="json")
    block = next(a for a in served["allocations"] if str(a["line_id"]) == w.line_a)
    served_placement = next(p for p in block["placements"] if p["kind"] == "inquiry")
    assert served_placement["linked_by_name"] == "ZZTDOC admin"
    assert served_placement["auto"] is False
    assert served_placement["linked_at"].startswith("2026-09-04T14:05")
