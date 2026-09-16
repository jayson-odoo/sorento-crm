"""Warn and allow: the package guard that replaced the set guard (S2, D2).

UAC: `documentation/plans/dealer-kit/price-tag-combos-acceptance-criteria.md`
(AC-S2-5, AC-S2-6, AC-S2-7, AC-S2-8, AC-S2-10).

Written test-FIRST (PRINCIPLES.md Phase 2). The line-parts model does not exist
yet, so the import below fails the WHOLE FILE with one `ModuleNotFoundError` at
collection rather than every case failing for its own reason.

What changed, in one sentence: submit is NEVER refused for a package reason
again. A guarded product with no package, or with parts taken off, carries a
`package_warning` for marketing to read; `SET_GUARD_VIOLATION` is deleted. The
warning rule (D2):

    guarded = system_settings.price_tag_guarded_classes
              (JSONB list, default ["Bathroom Furniture", "Kitchen Sink"])
    for each PRODUCT line:
      class_label not in guarded             -> None
      no combo chosen and host has none      -> "No package defined"
      no combo chosen and host has combos    -> "No package chosen"
      otherwise, anything the chosen combo
      asks for that no part row answers      -> "Missing: <codes or groups>"

`DUPLICATE_LINE` is untouched, and a product_set line keeps its existing path -
parts are a combo fact on a product line and a set line never grows any.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models.access import RespondContact
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_set import ProductSet, ProductSetMember
from app.models.user import SystemSetting
from app.services.price_tag_request_service import PriceTagRequestService, STATUS_NEW

# THE red imports. `product_combo` is S1's model; `PriceTagRequestLinePart` and
# the line's `combo_id` / `package_warning` columns are S2's (PLAN D2).
from app.models.product_combo import ProductCombo, ProductComboPart  # noqa: E402
from app.models.price_tag import (  # noqa: E402
    PriceTagRequestLine,
    PriceTagRequestLinePart,
)

from tests._pg_fixture import blank_session, unique_code

SORENTO = "00000000-0000-0000-0000-000000000001"
DEFAULT_GUARDED = ["Bathroom Furniture", "Kitchen Sink"]


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def db() -> Session:
    with blank_session() as session:
        yield session


def _contact(db: Session) -> RespondContact:
    from tests._portal_grant import link_contact_segment, seed_segment

    contact = RespondContact(
        id=_uid(),
        phone_number=f"+60{uuid.uuid4().hex[:9]}",
        name=unique_code("contact"),
    )
    db.add(contact)
    db.flush()
    segment = seed_segment(db, kinds=["price_tag_request"])
    link_contact_segment(db, contact.id, segment.code)
    return contact


def _product(db: Session, stem: str, *, class_label: str | None = None) -> Product:
    """A product and its whole FK chain - CI's database is empty."""
    category = ProductCategory(
        id=_uid(),
        category_code=unique_code("cat")[:50],
        category_name=unique_code("Category"),
        class_label=class_label,
    )
    brand = Brand(id=_uid(), brand_code=unique_code("br"), brand_name=unique_code("Brand"))
    uom = UnitOfMeasure(id=_uid(), uom_code=unique_code("uom")[:20], uom_name="Each")
    db.add_all([category, brand, uom])
    db.flush()
    product = Product(
        id=_uid(),
        company_id=SORENTO,
        product_code=unique_code(stem),
        product_name=f"ZZT {stem}",
        category_id=category.id,
        brand_id=brand.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
    )
    db.add(product)
    db.flush()
    return product


def _combo(db: Session, host: Product, name: str, parts) -> ProductCombo:
    """`parts` is a list of (product, choice_group) in display order."""
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


def _product_set(db: Session, member: Product) -> ProductSet:
    product_set = ProductSet(
        id=_uid(), set_code=unique_code("set"), name=unique_code("Set"), company_id=SORENTO
    )
    db.add(product_set)
    db.flush()
    db.add(
        ProductSetMember(
            id=_uid(),
            product_set_id=product_set.id,
            product_id=member.id,
            quantity=1,
            contributes_to_price=True,
            sort_order=0,
        )
    )
    db.flush()
    return product_set


