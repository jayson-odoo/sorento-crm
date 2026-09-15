"""What a tag with parts actually prints (S4, D4).

UAC: `documentation/plans/dealer-kit/price-tag-combos-acceptance-criteria.md`
(AC-S4-1, AC-S4-2).

Written test-FIRST (PRINCIPLES.md Phase 2). The combo and tag models do not
exist, so the imports below fail the WHOLE FILE at collection with one
`ModuleNotFoundError`.

One resolver feeds four consumers - the designer, the portal design payload, the
CRM/portal detail body and the print payload - so the two questions here are the
ones that decide what a customer reads off a printed tag:

* the `set_members` slot text, which every existing template already carries, so
  a cabinet's parts print with NO template change (D4);
* the price, which is now a TAG fact: host plus THIS tag's resolved parts, with
  an unresolved group contributing nothing and a marketing override winning.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.services.price_tag_request_service import PriceTagRequestService

# THE red imports. S1's combo tables and S3's tag table.
from app.models.product_combo import ProductCombo, ProductComboPart  # noqa: E402
from app.models.price_tag import PriceTagRequestTag  # noqa: E402

from tests._pg_fixture import blank_session, unique_code

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

SORENTO = "00000000-0000-0000-0000-000000000001"


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


# ---------------------------------------------------------------------------
# Seeding (CI's database is empty: every FK target is created here)
# ---------------------------------------------------------------------------


def _product(db, stem: str, *, list_price: str, dimensions=("800", "500", "220")):
    from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure

    code = unique_code(stem)
    category = ProductCategory(
        id=_uid(),
        category_code=code[:50],
        category_name=f"ZZT cat {code}",
        class_label="Bathroom Furniture",
    )
    brand = Brand(id=_uid(), brand_code=code[:50], brand_name=f"ZZT brand {code}")
    uom = UnitOfMeasure(id=_uid(), uom_code=code[:20], uom_name="Each")
    db.add_all([category, brand, uom])
    db.flush()
    product = Product(
        id=_uid(),
        company_id=SORENTO,
        product_code=code,
        product_name=f"ZZT {stem}",
        category_id=category.id,
        brand_id=brand.id,
        base_uom_id=uom.id,
        list_price=Decimal(list_price),
        currency="MYR",
        dimensions_length=Decimal(dimensions[0]),
        dimensions_width=Decimal(dimensions[1]),
        dimensions_height=Decimal(dimensions[2]),
        is_active=True,
        is_discontinued=False,
    )
    db.add(product)
    db.flush()
    return product


def _promotion(db, lines: list[tuple], *, description=None):
    """`lines` is a list of (product, promo_selling_price)."""
    from app.models.marketing import Promotion, PromotionGroup, PromotionProduct

    promotion = Promotion(
        id=_uid(),
        description=description or unique_code("ZZT promo"),
        start_date=date.today() - timedelta(days=1),
        end_date=date.today() + timedelta(days=30),
        is_active=True,
        access_levels=["dealer", "end_user"],
        company_id=SORENTO,
    )
    db.add(promotion)
    db.flush()
    group = PromotionGroup(promotion_id=promotion.id, group_name="ZZT group", sort_order=0)
    db.add(group)
    db.flush()
    for product, price in lines:
        db.add(
            PromotionProduct(
                id=_uid(),
                promotion_id=promotion.id,
                promotion_group_id=str(group.id),
                product_id=product.id,
                promo_selling_price=Decimal(price),
                company_id=SORENTO,
            )
        )
    db.flush()
    return promotion


def _contact(db):
    from app.models.access import RespondContact

    contact = RespondContact(
        id=_uid(), phone_number=f"+60{uuid.uuid4().hex[:9]}", name=unique_code("contact")
    )
    db.add(contact)
    db.flush()
    return contact


def _combo(db, host, name, parts):
    combo = ProductCombo(id=_uid(), host_product_id=host.id, name=name, sort_order=0)
    db.add(combo)
    db.flush()
    for index, (product, choice_group) in enumerate(parts):
        db.add(
            ProductComboPart(
                id=_uid(),
                combo_id=combo.id,
                part_product_id=product.id,
                choice_group=choice_group,
                sort_order=index,
            )
        )
    db.flush()
    return combo


def _request(db, *, product, combo=None, parts=None, promotion_id=None, price_mode="list"):
    return PriceTagRequestService.submit_request(
        db,
        contact_id=_contact(db).id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "promotion_id": promotion_id,
            "price_mode": price_mode,
            "lines": [
                {
                    "line_type": "product",
                    "product_id": product.id,
                    "combo_id": combo.id if combo is not None else None,
                    "quantity": 1,
                    "parts": parts or [],
                }
            ],
        },
    )


def _rows(db, request):
    from app.services.dealer_kit import tag_data_service

    return tag_data_service.resolve_request_line_data(db, request)


# --------------------------------------------------------------------------- AC-S4-1


def test_set_members_text_parts_and_open_group(db):
    """`+ CODE NAME DIMS` per resolved part, then `ROLE: CODE / CODE` per open group.

    The slot is `set_members` on purpose: every template already carries it, so a
    cabinet's package prints without one template being touched. The two shapes
    have to differ - a resolved part is a thing that is IN the box, an open group
    is a choice the reader makes - which is why the fixed rows lead with `+` and
    the open one leads with its own label.
    """
    cabinet = _product(db, "SRTBF11834", list_price="1599.00")
    mirror = _product(db, "SRTMR502-BL", list_price="199.00", dimensions=("500", "70", "700"))
    tap = _product(db, "SRTTP100", list_price="99.00", dimensions=("120", "45", "300"))
    white = _product(db, "SRTBS900-WH", list_price="299.00")
    black = _product(db, "SRTBS900-BK", list_price="299.00")
    combo = _combo(
        db,
        cabinet,
        "4 in 1",
        [(mirror, None), (tap, None), (white, "Basin"), (black, "Basin")],
    )

    request = _request(
        db,
        product=cabinet,
        combo=combo,
        parts=[
            {"product_id": mirror.id},
            {"product_id": tap.id},
            {"role": "Basin", "candidates": [white.id, black.id]},
        ],
    )
    db.flush()

    row = _rows(db, request)[0]
    assert row["set_members"] == "\n".join(
        [
            f"+ {mirror.product_code} {mirror.product_name} 500 x 70 x 700 mm",
            f"+ {tap.product_code} {tap.product_name} 120 x 45 x 300 mm",
            f"Basin: {white.product_code} / {black.product_code}",
        ]
    )
    # The same parts key by key, for the rail and the CRM Lines tab.
    assert [part["code"] for part in row["parts"]] == [
        mirror.product_code,
        tap.product_code,
    ]
    assert [group["role"] for group in row["open_groups"]] == ["Basin"]

    # Once the group is RESOLVED the open line becomes a `+` line in part order,
    # because a split tag prints a specific basin.
    tag = db.query(PriceTagRequestTag).filter(
        PriceTagRequestTag.line_id == request.lines[0].id
    ).one()
    tag.choices = {"Basin": black.id}
    # Answering a choice changes WHICH products the tag prints, so the pin taken
    # on the read above describes a different tag (r9 D16). Both routes that
    # write `choices` - PATCH and Split - drop the pin for exactly this reason;
    # this test writes the column directly, so it drops it directly too.
    tag.pinned_tag_data = None
    tag.pinned_at = None
    tag.data_change_ack_hash = None
    db.flush()

    resolved = _rows(db, request)[0]
    assert resolved["open_groups"] == []
    assert resolved["set_members"].splitlines()[-1] == (
        f"+ {black.product_code} {black.product_name} 800 x 500 x 220 mm"
    )


def test_a_tag_with_no_parts_is_exactly_todays_product_tag(db):
    """No combo, no parts: the text is empty and nothing else changed.

    Most tags will never carry a package, so the slice must not put a stray `+`
    line or an empty heading onto thousands of existing product tags.
    """
    product = _product(db, "SRTAC100", list_price="49.00")
    request = _request(db, product=product)
    db.flush()

    row = _rows(db, request)[0]
    assert row["set_members"] == ""
    assert row["parts"] == []
    assert row["open_groups"] == []
    assert row["code"] == product.product_code
    assert row["list_price"] == Decimal("49.00")


# --------------------------------------------------------------------------- AC-S4-2


def test_tag_price_sum_promotion_override(db):
    """Three cases: the list sum, the promotion engine's sum, and the override.

    A package price that silently printed the cabinet alone is the defect this
    pins: the customer reads one figure off the tag and pays for four products.
    An unresolved group contributes NOTHING - the four basins are one choice, not
    four purchases, and any of them would be a guess.
    """
    cabinet = _product(db, "SRTBF11834", list_price="1599.00")
    mirror = _product(db, "SRTMR502-BL", list_price="199.00")
    white = _product(db, "SRTBS900-WH", list_price="299.00")
    black = _product(db, "SRTBS900-BK", list_price="349.00")
    combo = _combo(
        db, cabinet, "3 in 1", [(mirror, None), (white, "Basin"), (black, "Basin")]
    )

    # Case 1: list price is the host plus the RESOLVED parts. The open Basin
    # group adds nothing.
    request = _request(
        db,
        product=cabinet,
        combo=combo,
        parts=[
            {"product_id": mirror.id},
            {"role": "Basin", "candidates": [white.id, black.id]},
        ],
    )
    db.flush()
    row = _rows(db, request)[0]
    assert row["list_price"] == Decimal("1798.00"), "1599 host + 199 mirror, no basin"

    # Case 2: the promotion engine answers per product and the tag sums it. The
    # mirror has no promotion line, so it contributes its LIST price - an offer
    # the engine does not have is not a discount.
    promotion = _promotion(db, [(cabinet, "1299.00"), (white, "249.00")])
    promoted = _request(
        db,
        product=cabinet,
        combo=combo,
        promotion_id=promotion.id,
        price_mode="selling",
        parts=[{"product_id": mirror.id}, {"product_id": white.id}],
    )
    db.flush()
    promoted_row = _rows(db, promoted)[0]
    assert promoted_row["list_price"] == Decimal("2097.00"), "1599 + 199 + 299"
    assert promoted_row["sell_price"] == Decimal("1747.00"), "1299 offer + 199 list + 249 offer"
    assert promoted_row["show_promo_price"] is True

    # Case 3: the marketing override on the TAG wins over the engine's sum. It is
    # a decision somebody made and logged a reason for; the engine cannot know it.
    tag = (
        db.query(PriceTagRequestTag)
        .filter(PriceTagRequestTag.line_id == promoted.lines[0].id)
        .one()
    )
    tag.marketing_price_override = Decimal("1499.00")
    tag.marketing_override_reason = "ZZT roadshow bundle"
    db.flush()

    overridden = _rows(db, promoted)[0]
    assert overridden["sell_price"] == Decimal("1499.00")
    # The override is a SELLING price - it never rewrites what the package lists at.
    assert overridden["list_price"] == Decimal("2097.00")


def test_two_split_tags_price_their_own_candidate(db):
    """Split siblings differ only by the candidate they resolved, and so do their prices.

    The reason price moved onto the tag at all: a white basin at 299 and a black
    one at 349 must not both print the same figure.
    """
    cabinet = _product(db, "SRTBF11834", list_price="1599.00")
    white = _product(db, "SRTBS900-WH", list_price="299.00")
    black = _product(db, "SRTBS900-BK", list_price="349.00")
    combo = _combo(db, cabinet, "2 in 1", [(white, "Basin"), (black, "Basin")])

    request = _request(
        db,
        product=cabinet,
        combo=combo,
        parts=[{"role": "Basin", "candidates": [white.id, black.id]}],
    )
    db.flush()

    line = request.lines[0]
    first = (
        db.query(PriceTagRequestTag).filter(PriceTagRequestTag.line_id == line.id).one()
    )
    first.choices = {"Basin": white.id}
    second = PriceTagRequestTag(
        id=_uid(),
        line_id=line.id,
        sort_order=1,
        quantity=line.quantity,
        choices={"Basin": black.id},
    )
    db.add(second)
    db.flush()

    rows = _rows(db, request)
    assert [row["tag_label"] for row in rows] == ["1a", "1b"]
    assert [row["list_price"] for row in rows] == [
        Decimal("1898.00"),
        Decimal("1948.00"),
    ]
    assert [row["set_members"].splitlines()[0].split()[1] for row in rows] == [
        white.product_code,
        black.product_code,
    ]


# ---------------------------------------------------------------------------
# S9 - subject parts carry full product data, basis per line, pin diff by part,
# per-line export guard (line promotion supersedes the header one, D1/D3/D10).
#
# Written test-FIRST against the CURRENT resolver. `_part_row` today returns
# only `{product_id, code, name, dimensions}` and `resolve_tags_live` writes no
# `sell_price_basis` key at all, so every assertion below that reads a NEW key
# off the resolved row is a plain `KeyError` - no raw SQL, no ImportError, just
# the field genuinely not there yet. The export-guard test is the one exception:
# it needs a PER-LINE promotion, which is a column `ptag_0011` has not added, so
# it writes it with raw SQL and lets Postgres's own `UndefinedColumn` be the red.
# ---------------------------------------------------------------------------


def test_parts_carry_full_product_data(db):
    """AC-S9-1: a part is a first-class product, not a code and a dimension string.

    D7 needs every part resolvable on its own - a layer may pick ANY part as its
    subject - so `_part_row` has to carry what `_line_product_data` already
    resolves for the host: images, specs, barcode, both prices.
    """
    cabinet = _product(db, "SRT9PART", list_price="1599.00")
    mirror = _product(db, "SRT9MIRR", list_price="199.00")
    combo = _combo(db, cabinet, "2 pc", [(mirror, None)])

    request = _request(
        db, product=cabinet, combo=combo, parts=[{"product_id": mirror.id}]
    )
    db.flush()

    part = _rows(db, request)[0]["parts"][0]
    for field in (
        "product_id",
        "code",
        "name",
        "dimensions",
        "spec_lines",
        "specs",
        "images",
        "barcode",
        "list_price",
        "sell_price",
    ):
        assert field in part, f"{field} missing from a resolved part"
    assert part["product_id"] == mirror.id
    assert part["list_price"] == Decimal("199.00")


def test_combo_without_offer_prints_lp(db):
    """AC-S9-3: `sell_price_basis` decides `show_promo_price`, not "is there a sum".

    The 1299+199+249 combo (a promotion covering the parent and one part) now
    asserts `basis == 'promotion'`; a second combo under a promotion that covers
    NONE of its products is `basis == 'list'` and prints like a plain product -
    the defect D3 retires (a combo summed at list used to still show as SP).
    """
    cabinet = _product(db, "SRT9COVER", list_price="1599.00")
    mirror = _product(db, "SRT9MIRR2", list_price="199.00")
    white = _product(db, "SRT9WH", list_price="299.00")
    combo = _combo(db, cabinet, "3 in 1", [(mirror, None), (white, "Basin")])
    promotion = _promotion(db, [(cabinet, "1299.00"), (white, "249.00")])

    covered = _request(
        db,
        product=cabinet,
        combo=combo,
        promotion_id=promotion.id,
        price_mode="selling",
        parts=[{"product_id": mirror.id}, {"product_id": white.id}],
    )
    db.flush()
    covered_row = _rows(db, covered)[0]
    assert covered_row["sell_price_basis"] == "promotion"
    assert covered_row["show_promo_price"] is True

    other_cabinet = _product(db, "SRT9NOCOV", list_price="899.00")
    other_combo = _combo(db, other_cabinet, "solo", [])
    not_covered = _request(
        db,
        product=other_cabinet,
        combo=other_combo,
        # A promotion exists but does not price THIS product at all.
        promotion_id=promotion.id,
        price_mode="selling",
    )
    db.flush()
    not_covered_row = _rows(db, not_covered)[0]
    assert not_covered_row["sell_price_basis"] == "list"
    assert not_covered_row["show_promo_price"] is False


def test_pin_includes_parts_and_diff_names_part_code(db):
    """AC-S9-4: the pin freezes `parts[]`, and a part's own change diffs under its code."""
    from app.services.dealer_kit import tag_data_service

    cabinet = _product(db, "SRT9PIN", list_price="1599.00")
    mirror = _product(db, "SRT9PINMIRR", list_price="199.00")
    combo = _combo(db, cabinet, "2 pc", [(mirror, None)])
    request = _request(
        db, product=cabinet, combo=combo, parts=[{"product_id": mirror.id}]
    )
    db.flush()

    tag_data_service.pin_tags(db, request, only_unpinned=True)
    db.commit()

    tag = request.lines[0].tags[0]
    pinned = tag.pinned_tag_data
    assert pinned is not None
    assert pinned.get("parts"), "the pin carries parts[]"
    assert pinned["parts"][0].get("code") == mirror.product_code

    # Master data moves under the part after the pin was taken.
    mirror.list_price = Decimal("259.00")
    db.flush()

    diffed = tag_data_service.resolve_request_line_data(db, request)[0]
    changed_fields = {change["field"] for change in diffed.get("data_changes") or []}
    assert any(mirror.product_code in field for field in changed_fields), (
        "a part's own price change is reported keyed under the PART's code, "
        f"not folded into the tag's own list_price - saw {changed_fields}"
    )


