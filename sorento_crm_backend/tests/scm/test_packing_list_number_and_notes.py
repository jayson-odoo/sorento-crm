"""R16 / R17 - what a converted packing list is CALLED, and what it does not write.

TEST-FIRST: at the time this file is written the convert still falls back to a random
`SHIP-DRAFT-<hex8>` when no numbering rule exists, and still fills the container's Notes with
a sentence nobody typed. Every test here is expected to be red until those two land.

  * R16 / AC-F1 - the number comes from the `inbound_shipment_draft` rule, `PL-YYMM-NNN`,
    monthly. Two conversions in one month increment; `/new` without a number draws from the
    same series; a company that holds no rule yet (created after migration 440 ran) gets one
    on the spot rather than a 500, while a rule DISABLED in Setup is still refused with
    `numbering_rule_missing`. Nothing invents a number nobody can quote back.
  * R17 / AC-F2, AC-F3 - conversion writes nothing to `notes`; an over-capacity override
    records its reason as a Timeline entry (an `audit_logs` row on the container).

Postgres via `pg_session`, rolled back at teardown. The numbering rule is seeded HERE rather
than assumed: the shared dev database has one whose counter has already issued numbers, and
CI's database is built with `create_all` and never runs a migration body. Both are made
deterministic by clearing the doc_type inside the transaction and re-seeding it at 1.
"""
from __future__ import annotations

import importlib.util
import re
from datetime import date as _date
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.audit import AuditLog
from app.models.procurement import InboundShipment
from app.services.error_handler import AppException
from app.services.scm import proforma_invoice_service as svc
from tests._pg_fixture import pg_session
from tests.scm.test_proforma_invoice_import import World, _invoices
from tests.scm.test_proforma_invoice_adjust import _apply_preloading, _seed_container_sizes


