"""Review round 1 (reviewer + security-reviewer) - one test per fix.

Each class below pins ONE numbered finding from the fix-round brief, named in
its own docstring by the same letter/number the brief used (B1, S1..S9,
SEC3..SEC5, N1). No new substrate: everything reuses the `env` fixture, the
record builders and the shipping-order helpers already seeded by
`tests.test_ingest_documents` and `tests.test_ingest_shipping_orders`, per the
same convention `tests/test_ingest_documents_v2_resolution.py` follows.

B1 itself already has its pin in `tests/test_ingest_contract_v2.py`
(`TestGoldenV1Payloads`) rather than here, since that file is where every
other golden v1 payload assertion lives; it is not repeated in this file.
"""
from __future__ import annotations

import inspect
import uuid

from sqlalchemy import text

from app.models.order import Customer

from tests._pg_fixture import unique_code
from tests.test_ingest_documents import (
    INGEST_PO,
    INGEST_SO,
    MARKER,
    _USER_ID,
    _po_line,
    _po_record,
    _ref,
    _so_line,
    _so_record,
    env,  # noqa: F401 - pytest fixture, imported for reuse
)
from tests.test_ingest_shipping_orders import (
    INGEST_SPO,
    READ_SPO,
    _seed_legacy_row,
    _spo_line,
    _spo_record,
    _spo_rows,
)

__all__ = ["env"]


def _called_from(func_name: str, filename_suffix: str) -> bool:
    """True when the immediate caller is `func_name` defined in a file ending
    `filename_suffix` - used to make a monkeypatched `db.flush()` fail only
    for the ONE explicit call the fix under test cares about, not every
    autoflush a middleware's own unrelated read triggers first, and not the
    route's final `db.commit()` after the record's own savepoint recovered.
    """
    frame = inspect.currentframe()
    caller = frame.f_back.f_back if frame and frame.f_back else None
    if caller is None:
        return False
    code = caller.f_code
    return code.co_name == func_name and code.co_filename.endswith(filename_suffix)


# ================================================================== S1 + S2
class TestS1LineNumberingAndS2SpoNumberConflict:
    def test_an_open_row_under_a_different_dockey_is_a_failed_spo_number_conflict(
        self, env
    ):
        """S2. A DIFFERENT, still-open DocKey holding this `spo_number` is a
        fact about the document, refused before anything else - the ladder
        never runs, and nothing is written for the conflicting push."""
        first = _spo_record(env, supplier_ref=env.supplier_ref)
        res = env.post(INGEST_SPO, [first])
        assert res.status_code == 200, res.text
        before = _spo_rows(env, first["spo_number"])
        assert len(before) == 1

        clash = _spo_record(
            env, number=first["spo_number"], supplier_ref=env.supplier_ref
        )
        res2 = env.post(INGEST_SPO, [clash])

        entry = res2.json()["records"][0]
        assert entry["outcome"] == "failed", res2.text
        assert "already linked to another source" in entry["errors"]["spo_number"]
        assert _spo_rows(env, first["spo_number"]) == before

    def test_line_numbering_climbs_past_rows_closed_under_an_old_dockey(self, env):
        """S1 + S2 together, the delete-and-recreate path: an old DocKey's
        rows are all CLOSED (by a push that stopped naming them), so S2's
        guard lets a fresh DocKey continue the same `spo_number` - and S1
        says the next line number must still climb past what that retired
        DocKey already claimed, not restart from what THIS DocKey's own
        (empty) row set implies."""
        first = _spo_record(
            env,
            lines=[_spo_line(env), _spo_line(env, product_ref=env.product2_ref)],
            supplier_ref=env.supplier_ref,
        )
        res = env.post(INGEST_SPO, [first])
        assert res.status_code == 200, res.text
        original = {r["spo_line_number"] for r in _spo_rows(env, first["spo_number"])}
        assert original == {1, 2}

        # Close both lines under the SAME DocKey by re-pushing it with none -
        # the leftover sweep closes every row nothing in the payload named.
        res2 = env.post(INGEST_SPO, [dict(first, lines=[])])
        assert res2.json()["records"][0]["outcome"] == "updated", res2.text
        closed = _spo_rows(env, first["spo_number"])
        assert {r["line_status"] for r in closed} == {"closed"}
        assert {r["spo_line_number"] for r in closed} == {1, 2}

        # A brand new DocKey continues the same spo_number (the retired
        # DocKey's rows are all closed, so S2 does not block this).
        second = _spo_record(
            env, number=first["spo_number"], supplier_ref=env.supplier_ref
        )
        res3 = env.post(INGEST_SPO, [second])

        # "created", not "updated" (correctly): the retired DocKey's rows
        # match neither of `_existing_rows`'s two conditions - they carry the
        # OLD source_doc_ref, not NULL - so this DocKey has no rows of its
        # own yet. S1 is specifically that the NUMBER still climbs past them
        # despite that.
        assert res3.json()["records"][0]["outcome"] == "created", res3.text
        rows = {r["source_ref"]: r for r in _spo_rows(env, first["spo_number"])}
        new_row = rows[second["lines"][0]["source_ref"]]
        # S1: 3, not 1 - the highest number this spo_number has EVER carried,
        # across the old (closed) DocKey's rows too.
        assert new_row["spo_line_number"] == 3


