"""S2 - order inquiry rows follow the AutoCount book, through the PO to SPO chain:
the two ingest hooks (created AND updated lines), the cap, and best-effort failure.

UAC: `documentation/plans/scm/oi-follow-book-chain-acceptance-criteria.md`, Group B
(AC-FB-21 to AC-FB-25).
Plan: `documentation/plans/scm/PLAN-oi-follow-book-chain.md`, S2 (section 4.2, callers
2 and 3): a PO push resolves the SO line refs named by lines written THIS push
(created and updated) to rows, and calls `ProjectOrderInquiryService
.follow_book_for_rows` on them from `ingest.py`'s post-write hook; an SPO push does
the same, through its own ref or the PO line it names.

None of this exists yet - `_run_supersede_and_relink_hooks` only calls the S5
`follow_book_repairing` MOVE-repair (a link must already exist on the target), and
`_run_shipping_order_forward_match_hook` / `_run_shipping_order_book_repair_hook`
carry no equivalent call either. Every RED state below is that missing hook call
proven through the ROUTE (`POST /api/v1/external/ingest/...`), never the service
directly - this is the seam the plan names for S2.

Chosen names the coder must honour (S2 is silent on them until this file pins
them):
  - `ProjectOrderInquiryService.FOLLOW_BOOK_FOR_ROWS_MAX_ROWS` - the cap
    AC-FB-24 asks for, the `follow_book_for_rows` sibling of
    `FOLLOW_BOOK_REPAIRING_MAX_MOVES`.
  - `summary["book_follow_rows_dropped"]` - the ingest response's sibling key to
    the existing `summary["book_repair_moves_dropped"]`.

Substrate reused byte-for-byte from `tests/test_ingest_documents.py` /
`tests/test_ingest_shipping_orders.py`, same as `tests/test_ingest_documents_v5_
so_po_links.py` (`env`, `INGEST_PO`, `_po_line`, `_po_record`, `_ref`,
`INGEST_SPO`, `_spo_line`, `_spo_record`). `_seed_so_line` and `_mirror_row` below
are local copies of that same file's helpers (a plain, undelivered sales order
line - no dedication concern here since `follow_book_for_rows` writes through
`pair_needs`/`_write_link` directly, never `place_on_po_allocations`, so G7
dedication never enters this file at all).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import text

from app.models.order import SalesOrder, SalesOrderLine
from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    INQUIRY_RAISED,
    IV_ORDER,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from tests.test_ingest_documents import (
    INGEST_PO,
    MARKER,
    _po_line,
    _po_record,
    _ref,
    env,  # noqa: F401 - pytest fixture, imported for reuse
)
from tests.test_ingest_shipping_orders import (
    INGEST_SPO,
    _spo_line,
    _spo_record,
    _spo_rows,
)

__all__ = ["env"]


# ------------------------------------------------------------------ substrate
def _seed_so_line(env, *, so_number: str, product_id: str, source_ref: str, qty=10):
    """Byte-for-byte copy of `test_ingest_documents_v5_so_po_links._seed_so_line`:
    a sales order + one line carrying a real `source_ref`, committed (not just
    flushed) so a dry-run ingest call's own rollback never takes it down too."""
    so = SalesOrder(so_number=so_number, status="open", company_id=env.company_a)
    env.db.add(so)
    env.db.flush()
    line = SalesOrderLine(
        sales_order_id=so.id,
        product_id=product_id,
        qty_ordered=qty,
        source_ref=source_ref,
        company_id=env.company_a,
    )
    env.db.add(line)
    env.db.flush()
    env.db.commit()
    return so, line


