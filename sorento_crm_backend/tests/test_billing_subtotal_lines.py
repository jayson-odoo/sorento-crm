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
from app.services.finance.billing_subtotal_lines import mark_uncounted_lines
from tests._mc_lookup_seed import product
from tests._pg_fixture import blank_session
from tests._sales_unified_seed import doc, grand, line, run, so
from tests.test_ingest_billing_documents import _minimal, _outcomes, env  # noqa: F401  (fixture)

D = Decimal
JAN15 = date(2026, 1, 15)


def _item(net, n, **over):
    amount = None if net is None else D(net)
    values = {
        "source_ref": f"L{n}", "line_no": n, "item_code": f"ITEM{n}", "product_id": None,
        "uom": "PCS", "quantity": D("1"), "unit_price": amount, "net_amount": amount,
        "from_doc_type": None, "from_doc_no": None, "from_line_ref": None,
        "sales_order_line_id": None,
    }
    values.update(over)
    return values


def _blank(net, n, **over):
    blank = {"item_code": None, "uom": None, "quantity": None, "unit_price": None}
    return _item(net, n, **{**blank, **over})


def _verdicts(lines, net_total=None):
    """Subtotal verdicts in the order the lines were given. `net_total` None: no header."""
    mark_uncounted_lines(lines, None if net_total is None else D(net_total))
    return [line["is_subtotal"] for line in lines]


def _marks(lines, net_total):
    """'S' subtotal, 'D' duplicate copy, '-' counted, in the order given; and the counted sum."""
    mark_uncounted_lines(lines, D(net_total))
    marks = "".join(
        "S" if x["is_subtotal"] else "D" if x["is_duplicate"] else "-" for x in lines
    )
    counted = sum(
        (x["net_amount"] or D("0") for x in lines if not (x["is_subtotal"] or x["is_duplicate"])),
        D("0"),
    )
    return marks, counted


# ------------------------------------------------------------------------------ R1


def test_r1_a_blank_line_equal_to_the_lines_above_is_a_subtotal():
    lines = [_item("100000.00", 1), _item("44604.00", 2), _blank("144604.00", 3)]
    assert _verdicts(lines, "144604.00") == [False, False, True]


def test_r1_a_subtotal_per_section_and_a_cumulative_one_are_both_subtotals():
    lines = [
        _item("10.00", 1), _item("20.00", 2), _blank("30.00", 3),   # section 1
        _item("5.00", 4), _blank("5.00", 5),                        # section 2 (since previous)
        _item("1.00", 6), _blank("36.00", 7),                       # since the start
    ]
    assert _verdicts(lines, "36.00") == [False, False, True, False, True, False, True]


def test_r1_a_freight_charge_line_with_no_qty_is_counted_and_part_of_the_subtotal():
    freight = _blank("50.00", 2, description="Freight")
    lines = [_item("100.00", 1), freight, _blank("150.00", 3)]
    assert _verdicts(lines, "150.00") == [False, False, True]


def test_r1_a_charge_equal_to_the_lines_above_stays_a_sale_when_the_lines_match_the_header():
    # Review R1: item 50 + freight 50 on a 100.00 invoice balances; nothing is a subtotal.
    lines = [_item("50.00", 1), _blank("50.00", 2, description="Freight")]
    assert _verdicts(lines, "100.00") == [False, False]
    # The same lines on a 50.00 header: the line sum overstates it, the blank line is a subtotal.
    assert _verdicts(lines, "50.00") == [False, True]


def test_r1_a_blank_line_that_misses_the_sum_by_a_cent_is_a_sale():
    assert _verdicts([_item("100.00", 1), _blank("100.01", 2)]) == [False, False]


@pytest.mark.parametrize("field,value", [
    ("item_code", "X1"), ("uom", "PCS"), ("quantity", D("1")), ("unit_price", D("100.00")),
    ("product_id", "5b8b9c10-9999-4222-8333-4444555566aa"),
])
def test_r1_a_line_naming_anything_is_never_a_subtotal(field, value):
    lines = [_item("100.00", 1), _blank("100.00", 2, **{field: value})]
    assert _verdicts(lines) == [False, False]