# ======================================================================= S3
class TestS3QuantityRoundingHalfUp:
    def test_fractional_quantities_round_half_up_to_the_nearest_whole_unit(self, env):
        line_a = _spo_line(env, qty_ordered="10.6")
        line_b = _spo_line(env, product_ref=env.product2_ref, qty_ordered="0.6")
        record = _spo_record(
            env, lines=[line_a, line_b], supplier_ref=env.supplier_ref
        )

        res = env.post(INGEST_SPO, [record])

        assert res.status_code == 200, res.text
        rows = {r["source_ref"]: r for r in _spo_rows(env, record["spo_number"])}
        first = rows[line_a["source_ref"]]
        second = rows[line_b["source_ref"]]
        assert first["allocated_quantity"] == 11
        assert first["line_status"] == "open"
        assert second["allocated_quantity"] == 1
        assert second["line_status"] == "open"


# ======================================================================= S4
class TestS4AlreadyRetiredRowsAreNotReAdopted:
    def test_a_cancelled_ref_less_document_line_is_not_adopted_by_a_new_dtlkey(
        self, env
    ):
        """S4 (document side). A ref-less line the system already cancelled -
        because something still points at it - is not a live adoption
        candidate for a fresh DtlKey any more; a NEW row is created instead,
        and the cancelled row is left exactly as it was."""
        from app.models.order import SalesOrder, SalesOrderLine

        record = _so_record(env, lines=[_so_line(env, qty_ordered=5)])
        res = env.post(INGEST_SO, [record])
        assert res.status_code == 200, res.text
        header = env.header("sales_orders", record["source_ref"])
        old_line = env.so_lines(header["id"])[0]

        # Simulate the state a prior cancellation-with-a-dependent already
        # left behind: ref-less, cancelled, and something (a stock transfer)
        # still pointing at it so it is never hard-deleted on a later sync.
        env.db.execute(
            text(
                "UPDATE sales_order_lines SET source_ref = NULL, line_status = "
                "'cancelled' WHERE id = :id"
            ),
            {"id": old_line["id"]},
        )
        env.stock_transfer(old_line["id"])
        env.db.commit()

        new_line = _so_line(env, qty_ordered=5)
        res2 = env.post(INGEST_SO, [dict(record, lines=[new_line])])

        assert res2.json()["records"][0]["outcome"] == "updated", res2.text
        lines = {
            row["id"]: row
            for row in env.db.execute(
                text(
                    "SELECT * FROM sales_order_lines WHERE sales_order_id = :id"
                ),
                {"id": header["id"]},
            )
            .mappings()
            .all()
        }
        assert len(lines) == 2
        old_after = lines[old_line["id"]]
        assert old_after["source_ref"] is None
        assert old_after["line_status"] == "cancelled"
        new_rows = [r for r in lines.values() if r["id"] != old_line["id"]]
        assert len(new_rows) == 1
        assert new_rows[0]["source_ref"] == new_line["source_ref"]

    def test_a_closed_ref_less_spo_row_is_not_adopted_by_a_new_dtlkey(self, env):
        """S4 (shipping-order side). Mirror of the document case: a legacy
        row this system already closed must not be resurrected by a new
        DtlKey naming the same product - a fresh row is created, and the
        closed row is left exactly as it was."""
        number = f"{MARKER}-SPO-{uuid.uuid4().hex[:8]}"
        legacy = _seed_legacy_row(
            env,
            spo_number=number,
            spo_line_number=1,
            allocated_quantity=10,
            quantity_received=10,
            line_status="closed",
        )

        line = _spo_line(env, qty_ordered=10)
        record = _spo_record(
            env, number=number, lines=[line], supplier_ref=env.supplier_ref
        )
        res = env.post(INGEST_SPO, [record])

        assert res.status_code == 200, res.text
        rows = {str(r["id"]): r for r in _spo_rows(env, number)}
        old_after = rows[str(legacy.id)]
        assert old_after["source_ref"] is None
        assert old_after["line_status"] == "closed"
        new_rows = [r for r in rows.values() if str(r["id"]) != str(legacy.id)]
        assert len(new_rows) == 1
        assert new_rows[0]["source_ref"] == line["source_ref"]
        # S1: the new row's number climbs past the legacy row's own number.
        assert new_rows[0]["spo_line_number"] == 2


