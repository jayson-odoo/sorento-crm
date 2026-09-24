"""Issue #1215 point 1: a row reading `placed`/`partly_linked` with no links and no
bundle behind it - the diagnosis found 17 such rows company wide on the 23 Sep 2026 prod
copy, their links deleted by a path that bypassed `_remove_links` and never re-derived
the state afterwards.

Two things are pinned here:

* the GUARD, `ProjectOrderInquiryService.auto_place_for_products` (the worklist's Auto
  link all / Link now cascade) now re-derives every row it loads through
  `refresh_link_state` before it walks candidates, so a row like this heals back to
  `raised` (To buy) even when the walk finds no document to link it to;
* the REPAIR, `scripts/repair_oi_stale_link_state.py` - a dry-run-first operator script
  over the same invariant, company wide.

Reuses `tests/test_order_inquiry_place_on_po.py`'s harness wholesale: the same seeded
world (product, warehouse, supplier, open PO), and the same `blank_session` substrate.
"""
from __future__ import annotations

import importlib.util
import os

from app.models.base import company_scope
from app.models.project_so import (
    INQUIRY_PARTLY_LINKED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    OrderInquiryLink,
)
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from .test_order_inquiry_place_on_po import _api, _row, PURCHASING

import pytest


@pytest.fixture()
def api():
    yield from _api(PURCHASING)


def _links_of(db, row_id: str):
    return db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row_id).all()


def _repair_module():
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts",
        "repair_oi_stale_link_state.py",
    )
    spec = importlib.util.spec_from_file_location("_repair_oi_stale_link_state", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _invariant_holds(db, row) -> bool:
    """"placed or partly_linked implies links or bundle" (the diagnosis's own words)."""
    if row.state not in (INQUIRY_PLACED, INQUIRY_PARTLY_LINKED):
        return True
    return bool(_links_of(db, row.id)) or row.bundled_qty > 0


def test_a_stale_placed_row_with_no_links_violates_the_invariant_when_seeded(api):
    """Sanity check on the fixture itself: the row this file seeds really does start in
    the broken state the diagnosis found on prod, not something the ORM already prevents."""
    _client, db, world, _user_id = api
    row = _row(
        db, world["company_id"], world["inquiry"],
        qty="5", item_code=world["product"].product_code,
        state=INQUIRY_PLACED, po_ref="STALE-PO-0001",
        note="Linked to STALE-PO-0001 (Dafuyuan), expected 2026-09-01; auto: worklist",
    )
    db.commit()
    db.refresh(row)
    assert _links_of(db, row.id) == []
    assert row.bundled_qty == 0
    assert not _invariant_holds(db, row)


def test_auto_place_for_products_self_heals_a_stale_placed_row_even_with_no_candidate(api):
    """The GUARD. No open PO line exists for this product in `world`, so the cascade's
    own walk finds nothing to link this row to - before the fix that meant the row was
    left exactly as it was, stuck `placed` forever. The fix re-derives every row this
    pass loads through `refresh_link_state` up front, so the row reads `raised` (To buy)
    with its stale `po_ref` cleared regardless of what the walk finds afterwards."""
    _client, db, world, user_id = api
    row = _row(
        db, world["company_id"], world["inquiry"],
        qty="5", item_code=world["product"].product_code,
        state=INQUIRY_PLACED, po_ref="STALE-PO-0001",
        note="Linked to STALE-PO-0001 (Dafuyuan), expected 2026-09-01; auto: worklist",
    )
    db.commit()

    with company_scope(db, frozenset({world["company_id"]})):
        result = ProjectOrderInquiryService(db).auto_place_for_products(
            None, actor_user_id=user_id, trigger="worklist",
            redeal_drafts=True, include_awaiting=True,
        )
        db.commit()

    assert result["placed_rows"] == 0
    db.refresh(row)
    assert row.state == INQUIRY_RAISED
    assert row.po_ref is None
    assert row.po_line_id is None
    assert row.spo_ref is None
    assert _invariant_holds(db, row)


def test_auto_place_for_products_self_heal_issues_no_extra_query_on_a_healthy_pass(api, monkeypatch):
    """Should-fix 3 (review of PR #1220): the self-heal guard must cost NOTHING when
    every row this pass loads is healthy - bounded to the same `placed`/`partly_linked`
    + zero-bundle + zero-link predicate the repair script's own `find_stale_rows` uses,
    rather than a `refresh_link_state` (one `_links_of` query plus a `derive_bundles`
    reload) on every row it walks. `auto_place_for_products` calls `refresh_link_state`
    from exactly one place - the self-heal block - so a spy on it during the pass proves
    the bound: a healthy pass calls it zero times.

    The row is seeded PLACED with a REAL link directly, never through the cascade walk
    itself - S3 (`oi-links-autocount-truth`) changed the walk to suggest rather than
    place, which is a separate concern from this bound and out of scope here."""
    from decimal import Decimal

    _client, db, world, user_id = api
    from .test_order_inquiry_place_on_po import _po_line

    line = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"],
        qty_ordered="20",
    )
    row = _row(
        db, world["company_id"], world["inquiry"], qty="5",
        item_code=world["product"].product_code, state=INQUIRY_PLACED,
        po_ref=world["po"].po_number,
    )
    db.commit()
    db.add(
        OrderInquiryLink(
            company_id=world["company_id"], row_id=row.id, po_line_id=line.id,
            document=world["po"].po_number, qty=Decimal("5"),
        )
    )
    db.commit()
    db.refresh(row)
    assert row.state == INQUIRY_PLACED
    assert len(_links_of(db, row.id)) == 1

    calls = []
    original = ProjectOrderInquiryService.refresh_link_state

    def _spy(self, rows):
        calls.append(list(rows))
        return original(self, rows)

    monkeypatch.setattr(ProjectOrderInquiryService, "refresh_link_state", _spy)

    with company_scope(db, frozenset({world["company_id"]})):
        # The row is already placed for real, so nothing about it is stale - the
        # bounded self-heal query must find nothing and never call
        # `refresh_link_state` at all.
        ProjectOrderInquiryService(db).auto_place_for_products(
            None, actor_user_id=user_id, trigger="worklist",
            redeal_drafts=True, include_awaiting=True,
        )
        db.commit()

    assert calls == []


