"""AC-REMOVED-LINES, red tests: the one-off reconciliation script.

UAC: documentation/plans/scm/ac-removed-lines-26oct-acceptance-criteria.md
     AC-RL-40 .. AC-RL-43 (`scripts/release_removed_autocount_lines.py`).

Contract pinned here (from the UAC, nothing more):
  * module `scripts.release_removed_autocount_lines`
  * `run(db, company_id, dry_run=True) -> dict`; a dry run writes nothing and the dict
    carries counts plus a per-line list naming document number, DtlKey, product code, line
    qty, linked qty and OI rows affected, and no customer or contact name. The exact KEY
    names are not fixed by the UAC, so the tests read the report as flattened text.
  * `main(argv) -> int` CLI: `--company <id>`, writes only with `--apply`. It opens its
    session through a module-level `SessionLocal` (the precedent
    scripts/backfill_retired_spo_lines.py does); the test swaps it for the scratch session.

The module does not exist yet, so it is imported INSIDE each test (precedent
tests/test_backfill_retired_spo_lines.py): each test fails on its own with
ModuleNotFoundError today.

World (all fake, one blank scratch schema per test): see `_world`.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.base import set_company_scope
from app.models.order import SalesOrder, SalesOrderLine
from app.models.procurement import (
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
    Supplier,
)
from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    INQUIRY_ACTIONED,
    INQUIRY_CANCELLED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ORDER_BACK,
    OrderInquiryLink,
    OrderInquiryRow,
)
from app.models.scm import OrderLinkClaim

from ._pg_fixture import blank_session
from .test_oi_cancelled_line_used_confirm import _inquiry, _line_chain, _oi_row
from .test_order_inquiry_kinds import _link, _product, _sorento, _uid

DB = "ZZT_DB"
# DtlKeys are distinctive 5-digit numbers so the report can be searched as text.
K_PO_REMOVED, K_PO_CLAIM_ONLY = "81001", "81002"
K_PO_RESOLVED_ONLY, K_PO_LINK_AND_RESOLVED, K_PO_LIVE = "81007", "81008", "81009"
K_PO_CANCEL_DOC, K_PO_REFLESS, K_PO_OPEN, K_PO_HDR_CANCELLED = "81003", "81004", "81005", "81006"
K_SO_REMOVED, K_SO_CS_BOARD, K_SO_NO_ROWS = "82001", "82002", "82003"
K_SO_CANCEL_DOC, K_SO_HDR_CANCELLED, K_SO_ACTIONED_ONLY = "82004", "82005", "82006"
K_SPO_RETIRED, K_SPO_NOT_RETIRED, K_SPO_RETIRED_B = "83001", "83002", "83003"
SELECTED = (K_PO_REMOVED, K_PO_CLAIM_ONLY, K_PO_RESOLVED_ONLY, K_PO_LINK_AND_RESOLVED, K_SO_REMOVED, K_SPO_RETIRED, K_SPO_RETIRED_B)
def _key(dtl: str) -> str:
    """The allow-list key (AC-RL-46): `<source DB>:<DtlKey>`."""
    return f"{DB}:{dtl}"


ALL_SPO = [_key(K_SPO_RETIRED), _key(K_SPO_RETIRED_B)]
# Same DtlKey in two AutoCount databases (E, F), and the same database + DtlKey under two
# DocKeys (G, H): the keys that are or are not unique.
K_SPO_TWIN = "84001"
K_SPO_DUP = "84002"
UNSELECTED = (
    K_PO_CANCEL_DOC, K_PO_REFLESS, K_PO_OPEN, K_PO_HDR_CANCELLED,
    K_SO_CS_BOARD, K_SO_NO_ROWS, K_SPO_NOT_RETIRED,
    K_SO_CANCEL_DOC, K_SO_HDR_CANCELLED, K_SO_ACTIONED_ONLY,
)


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


class World:
    pass


def _ref(dtl: str) -> str:
    return f"{DB}:4001:{dtl}"


def _po_line(db, company, header, product, dtl, *, status="cancelled", cancel_doc=False):
    line = PurchaseOrderLine(
        id=_uid(), company_id=company, purchase_order_id=header.id, product_id=product.id,
        qty_ordered=Decimal("10"), qty_received=Decimal("0"), line_status=status,
        source_system="autocount" if dtl else None, source_ref=_ref(dtl) if dtl else None,
        cancelled_by_cancel_doc=cancel_doc,
    )
    db.add(line)
    db.flush()
    return line


def _row_linked(db, company, product, *, po_line=None, spo=None, doc, qty="10", state=INQUIRY_PLACED):
    """A fresh SO chain + one OI row, linked to a PO line or an SPO allocation."""
    so, core, pso, mirror = _line_chain(db, company, product, qty=qty)
    inquiry = _inquiry(db, company, pso.id)
    row = _oi_row(
        db, company, inquiry.id, mirror.id, product.product_code, qty,
        state=state, ack_state=ACK_ACKNOWLEDGED,
    )
    if spo is not None:
        row.verb = IV_ORDER_BACK
    link = _link(
        db, company, row.id, qty,
        po_line_id=po_line.id if po_line else None,
        spo_allocation_id=spo.id if spo else None, document=doc,
    )
    row.po_ref = doc
    row.zzt_so_number = so.so_number
    return row, link


def _claim(db, company, product, doc, *, po_line):
    claim = OrderLinkClaim(
        so_number=f"ZZT-SO-{_uid()[:6]}", po_number=doc, item_code=product.product_code,
        source="manual", po_line_id=po_line.id, company_id=company,
    )
    db.add(claim)
    db.flush()
    return claim


def _world(db) -> World:
    w = World()
    set_company_scope(db, None)
    w.company = _sorento(db)
    c = w.company
    w.product = _product(db, f"ZZT-REL-{_uid()[:6]}", "ZZT release product")
    supplier = Supplier(
        id=_uid(), supplier_code=f"ZZT{_uid()[:8]}", supplier_name="ZZT supplier", company_id=c
    )
    db.add(supplier)
    db.flush()

    def _header(number, status="open"):
        h = PurchaseOrder(
            id=_uid(), company_id=c, po_number=number, supplier_id=supplier.id,
            status=status, source_system="autocount", source_ref=f"{DB}:HDR:{number}",
        )
        db.add(h)
        db.flush()
        return h

    w.po_number = f"ZZT-PO-{_uid()[:6]}"
    w.po_cancelled_number = f"ZZT-POC-{_uid()[:6]}"
    po = _header(w.po_number)
    po_cancelled = _header(w.po_cancelled_number, status="cancelled")

    # --- PO lines. Selected: removed + linked (K_PO_REMOVED), removed + open claim only.
    w.po_removed = _po_line(db, c, po, w.product, K_PO_REMOVED)
    w.row_po_removed, w.link_po_removed = _row_linked(
        db, c, w.product, po_line=w.po_removed, doc=w.po_number
    )
    w.po_claim_only = _po_line(db, c, po, w.product, K_PO_CLAIM_ONLY)
    w.claim_only = _claim(db, c, w.product, w.po_number, po_line=w.po_claim_only)
    # --- a removed line holding ONLY a RESOLVED claim (no OI link), and one with a link AND a
    # resolved claim: both selected, both lose every claim.
    w.po_resolved_only = _po_line(db, c, po, w.product, K_PO_RESOLVED_ONLY)
    w.resolved_only_claim = _claim(db, c, w.product, w.po_number, po_line=w.po_resolved_only)
    w.resolved_only_claim.source = "autocount"
    w.resolved_only_claim.resolved_at = datetime(2026, 10, 1)
    w.po_link_resolved = _po_line(db, c, po, w.product, K_PO_LINK_AND_RESOLVED)
    w.row_link_resolved, w.link_link_resolved = _row_linked(
        db, c, w.product, po_line=w.po_link_resolved, doc=w.po_number
    )
    w.link_resolved_claim = _claim(db, c, w.product, w.po_number, po_line=w.po_link_resolved)
    w.link_resolved_claim.source = "autocount"
    w.link_resolved_claim.resolved_at = datetime(2026, 10, 1)
    # --- AC-RL-47: a resolved claim from a LIVE PO line naming a REMOVED SO line. Left in
    # place by the script, but listed in the report for the owner to correct in AutoCount.
    w.po_live = _po_line(db, c, po, w.product, K_PO_LIVE, status="open")
    w.claim_to_removed_so_number = None  # set once the SO chains exist, below
    # --- PO lines that must NOT be selected, each with a live link.
    unselected = {
        "cancel_doc": _po_line(db, c, po, w.product, K_PO_CANCEL_DOC, cancel_doc=True),
        "refless": _po_line(db, c, po, w.product, None),
        "open": _po_line(db, c, po, w.product, K_PO_OPEN, status="open"),
        "hdr_cancelled": _po_line(db, c, po_cancelled, w.product, K_PO_HDR_CANCELLED),
    }
    w.kept_links = {}
    for name, line in unselected.items():
        doc = w.po_cancelled_number if name == "hdr_cancelled" else w.po_number
        _row, link = _row_linked(db, c, w.product, po_line=line, doc=doc)
        w.kept_links[name] = str(link.id)

    # --- SO lines: removed + live row (selected); CS board cancelled (cancelled_at set);
    # removed but its only row is already cancelled (no live rows).
    def _so_chain(dtl, *, cs_board=False, row_state=INQUIRY_RAISED, cancel_doc=False,
                  header_cancelled=False):
        so, core, pso, mirror = _line_chain(db, c, w.product, qty="10", line_status="cancelled")
        so.source_system = "autocount"
        if header_cancelled:
            so.status = "cancelled"
        core.source_system = "autocount"
        core.source_ref = _ref(dtl) if dtl else None
        core.cancelled_by_cancel_doc = cancel_doc
        if cs_board:
            core.cancelled_at = datetime(2026, 10, 1)
        inquiry = _inquiry(db, c, pso.id)
        row = _oi_row(
            db, c, inquiry.id, mirror.id, w.product.product_code, "10",
            state=row_state, ack_state=ACK_ACKNOWLEDGED,
        )
        db.flush()
        return so, core, row

    w.so_removed, w.so_core_removed, w.so_row_removed = _so_chain(K_SO_REMOVED)
    w.claim_to_removed_so = OrderLinkClaim(
        so_number=w.so_removed.so_number, po_number=w.po_number,
        item_code=w.product.product_code, source="autocount", po_line_id=w.po_live.id,
        so_line_id=w.so_core_removed.id, resolved_at=datetime(2026, 10, 1),
        qty=Decimal("6.5"), company_id=c,
    )
    db.add(w.claim_to_removed_so)
    db.flush()
    _so, _core, w.so_row_cs_board = _so_chain(K_SO_CS_BOARD, cs_board=True)
    _so, _core, w.so_row_no_live = _so_chain(K_SO_NO_ROWS, row_state=INQUIRY_CANCELLED)

    # --- SO lines the filter alone must keep out, each with a live row the retire would act on
    # (except the actioned-only one, whose row the retire only flags).
    _so, _core, w.so_row_cancel_doc = _so_chain(K_SO_CANCEL_DOC, cancel_doc=True)
    _so, _core, w.so_row_hdr_cancelled = _so_chain(K_SO_HDR_CANCELLED, header_cancelled=True)
    _so, _core, w.so_row_refless = _so_chain(None)
    _so, _core, w.so_row_actioned_only = _so_chain(
        K_SO_ACTIONED_ONLY, row_state=INQUIRY_ACTIONED
    )
    w.so_untouched = {
        "cancel_doc": (w.so_row_cancel_doc, INQUIRY_RAISED),
        "hdr_cancelled": (w.so_row_hdr_cancelled, INQUIRY_RAISED),
        "refless": (w.so_row_refless, INQUIRY_RAISED),
        "actioned_only": (w.so_row_actioned_only, INQUIRY_ACTIONED),
    }

    # --- SPO lines: retired + linked (selected), closed but never retired (not selected).
    def _spo(dtl, *, retired, source_ref=None):
        alloc = SPOAllocation(
            id=_uid(), company_id=c, spo_number=f"ZZT-SPO-{_uid()[:6]}", spo_line_number=1,
            product_id=w.product.id, allocated_quantity=10, line_status="closed",
            source_system="autocount", source_ref=source_ref or _ref(dtl),
            retired_at=datetime(2026, 9, 1) if retired else None,
        )
        db.add(alloc)
        db.flush()
        return alloc

    w.spo_retired = _spo(K_SPO_RETIRED, retired=True)
    w.row_spo_retired, w.link_spo_retired = _row_linked(
        db, c, w.product, spo=w.spo_retired, doc=w.spo_retired.spo_number
    )
    w.spo_retired_b = _spo(K_SPO_RETIRED_B, retired=True)
    w.row_spo_retired_b, w.link_spo_retired_b = _row_linked(
        db, c, w.product, spo=w.spo_retired_b, doc=w.spo_retired_b.spo_number
    )
    w.twin = {}
    for name, ref in (
        ("sorento", f"AED_SORENTO:ZZDOC1:{K_SPO_TWIN}"),
        ("mocha", f"AED_V2_MOCHA:ZZDOC2:{K_SPO_TWIN}"),
        ("dup1", f"AED_DUP:ZZDOC1:{K_SPO_DUP}"),
        ("dup2", f"AED_DUP:ZZDOC2:{K_SPO_DUP}"),
    ):
        alloc = _spo(K_SPO_TWIN, retired=True, source_ref=ref)
        row, link = _row_linked(db, c, w.product, spo=alloc, doc=alloc.spo_number)
        w.twin[name] = (alloc, row, link)
    w.spo_live = _spo(K_SPO_NOT_RETIRED, retired=False)
    _row, link = _row_linked(db, c, w.product, spo=w.spo_live, doc=w.spo_live.spo_number)
    w.kept_links["spo_not_retired"] = str(link.id)
    db.commit()
    return w


# ------------------------------------------------------------------------ readers
def _flat(value) -> str:
    """Every string, number and key of a nested report, as one lowercase blob."""
    if isinstance(value, dict):
        return " ".join(f"{_flat(k)} {_flat(v)}" for k, v in value.items())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flat(v) for v in value)
    return str(value).lower()


def _link_ids(db) -> set[str]:
    db.expire_all()
    return {str(r) for (r,) in db.query(OrderInquiryLink.id).all()}


def _row_state(db, row) -> str:
    db.expire_all()
    return db.get(OrderInquiryRow, row.id).state


def _open_claim(db, claim) -> bool:
    db.expire_all()
    got = db.get(OrderLinkClaim, claim.id)
    return got is not None and got.resolved_at is None


def _snapshot(db) -> dict:
    db.expire_all()
    return {
        "links": _link_ids(db),
        "states": {str(r.id): r.state for r in db.query(OrderInquiryRow).all()},
        "claims": {
            str(c.id): c.resolved_at for c in db.query(OrderLinkClaim).all()
        },
        "po_lines": {
            str(l.id): l.line_status for l in db.query(PurchaseOrderLine).all()
        },
    }


# ====================================================================== AC-RL-40
def test_ac_rl_40_dry_run_writes_nothing_and_reports_the_removed_lines(db):
    from scripts.release_removed_autocount_lines import run

    w = _world(db)
    before = _snapshot(db)

    report = run(db, w.company, dry_run=True)

    assert isinstance(report, dict)
    assert _snapshot(db) == before, "a dry run must write nothing"
    text_ = _flat(report)
    for dtl in SELECTED:
        assert dtl in text_, f"selected line {dtl} missing from the dry-run report"
    assert w.po_number.lower() in text_, "the report names the document number"
    assert w.product.product_code.lower() in text_, "the report names the product code"
    assert "customer" not in text_ and "contact" not in text_, (
        "the report must carry no customer or contact name"
    )


def test_ac_rl_40_run_defaults_to_a_dry_run(db):
    from scripts.release_removed_autocount_lines import run

    w = _world(db)
    before = _snapshot(db)

    run(db, w.company)

    assert _snapshot(db) == before


# ====================================================================== AC-RL-41
def test_ac_rl_41_selects_only_removed_autocount_lines_with_live_links_or_claims(db):
    from scripts.release_removed_autocount_lines import run

    w = _world(db)

    report = run(db, w.company, dry_run=True)

    text_ = _flat(report)
    for dtl in UNSELECTED:
        assert dtl not in text_, f"{dtl} must not be selected: {report}"
    for dtl in SELECTED:
        assert dtl in text_, f"{dtl} must be selected"


# ====================================================================== AC-RL-42
def test_ac_rl_42_apply_releases_exactly_what_the_ingest_releases_and_leaves_the_rest(db):
    from scripts.release_removed_autocount_lines import run

    w = _world(db)

    run(db, w.company, dry_run=False, spo_dtl_keys=ALL_SPO)

    db.expire_all()
    live_links = _link_ids(db)
    # PO line removed: link gone, row placed -> raised (AC-RL-01/02), ack untouched (03).
    assert str(w.link_po_removed.id) not in live_links
    assert _row_state(db, w.row_po_removed) == INQUIRY_RAISED
    assert db.get(OrderInquiryRow, w.row_po_removed.id).ack_state == ACK_ACKNOWLEDGED
    # open claim on a removed line is DELETED, not stamped resolved (AC-RL-04).
    assert db.get(OrderLinkClaim, w.claim_only.id) is None
    # AC-RL-04 / 41: a claim-only line (resolved claim, no link) is selected and its claim
    # goes; a line with a link AND a resolved claim loses both.
    assert db.get(OrderLinkClaim, w.resolved_only_claim.id) is None
    assert db.get(OrderLinkClaim, w.link_resolved_claim.id) is None
    assert str(w.link_link_resolved.id) not in live_links
    # SPO line retired: link gone (AC-RL-10).
    assert str(w.link_spo_retired.id) not in live_links
    assert _row_state(db, w.row_spo_retired) == INQUIRY_RAISED
    # SO line removed: live row retired like Transfer to Cancel SO (AC-RL-20), and the
    # core line is not given the CS board's `cancelled_at`.
    assert _row_state(db, w.so_row_removed) == INQUIRY_CANCELLED
    note = db.get(OrderInquiryRow, w.so_row_removed.id).note or ""
    assert "Removed in AutoCount" in note and "Transferred to Cancel SO" not in note, note
    core = db.execute(
        text("SELECT cancelled_at FROM sales_order_lines WHERE id = :i"),
        {"i": str(w.so_core_removed.id)},
    ).scalar()
    assert core is None
    # everything that is not a removed AutoCount line is untouched.
    for name, link_id in w.kept_links.items():
        assert link_id in live_links, f"{name}: link must survive the reconciliation"
    assert _row_state(db, w.so_row_cs_board) == INQUIRY_RAISED
    assert _row_state(db, w.so_row_no_live) == INQUIRY_CANCELLED
    # guard: every SO filter on its own keeps its line untouched (AC-RL-41).
    for name, (row, state) in w.so_untouched.items():
        assert _row_state(db, row) == state, f"{name} must not be touched by apply"
        assert db.get(OrderInquiryRow, row.id).note in (None, ""), name


def test_ac_rl_42_a_second_apply_finds_nothing(db):
    from scripts.release_removed_autocount_lines import run

    w = _world(db)
    run(db, w.company, dry_run=False, spo_dtl_keys=ALL_SPO)
    after_first = _snapshot(db)

    again = run(db, w.company, dry_run=False, spo_dtl_keys=ALL_SPO)

    # candidate entries only: AC-RL-47 keeps listing the claim that names a removed SO line.
    text_ = _flat(again["lines"])
    for dtl in SELECTED:
        assert dtl not in text_, f"{dtl} found again on the second run: {again}"
    assert all(v == 0 for v in again.values() if isinstance(v, int) and not isinstance(v, bool)), again
    assert _snapshot(db) == after_first
    # and a dry run afterwards is empty too
    dry = run(db, w.company, dry_run=True)
    for dtl in SELECTED:
        assert dtl not in _flat(dry["lines"])


# ====================================================================== AC-RL-43
class _Session:
    """Hands the scratch session to `main` and swallows its close()."""

    def __init__(self, db):
        self._db = db

    def __getattr__(self, name):
        return getattr(self._db, name)

    def close(self):
        return None


def test_ac_rl_43_cli_prints_the_dry_run_report_and_writes_only_with_apply(
    db, monkeypatch, capsys
):
    import scripts.release_removed_autocount_lines as mod

    w = _world(db)
    monkeypatch.setattr(mod, "SessionLocal", lambda: _Session(db))
    before = _snapshot(db)

    code = mod.main(["--company", str(w.company)])

    out = capsys.readouterr().out
    assert code in (0, None)
    assert _snapshot(db) == before, "no --apply: nothing written"
    for dtl in SELECTED:
        assert dtl in out, f"the CLI dry run must print {dtl}"

    code = mod.main(["--company", str(w.company), "--apply", "--only", _key(K_SPO_RETIRED)])

    assert code in (0, None)
    live_links = _link_ids(db)
    assert str(w.link_po_removed.id) not in live_links
    assert str(w.link_spo_retired.id) not in live_links
    assert _row_state(db, w.so_row_removed) == INQUIRY_CANCELLED


# ====================================================================== AC-RL-44
def test_ac_rl_44_apply_retires_so_rows_but_queues_no_handover(db, monkeypatch):
    from scripts.release_removed_autocount_lines import run

    from .test_order_inquiry_handover_automation import (
        _captured_dispatches,
        _handover_calls,
        _register,
    )

    w = _world(db)
    _register(None)
    calls = _captured_dispatches(monkeypatch)

    run(db, w.company, dry_run=False)

    assert _row_state(db, w.so_row_removed) == INQUIRY_CANCELLED, "the SO row is retired"
    assert _handover_calls(calls) == [], "the reconciliation must queue no handover"
    assert not [c for c in calls if str(c["trigger_type"]).startswith("order_inquiry")], calls


# ====================================================================== AC-RL-45
def test_ac_rl_45_dry_run_lists_each_spo_candidate_with_its_evidence(db):
    from scripts.release_removed_autocount_lines import run

    w = _world(db)

    report = run(db, w.company, dry_run=True)

    text_ = _flat(report)
    for dtl, alloc, row in (
        (K_SPO_RETIRED, w.spo_retired, w.row_spo_retired),
        (K_SPO_RETIRED_B, w.spo_retired_b, w.row_spo_retired_b),
    ):
        assert dtl in text_, dtl
        assert _key(dtl).lower() in text_, "the candidate's key is <source DB>:<DtlKey>"
        assert alloc.spo_number.lower() in text_, "the SPO number"
        assert row.zzt_so_number.lower() in text_, "the SO numbers of its links"
    assert w.product.product_code.lower() in text_, "the item code"
    assert " 10" in f" {text_}" or "10.0" in text_, "the placed qty"


def test_ac_rl_45_apply_without_an_allow_list_releases_no_spo_line(db):
    from scripts.release_removed_autocount_lines import run

    w = _world(db)

    run(db, w.company, dry_run=False)

    live = _link_ids(db)
    assert str(w.link_spo_retired.id) in live and str(w.link_spo_retired_b.id) in live
    assert _row_state(db, w.row_spo_retired) == INQUIRY_PLACED
    # PO and SO candidates are unaffected by the missing allow-list.
    assert str(w.link_po_removed.id) not in live
    assert _row_state(db, w.so_row_removed) == INQUIRY_CANCELLED


def test_ac_rl_45_apply_releases_only_the_listed_spo_line(db):
    from scripts.release_removed_autocount_lines import run

    w = _world(db)

    preview = run(db, w.company, dry_run=True)

    report = run(db, w.company, dry_run=False, spo_dtl_keys=[_key(K_SPO_RETIRED)])

    live = _link_ids(db)
    assert str(w.link_spo_retired.id) not in live, "A is listed: released"
    assert str(w.link_spo_retired_b.id) in live, "B is not listed: keeps its links"
    assert _row_state(db, w.row_spo_retired_b) == INQUIRY_PLACED

    # AC-RL-45: each SPO entry says whether it was released, and the summary counts cover
    # only the released lines (the owner reads these numbers).
    def _entry(rep, dtl):
        return next(l for l in rep["lines"] if dtl in _flat(l))

    def _released(entry):
        keys = [k for k in entry if "released" in str(k).lower()]
        assert keys, f"an apply entry must say whether it was released: {entry}"
        return bool(entry[keys[0]])

    assert _released(_entry(report, K_SPO_RETIRED)) is True
    assert _released(_entry(report, K_SPO_RETIRED_B)) is False
    assert report["spo_lines"] == 1, report
    unlisted_rows = sum(
        l["rows_affected"]
        for l in preview["lines"]
        if l.get("kind") == "spo" and l["dtl_key"] != K_SPO_RETIRED
    )
    assert report["rows_affected"] == preview["rows_affected"] - unlisted_rows, report


def test_ac_rl_45_a_listed_key_that_is_not_a_candidate_is_reported_and_ignored(db):
    from scripts.release_removed_autocount_lines import run

    w = _world(db)
    before = _snapshot(db)

    report = run(db, w.company, dry_run=False, spo_dtl_keys=[_key("99999"), _key(K_SPO_NOT_RETIRED)])

    text_ = _flat(report)
    assert _key("99999").lower() in text_ and _key(K_SPO_NOT_RETIRED).lower() in text_, (
        "unknown keys are reported"
    )
    live = _link_ids(db)
    assert w.kept_links["spo_not_retired"] in live, "a non-candidate is never touched"
    assert str(w.link_spo_retired.id) in live and str(w.link_spo_retired_b.id) in live
    assert before["links"] - live <= {
        str(w.link_po_removed.id), str(w.link_link_resolved.id)
    }, "only PO/SO work was done"


def test_ac_rl_45_cli_only_releases_that_spo_line_and_apply_alone_releases_none(
    db, monkeypatch
):
    import scripts.release_removed_autocount_lines as mod

    w = _world(db)
    monkeypatch.setattr(mod, "SessionLocal", lambda: _Session(db))

    mod.main(["--company", str(w.company), "--apply"])
    live = _link_ids(db)
    assert str(w.link_spo_retired.id) in live and str(w.link_spo_retired_b.id) in live

    mod.main(["--company", str(w.company), "--apply", "--only", _key(K_SPO_RETIRED_B)])
    live = _link_ids(db)
    assert str(w.link_spo_retired_b.id) not in live, "B listed with --only: released"
    assert str(w.link_spo_retired.id) in live, "A not listed: keeps its links"


# ====================================================================== AC-RL-46
def _refusal_keys(report) -> str:
    """Every report key that talks about a refusal (names are the implementation's)."""
    return " ".join(
        f"{k} {_flat(v)}"
        for k, v in report.items()
        if any(word in str(k).lower() for word in ("refus", "invalid", "ambig", "reject"))
    )


def test_ac_rl_46_the_same_dtl_key_in_two_databases_is_told_apart_by_the_key(db):
    from scripts.release_removed_autocount_lines import run

    w = _world(db)
    preview = run(db, w.company, dry_run=True)
    text_ = _flat(preview)
    assert f"aed_sorento:{K_SPO_TWIN}" in text_ and f"aed_v2_mocha:{K_SPO_TWIN}" in text_

    run(db, w.company, dry_run=False, spo_dtl_keys=[f"AED_SORENTO:{K_SPO_TWIN}"])

    live = _link_ids(db)
    assert str(w.twin["sorento"][2].id) not in live, "the AED_SORENTO line is released"
    assert str(w.twin["mocha"][2].id) in live, "the other database's line keeps its links"


def test_ac_rl_46_a_bare_dtl_key_is_refused_and_a_valid_key_in_the_same_run_applies(db):
    from scripts.release_removed_autocount_lines import run

    w = _world(db)

    report = run(
        db, w.company, dry_run=False,
        spo_dtl_keys=[K_SPO_TWIN, _key(K_SPO_RETIRED)],
    )

    live = _link_ids(db)
    assert str(w.twin["sorento"][2].id) in live and str(w.twin["mocha"][2].id) in live, (
        "a bare DtlKey releases nothing"
    )
    refused = _refusal_keys(report)
    assert K_SPO_TWIN in refused, f"the bare key must be reported as refused: {report}"
    assert str(w.link_spo_retired.id) not in live, "the valid key in the same run still applies"


def test_ac_rl_46_a_key_matching_two_candidates_is_refused(db):
    from scripts.release_removed_autocount_lines import run

    w = _world(db)
    ambiguous = f"AED_DUP:{K_SPO_DUP}"

    report = run(db, w.company, dry_run=False, spo_dtl_keys=[ambiguous, _key(K_SPO_RETIRED)])

    live = _link_ids(db)
    assert str(w.twin["dup1"][2].id) in live and str(w.twin["dup2"][2].id) in live
    assert ambiguous.lower() in _refusal_keys(report).lower(), report
    assert str(w.link_spo_retired.id) not in live, "the valid key in the same run still applies"


def test_ac_rl_46_cli_refuses_a_bare_key_and_says_so(db, monkeypatch, capsys):
    import scripts.release_removed_autocount_lines as mod

    w = _world(db)
    monkeypatch.setattr(mod, "SessionLocal", lambda: _Session(db))

    mod.main(["--company", str(w.company), "--apply", "--only", K_SPO_TWIN])

    out = capsys.readouterr().out.lower()
    live = _link_ids(db)
    assert str(w.twin["sorento"][2].id) in live and str(w.twin["mocha"][2].id) in live
    assert any(word in out for word in ("refus", "invalid", "ambig")), out


# ====================================================================== AC-RL-47
def test_ac_rl_47_a_claim_naming_a_removed_so_line_is_listed_and_left_in_place(db):
    from scripts.release_removed_autocount_lines import run

    w = _world(db)

    preview = run(db, w.company, dry_run=True)

    text_ = _flat(preview)
    assert w.po_number.lower() in text_, "PO number"
    assert K_PO_LIVE in text_, "the PO line's DtlKey"
    assert w.so_removed.so_number.lower() in text_, "SO number"
    assert K_SO_REMOVED in text_, "the SO line's DtlKey"
    assert "6.5" in text_, "claim qty"
    assert "customer" not in text_ and "contact" not in text_

    applied = run(db, w.company, dry_run=False, spo_dtl_keys=ALL_SPO)

    db.expire_all()
    assert db.get(OrderLinkClaim, w.claim_to_removed_so.id) is not None, "left in place"
    # it is a report entry only: it adds nothing to the line counts.
    assert (applied["po_lines"], applied["so_lines"]) == (4, 1), applied
    assert preview["spo_lines"] == 6, preview
    assert _flat(applied).count(w.so_removed.so_number.lower()) >= 1, "still reported on apply"