# ======================================================================= S5
class TestS5CancelledReadsBackClosedNotReDerived:
    def test_a_cancelled_push_reads_back_status_closed(self, env):
        record = _spo_record(env, supplier_ref=env.supplier_ref)
        res = env.post(INGEST_SPO, [record])
        assert res.status_code == 200, res.text

        res2 = env.post(INGEST_SPO, [dict(record, status="cancelled")])
        assert res2.json()["records"][0]["outcome"] == "updated", res2.text

        got = env.read(READ_SPO, [record["source_ref"]]).json()["records"][0]
        assert got["status"] == "closed"


# ======================================================================= S6
class TestS6PlanExceptionSnapshotIsOncePerBatch:
    def test_the_before_and_after_snapshots_run_once_per_batch_not_once_per_record(
        self, env, monkeypatch
    ):
        from app.services.scm import plan_exception_service

        calls: list[list[str]] = []
        real_snapshot = plan_exception_service.snapshot

        def _counting(db, product_ids):
            calls.append(list(product_ids))
            return real_snapshot(db, product_ids)

        monkeypatch.setattr(plan_exception_service, "snapshot", _counting)

        third_ref = env.link_product(env.company_a)
        records = [
            _so_record(env, lines=[_so_line(env, product_ref=env.product_ref)]),
            _so_record(env, lines=[_so_line(env, product_ref=env.product2_ref)]),
            _so_record(env, lines=[_so_line(env, product_ref=third_ref)]),
        ]

        res = env.post(INGEST_SO, records)

        assert res.status_code == 200, res.text
        assert res.json()["summary"]["created"] == 3, res.text
        # ONE call for the whole batch's BEFORE snapshot (`ingest()`, ahead of
        # the record loop) plus ONE for the route's AFTER snapshot
        # (`_run_plan_exception_hook`, post-commit) - never one per record,
        # which would be 3 + 1 = 4.
        assert len(calls) == 2, calls


# ======================================================================= S8
class TestS8CustomerBackCreateIsCompanyScoped:
    def test_a_pair_existing_only_in_another_company_creates_a_new_row_here(self, env):
        code = unique_code(MARKER)
        name = f"{MARKER} Only In Company B Sdn Bhd"
        foreign = Customer(customer_code=code, customer_name=name, company_id=env.company_b)
        env.db.add(foreign)
        env.db.flush()

        record = _so_record(env, customer_code=code, customer_name=name)
        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        header = env.header("sales_orders", record["source_ref"])
        assert header["customer_id"] is not None
        assert str(header["customer_id"]) != str(foreign.id)
        created = (
            env.db.execute(
                text("SELECT company_id FROM customers WHERE id = :id"),
                {"id": header["customer_id"]},
            )
            .mappings()
            .first()
        )
        assert str(created["company_id"]) == str(env.company_a)


