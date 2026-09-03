"""CRM SPO numbers run as `S-SPO-yyyy/mm-nnnn` from a seeded numbering rule.

CAPTAIN'S RULING (4 Sep, live on :3160): a created SPO showed `CRM-SPO-7bcb4582` - the dev
database (a prod copy) held numbering rules for `purchase_order`
(`PO-{year}/{month:02d}-####`) and `inbound_shipment_draft` (`PL-{yy}{month:02d}-###`), but
none for `purchase_order_crm_spo`, so `spo_conversion_service._spo_number`'s random-hex
fallback fired every time - same class of bug 440 fixed for the packing-list draft series.

  * `_spo_number` seeds the rule for the writing company ON THE SPOT when it is missing (same
    mechanism `proforma_invoice_service._draft_shipment_number` uses), so a company created
    after migration 470 ran still gets `S-SPO-yyyy/mm-0001` on its first Create SPO rather than
    the random-hex fallback.
  * Two Create SPO runs in the same month increment; a new month resets to `-0001`.
  * The `CRM-SPO-<hex8>` fallback stays reachable only when a rule EXISTS and is DISABLED - a
    decision made in Setup, not an absence this function papers over.

Postgres via `pg_session`, rolled back at teardown. The numbering rule is seeded HERE rather
than assumed, the same reasoning `test_packing_list_number_and_notes.py` documents: the shared
dev database may already hold a rule whose counter has issued numbers, and CI's database is
built with `create_all` and never runs a migration body. Cleared first so every assertion reads
`S-SPO-yyyy/mm-0001` regardless of what either database already holds.

**Own company, not Sorento (captain's fix, 4 Sep):** `tests/conftest.py` defaults every session's
company scope to the REAL Sorento company (`00000000-0000-0000-0000-000000000001`) so legacy
unscoped tests keep working. Left at that default, `_spo_number`'s rule lookup and the SPO's own
`purchase_orders` insert both land in Sorento too - the same company real traffic writes into on
the shared dev DB (a prod copy) - so a rolled-back test run can still collide with a REAL row on
`uq_purchase_orders_company_po_number` (`S-SPO-2026/09-0001` already existed there once). Every
test here creates its own throwaway `ZZT-` company and puts the session's scope on it, so the
number it writes lands in a company nothing else has ever written to.
"""
from __future__ import annotations

import importlib.util
import re
import uuid
from datetime import date as _date
from pathlib import Path

from sqlalchemy import text

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.procurement import PurchaseOrder
from app.services.numbering_defaults import CRM_SPO_DOC_TYPE
from app.services.scm import spo_conversion_service as svc
from tests._pg_fixture import pg_session
from tests.scm.conftest import requires_pg
from tests.scm.test_spo_conversion import World, _confirm_all

pytestmark = requires_pg

_NUMBER_RE = re.compile(r"^S-SPO-\d{4}/\d{2}-\d{4}$")


def _zzt_company(db) -> str:
    """A throwaway company this test alone writes into, scoped for the rest of the test.

    `Company` itself carries no `company_id` (it is not `CompanyScopedMixin`), so the insert
    needs no scope; every row created afterwards (the numbering rule, the SPO's `purchase_
    orders` header) does, so the scope is set to exactly this one company before returning.
    """
    company_id = str(uuid.uuid4())
    db.add(Company(id=company_id, name=f"ZZT-spo-numbering-{company_id[:8]}", code=f"ZZT{company_id[:8]}"))
    db.flush()
    set_company_scope(db, frozenset({company_id}))
    return company_id


def _migration_470():
    versions = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    spec = importlib.util.spec_from_file_location(
        "_m470_numbering", versions / "470_seed_crm_spo_numbering.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _clear_numbering(db, company_id: str) -> None:
    """No rule for the CRM SPO series in THIS company - the state that produced
    `CRM-SPO-7bcb4582`. Scoped to `company_id` alone so it never touches another
    company's real rule (Sorento's included) inside the same rolled-back transaction."""
    db.execute(
        text("delete from document_numbering_rules where doc_type = :d and company_id = :c"),
        {"d": CRM_SPO_DOC_TYPE, "c": company_id},
    )
    db.flush()


def _seed_numbering(db, company_id: str) -> None:
    """Migration 470's own seed, scoped to `company_id` alone, at a known starting value.

    Cleared first so the assertion is `S-SPO-yyyy/mm-0001` regardless of what this company
    already holds - the same "never assume" reasoning `test_packing_list_number_and_notes.py`
    documents, even though `company_id` names a company `_zzt_company` only just created.
    Passing `company_id` explicitly (never `None`) keeps the insert scoped to this one company
    row, so it can never seed - or collide with - the real Sorento rule.
    """
    module = _migration_470()
    _clear_numbering(db, company_id)
    module.seed_crm_spo_rule(db.connection(), company_id=company_id)
    db.flush()


def _expected_prefix(today: _date | None = None) -> str:
    today = today or _date.today()
    return f"S-SPO-{today.year}/{today.month:02d}-"


def _create_one(db, w: World) -> str:
    """One shipment, one line, one Create SPO run - the number it was written with."""
    supplier = w.supplier(f"S-{uuid.uuid4().hex[:6]}")
    shipment, lines = w.shipment([("A", 40, supplier)])
    out = svc.create(db, str(shipment.id), _confirm_all(lines), actor="tester")
    po_id = out["created_spos"][0]["purchase_order_id"]
    return db.query(PurchaseOrder.po_number).filter(PurchaseOrder.id == po_id).scalar()


def test_a_created_spo_is_numbered_from_the_monthly_rule():
    with pg_session() as db:
        company_id = _zzt_company(db)
        _seed_numbering(db, company_id)
        w = World(db)

        number = _create_one(db, w)

        assert number == f"{_expected_prefix()}0001"


def test_two_create_spo_runs_in_one_month_take_the_next_number_each():
    with pg_session() as db:
        company_id = _zzt_company(db)
        _seed_numbering(db, company_id)
        w = World(db)

        first = _create_one(db, w)
        second = _create_one(db, w)

        assert first == f"{_expected_prefix()}0001"
        assert second == f"{_expected_prefix()}0002"


def test_a_company_with_no_series_yet_gets_one_rather_than_the_random_hex_fallback():
    """Migration 470 ran once; a company created after it holds no rule of its own.

    The earlier code fell back to `CRM-SPO-<hex8>` here - the series is created on the spot
    instead, from the same definition the migration seeds, and the first SPO is
    `S-SPO-yyyy/mm-0001`.
    """
    with pg_session() as db:
        company_id = _zzt_company(db)
        _clear_numbering(db, company_id)
        w = World(db)

        first = _create_one(db, w)
        second = _create_one(db, w)

        assert _NUMBER_RE.match(first), first
        assert _NUMBER_RE.match(second), second
        assert first != second


def test_a_disabled_rule_falls_back_to_the_random_hex_rather_than_blocking_the_create():
    """A rule turned off in Setup keeps `create` working (unlike the packing-list draft
    series, which refuses outright) - `_spo_number`'s own last-resort fallback, kept for
    exactly this case."""
    with pg_session() as db:
        company_id = _zzt_company(db)
        _seed_numbering(db, company_id)
        db.execute(
            text(
                "update document_numbering_rules set enabled = false "
                "where doc_type = :d and company_id = :c"
            ),
            {"d": CRM_SPO_DOC_TYPE, "c": company_id},
        )
        db.flush()
        w = World(db)

        number = _create_one(db, w)

        assert number.startswith("CRM-SPO-"), number
        assert not _NUMBER_RE.match(number)