def _submit(db: Session, contact: RespondContact, lines: list[dict]):
    return PriceTagRequestService.submit_request(
        db,
        contact_id=contact.id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "needed_by_date": date.today() + timedelta(days=7),
            "lines": lines,
        },
    )


def _line_warnings(request) -> list[str | None]:
    return [
        line.package_warning
        for line in sorted(request.lines, key=lambda l: (l.sort_order or 0, l.id))
    ]


# --------------------------------------------------------------------------- AC-S2-5


def test_submit_package_warning_texts(db: Session):
    """The three texts marketing reads, and the NULL a clean line stores.

    Every case submits. The warning is the whole mitigation for softening the
    guard, so its wording is contract: "No package defined" says nobody has
    recorded the cabinet's packaging yet, "Missing: <code>" says the salesperson
    took a part off, and NULL says there is nothing to look at.
    """
    contact = _contact(db)

    # 1. Guarded class, and the host has no combo at all.
    bare = _product(db, "SRTBF11834", class_label="Bathroom Furniture")
    request = _submit(db, contact, [{"line_type": "product", "product_id": bare.id}])
    assert request.status == STATUS_NEW, "submit is never refused for a package reason"
    assert _line_warnings(request) == ["No package defined"]

    # 2. Guarded class, host HAS combos, none chosen.
    cabinet = _product(db, "SRTBF11835", class_label="Bathroom Furniture")
    mirror = _product(db, "SRTMR502-BL")
    top = _product(db, "SRTTT800")
    _combo(db, cabinet, "3 in 1", [(mirror, None), (top, None)])
    request = _submit(db, contact, [{"line_type": "product", "product_id": cabinet.id}])
    assert _line_warnings(request) == ["No package chosen"]

    # 3. Combo chosen, the mirror row removed: the missing part is NAMED by its
    #    code, because "something is missing" is not actionable.
    combo = (
        db.query(ProductCombo).filter(ProductCombo.host_product_id == cabinet.id).one()
    )
    request = _submit(
        db,
        contact,
        [
            {
                "line_type": "product",
                "product_id": cabinet.id,
                "combo_id": combo.id,
                "parts": [{"product_id": top.id}],
            }
        ],
    )
    assert _line_warnings(request) == [f"Missing: {mirror.product_code}"]

    # 4. Every fixed part present: clean, so NULL.
    request = _submit(
        db,
        contact,
        [
            {
                "line_type": "product",
                "product_id": cabinet.id,
                "combo_id": combo.id,
                "parts": [{"product_id": mirror.id}, {"product_id": top.id}],
            }
        ],
    )
    assert _line_warnings(request) == [None]

    # 5. A class NOT in the guarded list is never warned about, package or no.
    accessory = _product(db, "SRTAC100", class_label="Accessories")
    request = _submit(db, contact, [{"line_type": "product", "product_id": accessory.id}])
    assert _line_warnings(request) == [None]


def test_an_open_choice_group_answers_the_combo_and_is_not_missing(db: Session):
    """A group left OPEN is an answer, not an omission.

    The whole point of the open row is that the salesperson may not know which
    basin; marketing splits it into one tag per candidate later (S3). Warning
    about it would train them to pick one at random.
    """
    contact = _contact(db)
    cabinet = _product(db, "SRTBF11834", class_label="Bathroom Furniture")
    mirror = _product(db, "SRTMR502-BL")
    basin_white = _product(db, "SRTBS900-WH")
    basin_black = _product(db, "SRTBS900-BK")
    combo = _combo(
        db,
        cabinet,
        "3 in 1",
        [(mirror, None), (basin_white, "Basin"), (basin_black, "Basin")],
    )

    open_row = _submit(
        db,
        contact,
        [
            {
                "line_type": "product",
                "product_id": cabinet.id,
                "combo_id": combo.id,
                "parts": [
                    {"product_id": mirror.id},
                    {"role": "Basin", "candidates": [basin_white.id, basin_black.id]},
                ],
            }
        ],
    )
    assert _line_warnings(open_row) == [None]

    # Drop the group entirely - neither resolved nor open - and it IS missing,
    # named by the group label rather than by a code nobody chose.
    no_row = _submit(
        db,
        contact,
        [
            {
                "line_type": "product",
                "product_id": cabinet.id,
                "combo_id": combo.id,
                "parts": [{"product_id": mirror.id}],
            }
        ],
    )
    assert _line_warnings(no_row) == ["Missing: Basin"]


