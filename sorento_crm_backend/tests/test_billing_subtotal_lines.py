"""SALES-SUBTOTAL-LINES: an AutoCount subtotal line is kept on the document and never summed
as a sale (plan documentation/plans/sales/PLAN-sales-subtotal-lines-07nov.md).

  R1  the rule: blank item shape + net equals EXACTLY the counted lines above, since the start
      of the document or since the previous subtotal; a freight charge line is counted
  R2  the ingest marks the line on create and re-decides on a re-push; the line stays stored
  R3  the line-based sales sum (top selling items, the report ask's invoiced basis) equals the
      header `local_net_total` for a document carrying a subtotal line
  R4  the migration's backfill walk gives the same verdict as the ingest's rule

Kill test (R3): drop `inv.counted_line()` from `billing_document_lines._base` and
`test_r3_*` goes red (the line sum doubles).
"""
from __future__ import annotations

import importlib.util
import random
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from app.main import app  # noqa: F401  (import order: resolves the guards cycle)
from app.models.finance import BillingDocumentLine
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.finance.billing_subtotal_lines import mark_subtotal_lines
from tests._mc_lookup_seed import product
from tests._pg_fixture import blank_session
from tests._sales_unified_seed import doc, grand, line, run
from tests.test_ingest_billing_documents import _minimal, _outcomes, env  # noqa: F401  (fixture)

D = Decimal
JAN15 = date(2026, 1, 15)


def _item(net, n, **over):
    values = {
        "source_ref": f"L{n}", "line_no": n, "item_code": f"ITEM{n}", "product_id": None,
        "uom": "PCS", "quantity": D("1"), "unit_price": D(net), "net_amount": D(net),
        "from_doc_type": None, "from_doc_no": None, "from_line_ref": None,
        "sales_order_line_id": None,
    }
    values.update(over)
    return values


def _blank(net, n, **over):
    blank = {"item_code": None, "uom": None, "quantity": None, "unit_price": None}
    return _item(net, n, **{**blank, **over})


def _verdicts(lines):
    mark_subtotal_lines(lines)
    return [line["is_subtotal"] for line in sorted(lines, key=lambda x: x["line_no"])]


# ------------------------------------------------------------------------------ R1


def test_r1_a_blank_line_equal_to_the_lines_above_is_a_subtotal():
    lines = [_item("100000.00", 1), _item("44604.00", 2), _blank("144604.00", 3)]
    assert _verdicts(lines) == [False, False, True]


def test_r1_a_subtotal_per_section_and_a_cumulative_one_are_both_subtotals():
    lines = [
        _item("10.00", 1), _item("20.00", 2), _blank("30.00", 3),   # section 1
        _item("5.00", 4), _blank("5.00", 5),                        # section 2 (since previous)
        _item("1.00", 6), _blank("36.00", 7),                       # since the start
    ]
    assert _verdicts(lines) == [False, False, True, False, True, False, True]


def test_r1_a_freight_charge_line_with_no_qty_is_counted_and_part_of_the_subtotal():
    freight = _blank("50.00", 2, description="Freight")
    lines = [_item("100.00", 1), freight, _blank("150.00", 3)]
    assert _verdicts(lines) == [False, False, True]


def test_r1_a_blank_line_that_misses_the_sum_by_a_cent_is_a_sale():
    assert _verdicts([_item("100.00", 1), _blank("100.01", 2)]) == [False, False]


@pytest.mark.parametrize("field,value", [
    ("item_code", "X1"), ("uom", "PCS"), ("quantity", D("1")), ("unit_price", D("100.00")),
    ("from_doc_no", "DO-1"), ("from_doc_type", "DO"), ("product_id", str(uuid.uuid4())),
])
def test_r1_a_line_naming_anything_is_never_a_subtotal(field, value):
    lines = [_item("100.00", 1), _blank("100.00", 2, **{field: value})]
    assert _verdicts(lines) == [False, False]


def test_r1_a_blank_first_line_is_never_a_subtotal_and_order_is_line_no():
    lines = [_blank("0.00", 1), _blank("70.00", 3), _item("70.00", 2)]
    assert _verdicts(lines) == [False, False, True]


def test_r1_a_blank_item_code_string_counts_as_no_item():
    assert _verdicts([_item("9.00", 1), _blank("9.00", 2, item_code="  ")]) == [False, True]


# ------------------------------------------------------------------------------ R2