# ====================================================================== SEC3
class TestSEC3NonDomainExceptionsAreSanitized:
    def test_a_document_ingest_flush_failure_never_leaks_sql_or_uuids(
        self, env, monkeypatch
    ):
        leaking = (
            "INSERT INTO sales_orders (id, so_number) VALUES ('x') duplicate key "
            "value violates unique constraint; Key "
            "(id)=(5b8b9c10-1111-4222-8333-4444555566d1) already exists."
        )

        # Only the explicit `self.db.flush()` inside `_apply` fails - not an
        # unrelated autoflush the request-logging middleware's own reads
        # trigger before the route even runs, and not the route's own final
        # `db.commit()` after the record's savepoint has already recovered -
        # either of those blowing up 500s the whole batch instead of
        # producing the per-record `failed` verdict this fix is about.
        real_flush = env.db.flush

        def _boom(*args, **kwargs):
            if _called_from("_apply", "document_ingest_service.py"):
                raise RuntimeError(leaking)
            return real_flush(*args, **kwargs)

        monkeypatch.setattr(env.db, "flush", _boom)

        res = env.post(INGEST_SO, [_so_record(env)])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "failed", res.text
        assert "INSERT" not in res.text
        assert "5b8b9c10-1111-4222-8333-4444555566d1" not in res.text
        assert entry["errors"]["_"] == "internal error; see server logs"

    def test_a_shipping_order_ingest_flush_failure_never_leaks_sql_or_uuids(
        self, env, monkeypatch
    ):
        leaking = (
            "UPDATE spo_allocations SET allocated_quantity = 1 WHERE id = "
            "'5b8b9c10-2222-4222-8333-4444555566d1'"
        )

        real_flush = env.db.flush

        def _boom(*args, **kwargs):
            if _called_from("_apply", "shipping_order_ingest_service.py"):
                raise RuntimeError(leaking)
            return real_flush(*args, **kwargs)

        monkeypatch.setattr(env.db, "flush", _boom)

        res = env.post(INGEST_SPO, [_spo_record(env, supplier_ref=env.supplier_ref)])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "failed", res.text
        assert "UPDATE" not in res.text
        assert "5b8b9c10-2222-4222-8333-4444555566d1" not in res.text
        assert entry["errors"]["_"] == "internal error; see server logs"


# ====================================================================== SEC4
class TestSEC4MasterCodesAreCappedToTheirColumnWidth:
    def test_a_51_char_customer_code_is_a_field_level_failure(self, env):
        record = _so_record(env, customer_code="X" * 51)

        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "failed", res.text
        assert "customer_code" in entry["errors"], entry

    def test_a_51_char_supplier_code_is_a_field_level_failure(self, env):
        record = _po_record(env, supplier_code="X" * 51)

        res = env.post(INGEST_PO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "failed", res.text
        assert "supplier_code" in entry["errors"], entry


# ====================================================================== SEC5
class TestSEC5CardinalityCaps:
    def test_more_than_2000_lines_is_a_field_level_failure_naming_lines(self, env):
        lines = [_so_line(env) for _ in range(2001)]
        record = _so_record(env, lines=lines)

        res = env.post(INGEST_SO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "failed", res.text
        assert "lines" in entry["errors"], entry

    def test_more_than_50_from_so_numbers_on_one_line_is_a_field_level_failure(
        self, env
    ):
        line = _po_line(
            env, from_so_numbers=[f"{MARKER}-SO-{i}" for i in range(51)]
        )
        record = _po_record(env, lines=[line])

        res = env.post(INGEST_PO, [record])

        entry = res.json()["records"][0]
        assert entry["outcome"] == "failed", res.text
        assert any("from_so_numbers" in k for k in entry["errors"]), entry


# ======================================================================== N1
class TestN1PlanExceptionBatchRecordsTheCallingPrincipal:
    def test_the_plan_exception_batch_created_by_is_the_calling_principals_user_id(
        self, env
    ):
        from app.models.scm import PlanExceptionBatch

        record = _so_record(env)

        res = env.post(INGEST_SO, [record])

        assert res.json()["records"][0]["outcome"] == "created", res.text
        batch = (
            env.db.query(PlanExceptionBatch)
            .order_by(PlanExceptionBatch.generated_at.desc())
            .first()
        )
        assert batch is not None
        assert str(batch.created_by) == _USER_ID