def test_r1_a_blank_first_line_is_never_a_subtotal_and_order_is_line_no():
    lines = [_blank("0.00", 1), _blank("70.00", 3), _item("70.00", 2)]
    assert _verdicts(lines) == [False, True, False]


def test_r1_line_no_orders_before_source_ref_and_no_line_no_reads_last():
    # source_ref order (L10 < L2 < L3) runs against line_no order (2, 10, none).
    total = _blank("80.00", 10, source_ref="L2")
    lines = [_item("80.00", 2, source_ref="L10"), total, _item("5.00", None, source_ref="L3")]
    assert _verdicts(lines) == [False, True, False]
    # Read by source_ref the subtotal would come first and be a sale.
    late = _blank("5.00", None, source_ref="L0")
    assert _verdicts([_item("5.00", 1, source_ref="L9"), late]) == [False, True]


def test_r1_a_blank_line_with_no_amount_is_a_text_line_and_never_breaks_the_walk():
    lines = [_item("12.00", 1), _blank(None, 2, description="Note"), _blank("12.00", 3)]
    assert _verdicts(lines) == [False, False, True]


def test_r1_round2_a_subtotal_line_carrying_a_from_doc_ref_is_still_a_subtotal():
    # Crew round 2 (SRT Jan): the subtotal line names the DO it came from; nothing else changes.
    lines = [_item("64434.70", 1, from_doc_type="DO", from_doc_no="DO-1"),
             _blank("64434.70", 2, from_doc_type="DO", from_doc_no="DO-1",
                    from_line_ref="SRT_DB:DO:1:2",
                    sales_order_line_id="5b8b9c10-9999-4222-8333-4444555566ab")]
    assert _verdicts(lines, "64434.70") == [False, True]


def test_r1_a_blank_item_code_string_counts_as_no_item():
    assert _verdicts([_item("9.00", 1), _blank("9.00", 2, item_code="  ")]) == [False, True]


# ------------------------------------------------------------- R5 item-package copies
# Shapes from crew round 2 (dev copy, PR #2230 comment 6704659700): MCH (AED_V2_MOCHA) item
# packages, where the "SET PACKAGE" parent row (no item, no UOM) and its first child both carry the
# package's quantity, price and money; and SRT PSWR26-0001, a SubTotal line with a DO reference.


def _package_parent(qty, price, net, n, ref, discount="0.00"):
    return _item(net, n, source_ref=ref, item_code=None, uom=None, quantity=D(qty),
                 unit_price=D(price), discount_amount=D(discount),
                 description="IBORN TOP MOUNT NANO GRAIN KITCHEN SINK SET PACKAGE")


def _child(code, qty, price, net, n, ref, discount="0.00", **over):
    return _item(net, n, source_ref=ref, item_code=code, quantity=D(qty), unit_price=D(price),
                 discount_amount=D(discount), **over)


def test_r5_m2601_0858_the_package_parent_is_a_copy_of_its_first_child():
    lines = [_package_parent("17", "329", "5593.00", 16, "IV:20448970:20448971"),
             _child("IBKS8050-BL", "17", "329", "5593.00", 16, "IV:20448970:20448973"),
             _child("IBKT7823SS-BL", "17", "0", "0.00", 32, "IV:20448970:20448975"),
             _child("CARTON BOX", "17", "0", "0.00", 192, "IV:20448970:20448995")]
    assert _marks(lines, "5593.00") == ("D---", D("5593.00"))


def test_r5_m2601_1517_the_parent_need_not_share_the_childs_line_no():
    lines = [_child("IBKS7548-BL", "8", "405", "3240.00", 16, "IV:20488321:20488328"),
             _child("IBKT7823SS-BL", "8", "0", "0.00", 32, "IV:20488321:20488330"),
             _package_parent("8", "405", "3240.00", 48, "IV:20488321:20488326"),
             _child("IBKS470CB-YG", "8", "0", "0.00", 48, "IV:20488321:20488332")]
    assert _marks(lines, "3240.00") == ("--D-", D("3240.00"))


