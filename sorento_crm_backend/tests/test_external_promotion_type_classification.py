"""n8n's promotion create classifies the type from the file name (UAC C1, C5).

Calls the external route function directly against a blank schema, so the
classification is exercised through the same code path n8n hits.
"""
from __future__ import annotations

import uuid

import pytest

from app.api.v1.external.promotions import create_promotion
from app.models.marketing import Promotion, PromotionType
from app.schemas.external.marketing import PromotionRequest
from tests._pg_fixture import blank_session


TYPES = [
    ("special", ["special"], 10, False, False),
    ("pp", ["pp"], 20, True, False),
    ("a3_flyer", ["a3", "a3 flyer"], 40, True, False),
    ("standard", [], 99, True, True),
]


def _seed_types(db):
    for code, markers, priority, show_expired, is_default in TYPES:
        db.add(
            PromotionType(
                type_code=code,
                type_name=code.replace("_", " ").title(),
                match_markers=markers,
                match_priority=priority,
                show_expired=show_expired,
                is_default=is_default,
            )
        )
    db.flush()


def _payload(description: str) -> PromotionRequest:
    return PromotionRequest.model_validate(
        {
            "promotions": {
                "description": description,
                "start_date": "2026-07-01",
                # Still open: the route refuses to update a promotion past its
                # end date, and these cases exercise the re-send path.
                "end_date": "2099-12-31",
            },
            # A code that does not exist: the route warns and still creates the
            # promotion, which keeps this test about classification only.
            "promotion_products": [{"product_code": "ZZT-NO-SUCH-SKU", "selling_price": 10}],
        }
    )


def _user():
    return {"id": str(uuid.uuid4()), "auth_method": "api_key"}


@pytest.mark.parametrize(
    "description, expected",
    [
        ("SORENTO SPECIAL PROMO_22052026 DEALER.pdf", "special"),
        ("SORENTO PP PROMO COMBINE_08072026.pdf", "pp"),
        ("_SORENTO A3 FLYER 2025-2026_compressed", "a3_flyer"),
        ("CABANA SHELF PROMO 31032026 (DEALER USE)", "standard"),
    ],
)
def test_create_classifies_from_the_description(description, expected):  # C1, C2
    with blank_session() as db:
        _seed_types(db)
        response = create_promotion(_payload(description), current_user=_user(), db=db)

        assert response.promotion.promotion_type_code == expected
        assert response.promotion.promotion_type_source == "auto"


def test_resend_reclassifies_an_auto_row():  # C5 (auto half)
    with blank_session() as db:
        _seed_types(db)
        create_promotion(_payload("CABANA SHELF PROMO 31032026"), current_user=_user(), db=db)
        # Same file name, re-sent after marketing renamed it a special.
        response = create_promotion(
            _payload("CABANA SHELF PROMO 31032026"), current_user=_user(), db=db
        )
        assert response.already_existed is True

        promo = db.query(Promotion).one()
        promo.description = "CABANA SPECIAL SHELF PROMO 31032026"
        db.flush()
        response = create_promotion(
            _payload("CABANA SPECIAL SHELF PROMO 31032026"), current_user=_user(), db=db
        )
        assert response.promotion.promotion_type_code == "special"


def test_resend_never_overwrites_a_manual_classification():  # C5
    with blank_session() as db:
        _seed_types(db)
        create_promotion(_payload("CABANA SPECIAL SHELF PROMO"), current_user=_user(), db=db)

        promo = db.query(Promotion).one()
        standard = db.query(PromotionType).filter(PromotionType.type_code == "standard").one()
        promo.promotion_type_id = standard.id
        promo.promotion_type_source = "manual"
        db.commit()

        response = create_promotion(
            _payload("CABANA SPECIAL SHELF PROMO"), current_user=_user(), db=db
        )

        assert response.already_existed is True
        assert response.promotion.promotion_type_code == "standard"
        assert response.promotion.promotion_type_source == "manual"
