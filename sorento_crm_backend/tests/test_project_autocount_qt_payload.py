"""AC-QTSO-CRM: the AutoCount quotation lines built from an accepted quotation revision.

Owner ruling Q6 (5 Nov ~07:25 MYT): "For read-only line should be skip. Then for product set,
then it should be like exploded to the component under the set." So:

- a rate-only line (`is_rate_only`) is NOT sent to AutoCount, and the result names it;
- a product set line is sent as its component lines, each at part qty x set qty, priced the way
  the SO draft already splits a set (`project_so_draft_service.py:1229`: the driver at the set's
  quoted rate, the other parts at zero, so the set's money is counted once), and the result
  names the set and its components;
- an ordinary line goes as it is.

Red first: `app.services.project_autocount_write_service` does not exist yet. The builder is
pure (lines in, payload out), so these tests need no database.

Contract the coder makes green:

    build_quotation_lines(lines, *, location) -> QuotationLinesPayload
        .lines:    list of dicts in AutoCount's create shape
                   {itemCode, description, uom, qty, unitPrice, location}
                   qty / unitPrice as Decimal; order = the quotation's order, a set's
                   components in their snapshot order at the set's place
        .skipped:  list of {code, description} for rate-only lines
        .exploded: list of {code, components: [{code, qty}]} for set lines
"""
from decimal import Decimal
from types import SimpleNamespace


def _builder():
    # Imported per test, not at module scope, so a missing module FAILS each test (red)
    # rather than erroring collection of the whole file.
    from app.services.project_autocount_write_service import build_quotation_lines

    return build_quotation_lines