def test_r5_m2602_0736_the_discount_must_match_too():
    parent = _package_parent("10", "387.10", "3677.45", 16, "IV:20545958:20545959", discount="193.55")
    child = _child("IBKS8050-BL", "10", "387.10", "3677.45", 16, "IV:20545958:20545961", discount="193.55")
    assert _marks([parent, child], "3677.45") == ("D-", D("3677.45"))
    other = _child("IBKS8050-BL", "10", "387.10", "3677.45", 16, "IV:20545958:20545961", discount="0.00")
    assert _marks([_package_parent("10", "387.10", "3677.45", 16, "IV:x:1", discount="193.55"), other],
                  "3677.45")[0] == "--"


def test_r5_nothing_is_a_copy_when_the_lines_already_match_the_header():
    lines = [_package_parent("17", "329", "5593.00", 16, "a"), _child("X", "17", "329", "5593.00", 16, "b")]
    assert _marks(lines, "11186.00") == ("--", D("11186.00"))


def test_r5_a_copy_needs_the_same_quantity_price_and_money():
    for parent in (_package_parent("16", "329", "5593.00", 1, "a"),
                   _package_parent("17", "329.01", "5593.00", 1, "a"),
                   _package_parent("17", "329", "5593.01", 1, "a")):
        child = _child("X", "17", "329", "5593.00", 1, "b")
        assert "D" not in _marks([parent, child], "5593.00")[0]


def test_r5_a_copy_names_no_item_and_no_uom():
    child = _child("X", "17", "329", "5593.00", 1, "b")
    with_uom = _package_parent("17", "329", "5593.00", 1, "a")
    with_uom["uom"] = "SET"
    assert "D" not in _marks([with_uom, child], "5593.00")[0]
    named = _child("Y", "17", "329", "5593.00", 1, "a")
    assert "D" not in _marks([named, child], "5593.00")[0]


def test_r5_pswr26_0001_dated_charge_lines_are_sales_and_their_do_subtotal_is_not():
    # Blank-item "DO & INV" lines with qty 1 and a price are sales; no item line repeats them.
    lines = [_item("334.90", 32, item_code=None, uom=None, from_doc_type="DO", from_doc_no="PSWR2601-0003"),
             _item("132.20", 48, item_code=None, uom=None, from_doc_type="DO", from_doc_no="PSWR2601-0003"),
             _item("61757.60", 64, item_code=None, uom=None, from_doc_type="DO", from_doc_no="PSWR2601-0003"),
             _item("2210.00", 80, item_code=None, uom=None, from_doc_type="DO", from_doc_no="PSWR2601-0003"),
             _blank("64434.70", 96, description="SubTotal", from_doc_type="DO", from_doc_no="PSWR2601-0003"),
             _item("-6443.47", 112, item_code="RETENTION-006", from_doc_type="DO", from_doc_no="PSWR2601-0003")]
    assert _marks(lines, "57991.23") == ("----S-", D("57991.23"))


def test_r5_review2_a_charge_equal_to_an_item_is_not_a_copy_unless_dropping_it_balances():
    # Review round 2 probe: the subtotal makes the document off, so the header guard alone is off.
    lines = [_child("IT1", "1", "500", "500.00", 1, "a"), _package_parent("1", "500", "500.00", 2, "b"),
             _blank("1000.00", 3, source_ref="c", description="SubTotal")]
    assert _marks(lines, "1000.00") == ("--S", D("1000.00"))
    # Off by header-only money (footer charge 20.00): the charge stays a sale.
    lines = [_child("IT1", "1", "500", "500.00", 1, "a"), _package_parent("1", "500", "500.00", 2, "b")]
    assert _marks(lines, "1020.00") == ("--", D("1000.00"))


def test_r5_a_real_line_may_name_its_item_by_product_only():
    child = _child(None, "17", "329", "5593.00", 16, "b", product_id="5b8b9c10-9999-4222-8333-4444555566aa")
    assert _marks([_package_parent("17", "329", "5593.00", 16, "a"), child], "5593.00") == ("D-", D("5593.00"))


