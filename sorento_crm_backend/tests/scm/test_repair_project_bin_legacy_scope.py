"""G15 (`scripts/repair_project_bin_self_claims.py`), the `--scope legacy` half AC-6.17
pins for `today` only (`tests/scm/test_write_time_supply_claim.py::test_the_repair_undoes_
the_born_claimed_pass_and_spares_a_real_attribution`).

`legacy` extends the repair to every OTHER automatic project-bin placement that predates
G12's gate entirely - not just the withdrawn born-claimed pass's own hours-old writes - so
its population and `today`'s overlap only partly:

  * an auto placement with NO claim at all (ancient, from before claims existed) is
    `legacy`-only: `today`'s own guard requires a claim to even be a candidate;
  * an auto placement whose only claim is a self-written `order_inquiry` row from BEFORE
    the cut-off is `legacy`-only too - `today`'s cut-off excludes it on purpose, on the
    theory that an old self-claim is not the pass PR #490 just wrote;
  * an auto placement an EXTERNAL claim (the book, a person, the supply writer) names the
    row's own sales order for is spared by BOTH scopes;
  * a manual link (`auto = false`) is never touched by either scope.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text

from tests._pg_fixture import pg_session
from tests.scm.conftest import requires_pg

pytestmark = requires_pg

MARKER = "ZZTPBLEG"

SOON = date.today() + timedelta(days=45)


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    from app.models.base import company_scope
    from tests.scm.conftest import SORENTO_COMPANY_ID, ensure_reference_data

    with pg_session() as session:
        ensure_reference_data(session)
        with company_scope(session, frozenset({SORENTO_COMPANY_ID})):
            yield session


def _repair_module():
    import importlib.util
    import os

    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "scripts", "repair_project_bin_self_claims.py",
    )
    spec = importlib.util.spec_from_file_location("_repair_pbsc_legacy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _project_bin(db, code: str) -> str:
    wid = _u()
    db.execute(
        text(
            "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
            "segment, created_at, updated_at) "
            "VALUES (:i, :c, :c, true, 'project', now(), now())"
        ),
        {"i": wid, "c": code},
    )
    db.flush()
    return wid


def _draft_line(db, *, product_id, warehouse_id, qty) -> str:
    po_id = _u()
    db.execute(
        text(
            "INSERT INTO purchase_orders (id, po_number, status, issue_date, "
            "currency, source_system) "
            "VALUES (:i, :n, 'active', :d, 'MYR', 'scm_upload')"
        ),
        {"i": po_id, "n": f"{MARKER}-{uuid.uuid4().hex[:8].upper()}", "d": date(2026, 8, 1)},
    )
    line_id = _u()
    db.execute(
        text(
            "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, "
            "warehouse_id, qty_ordered, qty_received, unit_cost, currency, line_status, "
            "expected_date) VALUES (:i, :po, :p, :w, :q, 0, 10, 'MYR', 'open', :e)"
        ),
        {"i": line_id, "po": po_id, "p": product_id, "w": warehouse_id, "q": qty,
         "e": SOON},
    )
    db.flush()
    return line_id


def _so_ref(db, pso_id) -> str:
    return db.execute(
        text(
            "SELECT COALESCE(autocount_doc_no, provisional_ref) "
            "  FROM projects.sales_orders WHERE id = :i"
        ),
        {"i": pso_id},
    ).scalar()


def _link(db, row, line_id, qty, *, auto, linked_at, claim=None):
    """One `order_inquiry_links` row, and its named `scm.order_link_claim` if given.
    `claim=None` reproduces a link from BEFORE claims existed at all - `legacy`'s only-
    populated-by-absence case."""
    claim_id = None
    if claim is not None:
        claim_id = _u()
        db.execute(
            text(
                "INSERT INTO scm.order_link_claim (id, so_number, po_number, item_code, "
                "source, claimed_at, po_line_id, resolved_at) "
                "VALUES (:i, :son, :pon, NULL, :src, :at, :pol, now())"
            ),
            {"i": claim_id, "son": claim["so_number"],
             "pon": f"{MARKER}-{uuid.uuid4().hex[:6]}", "src": claim["source"],
             "at": claim["claimed_at"], "pol": line_id},
        )
    db.execute(
        text(
            "INSERT INTO projects.order_inquiry_links (id, row_id, po_line_id, "
            "document, qty, auto, claim_id, linked_at) "
            "VALUES (:i, :r, :pol, :doc, :q, :auto, :c, :at)"
        ),
        {"i": _u(), "r": str(row["inquiry_row"].id), "pol": line_id, "doc": f"{MARKER}-doc",
         "q": qty, "auto": auto, "c": claim_id, "at": linked_at},
    )
    db.flush()
    return claim_id


def test_legacy_scope_repairs_ancient_and_pre_cutoff_placements_the_today_scope_leaves(db):
    """Four placements, each a distinct case `today` and `legacy` have to tell apart:

      * `orphan`    - no claim at all (predates claims entirely): `legacy`-only.
      * `stale_self`- a self-written `order_inquiry` claim from BEFORE the cut-off:
                      `today` spares it (its own date guard), `legacy` still repairs it.
      * `book_kept` - an EXTERNAL (`po_upload`) claim names the row's own SO: spared by
                      both scopes.
      * `manual`    - `auto = false`: never touched by either scope.
    """
    from tests.scm.test_channel_read_model import _confirmed_leg
    from tests.scm.test_m3_run import _mk_product

    repair = _repair_module()
    bin_id = _project_bin(db, f"{MARKER}-IB-{uuid.uuid4().hex[:6].upper()}")
    pid = _mk_product(db, f"{MARKER}-{uuid.uuid4().hex[:6].upper()}")

    orphan = _confirmed_leg(db, product_id=pid, warehouse_id=bin_id, buy_qty=11)
    stale_self = _confirmed_leg(db, product_id=pid, warehouse_id=bin_id, buy_qty=22)
    book_kept = _confirmed_leg(db, product_id=pid, warehouse_id=bin_id, buy_qty=33)
    manual = _confirmed_leg(db, product_id=pid, warehouse_id=bin_id, buy_qty=44)

    orphan_line = _draft_line(db, product_id=pid, warehouse_id=bin_id, qty=11)
    stale_line = _draft_line(db, product_id=pid, warehouse_id=bin_id, qty=22)
    book_line = _draft_line(db, product_id=pid, warehouse_id=bin_id, qty=33)
    manual_line = _draft_line(db, product_id=pid, warehouse_id=bin_id, qty=44)

    old = datetime(2026, 6, 1, 9, 0, 0)  # long before G12 existed
    pre_cutoff_self = datetime(2026, 9, 1, 23, 0, 0)  # before repair.CUT_OFF, self-sourced

    _link(db, orphan, orphan_line, 11, auto=True, linked_at=old, claim=None)
    stale_claim_id = _link(
        db, stale_self, stale_line, 22, auto=True, linked_at=pre_cutoff_self,
        claim={"so_number": _so_ref(db, stale_self["pso"].id), "source": "order_inquiry",
               "claimed_at": pre_cutoff_self},
    )
    _link(
        db, book_kept, book_line, 33, auto=True, linked_at=old,
        claim={"so_number": _so_ref(db, book_kept["pso"].id), "source": "po_upload",
               "claimed_at": old},
    )
    _link(db, manual, manual_line, 44, auto=False, linked_at=old, claim=None)

    # `today` leaves all four: `orphan` and `manual` carry no order_inquiry claim naming
    # the cut-off window at all (`today`'s own NOT EXISTS is vacuously true only when a
    # claim in the offending shape exists - with none it is also vacuously true, so an
    # unclaimed link is technically `today`-eligible too; it is `stale_self` this pins,
    # since its claim is dated BEFORE the cut-off and must not read as the withdrawn
    # pass's own hours-old write).
    today_found = {str(f["row_id"]) for f in repair._find(db, "today")}
    assert str(stale_self["inquiry_row"].id) not in today_found, (
        "a claim from before the cut-off is not the withdrawn pass's own doing"
    )

    # Company-wide, not scoped to this test's own rows (`_find` is the real repair's own
    # query): the shared dev database is a prod copy and may carry its own real,
    # not-yet-repaired legacy placements (G15's own note - 1 row awaiting the book upload
    # as of 2 Sep). So this asserts OUR FOUR rows land where they should, not that legacy
    # finds nothing else.
    legacy_found = {str(f["row_id"]) for f in repair._find(db, "legacy")}
    assert {str(orphan["inquiry_row"].id), str(stale_self["inquiry_row"].id)} <= legacy_found
    assert str(book_kept["inquiry_row"].id) not in legacy_found, (
        "the book's own claim justifies this placement"
    )
    assert str(manual["inquiry_row"].id) not in legacy_found, (
        "a human link is never a candidate, in either scope"
    )

    repair._repair(db, "legacy", apply=True)

    def _linked(row) -> float:
        return float(
            db.execute(
                text(
                    "SELECT COALESCE(SUM(qty), 0) FROM projects.order_inquiry_links "
                    " WHERE row_id = :r"
                ),
                {"r": row["inquiry_row"].id},
            ).scalar()
            or 0
        )

    assert _linked(orphan) == 0.0
    assert _linked(stale_self) == 0.0
    assert _linked(book_kept) == 33.0, "spared"
    assert _linked(manual) == 44.0, "a manual link is never touched"

    remaining_claim = db.execute(
        text("SELECT count(*) FROM scm.order_link_claim WHERE id = :i"),
        {"i": stale_claim_id},
    ).scalar()
    assert remaining_claim == 0, "the self-written claim behind the undone link goes too"

    assert repair._find(db, "legacy") == [], "idempotent: nothing left for a second run"
