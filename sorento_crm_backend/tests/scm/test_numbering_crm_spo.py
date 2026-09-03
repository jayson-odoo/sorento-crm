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
"""
from __future__ import annotations

import importlib.util
import re
import uuid
from datetime import date as _date
from pathlib import Path

from sqlalchemy import text

from app.models.procurement import PurchaseOrder
from app.services.numbering_defaults import CRM_SPO_DOC_TYPE
from app.services.scm import spo_conversion_service as svc
from tests._pg_fixture import pg_session
from tests.scm.conftest import requires_pg
from tests.scm.test_spo_conversion import World, _confirm_all

pytestmark = requires_pg

_NUMBER_RE = re.compile(r"^S-SPO-\d{4}/\d{2}-\d{4}$")


def _migration_470():
    versions = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    spec = importlib.util.spec_from_file_location(
        "_m470_numbering", versions / "470_seed_crm_spo_numbering.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _clear_numbering(db) -> None:
    """No rule for the CRM SPO series at all - the state that produced `CRM-SPO-7bcb4582`."""
    db.execute(
        text("delete from document_numbering_rules where doc_type = :d"),
        {"d": CRM_SPO_DOC_TYPE},
    )
    db.flush()


def _seed_numbering(db) -> None:
    """Migration 470's own seed, at a known starting value.

    Cleared first so the assertion is `S-SPO-yyyy/mm-0001` on any database, however many
    numbers the rule on it has already issued. Both statements are inside the rolled-back
    transaction.
    """
    module = _migration_470()
    _clear_numbering(db)
    module.seed_crm_spo_rule(db.connection())
    seeded = db.execute(
        text("select count(*) from document_numbering_rules where doc_type = :d"),
        {"d": module.DOC_TYPE},
    ).scalar()
    if not seeded:
        # A database with no `companies` rows at all (CI). The rule still has to exist for
        # the series to work, and a company-less rule applies to everybody.
        db.execute(
            text(
                """
                insert into document_numbering_rules
                    (id, company_id, doc_type, enabled, prefix_template, number_digits,
                     next_value, start_value, reset_policy, created_at, updated_at)
                values (gen_random_uuid(), null, :d, true, :p, :n, 1, 1, :r, now(), now())
                """
            ),
            {
                "d": module.DOC_TYPE,
                "p": module.PREFIX_TEMPLATE,
                "n": module.NUMBER_DIGITS,
                "r": module.RESET_POLICY,
            },
        )
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
        _seed_numbering(db)
        w = World(db)

        number = _create_one(db, w)

        assert number == f"{_expected_prefix()}0001"


def test_two_create_spo_runs_in_one_month_take_the_next_number_each():
    with pg_session() as db:
        _seed_numbering(db)
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
        _clear_numbering(db)
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
        _seed_numbering(db)
        db.execute(
            text("update document_numbering_rules set enabled = false where doc_type = :d"),
            {"d": CRM_SPO_DOC_TYPE},
        )
        db.flush()
        w = World(db)

        number = _create_one(db, w)

        assert number.startswith("CRM-SPO-"), number
        assert not _NUMBER_RE.match(number)