def _line(**over):
    base = dict(
        product_id="p-1",
        product_set_id=None,
        set_parts_snapshot=None,
        product_code_snapshot="SRTWB242",
        description_snapshot="Wash basin 242",
        uom="UNIT",
        quantity=Decimal("10"),
        unit_price=Decimal("180.00"),
        line_total=Decimal("1800.00"),
        is_rate_only=False,
        sort_order=0,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _set_line(qty="4", price="950.00", sort_order=0):
    return _line(
        product_id=None,
        product_set_id="set-1",
        product_code_snapshot="SET-WC01",
        description_snapshot="Water closet set",
        uom="SET",
        quantity=Decimal(qty),
        unit_price=Decimal(price),
        line_total=Decimal(qty) * Decimal(price),
        sort_order=sort_order,
        set_parts_snapshot=[
            {"product_id": "p-wc", "product_code": "SRTWC100", "description": "Water closet",
             "quantity": "1", "is_driver": True, "uom": "UNIT"},
            {"product_id": "p-av", "product_code": "SRTAV020", "description": "Angle valve",
             "quantity": "2", "is_driver": False, "uom": "UNIT"},
            {"product_id": "p-fh", "product_code": "SRTFH030", "description": "Flexible hose",
             "quantity": "2", "is_driver": False, "uom": "UNIT"},
        ],
    )


def test_rate_only_line_is_skipped_and_named():
    build = _builder()
    rate_only = _line(
        product_code_snapshot="SRTWB250", description_snapshot="Alternate basin",
        is_rate_only=True, line_total=Decimal("0"), sort_order=1,
    )
    out = build([_line(sort_order=0), rate_only], location="BRW-BB")

    assert [l["itemCode"] for l in out.lines] == ["SRTWB242"]
    assert out.skipped == [{"code": "SRTWB250", "description": "Alternate basin"}]
    assert out.exploded == []


def test_ordinary_line_goes_as_it_is():
    build = _builder()
    out = build([_line()], location="BRW-BB")

    assert out.lines == [
        {
            "itemCode": "SRTWB242",
            "description": "Wash basin 242",
            "uom": "UNIT",
            "qty": Decimal("10"),
            "unitPrice": Decimal("180.00"),
            "location": "BRW-BB",
        }
    ]
    assert out.skipped == [] and out.exploded == []


def test_set_is_exploded_to_its_components_times_the_set_qty():
    build = _builder()
    out = build([_set_line(qty="4", price="950.00")], location="BRW-BB")

    assert [(l["itemCode"], l["qty"], l["unitPrice"], l["uom"]) for l in out.lines] == [
        ("SRTWC100", Decimal("4"), Decimal("950.00"), "UNIT"),   # driver: 1 x 4, the set's rate
        ("SRTAV020", Decimal("8"), Decimal("0"), "UNIT"),        # 2 x 4, zero
        ("SRTFH030", Decimal("8"), Decimal("0"), "UNIT"),        # 2 x 4, zero
    ]
    assert all(l["location"] == "BRW-BB" for l in out.lines)
    # The set's money is counted once: the exploded lines total the set line.
    assert sum(l["qty"] * l["unitPrice"] for l in out.lines) == Decimal("3800.00")
    # No set code reaches AutoCount.
    assert "SET-WC01" not in [l["itemCode"] for l in out.lines]
    assert out.exploded == [
        {
            "code": "SET-WC01",
            "components": [
                {"code": "SRTWC100", "qty": Decimal("4")},
                {"code": "SRTAV020", "qty": Decimal("8")},
                {"code": "SRTFH030", "qty": Decimal("8")},
            ],
        }
    ]


def test_mixed_quotation_keeps_order_skips_rate_only_and_explodes_sets():
    build = _builder()
    lines = [
        _line(product_code_snapshot="SRTWB242", sort_order=0),
        _line(product_code_snapshot="SRTWB250", description_snapshot="Alternate basin",
              is_rate_only=True, sort_order=1),
        _set_line(qty="2", sort_order=2),
        _line(product_code_snapshot="SRTBS110", description_snapshot="Bath spout",
              quantity=Decimal("40"), unit_price=Decimal("180.00"), sort_order=3),
    ]
    # Given out of order: the builder follows sort_order, as the printed quotation does.
    out = build(list(reversed(lines)), location="BRW-BB")

    assert [(l["itemCode"], l["qty"]) for l in out.lines] == [
        ("SRTWB242", Decimal("10")),
        ("SRTWC100", Decimal("2")),
        ("SRTAV020", Decimal("4")),
        ("SRTFH030", Decimal("4")),
        ("SRTBS110", Decimal("40")),
    ]
    assert [s["code"] for s in out.skipped] == ["SRTWB250"]
    assert [e["code"] for e in out.exploded] == ["SET-WC01"]


def test_a_quotation_of_only_rate_only_lines_has_nothing_to_send():
    build = _builder()
    out = build([_line(is_rate_only=True)], location="BRW-BB")

    assert out.lines == []
    assert len(out.skipped) == 1


# ---------------------------------------------------------------------------------------------
# Owner ruling R6a (5 Nov ~10:15 MYT, "for QTSO ok a"): the set's money always equals the accepted
# quotation. The driver's unit price is set rate / its qty per set, rounded to cents; when
# qty x that price misses set rate x set qty, the remainder cents go on the driver, sent as two
# lines of the same item: (n - 1) at the rounded price and 1 at the price that makes it exact.
# Only qty and unitPrice are used. Other parts stay at zero.
# ---------------------------------------------------------------------------------------------

import pytest  # noqa: E402


def _per_set_line(*, rate: str, set_qty: str, driver_qty: str, sort_order: int = 0):
    return _line(
        product_id=None,
        product_set_id="set-r6a",
        product_code_snapshot="SET-R6A",
        description_snapshot="R6a set",
        uom="SET",
        quantity=Decimal(set_qty),
        unit_price=Decimal(rate),
        line_total=Decimal(set_qty) * Decimal(rate),
        sort_order=sort_order,
        set_parts_snapshot=[
            {"product_id": "p-d", "product_code": "DRV100", "description": "Driver",
             "quantity": driver_qty, "is_driver": True, "uom": "UNIT"},
            {"product_id": "p-o", "product_code": "OTH200", "description": "Other",
             "quantity": "1", "is_driver": False, "uom": "UNIT"},
        ],
    )


def _money(lines):
    return sum((l["qty"] * l["unitPrice"] for l in lines), Decimal("0"))


def test_driver_two_per_set_is_one_line_at_half_the_set_rate():
    build = _builder()
    out = build([_per_set_line(rate="100.00", set_qty="2", driver_qty="2")], location="BRW-BB")

    driver = [l for l in out.lines if l["itemCode"] == "DRV100"]
    assert [(l["qty"], l["unitPrice"]) for l in driver] == [(Decimal("4"), Decimal("50.00"))]
    other = [l for l in out.lines if l["itemCode"] == "OTH200"]
    assert [(l["qty"], l["unitPrice"]) for l in other] == [(Decimal("2"), Decimal("0"))]
    assert _money(out.lines) == Decimal("200.00")


def test_driver_three_per_set_carries_the_remainder_cents_on_a_second_line():
    build = _builder()
    out = build([_per_set_line(rate="100.00", set_qty="2", driver_qty="3")], location="BRW-BB")

    driver = [l for l in out.lines if l["itemCode"] == "DRV100"]
    assert [(l["qty"], l["unitPrice"]) for l in driver] == [
        (Decimal("5"), Decimal("33.33")),
        (Decimal("1"), Decimal("33.35")),
    ]
    assert _money(out.lines) == Decimal("200.00")
    # The other part is still zero, at part qty x set qty.
    assert [(l["itemCode"], l["qty"], l["unitPrice"]) for l in out.lines if l["itemCode"] == "OTH200"] == [
        ("OTH200", Decimal("2"), Decimal("0"))
    ]


def test_the_exploded_note_lists_the_split_driver_once_with_its_total_qty():
    build = _builder()
    out = build([_per_set_line(rate="100.00", set_qty="2", driver_qty="3")], location="BRW-BB")

    assert out.exploded == [
        {
            "code": "SET-R6A",
            "components": [
                {"code": "DRV100", "qty": Decimal("6")},
                {"code": "OTH200", "qty": Decimal("2")},
            ],
        }
    ]


def test_the_two_driver_lines_sit_together_at_the_drivers_place():
    build = _builder()
    out = build([_per_set_line(rate="100.00", set_qty="2", driver_qty="3")], location="BRW-BB")

    assert [l["itemCode"] for l in out.lines] == ["DRV100", "DRV100", "OTH200"]
    assert all(l["location"] == "BRW-BB" and l["uom"] == "UNIT" for l in out.lines)


@pytest.mark.parametrize("rate", ["100.00", "950.00", "333.33"])
@pytest.mark.parametrize("set_qty", ["1", "2", "3"])
@pytest.mark.parametrize("driver_qty", ["1", "2", "3", "7"])
def test_the_sets_money_is_counted_exactly_once(rate, set_qty, driver_qty):
    build = _builder()
    out = build([_per_set_line(rate=rate, set_qty=set_qty, driver_qty=driver_qty)], location="BRW-BB")

    assert _money(out.lines) == Decimal(rate) * Decimal(set_qty)
    driver_units = sum(l["qty"] for l in out.lines if l["itemCode"] == "DRV100")
    assert driver_units == Decimal(driver_qty) * Decimal(set_qty)
    assert all(l["unitPrice"] >= 0 for l in out.lines)
