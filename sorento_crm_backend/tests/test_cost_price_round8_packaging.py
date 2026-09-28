"""Fix lane round 8 (#1288, PR #1305): cost per packaging method.

Owner ruling of 28 Sep 2026 (15:2x MYT), from the supplier's own 2500 series sheet: "for our
cost list upload right, for this, actually it is cost per packaging method, so we need the
packaging method ... there needs to be diffetent cost for differnet packging method correct".
Answers (15:3x MYT): "1 packagin value is free text yeah, a code with no bracket yeah correct,
yeah correct PO keep their own unit cost yeah".

AC-S1-04, AC-S1-10 (as amended), AC-PK-01, AC-PK-02, AC-CL-04 (as amended).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from tests.fixtures.cost_price.taiyang_shapes import LETTERHEAD_TEXT, simple_price_list_workbook
from tests.support.cost_price_env import (  # noqa: F401
    PS_EDIT_PERM,
    PS_VIEW_PERM,
    UPLOAD_PERM,
    VIEW_PERM,
    cost_price_env,
)

#: The supplier's own 2500 series rows, as the owner quoted them (fullwidth brackets).
SERIES_2500 = [
    ("CB2500SS-BL（彩盒）", "cfg", 9.50),
    ("CB2500SS-BL-DIY（OPP）", "cfg", 9.90),
    ("CB2500SS-BL-DIY（吊卡）", "cfg", 9.40),
]


def _upload(e, rows, *, products: dict[str, float | None]):
    """Seed a supplier, a product per code in `products` (linked at that cost when not None)
    and upload `rows`. Returns (supplier, {code: product}, set_id)."""
    user = e.user(UPLOAD_PERM, VIEW_PERM, PS_VIEW_PERM, PS_EDIT_PERM)
    e.as_user(user)
    e.seed_settings(cost_price_verification_enabled=False)
    supplier = e.supplier(name=LETTERHEAD_TEXT)
    made = {}
    for code, cost in products.items():
        made[code] = e.product(code=code)
        if cost is not None:
            e.link(made[code], supplier, unit_cost=cost, currency="CNY")
    data = simple_price_list_workbook(rows, letterhead=LETTERHEAD_TEXT)
    upload = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    assert upload.status_code == 201, upload.text
    return supplier, made, upload.json()["id"]


# ----------------------------------------------------------------------------- pure rules


def test_packaging_key_folds_nfkc_trim_and_case():
    from app.services.procurement.supplier_cost_service import packaging_key, packaging_label

    assert packaging_key("OPP") == packaging_key(" opp ") == packaging_key("ＯＰＰ") == "opp"
    assert packaging_key("彩盒") == "彩盒"
    assert packaging_key(None) == packaging_key("") == packaging_key("  ") == "standard"
    # Shown as written, only trimmed.
    assert packaging_label("  OPP ") == "OPP"
    assert packaging_label(None) == "standard"


def test_reader_keeps_the_bracket_as_packaging_and_a_plain_code_is_standard():
    from app.services.procurement.supplier_price_list_reader import read_supplier_price_list

    data = simple_price_list_workbook(SERIES_2500 + [("CB2500SS-BL", "cfg", 9.00)])
    rows = read_supplier_price_list(data, "x.xlsx").sheets[0].rows
    assert [(r.supplier_code, r.packaging_method, r.price) for r in rows] == [
        ("CB2500SS-BL", "彩盒", Decimal("9.50")),
        ("CB2500SS-BL-DIY", "OPP", Decimal("9.90")),
        ("CB2500SS-BL-DIY", "吊卡", Decimal("9.40")),
        ("CB2500SS-BL", "standard", Decimal("9.00")),
    ]


def _row(cost, key, *, start=None, created=0):
    return SimpleNamespace(
        unit_cost=Decimal(str(cost)), currency="CNY", start_date=start, end_date=None,
        packaging_key=key, packaging_method=key, created_at=datetime(2026, 9, 1) + timedelta(minutes=created),
    )


def test_current_cost_reader_is_keyed_by_packaging():
    """AC-PK-02: the reader takes the packaging as part of its key; three packagings, three costs."""
    from app.services.procurement.supplier_cost_service import current_cost

    today = date(2026, 9, 28)
    rows = [_row(9.50, "彩盒"), _row(9.90, "opp", created=1), _row(9.40, "吊卡", created=2)]
    assert current_cost(rows, today, "彩盒").unit_cost == Decimal("9.50")
    assert current_cost(rows, today, "OPP").unit_cost == Decimal("9.90")  # folded
    assert current_cost(rows, today, "吊卡").unit_cost == Decimal("9.40")
    assert current_cost(rows, today, "standard") is None
    # No packaging: several packagings and no standard line, so no answer (the caller keeps its price).
    assert current_cost(rows, today) is None


def test_current_cost_without_packaging_gets_the_standard_line():
    from app.services.procurement.supplier_cost_service import current_cost

    today = date(2026, 9, 28)
    rows = [_row(9.50, "彩盒"), _row(9.00, "standard", created=1)]
    assert current_cost(rows, today).unit_cost == Decimal("9.00")
    # One packaging only (no standard row): that packaging.
    assert current_cost([_row(9.50, "彩盒")], today).unit_cost == Decimal("9.50")
    assert current_cost([], today) is None


def test_status_is_decided_among_rows_of_the_same_packaging():
    from app.services.procurement.supplier_cost_service import cost_status

    today = date(2026, 9, 28)
    a, b = _row(9.50, "彩盒"), _row(9.90, "opp", created=1)
    # Two "always" rows of different packagings are both live, neither overrides the other.
    assert cost_status(a, [a, b], today) == "always"
    assert cost_status(b, [a, b], today) == "always"
    c = _row(9.60, "彩盒", created=5)
    assert cost_status(a, [a, b, c], today) == "overridden"
    assert cost_status(c, [a, b, c], today) == "always"


# ------------------------------------------------------------------------ the 2500 series


def test_2500_series_is_three_lines_with_three_costs(cost_price_env):
    e = cost_price_env
    _, _, set_id = _upload(e, SERIES_2500, products={"CB2500SS-BL": 9.00, "CB2500SS-BL-DIY": 9.00})

    lines = e.lines(set_id).json()["data"]
    assert [(ln["supplier_code"], ln["packaging_method"], ln["new_unit_cost"]) for ln in lines] == [
        ("CB2500SS-BL", "彩盒", 9.50),
        ("CB2500SS-BL-DIY", "OPP", 9.90),
        ("CB2500SS-BL-DIY", "吊卡", 9.40),
    ]
    for ln in lines:
        assert ln["duplicate_rows"] == [], ln
        assert "duplicate_code" not in ln["flags"], ln
        assert ln["skipped"] is False
        # The link has no cost list rows: only its standard price exists, no packaged one.
        assert ln["current_unit_cost"] is None
        assert ln["line_state"] == "changed"
    assert e.detail(set_id).json()["actions"]["apply_count"] == 3


def test_2500_series_applies_three_cost_rows_and_the_supplier_page_shows_three(cost_price_env):
    from app.models.cost_price import ProductSupplierCost
    from app.models.procurement import ProductSupplier

    e = cost_price_env
    supplier, made, set_id = _upload(e, SERIES_2500, products={"CB2500SS-BL": 9.00, "CB2500SS-BL-DIY": 9.00})
    r = e.apply(set_id)
    assert r.status_code == 200, r.text

    costs = e.db.query(ProductSupplierCost).all()
    assert sorted((c.packaging_method, c.packaging_key, c.unit_cost) for c in costs) == [
        ("OPP", "opp", Decimal("9.90")),
        ("吊卡", "吊卡", Decimal("9.40")),
        ("彩盒", "彩盒", Decimal("9.50")),
    ]

    bl = e.db.query(ProductSupplier).filter_by(product_id=made["CB2500SS-BL"].id).one()
    diy = e.db.query(ProductSupplier).filter_by(product_id=made["CB2500SS-BL-DIY"].id).one()
    e.db.refresh(bl)
    e.db.refresh(diy)
    # AC-CL-04 as amended: one packaging only, so the link follows it; two packagings and no
    # standard line, so the link keeps the price it had.
    assert bl.unit_cost == Decimal("9.50")
    assert diy.unit_cost == Decimal("9.00")

    listed = e.cost_lists(str(supplier.id)).json()
    entries = [
        (x["product"]["product_code"], x["packaging_method"], x["unit_cost"], [c["status"] for c in x["costs"]])
        for x in listed["data"]
    ]
    assert sorted(entries) == sorted([
        ("CB2500SS-BL", "彩盒", 9.50, ["always"]),
        ("CB2500SS-BL-DIY", "OPP", 9.90, ["always"]),
        ("CB2500SS-BL-DIY", "吊卡", 9.40, ["always"]),
    ])
    assert sorted(listed["packaging_options"]) == sorted(["OPP", "吊卡", "彩盒"])

    only_opp = e.cost_lists(str(supplier.id), packaging="opp").json()["data"]
    assert [(x["product"]["product_code"], x["packaging_method"]) for x in only_opp] == [("CB2500SS-BL-DIY", "OPP")]


def test_second_upload_compares_each_packaging_with_its_own_cost(cost_price_env):
    e = cost_price_env
    supplier, _, set_id = _upload(e, SERIES_2500, products={"CB2500SS-BL": None, "CB2500SS-BL-DIY": None})
    assert e.apply(set_id).status_code == 200

    data = simple_price_list_workbook(
        [("CB2500SS-BL-DIY（OPP）", "cfg", 9.90), ("CB2500SS-BL-DIY（吊卡）", "cfg", 9.80)],
        letterhead=LETTERHEAD_TEXT,
    )
    second = e.upload(data, supplier_id=str(supplier.id), currency="CNY")
    assert second.status_code == 201, second.text
    lines = {ln["packaging_method"]: ln for ln in e.lines(second.json()["id"]).json()["data"]}
    assert (lines["OPP"]["current_unit_cost"], lines["OPP"]["line_state"]) == (9.90, "unchanged")
    assert (lines["吊卡"]["current_unit_cost"], lines["吊卡"]["line_state"]) == (9.40, "changed")


def test_two_packagings_of_a_product_new_to_the_supplier_share_one_new_link(cost_price_env):
    from app.models.cost_price import ProductSupplierCost
    from app.models.procurement import ProductSupplier

    e = cost_price_env
    _, made, set_id = _upload(
        e, SERIES_2500[1:], products={"CB2500SS-BL-DIY": None},
    )
    lines = e.lines(set_id).json()["data"]
    assert [ln["line_state"] for ln in lines] == ["new_link", "new_link"]
    r = e.apply(set_id)
    assert r.status_code == 200, r.text
    links = e.db.query(ProductSupplier).filter_by(product_id=made["CB2500SS-BL-DIY"].id).all()
    assert len(links) == 1
    assert e.db.query(ProductSupplierCost).filter_by(product_supplier_id=links[0].id).count() == 2


# ------------------------------------------------------------- plain code beside a bracket


def test_plain_code_and_bracketed_code_of_one_product_are_two_lines(cost_price_env):
    from app.models.cost_price import ProductSupplierCost
    from app.models.procurement import ProductSupplier

    e = cost_price_env
    _, made, set_id = _upload(
        e, [("ZZCPC-R8-PLAIN", "cfg", 9.00), ("ZZCPC-R8-PLAIN（彩盒）", "cfg", 9.50)],
        products={"ZZCPC-R8-PLAIN": 8.00},
    )
    lines = e.lines(set_id).json()["data"]
    assert [(ln["packaging_method"], ln["new_unit_cost"], ln["current_unit_cost"]) for ln in lines] == [
        ("standard", 9.00, 8.00),  # the link's own price is its standard price
        ("彩盒", 9.50, None),
    ]
    assert all(ln["duplicate_rows"] == [] and "duplicate_code" not in ln["flags"] for ln in lines)

    assert e.apply(set_id).status_code == 200
    link = e.db.query(ProductSupplier).filter_by(product_id=made["ZZCPC-R8-PLAIN"].id).one()
    e.db.refresh(link)
    assert link.unit_cost == Decimal("9.00")  # the standard line, not 彩盒
    assert sorted(
        (c.packaging_method, c.unit_cost)
        for c in e.db.query(ProductSupplierCost).filter_by(product_supplier_id=link.id)
    ) == [("standard", Decimal("9.00")), ("彩盒", Decimal("9.50"))]


# ------------------------------------------------------------- same code, same packaging


def test_same_code_and_same_packaging_twice_is_a_duplicate_shown_inline(cost_price_env):
    e = cost_price_env
    _, _, set_id = _upload(
        e,
        [
            ("ZZCPC-R8-DUP（OPP）", "cfg", 9.90),
            ("ZZCPC-R8-DUP（吊卡）", "cfg", 9.40),
            ("ZZCPC-R8-DUP（opp）", "cfg", 9.95),  # same packaging, folded
        ],
        products={"ZZCPC-R8-DUP": 9.00},
    )
    lines = e.lines(set_id).json()["data"]
    assert [(ln["packaging_method"], ln["new_unit_cost"]) for ln in lines] == [("OPP", 9.90), ("吊卡", 9.40)]
    opp = lines[0]
    assert "duplicate_code" in opp["flags"]
    assert [(d["packaging_method"], d["new_unit_cost"]) for d in opp["duplicate_rows"]] == [("opp", 9.95)]
    assert lines[1]["duplicate_rows"] == []
    assert e.detail(set_id).json()["actions"]["can_apply"] is True


def test_plain_code_twice_is_a_duplicate(cost_price_env):
    e = cost_price_env
    _, _, set_id = _upload(
        e, [("ZZCPC-R8-PD", "cfg", 1.00), ("ZZCPC-R8-PD", "cfg", 2.00)], products={"ZZCPC-R8-PD": 3.00},
    )
    (line,) = e.lines(set_id).json()["data"]
    assert (line["packaging_method"], line["new_unit_cost"]) == ("standard", 1.00)
    assert [d["new_unit_cost"] for d in line["duplicate_rows"]] == [2.00]


# ------------------------------------------------------------------------- hand edits


def test_hand_added_cost_takes_a_packaging_and_defaults_to_standard(cost_price_env):
    e = cost_price_env
    e.as_user(e.user(PS_VIEW_PERM, PS_EDIT_PERM))
    supplier = e.supplier()
    link = e.link(e.product(), supplier, unit_cost=5, currency="CNY")
    r = e.post_cost(str(link.id), {"unit_cost": 6, "currency": "CNY", "packaging_method": " OPP "})
    assert r.status_code == 201, r.text
    assert r.json()["packaging_method"] == "OPP"
    r = e.post_cost(str(link.id), {"unit_cost": 7, "currency": "CNY"})
    assert r.status_code == 201, r.text
    assert r.json()["packaging_method"] == "standard"
    e.db.refresh(link)
    assert link.unit_cost == Decimal("7.00")