def test_export_guard_walks_line_promotions(db):
    """AC-S9-5: the export guard checks EVERY line's own promotion, names the line.

    `_check_promotion_expired` today reads only `request.promotion_id` - the
    header. Since D1 drops that column, this writes a promotion straight onto
    LINE 2 with raw SQL: the column does not exist yet, so this fails with
    Postgres's own `UndefinedColumn` naming exactly what is missing.
    """
    from sqlalchemy import text

    from app.services.dealer_kit.tag_sheet_export_service import (
        _check_promotion_expired,
    )
    from app.services.error_handler import AppException

    first = _product(db, "SRT9EXP1", list_price="199.00")
    second = _product(db, "SRT9EXP2", list_price="299.00")
    expired = _promotion(
        db, [(second, "199.00")], description="ZZT expired line promo"
    )
    expired.end_date = date.today() - timedelta(days=1)
    db.flush()

    request = PriceTagRequestService.submit_request(
        db,
        contact_id=_contact(db).id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "price_mode": "selling",
            "lines": [
                {"line_type": "product", "product_id": first.id, "quantity": 1},
                {"line_type": "product", "product_id": second.id, "quantity": 1},
            ],
        },
    )
    db.flush()
    line_two_id = sorted(request.lines, key=lambda line: line.sort_order or 0)[1].id

    # THE red statement: `price_tag_request_lines.promotion_id` does not exist
    # until ptag_0011 lands.
    db.execute(
        text("UPDATE price_tag_request_lines SET promotion_id = :p WHERE id = :l"),
        {"p": expired.id, "l": line_two_id},
    )
    db.flush()

    with pytest.raises(AppException) as excinfo:
        _check_promotion_expired(db, request)
    assert excinfo.value.status_code == 409
    assert "line 2" in excinfo.value.message.lower()