def test_r1_a_tab_is_not_blank_to_the_sql_btrim_either():
    # BTRIM trims spaces only; the Python rule must agree with the backfill.
    assert _verdicts([_item("9.00", 1), _blank("9.00", 2, item_code="\t")]) == [False, False]


def test_r5_one_real_line_excuses_one_copy():
    lines = [_child("X", "1", "50", "50.00", 1, "a"),
             _package_parent("1", "50", "50.00", 1, "b"), _child("Y", "1", "50", "50.00", 2, "c"),
             _package_parent("1", "50", "50.00", 2, "d"), _package_parent("1", "50", "50.00", 3, "e")]
    # Two real lines excuse two copies (b, d); the third (e) is left, so the doc stays off and
    # nothing is marked: a visible miss in reconcile Query 2, never a guess.
    assert _marks(lines, "100.00") == ("-----", D("250.00"))
    assert _marks(lines[:4], "100.00") == ("-D-D", D("100.00"))


def test_r5_known_limit_a_package_and_a_subtotal_on_one_document_are_left_unmarked():
    # Copies are taken only when dropping them balances the header; with a subtotal also on the
    # document it does not, so both stay counted and reconcile Query 2 lists the document.
    lines = [_child("X", "1", "10", "10.00", 1, "a"), _package_parent("1", "10", "10.00", 1, "b"),
             _child("Y", "2", "10", "20.00", 2, "c"), _blank("30.00", 3, source_ref="d")]
    assert _marks(lines, "30.00") == ("----", D("70.00"))


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


def test_r2_the_ingest_marks_a_duplicate_copy_and_keeps_it(env):  # noqa: F811
    ref = f"MCH_DB:IV:{uuid.uuid4().int % 10**9}"
    record = _minimal(ref, doc_no=f"ZZDUP-{ref[-6:]}")
    copy = dict(record["lines"][0], source_ref=f"{ref}:1b")
    copy.pop("product_code")
    record["lines"].append(copy)
    assert _outcomes(env.push([record])) == {ref: "created"}
    lines = env.lines(env.doc(ref).id)
    assert [(x.source_ref, x.is_duplicate, x.is_subtotal) for x in lines] == [
        (f"{ref}:1", False, False), (f"{ref}:1b", True, False)]


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


def test_r3_the_line_sum_of_a_document_with_a_duplicate_copy_is_its_header(db):
    p = product(db, company_id=DEFAULT_COMPANY_ID)
    header = doc(db, "invoice", "138356.80", JAN15, lines=[
        line(qty="1", net="138356.80", prod=p),
        line(qty="1", net="138356.80", description="copy"),
    ])
    copy = db.query(BillingDocumentLine).filter_by(document_id=header.id, line_no=2).one()
    copy.line_no = 1
    copy.is_duplicate = True
    db.flush()

    result = run(db, "top_selling_items", rows="item", cols="year", measures=("sales_value",))
    assert grand(result) == header.local_net_total == D("138356.80")


# ------------------------------------------------------------------------------ R4