def _mirror_row(env, *, core_line, product_id, qty: str, line_no: int = 1):
    """Byte-for-byte copy of `test_ingest_documents_v5_so_po_links._mirror_row`: a
    project mirror of `core_line`, with its own RAISED order inquiry row - the row
    a book-named document has to reach."""
    so_number = env.db.execute(
        text("SELECT so_number FROM sales_orders WHERE id = :id"),
        {"id": core_line.sales_order_id},
    ).scalar()
    pso = ProjectSalesOrder(
        id=str(uuid.uuid4()), company_id=env.company_a, project_id=None,
        so_id=core_line.sales_order_id, provisional_ref=f"{MARKER}-PSO-{uuid.uuid4().hex[:8]}",
        autocount_doc_no=so_number, status="adopted",
    )
    env.db.add(pso)
    env.db.flush()
    mirror_line = ProjectSalesOrderLine(
        id=str(uuid.uuid4()), company_id=env.company_a, project_sales_order_id=pso.id,
        line_no=line_no, core_sales_order_line_id=core_line.id, product_id=product_id,
        description=f"{MARKER} mirror", qty=Decimal(qty), uom="UNIT",
        unit_price=Decimal("10.00"), amount=Decimal("0"),
    )
    env.db.add(mirror_line)
    env.db.flush()
    inquiry = OrderInquiry(
        id=str(uuid.uuid4()), company_id=env.company_a, project_sales_order_id=pso.id,
    )
    env.db.add(inquiry)
    env.db.flush()
    row = OrderInquiryRow(
        id=str(uuid.uuid4()), company_id=env.company_a, order_inquiry_id=inquiry.id,
        so_line_id=mirror_line.id, qty=Decimal(qty), verb=IV_ORDER, state=INQUIRY_RAISED,
        ack_state=ACK_ACKNOWLEDGED,
    )
    env.db.add(row)
    env.db.flush()
    env.db.commit()
    return pso, mirror_line, inquiry, row


def _links_of(env, row_id):
    return env.db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row_id).all()


# ============================================================== AC-FB-21 / 25
class TestPoPushLinksExistingRow:
    def test_fb21_po_push_links_existing_row(self, env):
        """AC-FB-21: the row exists, unlinked, need 2, BEFORE the push. A PO push
        whose NEW line carries `from_so_line_ref` = the SO line's own ref (and no
        SPO at all) links the row inside that same ingest call's post-write hook."""
        product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)
        so_ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            env, so_number=f"{MARKER}-SO-{uuid.uuid4().hex[:8]}", product_id=product_id,
            source_ref=so_ref,
        )
        _pso, _mirror, _inquiry, row = _mirror_row(
            env, core_line=core_line, product_id=product_id, qty="2",
        )

        line = _po_line(env, from_so_line_ref=so_ref, qty_ordered=2)
        record = _po_record(env, lines=[line])

        res = env.post(INGEST_PO, [record])

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text

        env.db.expire_all()
        links = _links_of(env, row.id)
        assert len(links) == 1, links
        assert links[0].po_line_id is not None
        assert links[0].spo_allocation_id is None
        assert Decimal(str(links[0].qty)) == Decimal("2")
        assert links[0].auto is True

    def test_fb25_created_line_triggers(self, env):
        """AC-FB-25: a newly CREATED PO line triggers the hook (part 1) - not only
        an UPDATED one that adds the ref for the first time (part 2), which today's
        `ref_moves` capture never reaches either, since `_follow_one_move` only
        MOVES a link that already exists on the target and this target never had
        one."""
        product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)

        # Part 1: a freshly CREATED line.
        ref_created = _ref("SOLC")
        _so_c, core_line_c = _seed_so_line(
            env, so_number=f"{MARKER}-SOC-{uuid.uuid4().hex[:8]}", product_id=product_id,
            source_ref=ref_created,
        )
        _pso_c, _line_c, _inquiry_c, row_c = _mirror_row(
            env, core_line=core_line_c, product_id=product_id, qty="2",
        )
        line_c = _po_line(env, from_so_line_ref=ref_created, qty_ordered=2)
        record_c = _po_record(env, lines=[line_c])
        res_c = env.post(INGEST_PO, [record_c])
        assert res_c.json()["records"][0]["outcome"] == "created", res_c.text

        env.db.expire_all()
        assert len(_links_of(env, row_c.id)) == 1, _links_of(env, row_c.id)

        # Part 2: the line exists WITHOUT a ref first; a second push adds
        # `from_so_line_ref` for the first time.
        ref_updated = _ref("SOLU")
        _so_u, core_line_u = _seed_so_line(
            env, so_number=f"{MARKER}-SOU-{uuid.uuid4().hex[:8]}", product_id=product_id,
            source_ref=ref_updated,
        )
        _pso_u, _line_u, _inquiry_u, row_u = _mirror_row(
            env, core_line=core_line_u, product_id=product_id, qty="2",
        )
        plain_line = _po_line(env, qty_ordered=2)
        record_u = _po_record(env, lines=[plain_line])
        res_u1 = env.post(INGEST_PO, [record_u])
        assert res_u1.json()["records"][0]["outcome"] == "created", res_u1.text

        env.db.expire_all()
        assert _links_of(env, row_u.id) == []

        repush_line = _po_line(
            env, ref=plain_line["source_ref"], from_so_line_ref=ref_updated, qty_ordered=2,
        )
        record_u2 = dict(record_u, lines=[repush_line])
        res_u2 = env.post(INGEST_PO, [record_u2])
        assert res_u2.json()["records"][0]["outcome"] == "updated", res_u2.text

        env.db.expire_all()
        links_u = _links_of(env, row_u.id)
        assert len(links_u) == 1, links_u


