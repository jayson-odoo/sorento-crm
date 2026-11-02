"""Shared seed for the PRICETAG-COMBO suites (not a test module).

Every row is created here with its own FK chain: CI's database is empty. Figures and
codes are synthetic. The new combo columns are passed straight to the model
constructors, so a missing column surfaces as a TypeError in the test that needs it.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from app.models.product_combo import ProductCombo, ProductComboPart
from app.services.price_tag_request_service import PriceTagRequestService

from tests import _ptag_r9_seed as r9
from tests._pg_fixture import unique_code

SORENTO = r9.SORENTO


def product(db, stem: str = "ZZC", *, list_price="100.00", tag_text=None, company_id=SORENTO):
    """A product whose name equals its code (as on real data) and its own FK chain."""
    row = r9.seed_product(db, list_price=Decimal(list_price))
    row.product_code = unique_code(stem)
    row.product_name = row.product_code
    row.price_tag_description = tag_text
    row.description = tag_text  # option text reads products.description (AC-2.1)
    row.company_id = company_id
    db.flush()
    return row


def combo(db, host, name="ZZT combo", *, parts=(), **fields):
    """`parts` is a list of dicts: {product, group=None, **part columns}."""
    row = ProductCombo(id=str(uuid.uuid4()), host_product_id=host.id, name=name, sort_order=0, **fields)
    db.add(row)
    db.flush()
    for index, spec in enumerate(parts):
        spec = dict(spec)
        item = spec.pop("product")
        group = spec.pop("group", None)
        db.add(
            ProductComboPart(
                id=str(uuid.uuid4()),
                combo_id=row.id,
                part_product_id=item.id,
                choice_group=group,
                sort_order=index,
                **spec,
            )
        )
    db.flush()
    return row


def contact(db):
    from app.models.access import RespondContact

    row = RespondContact(
        id=str(uuid.uuid4()), phone_number=f"+60{uuid.uuid4().hex[:9]}", name=unique_code("contact")
    )
    db.add(row)
    db.flush()
    return row


def line_dict(host, combo_row=None, parts=None, **extra):
    return {
        "line_type": "product",
        "product_id": host.id,
        "combo_id": combo_row.id if combo_row is not None else None,
        "quantity": 1,
        "parts": parts or [],
        **extra,
    }


def submit(db, lines, *, price_mode="list"):
    return PriceTagRequestService.submit_request(
        db,
        contact_id=contact(db).id,
        company_id=SORENTO,
        data={
            "debtor_name": "ZZT Dealer",
            "price_mode": price_mode,
            "needed_by_date": date.today() + timedelta(days=7),
            "lines": lines,
        },
    )


def submit_one(db, host, combo_row=None, parts=None, *, price_mode="list", **line_extra):
    return submit(db, [line_dict(host, combo_row, parts, **line_extra)], price_mode=price_mode)


def rows(db, request):
    from app.services.dealer_kit import tag_data_service

    return tag_data_service.resolve_request_line_data(db, request)


def promotion(db, lines, *, description=None):
    """`lines` is a list of (product, promo_selling_price)."""
    from app.models.marketing import Promotion, PromotionGroup, PromotionProduct

    promo = Promotion(
        id=str(uuid.uuid4()),
        description=description or unique_code("ZZT promo"),
        start_date=date.today() - timedelta(days=1),
        end_date=date.today() + timedelta(days=30),
        is_active=True,
        access_levels=["dealer", "end_user"],
        company_id=SORENTO,
    )
    db.add(promo)
    db.flush()
    group = PromotionGroup(promotion_id=promo.id, group_name="ZZT group", sort_order=0)
    db.add(group)
    db.flush()
    for item, price in lines:
        db.add(
            PromotionProduct(
                id=str(uuid.uuid4()),
                promotion_id=promo.id,
                promotion_group_id=str(group.id),
                product_id=item.id,
                promo_selling_price=Decimal(price),
                company_id=SORENTO,
            )
        )
    db.flush()
    return promo


def basin_combo(db, **combo_fields):
    """The standard fixture: host 1000, fixed mirror 200, Basin group of two (300, 400),
    one upgrade part at list 500. Returns a namespace-like dict."""
    host = product(db, "ZZCHOST", list_price="1000.00", tag_text="Host text")
    mirror = product(db, "ZZCMIR", list_price="200.00")
    white = product(db, "ZZCWH", list_price="300.00", tag_text="White basin")
    black = product(db, "ZZCBK", list_price="400.00")
    upgrade = product(db, "ZZCUP", list_price="500.00", tag_text="Stone basin")
    return host, mirror, white, black, upgrade


def resplit_per_combination(db, request):
    """Rebuild the one-tag-per-combination set a request IN FLIGHT already holds.

    AC-3.1 mints one tag for a combo line, but AC-3.4 keeps a split that marketing made
    by hand (or that was minted before this lane) untouched. Existing tests that pin
    per-candidate tag behaviour on a combo line start from that state: the line is
    submitted, then this puts back the tag per combination the old rule minted. The
    first tag keeps its id; the rest copy its quantity. A line with no open group, or one
    already split, is left alone.
    """
    from itertools import product as cartesian

    from app.models.price_tag import PriceTagRequestTag

    for line in request.lines:
        open_groups = [
            (part.role or "", list(part.candidates or []))
            for part in (line.parts or [])
            if not part.product_id and part.candidates
        ]
        if not open_groups or not line.combo_id:
            continue
        roles = [role for role, _ in open_groups]
        maps = [dict(zip(roles, combo)) for combo in cartesian(*[c for _, c in open_groups])]
        tags = sorted(line.tags, key=lambda t: (t.sort_order or 0, t.id))
        if len(tags) != 1 or tags[0].choices:
            continue  # already split per combination: nothing to rebuild
        tags[0].choices = maps[0]
        for index, choices in enumerate(maps[1:], start=1):
            db.add(
                PriceTagRequestTag(
                    line_id=line.id,
                    sort_order=index,
                    quantity=tags[0].quantity,
                    choices=choices,
                )
            )
    db.flush()
    db.expire(request, ["lines"])
    for line in request.lines:
        db.expire(line, ["tags"])
    return request