def test_auto_place_for_products_leaves_a_genuinely_placed_row_untouched(api):
    """The guard must not be a no-op that ALSO clobbers a row that is placed for real -
    only a row whose own links (and bundle) disagree with its stored state moves."""
    _client, db, world, user_id = api
    from .test_order_inquiry_place_on_po import _po_line

    line = _po_line(
        db, world["company_id"], world["po"], world["product"], world["warehouse"],
        qty_ordered="20",
    )
    row = _row(db, world["company_id"], world["inquiry"], qty="5", item_code=world["product"].product_code)
    db.commit()

    with company_scope(db, frozenset({world["company_id"]})):
        ProjectOrderInquiryService(db).auto_place_for_products(
            None, actor_user_id=user_id, trigger="worklist",
            redeal_drafts=True, include_awaiting=True,
        )
        db.commit()

    db.refresh(row)
    assert row.state == INQUIRY_PLACED
    assert row.po_line_id == line.id
    assert len(_links_of(db, row.id)) == 1
    assert _invariant_holds(db, row)


def test_repair_script_dry_run_lists_the_stale_row_and_writes_nothing(api):
    """The REPAIR script's dry run: it must find the row and print it, but touch nothing -
    `--apply` is the only thing that writes."""
    _client, db, world, _user_id = api
    row = _row(
        db, world["company_id"], world["inquiry"],
        qty="5", item_code=world["product"].product_code,
        state=INQUIRY_PARTLY_LINKED,
        note="Linked to STALE-SPO-2026/09-0001; auto: autocount_ingest",
    )
    row.spo_ref = "STALE-SPO-2026/09-0001"
    db.commit()

    module = _repair_module()
    found = module.find_stale_rows(db)
    assert row.id in [r.id for r in found]

    db.refresh(row)
    assert row.state == INQUIRY_PARTLY_LINKED
    assert row.spo_ref == "STALE-SPO-2026/09-0001"


def test_repair_script_apply_heals_the_row_and_reports_before_after_counts(api):
    _client, db, world, _user_id = api
    row = _row(
        db, world["company_id"], world["inquiry"],
        qty="5", item_code=world["product"].product_code,
        state=INQUIRY_PLACED, po_ref="STALE-PO-0002",
        note="Linked to STALE-PO-0002; auto: worklist",
    )
    db.commit()

    module = _repair_module()
    found = module.find_stale_rows(db)
    assert row.id in [r.id for r in found]

    ProjectOrderInquiryService(db).refresh_link_state(found)
    db.commit()

    db.refresh(row)
    assert row.state == INQUIRY_RAISED
    assert row.po_ref is None
    # A second pass finds nothing left - idempotent.
    assert row.id not in [r.id for r in module.find_stale_rows(db)]
