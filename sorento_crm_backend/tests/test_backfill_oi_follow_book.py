"""S4 - `scripts/backfill_oi_follow_book.py`: give every EXISTING order inquiry
row the one book-following pass S1-S3 only wired into the ingest hooks and the
cascade.

UAC: `documentation/plans/scm/oi-follow-book-chain-acceptance-criteria.md`,
Group D (AC-FB-40, AC-FB-41).
Plan: `documentation/plans/scm/PLAN-oi-follow-book-chain.md`, S4.

Test-AFTER: the script (`scripts/backfill_oi_follow_book.py`, commit
bd9145dd7) already exists, `main(argv: Optional[Sequence[str]] = None,
db=None) -> int`. Driven the way `tests/test_backfill_retire_superseded_
order_inquiry_rows.py` drives its own backfill's `main`/`run` on a fixture
session; seeded the way `tests/test_oi_follow_book_chain.py` (S1) seeds a
book chain - `ctx` and its helpers are reused here by import, unedited.

Every test below can still fail - the line of the script that would turn it
red is named in each test's own docstring. `test_dry_run_writes_nothing_and_
reports` was ACTUALLY broken and restored to confirm this (see its docstring);
the rest are stated, not executed, per the tester brief.
"""
from __future__ import annotations

from decimal import Decimal

import uuid

from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ORDER,
    OrderInquiryLink,
    OrderInquiryRow,
)
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from tests.test_oi_follow_book_chain import (
    ctx,  # noqa: F401 - pytest fixture, imported for reuse
    _existing_link,
    _links_of,
    _ref,
    _seed_mirror,
    _seed_product,
    _seed_row,
    _seed_row_and_mirror,
    _seed_so_line,
    _seed_spo_line,
)

import scripts.backfill_oi_follow_book as backfill

__all__ = ["ctx"]


# --------------------------------------------------------------------- world
def _seed_free_row(db, *, company_id, product_id, qty):
    """A row whose book document has FREE capacity - the plain case (AC-FB-1
    shape): a visible SPO allocation naming the row's own core line directly,
    nobody else holding it. Returns `(row, spo)`."""
    ref = _ref("SOL")
    _so, core_line = _seed_so_line(
        db, company_id=company_id, product_id=product_id, source_ref=ref, qty=qty
    )
    spo = _seed_spo_line(
        db, company_id=company_id, product_id=product_id,
        from_so_line_ref=ref, allocated_quantity=int(qty),
    )
    _pso, _mirror, _inquiry, row = _seed_row_and_mirror(
        db, company_id=company_id, core_line=core_line, product_id=product_id, qty=qty,
    )
    return row, spo


def _seed_displacement_pair(db, *, company_id, product_id, qty):
    """A book row (`row_disp`) whose document is fully held by a DIFFERENT
    core line's row (`holder_row`, auto-linked) - the D3 shape (AC-FB-30).
    Returns `(row_disp, holder_row, spo)`."""
    ref_disp = _ref("SOL")
    _so_disp, core_line_disp = _seed_so_line(
        db, company_id=company_id, product_id=product_id, source_ref=ref_disp, qty=qty,
    )
    spo = _seed_spo_line(
        db, company_id=company_id, product_id=product_id,
        from_so_line_ref=ref_disp, allocated_quantity=int(qty),
    )
    _pso_disp, _mirror_disp, _inquiry_disp, row_disp = _seed_row_and_mirror(
        db, company_id=company_id, core_line=core_line_disp, product_id=product_id, qty=qty,
    )

    ref_holder = _ref("SOL")
    _so_holder, core_line_holder = _seed_so_line(
        db, company_id=company_id, product_id=product_id, source_ref=ref_holder, qty=qty,
    )
    _pso_holder, mirror_holder, inquiry_holder = _seed_mirror(
        db, company_id=company_id, core_line=core_line_holder, product_id=product_id, qty=qty,
    )
    holder_row = _seed_row(
        db, company_id=company_id, inquiry_id=inquiry_holder.id, so_line_id=mirror_holder.id,
        qty=qty, state=INQUIRY_PLACED, ack_state=ACK_ACKNOWLEDGED,
    )
    _existing_link(
        db, company_id=company_id, row_id=holder_row.id, document=spo.spo_number,
        qty=qty, spo_allocation_id=spo.id, auto=True,
    )
    return row_disp, holder_row, spo