def _migration_440():
    versions = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    spec = importlib.util.spec_from_file_location(
        "_m440_numbering", versions / "440_seed_inbound_shipment_draft_numbering.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _clear_numbering(db) -> None:
    """No rule for the draft series at all - the state that produced `SHIP-DRAFT-46949e1c`."""
    db.execute(
        text("delete from document_numbering_rules where doc_type = :d"),
        {"d": _migration_440().DOC_TYPE},
    )
    db.flush()


def _seed_numbering(db) -> None:
    """Migration 440's own seed, at a known starting value.

    Cleared first so the assertion is `PL-YYMM-001` on any database, however many numbers the
    rule on it has already issued. Both statements are inside the rolled-back transaction.
    """
    module = _migration_440()
    _clear_numbering(db)
    module.seed_inbound_shipment_draft_rule(db.connection())
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
    return f"PL-{today.year % 100:02d}{today.month:02d}-"


def _number(db, shipment_id: str) -> str:
    return (
        db.query(InboundShipment.shipment_number)
        .filter(InboundShipment.id == str(shipment_id))
        .scalar()
    )


# --------------------------------------------------------------------------------- #
# R16 / AC-F1 - the number
# --------------------------------------------------------------------------------- #


def test_a_converted_packing_list_is_numbered_from_the_monthly_rule():
    with pg_session() as db:
        _seed_container_sizes(db)
        _seed_numbering(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[4]

        out = svc.convert_to_draft_shipment(db, [str(invoice.id)])

        assert _number(db, out["shipment_id"]) == f"{_expected_prefix()}001"


def test_two_conversions_in_one_month_take_the_next_number_each():
    with pg_session() as db:
        _seed_container_sizes(db)
        _seed_numbering(db)
        w = World(db)
        invoices = _apply_preloading(db, w)
        # Block 5 fits a 40HQ; block 1 is 69.36 cbm and is loaded over it on purpose, so the
        # second number is taken on the override path too.
        first = svc.convert_to_draft_shipment(db, [str(invoices[4].id)])
        second = svc.convert_to_draft_shipment(
            db,
            [str(invoices[0].id)],
            override_capacity=True,
            override_reason="Second container booked",
        )

        assert _number(db, first["shipment_id"]) == f"{_expected_prefix()}001"
        assert _number(db, second["shipment_id"]) == f"{_expected_prefix()}002"


def test_a_container_created_without_a_number_draws_from_the_same_series():
    """AC-F3.3 - `/new` no longer asks for a shipment number, so create issues one."""
    from app.schemas.procurement import InboundShipmentCreate
    from app.services.procurement_service import InboundShipmentService

    with pg_session() as db:
        _seed_numbering(db)
        w = World(db)
        payload = InboundShipmentCreate(
            supplier_id=str(w.supplier.id),
            shipment_date=_date.today(),
            shipment_lines=[],
        )

        shipment = InboundShipmentService(db).create_shipment(payload, created_by=None)

        assert shipment.shipment_number == f"{_expected_prefix()}001"


def test_a_company_with_no_series_yet_gets_one_rather_than_a_500():
    """Migration 440 ran once; a company created after it holds no rule of its own.

    The convert used to be refused with `numbering_rule_missing` - a 500 on a screen where
    the operator had done nothing wrong. The series is created on the spot instead, from the
    same definition the migration seeds, and the first packing list is `PL-YYMM-001`.
    """
    with pg_session() as db:
        _seed_container_sizes(db)
        _clear_numbering(db)
        w = World(db)
        invoices = _apply_preloading(db, w)

        first = svc.convert_to_draft_shipment(db, [str(invoices[4].id)])
        second = svc.convert_to_draft_shipment(
            db,
            [str(invoices[0].id)],
            override_capacity=True,
            override_reason="Second container booked",
        )

        assert _number(db, first["shipment_id"]) == f"{_expected_prefix()}001"
        assert _number(db, second["shipment_id"]) == f"{_expected_prefix()}002"


def test_a_disabled_rule_is_still_refused_rather_than_worked_around():
    """A rule turned off in Setup is a decision, not an absence: creating a second one behind
    the admin's back would quietly undo it. The refusal is kept for exactly this case."""
    with pg_session() as db:
        _seed_container_sizes(db)
        _seed_numbering(db)
        db.execute(
            text("update document_numbering_rules set enabled = false where doc_type = :d"),
            {"d": _migration_440().DOC_TYPE},
        )
        db.flush()
        w = World(db)
        invoice = _apply_preloading(db, w)[4]

        with pytest.raises(AppException) as exc:
            svc.convert_to_draft_shipment(db, [str(invoice.id)])

        assert exc.value.status_code >= 500
        assert exc.value.detail["code"] == "numbering_rule_missing"


def test_no_random_suffix_survives_anywhere_in_the_numbering_path():
    source = (
        Path(svc.__file__).with_name("proforma_invoice_service.py").read_text(encoding="utf-8")
    )
    body = source[source.index("def _draft_shipment_number") :]
    body = body[: body.index("\ndef ", 1)]
    assert "uuid" not in body
    # The prefix may only survive as prose explaining why it is gone, never as code.
    code = [
        line
        for line in source.splitlines()
        if "SHIP-DRAFT" in line and not line.lstrip().startswith("#")
    ]
    assert code == []


# --------------------------------------------------------------------------------- #
# R17 / AC-F2, AC-F3 - the notes, and the timeline
# --------------------------------------------------------------------------------- #


def test_conversion_leaves_the_containers_notes_empty():
    with pg_session() as db:
        _seed_container_sizes(db)
        _seed_numbering(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[4]

        out = svc.convert_to_draft_shipment(db, [str(invoice.id)])

        shipment = (
            db.query(InboundShipment).filter(InboundShipment.id == out["shipment_id"]).one()
        )
        assert not (shipment.notes or "")


def test_an_over_capacity_override_writes_its_reason_to_the_timeline_not_the_notes():
    with pg_session() as db:
        _seed_container_sizes(db)
        _seed_numbering(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[0]

        out = svc.convert_to_draft_shipment(
            db,
            [str(invoice.id)],
            override_capacity=True,
            override_reason="Second container booked",
        )

        shipment = (
            db.query(InboundShipment).filter(InboundShipment.id == out["shipment_id"]).one()
        )
        assert not (shipment.notes or "")

        entries = [
            row.description
            for row in db.query(AuditLog)
            .filter(
                AuditLog.entity_type == "inbound_shipments",
                AuditLog.entity_id == str(out["shipment_id"]),
            )
            .all()
            if row.description
        ]
        assert any(
            e.startswith("Converted over capacity:")
            and "Reason: Second container booked" in e
            and "69.36" in e
            for e in entries
        ), entries


def test_a_conversion_that_fits_writes_no_over_capacity_entry():
    with pg_session() as db:
        _seed_container_sizes(db)
        _seed_numbering(db)
        w = World(db)
        invoice = _apply_preloading(db, w)[4]

        out = svc.convert_to_draft_shipment(db, [str(invoice.id)])

        descriptions = [
            row.description or ""
            for row in db.query(AuditLog)
            .filter(
                AuditLog.entity_type == "inbound_shipments",
                AuditLog.entity_id == str(out["shipment_id"]),
            )
            .all()
        ]
        assert not any("over capacity" in d.lower() for d in descriptions)


def test_the_draft_notes_helper_is_gone():
    """Nothing writes the container's story into a field the operator types in."""
    assert not hasattr(svc, "_draft_notes")
    source = (
        Path(svc.__file__).with_name("proforma_invoice_service.py").read_text(encoding="utf-8")
    )
    assert "Draft from proforma invoice(s)" not in source
