"""S5 - the one-time conversion of the existing "auto" order inquiry links on prod.

UAC: `documentation/plans/scm/oi-links-autocount-truth-24sep-acceptance-criteria.md`,
Group S5, AC-LT-41 to AC-LT-45.
Plan: `documentation/plans/scm/PLAN-oi-links-autocount-truth-24sep.md`, section 3.8.

RED at this slice, on purpose: `scripts/convert_oi_cascade_links.py` does not exist
yet, so `_module()` below fails at `spec.loader.exec_module` with a `FileNotFoundError`
for every test in this file - not a typo, not a fixture bug, the missing script the
coder writes next. Once that lands this file becomes an ordinary suite.

One seeded row per class (plan 3.8's own table), reusing `tests.test_oi_follow_book_
chain`'s harness wholesale - the same seam `test_order_inquiry_suggested_links.py`
already reuses for exactly this "book vs cascade, open vs closed target" question:

* `ctx` - one blank Postgres schema per test, `company_a` visible under
  `set_company_scope(db, None)`;
* `_seed_product` / `_seed_so_line` (the CORE line, `source_ref` the book joins
  against) / `_seed_po_line` (`from_so_line_ref` names or does not name it, `line_
  status` open or closed) / `_seed_row_and_mirror` (the project mirror + inquiry +
  `OrderInquiryRow` naming that core line through `so_line_id`) / `_existing_link`
  (a real `OrderInquiryLink`) / `_links_of` / `_suggested_of`.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from decimal import Decimal

from app.models.project_so import (
    INQUIRY_ACTIONED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    OrderInquiryLink,
    OrderInquiryReserveRequest,
    OrderInquiryReserveRequestRow,
)
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from tests.test_oi_follow_book_chain import (
    ctx,  # noqa: F401 - pytest fixture, imported for reuse
    _existing_link,
    _links_of,
    _ref,
    _seed_po_line,
    _seed_product,
    _seed_row_and_mirror,
    _seed_so_line,
    _suggested_of,
)

__all__ = ["ctx"]


def _module():
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts",
        "convert_oi_cascade_links.py",
    )
    spec = importlib.util.spec_from_file_location("_convert_oi_cascade_links", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _NoCloseSession:
    """`main()` owns `SessionLocal()` end to end, including its own `db.close()` - but
    the test's `db` is `ctx`'s one rolled-back session, so letting `main()` close it
    would break every assertion made after it returns. Forwards everything except
    `close`, which the fixture alone is allowed to call - the same idiom
    `test_oi_stale_link_state_repair.py` uses for `repair_oi_stale_link_state.py`."""

    def __init__(self, session):
        self._session = session

    def __getattr__(self, name):
        return getattr(self._session, name)

    def close(self):
        pass


def _reserve_link(db, *, company_id, row, qty="5"):
    """A CS reserve link - the third target `OrderInquiryLink` may name, never a PO or
    SPO line (plan 3.8's class (e))."""
    request = OrderInquiryReserveRequest(
        company_id=company_id, order_inquiry_id=row.order_inquiry_id, ordinal=1,
    )
    db.add(request)
    db.flush()
    request_row = OrderInquiryReserveRequestRow(
        company_id=company_id, request_id=request.id, row_id=row.id,
        qty_requested=Decimal(str(qty)),
    )
    db.add(request_row)
    db.flush()
    link = OrderInquiryLink(
        company_id=company_id, row_id=row.id, reserve_request_row_id=request_row.id,
        document="Reserved @ ZZT", qty=Decimal(str(qty)), auto=False,
    )
    db.add(link)
    db.flush()
    return link


def _seeded_row(db, *, company_id, product, qty="5", state=INQUIRY_PLACED):
    """A row on its own core line, mirror and inquiry - `core_line.source_ref` is what
    the book, not the cascade, is later given a chance to claim."""
    ref = _ref("SOL")
    core_line = _seed_so_line(
        db, company_id=company_id, product_id=product.id, source_ref=ref, qty=qty
    )[1]
    row = _seed_row_and_mirror(
        db, company_id=company_id, core_line=core_line, product_id=product.id, qty=qty,
        state=state,
    )[3]
    return core_line, row


# ---------------------------------------------------------------------------
# one seeded row per class (plan 3.8's own table)
# ---------------------------------------------------------------------------


def _seed_class_a_book(db, *, company_id, product):
    """(a) book: `auto` and the book itself names this target for the row's own core
    line (`from_so_line_ref` matches `core_line.source_ref`)."""
    core_line, row = _seeded_row(db, company_id=company_id, product=product)
    po, po_line = _seed_po_line(
        db, company_id=company_id, product_id=product.id,
        from_so_line_ref=core_line.source_ref, qty_ordered="5",
    )
    link = _existing_link(
        db, company_id=company_id, row_id=row.id, document=po.po_number, qty="5",
        po_line_id=po_line.id, auto=True,
    )
    return row, link


def _seed_class_b_cascade_open(db, *, company_id, product):
    """(b) cascade, open target: `auto`, not book (no `from_so_line_ref`), the target
    line still open."""
    _core_line, row = _seeded_row(db, company_id=company_id, product=product)
    po, po_line = _seed_po_line(db, company_id=company_id, product_id=product.id, qty_ordered="5")
    link = _existing_link(
        db, company_id=company_id, row_id=row.id, document=po.po_number, qty="5",
        po_line_id=po_line.id, auto=True,
    )
    return row, link, po_line


def _seed_class_c_cascade_closed(db, *, company_id, product):
    """(c) cascade, closed target: `auto`, not book, the target line fully received
    (`line_status` auto-computes to `closed`)."""
    _core_line, row = _seeded_row(db, company_id=company_id, product=product)
    po, po_line = _seed_po_line(
        db, company_id=company_id, product_id=product.id, qty_ordered="5", qty_received="5",
    )
    link = _existing_link(
        db, company_id=company_id, row_id=row.id, document=po.po_number, qty="5",
        po_line_id=po_line.id, auto=True,
    )
    return row, link


def _seed_class_d_not_auto(db, *, company_id, product):
    """(d) not auto: a manual link (or borrow / reallocation / shift / tick - every one
    of them writes `auto = false`)."""
    _core_line, row = _seeded_row(db, company_id=company_id, product=product)
    po, po_line = _seed_po_line(db, company_id=company_id, product_id=product.id, qty_ordered="5")
    link = _existing_link(
        db, company_id=company_id, row_id=row.id, document=po.po_number, qty="5",
        po_line_id=po_line.id, auto=False,
    )
    return row, link


def _seed_class_e_reserve(db, *, company_id, product):
    """(e) CS reserve: `reserve_request_row_id` set."""
    _core_line, row = _seeded_row(db, company_id=company_id, product=product)
    link = _reserve_link(db, company_id=company_id, row=row, qty="5")
    return row, link


def _seed_one_of_each(db, *, company_id, product):
    row_a, link_a = _seed_class_a_book(db, company_id=company_id, product=product)
    row_b, link_b, po_line_b = _seed_class_b_cascade_open(db, company_id=company_id, product=product)
    row_c, link_c = _seed_class_c_cascade_closed(db, company_id=company_id, product=product)
    row_d, link_d = _seed_class_d_not_auto(db, company_id=company_id, product=product)
    row_e, link_e = _seed_class_e_reserve(db, company_id=company_id, product=product)
    return {
        "a": (row_a, link_a),
        "b": (row_b, link_b, po_line_b),
        "c": (row_c, link_c),
        "d": (row_d, link_d),
        "e": (row_e, link_e),
    }


# ============================================================== AC-LT-41
def test_dry_run_counts_each_class_and_writes_nothing(ctx):
    db = ctx.db
    product = _seed_product(db, company_id=ctx.company_a)
    seeded = _seed_one_of_each(db, company_id=ctx.company_a, product=product)
    db.commit()

    module = _module()
    summary = module.run(db, apply=False)

    counts = summary["class_counts"][ctx.company_a]
    assert counts[module.CLASS_BOOK] == 1
    assert counts[module.CLASS_CASCADE_OPEN] == 1
    assert counts[module.CLASS_CASCADE_CLOSED] == 1
    assert counts[module.CLASS_NOT_AUTO] == 1
    assert counts[module.CLASS_RESERVE] == 1

    # nothing written: every real link still stands, no suggestion exists
    for key in "abcde":
        row = seeded[key][0]
        assert len(_links_of(db, row.id)) == 1, key
        assert _suggested_of(db, row.id) == [], key
        db.refresh(row)
        assert row.state == INQUIRY_PLACED, key

    # (b) and (c) would both go fully uncovered - placed -> raised
    transitions = summary["transition_counts"][ctx.company_a]
    assert transitions[(INQUIRY_PLACED, INQUIRY_RAISED)] == 2
    assert summary["qty_delta"][ctx.company_a] == Decimal("10")
    assert summary["touched_row_count"] == 0


# ============================================================== AC-LT-42
def test_apply_converts_b_and_c_only(ctx):
    db = ctx.db
    product = _seed_product(db, company_id=ctx.company_a)
    seeded = _seed_one_of_each(db, company_id=ctx.company_a, product=product)
    db.commit()

    module = _module()
    summary = module.run(db, apply=True)
    db.commit()

    row_a, _link_a = seeded["a"]
    row_b, _link_b, po_line_b = seeded["b"]
    row_c, _link_c = seeded["c"]
    row_d, _link_d = seeded["d"]
    row_e, _link_e = seeded["e"]

    # (a), (d), (e) untouched
    assert len(_links_of(db, row_a.id)) == 1
    assert len(_links_of(db, row_d.id)) == 1
    assert len(_links_of(db, row_e.id)) == 1

    # (b) becomes a suggested link of the same target and qty, trigger "converted";
    # the real link and its claim are gone.
    assert _links_of(db, row_b.id) == []
    suggestions_b = _suggested_of(db, row_b.id)
    assert len(suggestions_b) == 1
    assert suggestions_b[0].po_line_id == po_line_b.id
    assert suggestions_b[0].qty == Decimal("5")
    assert suggestions_b[0].trigger == "converted"

    # (c) is removed with its claim, no suggestion, and the row carries the ruling note
    assert _links_of(db, row_c.id) == []
    assert _suggested_of(db, row_c.id) == []
    db.refresh(row_c)
    assert (
        "removed: suggested by the cascade, not named by AutoCount (24 Sep ruling)"
        in row_c.note
    )

    # the state changes match what refresh_link_state itself derives
    db.refresh(row_a)
    db.refresh(row_b)
    db.refresh(row_d)
    db.refresh(row_e)
    assert row_a.state == INQUIRY_PLACED
    assert row_b.state == INQUIRY_RAISED
    assert row_c.state == INQUIRY_RAISED
    assert row_d.state == INQUIRY_PLACED
    assert row_e.state == INQUIRY_PLACED

    assert summary["touched_row_count"] == 2


# ============================================================== AC-LT-43
def test_second_apply_changes_nothing(ctx):
    db = ctx.db
    product = _seed_product(db, company_id=ctx.company_a)
    row_b, _link_b, po_line_b = _seed_class_b_cascade_open(
        db, company_id=ctx.company_a, product=product
    )
    row_c, _link_c = _seed_class_c_cascade_closed(db, company_id=ctx.company_a, product=product)
    db.commit()

    module = _module()
    module.run(db, apply=True)
    db.commit()

    suggested_before = [
        (s.id, s.po_line_id, s.qty, s.trigger) for s in _suggested_of(db, row_b.id)
    ]
    note_before = row_c.note

    second = module.run(db, apply=True)
    db.commit()

    assert second["touched_row_count"] == 0
    counts = second["class_counts"].get(ctx.company_a, {})
    assert counts.get(module.CLASS_CASCADE_OPEN, 0) == 0
    assert counts.get(module.CLASS_CASCADE_CLOSED, 0) == 0
    assert [
        (s.id, s.po_line_id, s.qty, s.trigger) for s in _suggested_of(db, row_b.id)
    ] == suggested_before
    db.refresh(row_c)
    assert row_c.note == note_before


def test_actioned_and_cancelled_rows_are_never_touched(ctx):
    """AC-LT-43: `actioned`/`cancelled` rows are excluded from the row query outright,
    so a class (b)-shaped link sitting on one is never even classified."""
    db = ctx.db
    product = _seed_product(db, company_id=ctx.company_a)
    row, _link, _po_line = _seed_class_b_cascade_open(
        db, company_id=ctx.company_a, product=product
    )
    row.state = INQUIRY_ACTIONED
    db.flush()
    db.commit()

    module = _module()
    summary = module.run(db, apply=True)
    db.commit()

    counts = summary["class_counts"].get(ctx.company_a, {})
    assert counts.get(module.CLASS_CASCADE_OPEN, 0) == 0
    assert len(_links_of(db, row.id)) == 1
    db.refresh(row)
    assert row.state == INQUIRY_ACTIONED


# ============================================================== AC-LT-44
def test_classification_reads_the_book_helper_not_the_note(ctx):
    """AC-LT-44: a book link whose row note reads `auto: worklist` (the book step runs
    INSIDE every cascade pass too, plan 2.1) is still class (a) - classification never
    reads the note's `auto:` stamp."""
    db = ctx.db
    product = _seed_product(db, company_id=ctx.company_a)
    row, link = _seed_class_a_book(db, company_id=ctx.company_a, product=product)
    row.note = f"Linked to {link.document}; auto: worklist"
    db.flush()
    db.commit()

    module = _module()
    svc = ProjectOrderInquiryService(db)
    assert module.classify_link(db, svc, row, link) == module.CLASS_BOOK


# ============================================================== main()
def test_main_default_run_writes_nothing(ctx, monkeypatch):
    db = ctx.db
    product = _seed_product(db, company_id=ctx.company_a)
    row, _link, _po_line = _seed_class_b_cascade_open(
        db, company_id=ctx.company_a, product=product
    )
    db.commit()

    module = _module()
    monkeypatch.setattr(module, "SessionLocal", lambda: _NoCloseSession(db))
    monkeypatch.setattr(sys, "argv", ["convert_oi_cascade_links.py"])

    exit_code = module.main()

    assert exit_code == 0
    assert len(_links_of(db, row.id)) == 1
    assert _suggested_of(db, row.id) == []


def test_main_apply_converts_through_refresh_link_state(ctx, monkeypatch):
    db = ctx.db
    product = _seed_product(db, company_id=ctx.company_a)
    row, _link, po_line = _seed_class_b_cascade_open(
        db, company_id=ctx.company_a, product=product
    )
    db.commit()

    module = _module()
    monkeypatch.setattr(module, "SessionLocal", lambda: _NoCloseSession(db))
    monkeypatch.setattr(sys, "argv", ["convert_oi_cascade_links.py", "--apply"])

    exit_code = module.main()

    assert exit_code == 0
    assert _links_of(db, row.id) == []
    suggestions = _suggested_of(db, row.id)
    assert len(suggestions) == 1
    assert suggestions[0].po_line_id == po_line.id
    db.refresh(row)
    assert row.state == INQUIRY_RAISED