def _seed_world(ctx):
    """Company A: one free-capacity row (named 1, linked 1) plus one
    displacement pair (named +1, linked +1, displaced +1) -> named 2, linked
    2, displaced 1. Company B: one free-capacity row -> named 1, linked 1,
    displaced 0. Matches the fix-round brief's own figures exactly."""
    db = ctx.db
    product_a = _seed_product(db, company_id=ctx.company_a)
    row_free, spo_free = _seed_free_row(db, company_id=ctx.company_a, product_id=product_a.id, qty="3")
    row_disp, holder_row, spo_disp = _seed_displacement_pair(
        db, company_id=ctx.company_a, product_id=product_a.id, qty="5"
    )

    product_b = _seed_product(db, company_id=ctx.company_b)
    row_b, spo_b = _seed_free_row(db, company_id=ctx.company_b, product_id=product_b.id, qty="2")

    db.commit()
    return {
        "row_free": row_free, "spo_free": spo_free,
        "row_disp": row_disp, "holder_row": holder_row, "spo_disp": spo_disp,
        "row_b": row_b, "spo_b": spo_b,
    }


def _all_links(db):
    return db.query(OrderInquiryLink).all()


def _refresh(db, row):
    db.expire_all()
    return db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row.id).one()


# ============================================================== AC-FB-40
def test_dry_run_writes_nothing_and_reports(ctx, capsys):
    """AC-FB-40: `--dry-run` (and no args, the same default) writes nothing at
    all and reports the four figures per company.

    Break line to see this red: `scripts/backfill_oi_follow_book.py`'s
    `run_company`, the `else: savepoint.rollback()` branch - comment it out
    (or replace with `pass`) so a dry run actually keeps what each page wrote.
    ACTUALLY DONE: commented out `savepoint.rollback()`, reran this test,
    watched it fail (`links after dry run` == 3 instead of 1, the holder's
    link had moved), restored the line, reran, green again. Not committed.
    """
    world = _seed_world(ctx)
    db = ctx.db

    links_before = {link.id: (link.spo_allocation_id, link.po_line_id, Decimal(str(link.qty)))
                    for link in _all_links(db)}
    assert len(links_before) == 1, links_before  # only the holder's own seeded link

    out = backfill.main(["--dry-run"], db=db)
    assert out == 0

    captured = capsys.readouterr()
    # Scoped to the PER-COMPANY blocks only - the "=== summary, all
    # companies ===" section below prints the same totals again and would
    # otherwise double-count a substring match.
    per_company_out = captured.out.split("=== summary")[0]
    assert per_company_out.count("rows named by the book: 2") == 1, per_company_out
    assert per_company_out.count("rows linked:            2") == 1, per_company_out
    assert per_company_out.count("rows displaced:         1") == 1, per_company_out
    assert per_company_out.count("rows named by the book: 1") == 1, per_company_out
    assert per_company_out.count("rows linked:            1") == 1, per_company_out

    # Nothing written: same single link, same row, same qty, same id.
    links_after = {link.id: (link.spo_allocation_id, link.po_line_id, Decimal(str(link.qty)))
                   for link in _all_links(db)}
    assert links_after == links_before, (links_before, links_after)

    row_free = _refresh(db, world["row_free"])
    row_disp = _refresh(db, world["row_disp"])
    holder_row = _refresh(db, world["holder_row"])
    assert row_free.note is None and row_free.state == INQUIRY_RAISED
    assert row_disp.note is None and row_disp.state == INQUIRY_RAISED
    assert holder_row.note is None and holder_row.state == INQUIRY_PLACED

    # The same call with NO CLI flags at all is the same default - re-run to
    # prove it, on the same unchanged state. `argv=[]` is "no flags given" to
    # the script's own parser; `argv=None` would tell argparse to read the
    # REAL `sys.argv`, which under pytest is pytest's own arguments, not the
    # script's - a fixture bug this test caught in itself, not the script.
    out2 = backfill.main([], db=db)
    assert out2 == 0
    links_after_2 = {link.id: (link.spo_allocation_id, link.po_line_id, Decimal(str(link.qty)))
                     for link in _all_links(db)}
    assert links_after_2 == links_before