# ============================================================== AC-FB-22
class TestSpoPushLinksThroughPoLine:
    def test_fb22_spo_push_links_through_po_line(self, env):
        """AC-FB-22: the row exists, and an SPO push writes a line naming ONLY a PO
        line (no `from_so_line_ref` of its own), that PO line naming L - closed and
        fully received, so S1's own cascade has nothing to do with it. The link
        lands on the SPO allocation, none on the PO line."""
        product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)
        so_ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            env, so_number=f"{MARKER}-SO-{uuid.uuid4().hex[:8]}", product_id=product_id,
            source_ref=so_ref,
        )

        po_line_payload = _po_line(env, from_so_line_ref=so_ref, qty_ordered=2, qty_received=2)
        po_record = _po_record(env, lines=[po_line_payload])
        po_res = env.post(INGEST_PO, [po_record])
        assert po_res.json()["records"][0]["outcome"] == "created", po_res.text
        po_header = env.header("purchase_orders", po_record["source_ref"])
        po_line_row = env.po_lines(po_header["id"])[0]
        assert po_line_row["line_status"] == "closed", "fixture must be genuinely received"

        _pso, _mirror, _inquiry, row = _mirror_row(
            env, core_line=core_line, product_id=product_id, qty="2",
        )

        spo_line_payload = _spo_line(
            env, from_po_line_ref=po_line_row["source_ref"], from_po_number=po_record["po_number"],
            qty_ordered=2,
        )
        spo_record = _spo_record(env, lines=[spo_line_payload], supplier_ref=env.supplier_ref)
        res = env.post(INGEST_SPO, [spo_record])

        assert res.status_code == 200, res.text
        assert res.json()["records"][0]["outcome"] == "created", res.text

        env.db.expire_all()
        links = _links_of(env, row.id)
        assert len(links) == 1, links
        assert links[0].po_line_id is None
        assert links[0].spo_allocation_id is not None
        spo_rows = _spo_rows(env, spo_record["spo_number"])
        assert str(links[0].spo_allocation_id) == str(spo_rows[0]["id"])


# ============================================================== AC-FB-21 (fail-open)
class TestHookFailureNeverFailsIngest:
    def test_fb21b_hook_failure_never_fails_ingest(self, env, monkeypatch):
        """AC-FB-21: "a failure in the hook is logged and never fails the ingest."
        The monkeypatch also proves the hook is actually CALLED - `calls` stays
        empty today because the hook this test targets does not exist yet, which
        is the honest RED here, not the ingest response (that half already holds
        with no hook at all, so asserting only status/outcome would pass by
        accident for the wrong reason)."""
        calls: list = []

        def _raise(self, row_ids, **kwargs):
            calls.append(list(row_ids))
            raise RuntimeError("zzt boom")

        monkeypatch.setattr(ProjectOrderInquiryService, "follow_book_for_rows", _raise)

        product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)
        so_ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            env, so_number=f"{MARKER}-SO-{uuid.uuid4().hex[:8]}", product_id=product_id,
            source_ref=so_ref,
        )
        _pso, _mirror, _inquiry, row = _mirror_row(
            env, core_line=core_line, product_id=product_id, qty="2",
        )

        line = _po_line(env, from_so_line_ref=so_ref, qty_ordered=2)
        record = _po_record(env, lines=[line])

        res = env.post(INGEST_PO, [record])

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "created", res.text
        header = env.header("purchase_orders", record["source_ref"])
        assert header is not None
        assert calls, "follow_book_for_rows was never invoked by the ingest hook"