def _subtotal_record(ref):
    record = _minimal(ref, doc_no=f"ZZSUB-{ref[-6:]}")
    record.update(net_total=10, total=10, local_net_total=10)
    record["lines"].append({
        "source_ref": f"{ref}:2", "line_number": 2, "description": "SUB TOTAL",
        "net_amount": 10, "tax_amount": 0, "line_total": 10,
    })
    return record


def test_r2_the_ingest_marks_the_subtotal_line_and_keeps_it(env):  # noqa: F811
    ref = f"SRT_DB:IV:{uuid.uuid4().int % 10**9}"
    assert _outcomes(env.push([_subtotal_record(ref)])) == {ref: "created"}
    lines = env.lines(env.doc(ref).id)
    assert [(x.source_ref, x.is_subtotal) for x in lines] == [(f"{ref}:1", False), (f"{ref}:2", True)]

    # Re-pushed with the blank line no longer equal to the lines above: re-decided, a sale.
    changed = _subtotal_record(ref)
    changed["lines"][1]["net_amount"] = 4
    changed["lines"][1]["line_total"] = 4
    changed.update(net_total=14, total=14, local_net_total=14)
    assert _outcomes(env.push([changed])) == {ref: "updated"}
    assert [x.is_subtotal for x in env.lines(env.doc(ref).id)] == [False, False]

    # An identical replay of the subtotal shape writes nothing.
    assert _outcomes(env.push([_subtotal_record(ref)])) == {ref: "updated"}
    assert _outcomes(env.push([_subtotal_record(ref)])) == {ref: "unchanged"}


# ------------------------------------------------------------------------------ R3


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def test_r3_the_line_sum_of_a_document_with_a_subtotal_line_is_its_header(db):
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    q = product(db, company_id=DEFAULT_COMPANY_ID)
    header = doc(db, "invoice", "144604.00", JAN15, lines=[
        line(qty="1", net="100000.00", prod=p),
        line(qty="1", net="44604.00", prod=q),
        line(qty="1", net="144604.00", description="SUB TOTAL"),
    ])
    subtotal = db.query(BillingDocumentLine).filter_by(document_id=header.id, line_no=3).one()
    subtotal.quantity = None
    subtotal.is_subtotal = True
    db.flush()

    result = run(db, "top_selling_items", rows="item", cols="year", measures=("sales_value",))
    assert grand(result) == header.local_net_total == D("144604.00")


# ------------------------------------------------------------------------------ R4


def _migration():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "sbt_0001_billing_subtotal_lines.py"
    spec = importlib.util.spec_from_file_location("sbt_0001", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_r4_the_migration_backfill_agrees_with_the_ingest_rule(db):
    rng = random.Random(7)
    expected = {}
    for _ in range(30):
        header = doc(db, "invoice", "1.00", JAN15)
        specs, running, section = [], D("0"), D("0")
        for n in range(1, rng.randint(2, 7) + 1):
            roll = rng.random()
            if roll < 0.25 and specs:
                net = rng.choice([running, section, running + D("0.01")])
                values = _blank(str(net), n)
            elif roll < 0.35:
                values = _blank(str(D(rng.randint(1, 500))), n, description="Freight")
            else:
                values = _item(str(D(rng.randint(1, 9999)) / 100), n)
            specs.append(values)
            mark_subtotal_lines(specs)
            running = sum((x["net_amount"] for x in specs if not x["is_subtotal"]), D("0"))
            section = D("0")
            for x in specs:
                section = D("0") if x["is_subtotal"] else section + x["net_amount"]
        mark_subtotal_lines(specs)
        for values in specs:
            row = BillingDocumentLine(
                id=str(uuid.uuid4()), document_id=header.id, company_id=DEFAULT_COMPANY_ID,
                **{k: v for k, v in values.items() if k != "is_subtotal"},
                is_subtotal=False,
            )
            db.add(row)
            expected[row.id] = values["is_subtotal"]
    db.flush()
    assert any(expected.values()) and not all(expected.values())

    # blank_session keeps `finance` in a scratch schema; the migration names the real one.
    finance = db.execute(text("SELECT current_schema()")).scalar() + "_finance"
    db.execute(text(_migration().BACKFILL.replace("finance.", f'"{finance}".')))
    got = dict(db.execute(
        text(f'SELECT id::text, is_subtotal FROM "{finance}".billing_document_lines WHERE id::text = ANY(:ids)'),
        {"ids": list(expected)},
    ).all())
    assert got == expected
