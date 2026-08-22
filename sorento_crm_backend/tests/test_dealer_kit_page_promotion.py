"""A brochure links to exactly ONE promotion, explicitly and optionally (D5).

A Sorento flyer IS a promotion in this system: ``promotions.description`` holds
the PDF's filename and audience variants are separate promotion rows. So the
page does not need a price of its own, it needs to say WHICH promotion prices
it. No link is not a broken page - it is list prices only, which is the defined
fallback (PLAN D6, ADR 0008 rule 5).

Postgres only, per the hard rule: ``schema="dealer_kit"`` models cannot be
created on sqlite at all, so a sqlite run here would prove nothing.

Every row this file creates is named with the reserved ``ZZT`` prefix and every
session is rolled back, because the local database holds real records. Nothing
here counts rows globally and nothing here deletes by anything other than the
ids it created.
"""
from __future__ import annotations

import os
import uuid

import pytest

from app.models.dealer_kit import Page
from app.models.marketing import Promotion
from app.services.dealer_kit import page_service as svc
from app.services.error_handler import AppException
from tests._pg_fixture import pg_session, unique_code

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

# The incumbent company. Set explicitly because the scope listeners that would
# stamp it are registered by app.main, which a service-level test never imports,
# and promotions.company_id is NOT NULL in the real database.
_SORENTO = "00000000-0000-0000-0000-000000000001"


def _page(db, slug_stem="promo-page") -> Page:
    slug = unique_code(slug_stem).lower()
    return svc.create_page(db, name=f"ZZT {slug}", slug=slug, user_id=None)


def _promotion(db, description: str | None = "A3 FLYER 2025-2026.pdf") -> Promotion:
    promo = Promotion(
        id=str(uuid.uuid4()),
        description=None if description is None else f"{unique_code('promo')} {description}",
        is_active=True,
        company_id=_SORENTO,
    )
    db.add(promo)
    db.flush()
    return promo


class TestLinkingAPromotion:
    def test_a_new_page_starts_with_no_promotion(self):
        with pg_session() as db:
            # Not a defect state: no link means list prices only, and a page
            # must never be forced to claim an offer it does not have.
            assert _page(db).promotion_id is None

    def test_setting_the_link_persists(self):
        with pg_session() as db:
            page, promo = _page(db), _promotion(db)

            svc.set_promotion(db, page.id, promo.id)

            stored = db.query(Page).filter(Page.id == page.id).one()
            assert stored.promotion_id == promo.id

    def test_clearing_the_link_leaves_the_promotion_alone(self):
        with pg_session() as db:
            page, promo = _page(db), _promotion(db)
            svc.set_promotion(db, page.id, promo.id)

            svc.set_promotion(db, page.id, None)

            assert db.query(Page).filter(Page.id == page.id).one().promotion_id is None
            # Unlinking a brochure is an editorial decision about the brochure.
            # It must never reach into marketing's data.
            assert db.query(Promotion).filter(Promotion.id == promo.id).count() == 1

    def test_an_unknown_promotion_is_404_and_changes_nothing(self):
        with pg_session() as db:
            page, promo = _page(db), _promotion(db)
            svc.set_promotion(db, page.id, promo.id)

            with pytest.raises(AppException) as err:
                svc.set_promotion(db, page.id, str(uuid.uuid4()))
            assert err.value.status_code == 404

            # A rejected write must not have wiped the link it was replacing.
            assert db.query(Page).filter(Page.id == page.id).one().promotion_id == promo.id

    def test_an_unknown_page_is_404(self):
        with pg_session() as db:
            promo = _promotion(db)
            with pytest.raises(AppException) as err:
                svc.set_promotion(db, str(uuid.uuid4()), promo.id)
            assert err.value.status_code == 404

    def test_a_page_can_be_created_already_linked(self):
        with pg_session() as db:
            promo = _promotion(db)
            slug = unique_code("seeded").lower()

            page = svc.create_page(
                db, name=f"ZZT {slug}", slug=slug, user_id=None, promotion_id=promo.id
            )

            # The seed suggests the promotion whose description matches the
            # uploaded filename, so create has to be able to carry it.
            assert page.promotion_id == promo.id

    def test_creating_against_an_unknown_promotion_is_404(self):
        with pg_session() as db:
            slug = unique_code("bad-link").lower()
            with pytest.raises(AppException) as err:
                svc.create_page(
                    db, name=f"ZZT {slug}", slug=slug, user_id=None,
                    promotion_id=str(uuid.uuid4()),
                )
            assert err.value.status_code == 404


class TestPromotionDeletion:
    def test_deleting_the_promotion_unlinks_the_page_rather_than_removing_it(self):
        with pg_session() as db:
            page, promo = _page(db), _promotion(db)
            svc.set_promotion(db, page.id, promo.id)
            page_id, promo_id = page.id, promo.id

            db.query(Promotion).filter(Promotion.id == promo_id).delete()
            db.flush()
            db.expire_all()

            # ON DELETE SET NULL, deliberately. CASCADE would let marketing
            # delete a promotion and take a published catalogue down with it;
            # RESTRICT would let one brochure freeze marketing's own data.
            # Falling back to list prices is the one outcome nobody has to
            # discover from a customer.
            survivor = db.query(Page).filter(Page.id == page_id).one()
            assert survivor.promotion_id is None


class TestPromotionLabels:
    def test_a_label_is_resolved_for_the_screen(self):
        with pg_session() as db:
            promo = _promotion(db)
            labels = svc.promotion_labels(db, [promo.id])
            assert labels[promo.id] == promo.description

    def test_a_promotion_with_no_description_resolves_to_nothing_rather_than_an_id(self):
        with pg_session() as db:
            promo = _promotion(db, description=None)
            # None, never the uuid: the id must not reach a screen even as a
            # last-resort label.
            assert svc.promotion_labels(db, [promo.id]).get(promo.id) is None

    def test_listing_reports_the_link_and_its_label(self):
        with pg_session() as db:
            page, promo = _page(db), _promotion(db)
            svc.set_promotion(db, page.id, promo.id)

            row = next(r for r in svc.list_pages(db) if r["id"] == page.id)
            assert row["promotion_id"] == promo.id
            assert row["promotion_label"] == promo.description
