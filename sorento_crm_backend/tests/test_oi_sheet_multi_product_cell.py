"""One order inquiry sheet cell naming several products.

Contract: `documentation/plans/scm/scm-oi-sheet-multi-product-cell-acceptance-criteria.md`,
AC-M-1 to AC-M-12 (AC-M-13 is a prod-copy evidence run, not a pytest). Plan:
`documentation/plans/scm/PLAN-scm-oi-sheet-multi-product-cell.md`. One test per criterion,
named for it.

TEST-FIRST, written before `_members` / the `_plan` expansion exist. Today
(`project_order_inquiry_import_service._match_row`) an ITEM CODE cell is compared WHOLE
against a line's product code, so a cell joining several codes with `+` never matches any
single line and the whole cell lands in `line_not_found` as `no_line_for_item` - never split,
never raised. So every test below except AC-M-3 and AC-M-6 is RED for that one reason: a
count mismatch (`rows_raised` too low, `line_not_found` holding the whole cell instead of
one entry per stray member) - never an import error or a fixture bug. AC-M-3 and AC-M-6 pin
TODAY's behaviour (a cell that IS a product's own code, and a cell joined by `&` / `/` /
`C/W`) and are expected to PASS already, as regression guards for the slice that follows.

Postgres only (`tests/_pg_fixture.py`, `blank_session` through the parent file's `world()`).
Every product, line, order and purchase-order line is seeded here; nothing is read off an
existing row, because CI's database is empty. Product codes are always minted through
`World.product_row()` (unique per call) and referenced by variable - never hardcoded letters
- so two tests, or two blocks of one test, can never collide on a product code.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services import project_order_inquiry_import_service as importer
from app.services.import_outcome import ImportOutcome

from .test_project_order_inquiry_import_migration import (  # the seeded world, not copied
    D_NOV,
    D_OCT,
    MARKER,
    World,
    _names,
    _ref,
    _with_ref,
    book,
    sheet,
    world,
)


def _line_for(w: World, order, *, qty_ordered: str = "5"):
    """A fresh product with an open line on `order`, for one member of a `+` cell."""
    product = w.product_row()
    line = w.line(order, product=product, qty_ordered=qty_ordered, required_date=D_OCT)
    return product, line


# --------------------------------------------------------------------------- #
# splitting (plan section 1)                                                   #
# --------------------------------------------------------------------------- #


def test_ac_m_1_three_member_cell_raises_three_rows():
    """AC-M-1. RED: today the whole `A + B + C` cell fails to match ANY line's product code
    whole, so one `no_line_for_item` entry is reported and nothing is raised. After the fix,
    each member raises its own row on its own line, all at the cell's quantity."""
    with world() as w:
        order = w.order()
        product_a, line_a = _line_for(w, order, qty_ordered="5")
        product_b, line_b = _line_for(w, order, qty_ordered="5")
        product_c, line_c = _line_for(w, order, qty_ordered="5")
        cell = (
            f"{product_a.product_code} + {product_b.product_code} + "
            f"{product_c.product_code}"
        )
        data = sheet([
            (order.so_number, cell, 5, D_OCT, w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 3, result
        assert result["rows_line_not_found"] == 0, result
        rows = w.rows()
        assert len(rows) == 3
        mirrors = {
            str(w.mirror_of(line_a).id),
            str(w.mirror_of(line_b).id),
            str(w.mirror_of(line_c).id),
        }
        assert {str(row.so_line_id) for row in rows} == mirrors
        assert all(Decimal(str(row.qty)) == Decimal("5") for row in rows)
        assert all(row.delivery_date == D_OCT for row in rows)


@pytest.mark.parametrize("template", ["{a}+{b}", "{a} +{b}", "{a}+ {b}"])
def test_ac_m_2_spacing_variants_both_raise(template):
    """AC-M-2. RED for the same reason as AC-M-1: whitespace around `+` must not matter."""
    with world() as w:
        order = w.order()
        product_a, line_a = _line_for(w, order, qty_ordered="5")
        product_b, line_b = _line_for(w, order, qty_ordered="5")
        cell = template.format(a=product_a.product_code, b=product_b.product_code)
        data = sheet([
            (order.so_number, cell, 2, D_OCT, w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 2, result
        rows = w.rows()
        assert {str(row.so_line_id) for row in rows} == {
            str(w.mirror_of(line_a).id),
            str(w.mirror_of(line_b).id),
        }
        assert all(Decimal(str(row.qty)) == Decimal("2") for row in rows)


def test_ac_m_3_product_code_itself_contains_plus_stays_one_row():
    """AC-M-3. Expected to PASS already (regression guard): a cell that IS a line's own
    product code is never split, `+` and all - `FUR-GA30T+A66C` must not become two
    `no_line_for_item` misses for `FUR-GA30T` and `A66C`."""
    with world() as w:
        order = w.order()
        product = w.product_row(code="FUR-GA30T+A66C")
        w.line(order, product=product, qty_ordered="5", required_date=D_OCT)
        data = sheet([
            (order.so_number, product.product_code, 5, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 1, result
        assert result["line_not_found"] == [], result["line_not_found"]


def test_ac_m_4_unmatched_member_reports_alone():
    """AC-M-4. RED: today the report names the WHOLE `A + B + Z` cell, not `Z` alone."""
    with world() as w:
        order = w.order()
        product_a, line_a = _line_for(w, order, qty_ordered="5")
        product_b, line_b = _line_for(w, order, qty_ordered="5")
        cell = f"{product_a.product_code} + {product_b.product_code} + ZZT-M4-NOPE"
        data = sheet([
            (order.so_number, cell, 1, D_OCT, w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 2, result
        assert result["line_not_found"] == [
            {
                "so_number": order.so_number,
                "item_code": "ZZT-M4-NOPE",
                "qty": 1.0,
                "reason": "no_line_for_item",
            }
        ], result["line_not_found"]
        rows = w.rows()
        assert {str(row.so_line_id) for row in rows} == {
            str(w.mirror_of(line_a).id),
            str(w.mirror_of(line_b).id),
        }


@pytest.mark.parametrize("template", ["{a} + + {b}", "{a} + {b} +", "+ {a} + {b}"])
def test_ac_m_5_empty_members_are_dropped(template):
    """AC-M-5. RED: today the whole cell (leading/trailing/doubled `+` and all) misses as
    one `no_line_for_item` entry; after the fix the empty member is dropped silently and
    only A and B raise - no `""` item_code anywhere in the result."""
    with world() as w:
        order = w.order()
        product_a, line_a = _line_for(w, order, qty_ordered="5")
        product_b, line_b = _line_for(w, order, qty_ordered="5")
        cell = template.format(a=product_a.product_code, b=product_b.product_code)
        data = sheet([
            (order.so_number, cell, 1, D_OCT, w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 2, result
        rows = w.rows()
        assert {str(row.so_line_id) for row in rows} == {
            str(w.mirror_of(line_a).id),
            str(w.mirror_of(line_b).id),
        }
        assert all(row.item_code != "" for row in rows), [row.item_code for row in rows]
        assert all(
            entry["item_code"] != "" for entry in result["line_not_found"]
        ), result["line_not_found"]


@pytest.mark.parametrize("template", ["{a} & {b}", "{a} / {b}", "{a} C/W {b}"])
def test_ac_m_6_other_separators_never_split(template):
    """AC-M-6. Expected to PASS already (regression guard): only `+` splits a cell. `&`,
    `/` and `C/W` stay whole, landing as ONE `no_line_for_item` entry naming the whole
    cell - exactly today's behaviour, unchanged by this slice."""
    with world() as w:
        order = w.order()
        product_a, line_a = _line_for(w, order, qty_ordered="5")
        product_b, line_b = _line_for(w, order, qty_ordered="5")
        cell = template.format(a=product_a.product_code, b=product_b.product_code)
        data = sheet([
            (order.so_number, cell, 1, D_OCT, w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 0, result
        assert w.rows() == []
        assert result["line_not_found"] == [
            {
                "so_number": order.so_number,
                "item_code": cell,
                "qty": 1.0,
                "reason": "no_line_for_item",
            }
        ], result["line_not_found"]


# --------------------------------------------------------------------------- #
# downstream stays right (plan section 2)                                      #
# --------------------------------------------------------------------------- #


def test_ac_m_7_restatement_across_tabs_raises_each_member_once():
    """AC-M-7. RED: today neither tab's cell matches any line, so both land in
    `line_not_found` and nothing is raised at all - never mind the restatement dedup this
    checks once the members exist to be deduped."""
    with world() as w:
        order = w.order()
        product_a, line_a = _line_for(w, order, qty_ordered="5")
        product_b, line_b = _line_for(w, order, qty_ordered="5")
        cell = f"{product_a.product_code} + {product_b.product_code}"
        stated = (order.so_number, cell, 3, D_OCT, w.warehouse.warehouse_code, "")

        result = w.apply(book(JAN26=[stated], ROLLUP=[stated]))

        assert result["rows_raised"] == 2, result
        rows = w.rows()
        assert len(rows) == 2
        assert {str(row.so_line_id) for row in rows} == {
            str(w.mirror_of(line_a).id),
            str(w.mirror_of(line_b).id),
        }


def test_ac_m_8_second_row_member_reports_qty_exceeds_ordered():
    """AC-M-8. RED: today the FIRST row alone (whole cell `A + B`) misses as
    `no_line_for_item` and the ledger never charges line A, so the second row (plain `A`)
    matches cleanly instead of exceeding it - the wrong reason, on the wrong row."""
    with world() as w:
        order = w.order()
        product_a, line_a = _line_for(w, order, qty_ordered="5")
        product_b, line_b = _line_for(w, order, qty_ordered="5")
        cell = f"{product_a.product_code} + {product_b.product_code}"
        data = sheet([
            (order.so_number, cell, 5, D_OCT, w.warehouse.warehouse_code, ""),
            (order.so_number, product_a.product_code, 1, D_OCT,
             w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 2, result
        assert [entry["reason"] for entry in result["line_not_found"]] == [
            "qty_exceeds_ordered"
        ], result["line_not_found"]
        assert result["line_not_found"][0]["item_code"] == product_a.product_code
        assert result["line_not_found"][0]["qty"] == 1.0
        rows = w.rows()
        assert {str(row.so_line_id) for row in rows} == {
            str(w.mirror_of(line_a).id),
            str(w.mirror_of(line_b).id),
        }


def test_ac_m_9_preview_matches_apply():
    """AC-M-9. RED for the same undercount as AC-M-1: `preview` and `apply` must agree, and
    today both agree on the WRONG numbers (0 raised, 1 line-not-found for the whole cell)."""
    with world() as w:
        order = w.order()
        product_a, line_a = _line_for(w, order, qty_ordered="5")
        product_b, line_b = _line_for(w, order, qty_ordered="5")
        product_c, line_c = _line_for(w, order, qty_ordered="5")
        cell = (
            f"{product_a.product_code} + {product_b.product_code} + "
            f"{product_c.product_code}"
        )
        data = sheet([
            (order.so_number, cell, 5, D_OCT, w.warehouse.warehouse_code, ""),
        ])

        previewed = w.preview(data)
        applied = w.apply(data)

        for key in ("rows", "rows_raised", "rows_line_not_found"):
            assert previewed[key] == applied[key], (key, previewed[key], applied[key])
        assert applied["rows_raised"] == 3, applied


def test_ac_m_10_on_total_rows_and_result_rows_report_expanded_count():
    """AC-M-10. RED: `on_total_rows` today fires with `len(parsed.rows)` (2, the SOURCE row
    count) and `result["rows"]` is `len(plan.parsed.rows)` too - neither reports the 4
    member rows `ImportOutcome` actually records one outcome for."""
    with world() as w:
        order = w.order()
        product_a, line_a = _line_for(w, order, qty_ordered="5")
        product_b, line_b = _line_for(w, order, qty_ordered="5")
        product_c, line_c = _line_for(w, order, qty_ordered="5")
        cell = (
            f"{product_a.product_code} + {product_b.product_code} + "
            f"{product_c.product_code}"
        )
        row1 = (order.so_number, cell, 1, D_OCT, w.warehouse.warehouse_code, "")
        row2 = (order.so_number, product_a.product_code, 1, D_NOV,
                w.warehouse.warehouse_code, "")
        data = book(JAN26=[row1], FEB26=[row2])
        captured: list[int] = []
        outcome = ImportOutcome(None, persist=False)

        result = importer.apply(
            w.db, data, actor=w.actor, outcome=outcome, on_total_rows=captured.append,
        )

        assert captured == [4], captured
        assert result["rows"] == 4, result


def test_ac_m_11_member_row_links_like_a_plain_row():
    """AC-M-11. RED: today the `A + B` cell never matches line A at all, so there is no row
    for a link to hang off of - `w.links(row_a)` cannot even be asked, let alone answer
    with the PO line."""
    with world() as w:
        order = w.order()
        ref = _ref()
        product_a = w.product_row()
        line_a = _with_ref(
            w, w.line(order, product=product_a, qty_ordered="5", required_date=D_OCT), ref,
        )
        product_b, line_b = _line_for(w, order, qty_ordered="5")
        po, po_line = w.po_line(qty_ordered="5", product=product_a)
        _names(w, po_line, ref)
        cell = f"{product_a.product_code} + {product_b.product_code}"
        data = sheet([
            (order.so_number, cell, 5, D_OCT, w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["rows_raised"] == 2, result
        rows = w.rows()
        row_a = next(
            row for row in rows if str(row.so_line_id) == str(w.mirror_of(line_a).id)
        )
        links = w.links(row_a)
        assert len(links) == 1, links
        assert str(links[0].po_line_id) == str(po_line.id)
        assert Decimal(str(links[0].qty)) == Decimal("5")


def test_ac_m_12_unknown_order_names_once_and_raises_nothing():
    """AC-M-12. Likely PASSES already: an order the CRM does not hold is refused before any
    line matching happens, whether or not its item cell would split - listed for AC-M-12's
    own coverage regardless."""
    with world() as w:
        cell = "ZZT-M12-A + ZZT-M12-B"
        data = sheet([
            (f"{MARKER}-SO-M12-ABSENT", cell, 1, D_OCT, w.warehouse.warehouse_code, ""),
        ])

        result = w.apply(data)

        assert result["sales_orders_not_found"] == [f"{MARKER}-SO-M12-ABSENT"]
        assert result["rows_raised"] == 0, result
        assert w.rows() == []