# --------------------------------------------------------------------------- AC-S2-6


def test_settings_guarded_classes_round_trip(db: Session):
    """The list is a system setting, it defaults to the two classes, and it reaches the FE.

    The manual GET dict is the trap here (LESSONS-LEARNT): a settings column that
    is not on it never reaches the settings page, and the multi-select renders
    empty as though nothing were guarded.
    """
    from app.api.v1.user_management.settings import (
        SystemSettingUpdate,
        _update_general_settings_impl,
        get_settings,
    )

    db.add(SystemSetting(id="ss-1"))
    db.commit()

    row = db.query(SystemSetting).first()
    assert list(row.price_tag_guarded_classes or []) == DEFAULT_GUARDED, (
        "the column's server default is the two classes the owner named"
    )

    _update_general_settings_impl(
        SystemSettingUpdate(price_tag_guarded_classes=["Kitchen Sink", "Shower"]), db
    )
    db.expire_all()
    assert list(db.query(SystemSetting).first().price_tag_guarded_classes) == [
        "Kitchen Sink",
        "Shower",
    ]

    payload = asyncio.run(get_settings(current_user={"id": _uid()}, db=db))
    assert payload["settings"]["price_tag_guarded_classes"] == ["Kitchen Sink", "Shower"], (
        "a new settings column reaches the FE only if it is on the manual GET dict"
    )


def test_the_guard_reads_the_setting_not_a_hardcoded_list(db: Session):
    """Editing the setting changes which lines get warned about.

    Otherwise the settings control is decorative and the tenant that packages
    shower trays has no way to say so.
    """
    db.add(SystemSetting(id="ss-1", price_tag_guarded_classes=["Shower"]))
    db.commit()

    contact = _contact(db)
    shower = _product(db, "SRTSH900", class_label="Shower")
    cabinet = _product(db, "SRTBF11834", class_label="Bathroom Furniture")

    request = _submit(
        db,
        contact,
        [
            {"line_type": "product", "product_id": shower.id},
            {"line_type": "product", "product_id": cabinet.id},
        ],
    )
    assert _line_warnings(request) == ["No package defined", None]


# --------------------------------------------------------------------------- AC-S2-7


def test_set_guard_violation_retired(db: Session):
    """The two cases that used to be a 422 now submit, carrying a warning.

    `SET_GUARD_VIOLATION` is deleted along with `validate_set_guard`,
    `_ala_carte_offender` and `_set_guard_refusal`. A set line keeps its
    existing path untouched: parts are a combo fact on a PRODUCT line.
    """
    contact = _contact(db)

    # Former case 1: one ala-carte Bathroom Furniture line -> was 422.
    bad = _product(db, "SRTBF11834", class_label="Bathroom Furniture")
    single = _submit(db, contact, [{"line_type": "product", "product_id": bad.id}])
    assert single.status == STATUS_NEW
    assert _line_warnings(single) == ["No package defined"]

    # Former case 2: a clean line beside a guarded one -> was 422 naming line:1.
    ok = _product(db, "SRTAC100", class_label="Accessories")
    second_bad = _product(db, "SRTBF11835", class_label="Bathroom Furniture")
    pair = _submit(
        db,
        contact,
        [
            {"line_type": "product", "product_id": ok.id},
            {"line_type": "product", "product_id": second_bad.id},
        ],
    )
    assert pair.status == STATUS_NEW
    assert _line_warnings(pair) == [None, "No package defined"]

    # The name itself is gone from the service.
    assert not hasattr(PriceTagRequestService, "validate_set_guard")

    # A product_set line is unchanged: it submits, and it carries no warning
    # (nothing about a set is a package question).
    member = _product(db, "SRTBF11836", class_label="Bathroom Furniture")
    product_set = _product_set(db, member)
    as_set = _submit(
        db, contact, [{"line_type": "product_set", "product_set_id": product_set.id}]
    )
    assert as_set.status == STATUS_NEW
    assert _line_warnings(as_set) == [None]


# --------------------------------------------------------------------------- AC-S2-8