def _migration():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "sbt_0001_billing_subtotal_lines.py"
    spec = importlib.util.spec_from_file_location("sbt_0001", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _random_lines(rng, so_line_id):
    """One document's lines: items, freight-style charges, text lines with no amount, blank-item
    lines that do or do not equal the lines above, blank strings, missing line numbers, and
    source refs whose order runs against the line numbers."""
    specs = []
    for n in range(1, rng.randint(2, 8) + 1):
        line_no = None if rng.random() < 0.1 else n
        ref = {"source_ref": f"R{rng.randint(0, 99)}-{n}"}
        roll = rng.random()
        if roll < 0.3 and specs:
            mark_uncounted_lines(specs, None)
            kept = [x for x in sorted(specs, key=lambda x: (x["line_no"] is None, x["line_no"] or 0,
                                                            x["source_ref"].encode()))
                    if not x["is_duplicate"]]
            running = sum((x["net_amount"] or D("0") for x in kept if not x["is_subtotal"]), D("0"))
            section = D("0")
            for x in kept:
                section = D("0") if x["is_subtotal"] else section + (x["net_amount"] or D("0"))
            net = rng.choice([running, section, running + D("0.01")])
            extra = rng.choice([{}, {"item_code": "  "}, {"uom": ""}, {"from_line_ref": "SRT_DB:SO:1:1"},
                                {"sales_order_line_id": so_line_id}, {}])
            values = _blank(str(net), line_no, **ref, **extra)
        elif roll < 0.4:
            values = _blank(str(D(rng.randint(1, 500))), line_no, description="Freight", **ref)
        elif roll < 0.45:
            values = _blank(None, line_no, description="Note", **ref)
        elif roll < 0.6 and any(x["item_code"] for x in specs):
            real = rng.choice([x for x in specs if x["item_code"]])
            # A package parent repeating a real line; sometimes off by a cent, a discount, or a UOM.
            net = real["net_amount"] + (D("0.01") if rng.random() < 0.15 else D("0"))
            extra = rng.choice([{}, {}, {"discount_amount": D("1.00")}, {"uom": "SET"}, {"uom": " "}])
            values = _item(str(net), rng.choice([real["line_no"], line_no]), **ref, item_code=None,
                           uom=None, quantity=real["quantity"], unit_price=real["unit_price"])
            values.update(extra)
            values["copy"] = True
        else:
            values = _item(str(D(rng.randint(1, 9999)) / 100), line_no, **ref)
        specs.append(values)
    return specs


def test_r4_the_migration_backfill_agrees_with_the_ingest_rule(db):
    rng = random.Random(7)
    _, (so_line,) = so(db)
    expected = {}
    for _ in range(60):
        specs = _random_lines(rng, so_line.id)
        lines_sum = sum((x["net_amount"] or D("0") for x in specs), D("0"))
        copied = sum((x["net_amount"] for x in specs if x.get("copy")), D("0"))
        # The header equals the line sum (the guard), the lines less the package copies (the
        # copies' exact check), or neither.
        net_total = rng.choice([lines_sum, lines_sum - copied, lines_sum - copied, lines_sum + D("1.00")])
        for x in specs:
            x.pop("copy", None)
        header = doc(db, "invoice", str(net_total), JAN15)
        if rng.random() < 0.3:
            # Explicit (v2.13): each item line names a random blank line as its package parent.
            parents = [x for x in specs if not x["item_code"]]
            for x in specs:
                if x["item_code"] and parents and rng.random() < 0.7:
                    x["parent_line_ref"] = rng.choice(parents)["source_ref"]
        mark_uncounted_lines(specs, net_total)
        for values in specs:
            row = BillingDocumentLine(
                id=str(uuid.uuid4()), document_id=header.id, company_id=DEFAULT_COMPANY_ID,
                **{k: v for k, v in values.items() if k not in ("is_subtotal", "is_duplicate")},
                is_subtotal=False, is_duplicate=False,
            )
            db.add(row)
            expected[row.id] = (values["is_subtotal"], values["is_duplicate"])
    db.flush()
    seen = set(expected.values())
    assert {(True, False), (False, True), (False, False)} <= seen and (True, True) not in seen

    # blank_session keeps `finance` in a scratch schema; the migration names the real one.
    finance = db.execute(text("SELECT current_schema()")).scalar() + "_finance"
    db.execute(text(_migration().BACKFILL.replace("finance.", f'"{finance}".')))
    got = {
        row[0]: (row[1], row[2])
        for row in db.execute(
            text(f'SELECT id::text, is_subtotal, is_duplicate FROM "{finance}".billing_document_lines '
                 "WHERE id::text = ANY(:ids)"),
            {"ids": list(expected)},
        ).all()
    }
    assert got == expected


# ------------------------------------------------------------------------------ R6


def _seed(db, net_total, specs):
    header = doc(db, "invoice", net_total, JAN15)
    for values in specs:
        db.add(BillingDocumentLine(
            id=str(uuid.uuid4()), document_id=header.id, company_id=DEFAULT_COMPANY_ID,
            **{k: v for k, v in values.items() if k not in ("is_subtotal", "is_duplicate")},
        ))
    db.flush()
    return header


def test_r6_the_reconciliation_lists_no_document_once_the_rules_apply(db):
    """The shipped read-only SQL over the crew round 2 shapes: Query 2 (documents still off)
    is empty, Query 1 counts the marks and the overstatement."""
    # Contract v2.13: the same package with its children naming the parent (review round 3).
    _seed(db, "5593.00", [
        _package_parent("17", "329", "5593.00", 16, _PARENT),
        _named_child("IBKS8050-BL", "17", "329", "5593.00", 16, "AED_V2_MOCHA:IV:20448970:20448973"),
        _named_child("IBKT7823SS-BL", "17", "0", "0.00", 32, "AED_V2_MOCHA:IV:20448970:20448975")])
    _seed(db, "3240.00", [
        _child("IBKS7548-BL", "8", "405", "3240.00", 16, "IV:20488321:20488328"),
        _package_parent("8", "405", "3240.00", 48, "IV:20488321:20488326"),
        _child("IBKS470CB-YG", "8", "0", "0.00", 48, "IV:20488321:20488332")])
    _seed(db, "57991.23", [
        _item("64434.70", 32, item_code=None, uom=None, from_doc_type="DO", from_doc_no="PSWR2601-0003"),
        _blank("64434.70", 96, description="SubTotal", from_doc_type="DO", from_doc_no="PSWR2601-0003"),
        _item("-6443.47", 112, item_code="RETENTION-006")])
    # Balanced: a charge equal to the line above stays a sale.
    _seed(db, "100.00", [_item("50.00", 1), _blank("50.00", 2, description="Freight")])

    finance = db.execute(text("SELECT current_schema()")).scalar() + "_finance"
    sql = (Path(__file__).resolve().parents[2] / "documentation" / "plans" / "sales"
           / "SQL-sales-subtotal-reconcile.sql").read_text().replace("finance.", f'"{finance}".')
    # The file carries the migration's verdict SQL verbatim (only the scope differs).
    for chunk in _migration().VERDICT_SQL.strip().split("{scope}"):
        assert chunk.strip().replace("finance.", f'"{finance}".') in sql
    query1, query2 = [part for part in sql.split(";") if "WITH RECURSIVE" in part]
    assert db.execute(text(query2)).all() == []
    rows = [r._mapping for r in db.execute(text(query1)).all()]
    mine = [r for r in rows if r["month"] == "2026-01"]
    assert sum(r["package_copies"] for r in mine) == 2 and sum(r["subtotal_lines"] for r in mine) == 1
    assert all(r["diff_after"] == 0 for r in mine)


# ----------------------------------------------------------- R7 explicit package parents
# Contract v2.13 (SS-PACKAGE-LINES, ss PR #226): a child line names its parent's source_ref.

_PARENT = "AED_V2_MOCHA:IV:20448970:20448971"


def _named_child(code, qty, price, net, n, ref, parent=_PARENT):
    return _child(code, qty, price, net, n, ref, parent_line_ref=parent)


def test_r7_m2601_0858_a_named_parent_whose_children_repeat_its_money_is_not_summed():
    lines = [_package_parent("17", "329", "5593.00", 16, _PARENT),
             _named_child("IBKS8050-BL", "17", "329", "5593.00", 16, "AED_V2_MOCHA:IV:20448970:20448973"),
             _named_child("IBKT7823SS-BL", "17", "0", "0.00", 32, "AED_V2_MOCHA:IV:20448970:20448975")]
    assert _marks(lines, "5593.00") == ("D--", D("5593.00"))


def test_r7_srt_a_named_parent_whose_children_carry_no_money_keeps_it():
    # RUNBOOK (AED_SORENTO): "package children carry no money". The parent is the sale.
    lines = [_package_parent("2", "500", "1000.00", 16, _PARENT),
             _named_child("A1", "2", "0", "0.00", 16, "c1"), _named_child("A2", "2", "0", "0.00", 32, "c2")]
    assert _marks(lines, "1000.00") == ("---", D("1000.00"))
    # Off by header-only money: the header guard is off, the children-sum check still keeps it.
    assert _marks(lines, "1020.00") == ("---", D("1000.00"))


def test_r7_a_document_with_named_parents_is_never_decided_by_the_inference():
    # The unnamed package-shaped line would be an inferred copy; on an explicit doc it is not.
    lines = [_package_parent("17", "329", "5593.00", 16, _PARENT),
             _named_child("IBKS8050-BL", "17", "329", "5593.00", 16, "c1"),
             _package_parent("1", "10", "10.00", 48, "x"), _child("Z", "1", "10", "10.00", 48, "y")]
    assert _marks(lines, "5603.00")[0] == "D---"


def test_r7_the_ingest_accepts_and_echoes_the_v2_13_keys(env):  # noqa: F811
    contract = env.client.get("/api/v1/external/contract").json()
    assert contract["version"] == "2.14"
    assert {"lines.parent_line_ref", "lines.line_type"} <= set(contract["fields_added"]["billing_documents"])

    ref = f"MCH_DB:IV:{uuid.uuid4().int % 10**9}"
    record = _minimal(ref, doc_no=f"ZZPKG-{ref[-6:]}")
    child = dict(record["lines"][0], source_ref=f"{ref}:2", line_number=1, parent_line_ref=f"{ref}:1")
    parent = dict(record["lines"][0], source_ref=f"{ref}:1", line_number=1)
    parent.pop("product_code")
    record["lines"] = [parent, child]
    assert _outcomes(env.push([record])) == {ref: "created"}
    lines = env.lines(env.doc(ref).id)
    assert [(x.source_ref, x.parent_line_ref, x.is_duplicate) for x in lines] == [
        (f"{ref}:1", None, True), (f"{ref}:2", f"{ref}:1", False)]
    read = env.read([ref]).json()
    echoed = {x["source_ref"]: x["parent_line_ref"] for x in read["records"][0]["lines"]}
    assert echoed == {f"{ref}:1": None, f"{ref}:2": f"{ref}:1"}


def test_r7_fixed_explicit_shapes_get_the_same_verdict_from_the_backfill(db):
    """Review round 3: R4's random parents rarely balance, so the backfill's explicit-parent mark
    is pinned here on fixed shapes, each with its expected verdict."""
    cases = {
        # M2601-0858 with refs: the parent is the copy.
        "mch": ("5593.00", [_package_parent("17", "329", "5593.00", 16, "P1"),
                            _named_child("C1", "17", "329", "5593.00", 16, "P1c1", parent="P1"),
                            _named_child("C2", "17", "0", "0.00", 32, "P1c2", parent="P1")], "D--"),
        # A 0.00 parent named by 0.00 children on an off document: nothing to drop, kept.
        "zero": ("10.00", [_item("0.00", 1, source_ref="Z", item_code=None, uom=None),
                           _named_child("C1", "1", "0", "0.00", 1, "Zc1", parent="Z"),
                           _item("5.00", 2, source_ref="other")], "---"),
        # A line naming itself is not a package: its money stays.
        "self": ("10.00", [_item("20.00", 1, source_ref="S", parent_line_ref="S")], "-"),
    }
    expected = {}
    for name, (net_total, specs, marks) in cases.items():
        assert _marks([dict(x) for x in specs], net_total)[0] == marks, name
        header = _seed(db, net_total, specs)
        by_ref = {x["source_ref"]: x for x in specs}
        mark_uncounted_lines(specs, D(net_total))
        for row in db.query(BillingDocumentLine).filter_by(document_id=header.id):
            expected[str(row.id)] = (by_ref[row.source_ref]["is_subtotal"], by_ref[row.source_ref]["is_duplicate"])

    finance = db.execute(text("SELECT current_schema()")).scalar() + "_finance"
    db.execute(text(_migration().BACKFILL.replace("finance.", f'"{finance}".')))
    got = {
        row[0]: (row[1], row[2])
        for row in db.execute(
            text(f'SELECT id::text, is_subtotal, is_duplicate FROM "{finance}".billing_document_lines '
                 "WHERE id::text = ANY(:ids)"),
            {"ids": list(expected)},
        ).all()
    }
    assert got == expected
    assert sum(v[1] for v in got.values()) == 1