# ============================================================== AC-FB-41
def test_apply_writes_what_dry_run_printed(ctx, capsys):
    """AC-FB-41: `--apply` writes exactly what the dry run counted.

    Break line to see this red: `run_company`'s `if apply: db.commit()` -
    invert it to `if not apply: db.commit()` so an apply pass never persists
    and a dry run does; every link assertion below would then find nothing.
    """
    world = _seed_world(ctx)
    db = ctx.db

    dry = backfill.run(db, apply=False, batch=500)
    named_a = dry[ctx.company_a]["rows_named_by_book"]
    linked_a = dry[ctx.company_a]["rows_linked"]
    displaced_a = dry[ctx.company_a]["rows_displaced"]
    assert (named_a, linked_a, displaced_a) == (2, 2, 1), dry[ctx.company_a]
    named_b = dry[ctx.company_b]["rows_named_by_book"]
    linked_b = dry[ctx.company_b]["rows_linked"]
    assert (named_b, linked_b) == (1, 1), dry[ctx.company_b]

    out = backfill.main(["--apply"], db=db)
    assert out == 0
    capsys.readouterr()

    row_free = _refresh(db, world["row_free"])
    row_disp = _refresh(db, world["row_disp"])
    holder_row = _refresh(db, world["holder_row"])
    row_b = _refresh(db, world["row_b"])

    free_links = _links_of(db, row_free.id)
    assert len(free_links) == 1 and free_links[0].spo_allocation_id == world["spo_free"].id
    assert Decimal(str(free_links[0].qty)) == Decimal("3")

    disp_links = _links_of(db, row_disp.id)
    assert len(disp_links) == 1 and disp_links[0].spo_allocation_id == world["spo_disp"].id
    assert Decimal(str(disp_links[0].qty)) == Decimal("5")

    assert _links_of(db, holder_row.id) == [], "the holder must be displaced, not left holding it"
    assert "AutoCount states" in (holder_row.note or ""), holder_row.note
    assert holder_row.state != INQUIRY_PLACED

    b_links = _links_of(db, row_b.id)
    assert len(b_links) == 1 and b_links[0].spo_allocation_id == world["spo_b"].id
    assert Decimal(str(b_links[0].qty)) == Decimal("2")

    # rows_linked counted (row_free, row_disp) for A and (row_b) for B, exactly
    # what the dry run counted, and displaced counted the holder - the same
    # figures the dry run already printed.
    assert linked_a == 2 and displaced_a == 1 and linked_b == 1


def test_apply_twice_is_idempotent(ctx, capsys):
    """AC-FB-41: a second `--apply` writes nothing - same link ids and qtys,
    row notes unchanged, and the SECOND run's own report says linked 0,
    displaced 0.

    Break line to see this red: `ProjectOrderInquiryService.follow_book_for_
    rows`'s own `_unlinked_need(row) <= _ZERO: continue` guard is what makes
    this idempotent - but scoped to the SCRIPT itself, the break is
    `_company_link_snapshot`'s comparison in `run_company`
    (`if now > was: rows_linked.add(...)`) - loosen it to `if now >= was` and
    the SECOND pass would wrongly count every already-linked row as newly
    linked again, even though nothing in the database actually changed.
    """
    world = _seed_world(ctx)
    db = ctx.db

    backfill.main(["--apply"], db=db)
    capsys.readouterr()

    links_after_first = {
        link.id: (link.row_id, link.spo_allocation_id, link.po_line_id, Decimal(str(link.qty)))
        for link in _all_links(db)
    }
    notes_after_first = {
        row_id: _refresh(db, world[key]).note
        for row_id, key in (
            (world["row_free"].id, "row_free"),
            (world["row_disp"].id, "row_disp"),
            (world["holder_row"].id, "holder_row"),
            (world["row_b"].id, "row_b"),
        )
    }

    out = backfill.main(["--apply"], db=db)
    assert out == 0
    captured = capsys.readouterr()
    per_company_out = captured.out.split("=== summary")[0]

    assert per_company_out.count("rows linked:            0") == 2, per_company_out
    assert per_company_out.count("rows displaced:         0") == 2, per_company_out

    links_after_second = {
        link.id: (link.row_id, link.spo_allocation_id, link.po_line_id, Decimal(str(link.qty)))
        for link in _all_links(db)
    }
    assert links_after_second == links_after_first

    for row_id, key in (
        (world["row_free"].id, "row_free"),
        (world["row_disp"].id, "row_disp"),
        (world["holder_row"].id, "holder_row"),
        (world["row_b"].id, "row_b"),
    ):
        assert _refresh(db, world[key]).note == notes_after_first[row_id]