# ============================================================== AC-FB-23
class TestIdempotentRepush:
    def test_fb23_idempotent_repush(self, env):
        """AC-FB-23: the same payload pushed twice links once, keeps the row's note
        unchanged, and the link's own quantity unchanged."""
        product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)
        so_ref = _ref("SOL")
        _so, core_line = _seed_so_line(
            env, so_number=f"{MARKER}-SO-{uuid.uuid4().hex[:8]}", product_id=product_id,
            source_ref=so_ref,
        )
        _pso, _mirror, _inquiry, row = _mirror_row(
            env, core_line=core_line, product_id=product_id, qty="2",
        )

        line = _spo_line(env, from_so_line_ref=so_ref, qty_ordered=2)
        record = _spo_record(env, lines=[line], supplier_ref=env.supplier_ref)

        res1 = env.post(INGEST_SPO, [record])
        assert res1.json()["records"][0]["outcome"] == "created", res1.text

        env.db.expire_all()
        links1 = _links_of(env, row.id)
        assert len(links1) == 1, links1
        assert Decimal(str(links1[0].qty)) == Decimal("2")
        row_after_first = env.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row.id).one()
        note_after_first = row_after_first.note

        res2 = env.post(INGEST_SPO, [record])
        assert res2.json()["records"][0]["outcome"] == "updated", res2.text

        env.db.expire_all()
        links2 = _links_of(env, row.id)
        assert len(links2) == 1, links2
        assert Decimal(str(links2[0].qty)) == Decimal("2")
        assert str(links2[0].id) == str(links1[0].id)
        row_after_second = env.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row.id).one()
        assert row_after_second.note == note_after_first


# ============================================================== AC-FB-24
class TestCapAndDroppedCount:
    def test_fb24_cap_and_dropped_count(self, env, monkeypatch):
        """AC-FB-24 [SEC]: a push naming more rows than the cap links only the cap's
        worth, drops the rest, logs it, and the ingest response's `summary` carries
        the dropped count under `book_follow_rows_dropped` - the sibling key to the
        existing `book_repair_moves_dropped` (`app/services/master_ingest_service.py`
        `IngestResult.as_dict`)."""
        monkeypatch.setattr(
            ProjectOrderInquiryService, "FOLLOW_BOOK_FOR_ROWS_MAX_ROWS", 1, raising=False,
        )
        product_id = env.refs.resolve(entity_type="products", source_ref=env.product_ref)
        ref_a = _ref("SOLA")
        ref_b = _ref("SOLB")
        _so_a, core_line_a = _seed_so_line(
            env, so_number=f"{MARKER}-SOA-{uuid.uuid4().hex[:8]}", product_id=product_id,
            source_ref=ref_a,
        )
        _so_b, core_line_b = _seed_so_line(
            env, so_number=f"{MARKER}-SOB-{uuid.uuid4().hex[:8]}", product_id=product_id,
            source_ref=ref_b,
        )
        _pso_a, _line_a, _inquiry_a, row_a = _mirror_row(
            env, core_line=core_line_a, product_id=product_id, qty="2",
        )
        _pso_b, _line_b, _inquiry_b, row_b = _mirror_row(
            env, core_line=core_line_b, product_id=product_id, qty="2",
        )

        line1 = _po_line(env, from_so_line_ref=ref_a, qty_ordered=2)
        line2 = _po_line(env, from_so_line_ref=ref_b, qty_ordered=2)
        record = _po_record(env, lines=[line1, line2])

        res = env.post(INGEST_PO, [record])

        assert res.status_code == 200, res.text
        summary = res.json()["summary"]
        assert summary.get("book_follow_rows_dropped") == 1, summary

        env.db.expire_all()
        links_a = _links_of(env, row_a.id)
        links_b = _links_of(env, row_b.id)
        linked_count = (1 if links_a else 0) + (1 if links_b else 0)
        assert linked_count == 1, (links_a, links_b)