def test_line_parts_persist_in_order(db: Session):
    """Three parts, mixed shapes, stored in the order the form sent them.

    Order is display order on the request, on the tag's parts text (D4) and in
    the designer's rail, so a stored set rather than a stored list would silently
    reorder what marketing prints.
    """
    contact = _contact(db)
    cabinet = _product(db, "SRTBF11834", class_label="Bathroom Furniture")
    mirror = _product(db, "SRTMR502-BL")
    tap = _product(db, "SRTTP100")
    basin_white = _product(db, "SRTBS900-WH")
    basin_black = _product(db, "SRTBS900-BK")
    combo = _combo(
        db,
        cabinet,
        "4 in 1",
        [(mirror, None), (tap, None), (basin_white, "Basin"), (basin_black, "Basin")],
    )

    request = _submit(
        db,
        contact,
        [
            {
                "line_type": "product",
                "product_id": cabinet.id,
                "combo_id": combo.id,
                "parts": [
                    {"product_id": mirror.id, "role": None},
                    {"role": "Basin", "candidates": [basin_white.id, basin_black.id]},
                    {"product_id": tap.id, "role": "Tap"},
                ],
            }
        ],
    )
    db.flush()

    line = request.lines[0]
    assert line.combo_id == combo.id
    parts = (
        db.query(PriceTagRequestLinePart)
        .filter(PriceTagRequestLinePart.line_id == line.id)
        .order_by(PriceTagRequestLinePart.sort_order)
        .all()
    )
    assert [p.sort_order for p in parts] == [0, 1, 2]

    # A RESOLVED row names a product and carries no candidates.
    assert parts[0].product_id == mirror.id
    assert parts[0].role is None
    assert list(parts[0].candidates or []) == []

    # An OPEN row names the group and its candidates, and no product.
    assert parts[1].product_id is None
    assert parts[1].role == "Basin"
    assert list(parts[1].candidates) == [basin_white.id, basin_black.id]

    # A resolved row still says WHICH group it answered.
    assert parts[2].product_id == tap.id
    assert parts[2].role == "Tap"

    # `alternatives` is gone from the line for good (AC-S2-8).
    assert not hasattr(PriceTagRequestLine, "alternatives")


def test_show_promo_price_is_never_true_at_plain_list(db: Session):
    """The client does not send it, and the server derives it (r7 D5) -
    but D3 (PLAN-price-tag-line-promo-combo-subject.md) retires the OLD
    rule this test used to pin (`price_mode == 'selling'` alone), which
    printed SP on a line summed at plain list. The rule now is AC-S7-5:
    Selling AND `sell_price_basis != 'list'` - a line with no covering
    promotion and no manual price is LP even in Selling mode.

    Spelled out because AC-S2-8 lists `show_promo_price` in the line payload
    and the r7 review settled it as server-derived, never client-sent; that
    decision stands, so a line that sends it must not be able to contradict
    what the server derives.
    """
    contact = _contact(db)
    product = _product(db, "SRTAC100", class_label="Accessories")

    request = PriceTagRequestService.submit_request(
        db,
        contact_id=contact.id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "needed_by_date": date.today() + timedelta(days=7),
            "price_mode": "selling",
            "lines": [{"line_type": "product", "product_id": product.id}],
        },
    )
    assert request.lines[0].show_promo_price is False, (
        "no covering promotion, no manual price - basis is list"
    )


# --------------------------------------------------------------------------- AC-S2-10


def test_duplicate_line_still_refused(db: Session):
    """Softening the package guard does not soften this one.

    The same product twice on one request is still a mistake - one tag per
    product per request is what `uq_ptag_line_request_product` is for, and the
    refusal must stay a named `DUPLICATE_LINE`, never a raw integrity 500.
    """
    contact = _contact(db)
    product = _product(db, "SRTBF11834", class_label="Bathroom Furniture")

    with pytest.raises(Exception) as exc_info:
        _submit(
            db,
            contact,
            [
                {"line_type": "product", "product_id": product.id},
                {"line_type": "product", "product_id": product.id},
            ],
        )

    error = exc_info.value
    assert getattr(error, "status_code", None) == 422
    detail = getattr(error, "detail", None)
    code = detail.get("code") if isinstance(detail, dict) else None
    assert code == "DUPLICATE_LINE"