# ============================================================== [SEC]
def test_company_isolation(ctx):
    """[SEC] Company B's row is never linked to company A's document even
    when the refs collide textually (same `source_ref` string in both
    companies) - the per-company `company_scope` the script's own `run()`
    enters must hold even though the STRING is identical.

    Widening the SCRIPT's own `run()` `company_scope` line to `company_scope(db,
    None)` does NOT turn this test red (reviewer's kill test, review round item
    12b) - `ProjectOrderInquiryService.follow_book_for_rows` re-pins its own
    scope via `company_id=company_id` regardless of what scope it is called
    under, so the script's `with company_scope(...)` line is redundant belt,
    not the guard. The real guard is that service-level scope pin; a test that
    would actually go red is a defect INSIDE `follow_book_for_rows` itself
    that ignores or widens its own `company_id` argument.
    """
    db = ctx.db
    shared_ref = _ref("SHARED")

    product_a = _seed_product(db, company_id=ctx.company_a)
    _so_a, core_line_a = _seed_so_line(
        db, company_id=ctx.company_a, product_id=product_a.id, source_ref=shared_ref, qty="4",
    )
    spo_a = _seed_spo_line(
        db, company_id=ctx.company_a, product_id=product_a.id,
        from_so_line_ref=shared_ref, allocated_quantity=4,
    )
    _pso_a, _mirror_a, _inquiry_a, row_a = _seed_row_and_mirror(
        db, company_id=ctx.company_a, core_line=core_line_a, product_id=product_a.id, qty="4",
    )

    product_b = _seed_product(db, company_id=ctx.company_b)
    _so_b, core_line_b = _seed_so_line(
        db, company_id=ctx.company_b, product_id=product_b.id, source_ref=shared_ref, qty="4",
    )
    # No document at all in company B naming this ref - only company A's does.
    _pso_b, _mirror_b, _inquiry_b, row_b = _seed_row_and_mirror(
        db, company_id=ctx.company_b, core_line=core_line_b, product_id=product_b.id, qty="4",
    )
    db.commit()

    out = backfill.main(["--apply"], db=db)
    assert out == 0

    links_a = _links_of(db, row_a.id)
    links_b = _links_of(db, row_b.id)
    assert len(links_a) == 1 and links_a[0].spo_allocation_id == spo_a.id, links_a
    assert links_b == [], "company B's row must never resolve company A's document"


# ============================================================== AC-FB-40/41
def test_pages_by_keyset(ctx):
    """Pages by id, never OFFSET - `run_company`'s own keyset loop
    (`OrderInquiryRow.id > last_id`, `ORDER BY id ASC`). Five free-capacity
    rows, `--batch 2` (the script's only page-size control - there is no
    separate module-level constant to monkeypatch, see report), forcing
    three pages (2 + 2 + 1); all five must still be linked.

    Break line to see this red: `run_company`'s `last_id = page_ids[-1]` -
    change to `page_ids[0]` (the wrong cursor) and the second page would
    re-read (or skip past) rows the first page already covered, so not every
    row reaches `follow_book_for_rows` across the run.
    """
    db = ctx.db
    product = _seed_product(db, company_id=ctx.company_a)
    rows = []
    for _ in range(5):
        row, _spo = _seed_free_row(db, company_id=ctx.company_a, product_id=product.id, qty="1")
        rows.append(row)
    db.commit()

    out = backfill.main(["--apply", "--batch", "2"], db=db)
    assert out == 0

    for row in rows:
        links = _links_of(db, row.id)
        assert len(links) == 1, (row.id, links)


# ============================================================== review round item 3
def test_redirected_row_never_linked_by_backfill(ctx):
    """Review round item 3: `follow_book_for_rows`'s own row-narrowing carries
    no `redirected_to_pool` filter, so the backfill script - which drives that
    same narrowing over every existing row - links a REDIRECTED row too. A
    fresh sibling row of the same mirror line must get the document instead."""
    db = ctx.db
    product = _seed_product(db, company_id=ctx.company_a)
    row_redirected, spo = _seed_free_row(db, company_id=ctx.company_a, product_id=product.id, qty="2")
    row_redirected.redirected_to_pool = True
    db.add(row_redirected)

    fresh_row = OrderInquiryRow(
        company_id=ctx.company_a, order_inquiry_id=row_redirected.order_inquiry_id,
        so_line_id=row_redirected.so_line_id, qty=Decimal("2"), verb=IV_ORDER,
        state=INQUIRY_RAISED, ack_state=ACK_ACKNOWLEDGED,
    )
    db.add(fresh_row)
    db.commit()

    out = backfill.main(["--apply"], db=db)
    assert out == 0

    assert _links_of(db, row_redirected.id) == [], _links_of(db, row_redirected.id)
    fresh_links = _links_of(db, fresh_row.id)
    assert len(fresh_links) == 1 and fresh_links[0].spo_allocation_id == spo.id, fresh_links


