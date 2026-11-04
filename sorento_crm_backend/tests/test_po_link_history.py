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
4. the backfill migration seeds one "first seen" event per linked line, idempotently;
5. the Placed popup's order-inquiry rows carry who linked them and when.

Driven through the real HTTP ingest route (the `env` fixture of
tests/test_ingest_documents.py). Postgres only. Every test seeds its own chain.
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import date, datetime
from pathlib import Path

import pytest
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
def test_po_history_is_readable_with_purchase_orders_view_and_not_without():
    """Gated on `scm.purchase_orders.view` (crew ruling, 4 Nov). The PO page's own
    `scm.dashboard.view` alone does not open it. Company-scoped like every per-record read,
    and no IP address."""
    from fastapi.testclient import TestClient

    import app.database as app_database
    from app.dependencies import get_current_user_or_api_key
    from app.main import app
    from app.models.base import set_company_scope
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from app.services.company_scope_resolver import apply_company_scope
    from tests._pg_fixture import blank_session
    from tests.test_audit_read_gate import _role, _user

    with blank_session() as db:
        buyer = _user(db, "buyer", _role(db, "zz_po_viewer", ["scm.purchase_orders.view"]))
        page_only = _user(db, "page_only", _role(db, "zz_page_only", ["scm.dashboard.view"]))
        plain = _user(db, "plain", _role(db, "zz_nothing", []))
        po_id = str(uuid.uuid4())
        db.add(AuditLog(
            id=str(uuid.uuid4()), entity_type="purchase_order_lines", entity_id=str(uuid.uuid4()),
            action="EVENT", event=CHANGE, description="ZZT: S/O none → ZZT-SO",
            root_entity_type="purchase_orders", root_entity_id=po_id,
            company_id=DEFAULT_COMPANY_ID, ip_address="10.9.8.7",
        ))
        db.commit()
        caller = {"id": None, "scope": frozenset({DEFAULT_COMPANY_ID})}

        def _override_db():
            yield db

        async def _override_scope():
            set_company_scope(db, caller["scope"])
            return caller["scope"]

        app.dependency_overrides[app_database.get_db] = _override_db
        app.dependency_overrides[apply_company_scope] = _override_scope
        app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": caller["id"]}
        try:
            url = (
                "/api/v1/audit/logs/?entity_type=purchase_orders"
                f"&entity_id={po_id}&include_children=true"
            )
            caller["id"] = buyer
            r = TestClient(app).get(url)
            assert r.status_code == 200, r.text
            rows = r.json()["data"]
            assert [row["event"] for row in rows] == [CHANGE]
            assert rows[0]["ip_address"] is None
            caller["id"] = plain
            assert TestClient(app).get(url).status_code == 403
            caller["id"] = page_only
            assert TestClient(app).get(url).status_code == 403
            # Scoped to that PO: the permission opens no other record type's history.
            other = f"/api/v1/audit/logs/?entity_type=users&entity_id={uuid.uuid4()}"
            caller["id"] = buyer
            assert TestClient(app).get(other).status_code == 403
            # The view permission opens that PO's history, not the line table's listing.
            caller["id"] = buyer
            r = TestClient(app).get("/api/v1/audit/logs/?entity_type=purchase_order_lines")
            assert r.status_code == 403
            # Another company's viewer sees nothing of this company's PO.
            caller["scope"] = frozenset({str(uuid.uuid4())})
            r = TestClient(app).get(url)
            assert r.status_code == 200, r.text
            assert r.json()["data"] == []
        finally:
            app.dependency_overrides.clear()


# ============================================================== 4. the backfill migration
MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "polh_0001_seen_backfill.py"
)


def _run_backfill(db, batch: int | None = None) -> None:
    spec = importlib.util.spec_from_file_location("polh_0001", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if batch is not None:
        module._BATCH = batch  # walk the keyset loop over several batches
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        module.upgrade()


class TestBackfill:
    def test_seeds_one_seen_event_per_linked_line_and_reruns_as_a_no_op(self, env):
        from app.models.scm import OrderLinkClaim

        linked = _po_line(env, from_so_line_ref="ZZT_BF:1:1")
        claimed = _po_line(env, from_so_line_ref="ZZT_BF:1:2")
        bare = _po_line(env)
        record = _po_record(env, lines=[linked, claimed, bare])
        _push(env, record)
        ids = _line_ids(env, record)
        header = env.header("purchase_orders", record["source_ref"])
        # The lines were born before history began: drop the ingest's own events and date
        # the lines and one claim in the past.
        env.db.execute(text("SET LOCAL sorento.audit_maintenance = 'on'"))
        env.db.execute(
            text("DELETE FROM audit_logs WHERE entity_type = 'purchase_order_lines' "
                 "AND entity_id = ANY(:ids)"),
            {"ids": list(ids.values())},
        )
        env.db.execute(
            text("UPDATE purchase_order_lines SET created_at = :at WHERE id = ANY(CAST(:ids AS uuid[]))"),
            {"at": datetime(2026, 9, 10, 8, 0), "ids": list(ids.values())},
        )
        env.db.add(OrderLinkClaim(
            id=str(uuid.uuid4()), company_id=env.company_a, so_number="ZZT-SO",
            po_number=record["po_number"], source="autocount",
            claimed_at=datetime(2026, 9, 2, 9, 30),  # MYT wall time, as `_now()` stamps it
            po_line_id=ids[claimed["source_ref"]],
        ))
        env.db.flush()

        _run_backfill(env.db, batch=1)

        env.db.expire_all()
        seen_linked = _events(env, ids[linked["source_ref"]], SEEN)
        seen_claimed = _events(env, ids[claimed["source_ref"]], SEEN)
        assert _events(env, ids[bare["source_ref"]], SEEN) == []
        assert len(seen_linked) == 1 and len(seen_claimed) == 1
        assert seen_linked[0].changed_at == datetime(2026, 9, 10, 8, 0)
        # The earliest AutoCount claim beats the line's own created_at. `claimed_at` is
        # Malaysian wall time (`order_link_service._now`) and `changed_at` is UTC, so
        # 09:30 MYT on 2 Sep lands as 01:30 UTC (crew pass on 2339d063: 22,248 rows 8 h late).
        assert seen_claimed[0].changed_at == datetime(2026, 9, 2, 1, 30)
        ev = seen_linked[0]
        assert ev.action == "EVENT"
        assert ev.new_values == {"from_so_line_ref": "ZZT_BF:1:1"}
        assert ev.root_entity_type == "purchase_orders"
        assert ev.root_entity_id == str(header["id"])
        assert str(ev.company_id) == env.company_a

        _run_backfill(env.db)

        assert len(_events(env, ids[linked["source_ref"]], SEEN)) == 1

    def test_a_line_that_already_has_a_change_event_is_skipped(self, env):
        key = _held_so(env, "ZZTPLH-SO-BF")
        line = _po_line(env, from_so_line_ref=f"{key}:1")
        record = _po_record(env, lines=[line])
        _push(env, record)
        line_id = _line_ids(env, record)[line["source_ref"]]

        _run_backfill(env.db)

        assert _events(env, line_id, SEEN) == []


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