# ============================================================== review round item 9
def test_backfill_displacement_note_names_the_backfill_trigger(ctx):
    """Review round item 9 (security S6): the displaced holder's note must name
    the TRIGGER the call ran under, not only the document and SO number - the
    backfill script passes through the exact same `_displace_other_line_
    holders` path with `trigger="backfill"` hardcoded
    (`scripts/backfill_oi_follow_book.py` line 160), and the fragment written
    today (`f"AutoCount states {document} is for {so_number}, {when}"`) never
    embeds the trigger at all. Keeps the existing "AutoCount states" substring
    assertions (`test_apply_writes_what_dry_run_printed`) valid - this only
    ADDS the trigger assertion, on the same note."""
    world = _seed_world(ctx)
    db = ctx.db

    out = backfill.main(["--apply"], db=db)
    assert out == 0

    holder_row = _refresh(db, world["holder_row"])
    note = holder_row.note or ""
    assert "AutoCount states" in note, note
    assert "backfill" in note, note


# ============================================================== review round item 10
def test_backfill_counts_displacement_even_when_recascade_nets_to_the_same_total(ctx, capsys):
    """Review round item 10 (reviewer finding 10): `rows_linked` / `quantity_
    linked` must count only what the BOOK placed, not what the trailing
    cascade re-links for a displaced holder - and a displaced row the cascade
    re-links to the SAME total quantity must still count as displaced.

    Seeded here (not in `_seed_world`, so the other three tests reusing it are
    untouched): the same D3 displacement pair as `_seed_displacement_pair`,
    PLUS a second OPEN document naming the holder's own line directly - free
    capacity the ordinary cascade can hand straight back to the holder, for
    the SAME quantity it just lost, inside the SAME `follow_book_for_rows`
    call (AC-FB-30's own "offered to the cascade once" nested pass).

    Break line to see this red: `run_company`'s snapshot diff, `if now > was:
    rows_linked... elif now < was: rows_displaced...` - a same-row link SET
    change (different target id) that leaves the TOTAL quantity unchanged
    (`now == was`) falls into neither bucket, so the book's own displacement
    of the holder vanishes from the report entirely.
    """
    db = ctx.db
    product = _seed_product(db, company_id=ctx.company_a)

    ref_disp = _ref("SOL")
    _so_disp, core_line_disp = _seed_so_line(
        db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_disp, qty="5",
    )
    spo_disp = _seed_spo_line(
        db, company_id=ctx.company_a, product_id=product.id,
        from_so_line_ref=ref_disp, allocated_quantity=5,
    )
    _pso_disp, _mirror_disp, _inquiry_disp, row_disp = _seed_row_and_mirror(
        db, company_id=ctx.company_a, core_line=core_line_disp, product_id=product.id, qty="5",
    )

    ref_holder = _ref("SOL")
    _so_holder, core_line_holder = _seed_so_line(
        db, company_id=ctx.company_a, product_id=product.id, source_ref=ref_holder, qty="5",
    )
    _pso_holder, mirror_holder, inquiry_holder = _seed_mirror(
        db, company_id=ctx.company_a, core_line=core_line_holder, product_id=product.id, qty="5",
    )
    holder_row = _seed_row(
        db, company_id=ctx.company_a, inquiry_id=inquiry_holder.id, so_line_id=mirror_holder.id,
        qty="5", state=INQUIRY_PLACED, ack_state=ACK_ACKNOWLEDGED,
    )
    _existing_link(
        db, company_id=ctx.company_a, row_id=holder_row.id, document=spo_disp.spo_number,
        qty="5", spo_allocation_id=spo_disp.id, auto=True,
    )
    # The rebound capacity: an OPEN document naming the HOLDER's own line, free
    # for the ordinary cascade to give straight back once the book takes
    # spo_disp away, for the same total quantity (5).
    spo_rebound = _seed_spo_line(
        db, company_id=ctx.company_a, product_id=product.id,
        from_so_line_ref=ref_holder, allocated_quantity=5,
    )
    db.commit()

    out = backfill.main(["--dry-run"], db=db)
    assert out == 0
    captured = capsys.readouterr()
    per_company_out = captured.out.split("=== summary")[0]

    assert per_company_out.count("rows displaced:         1") == 1, per_company_out
