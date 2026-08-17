"""A PDF exported for dealers has to be the dealer's PDF.

`viewer_for` built a ViewerContext from the export request's `audience` but only
ever set `is_staff`, leaving `access_codes` empty. Access codes are the one knob
that decides whether a promotion applies to a reader (ADR 0008) and which
imagery they may see (`product_images._may_see`), so a request that said
"dealer" produced a document priced and illustrated for a consumer.

Nobody would notice from the export screen. They would notice when a dealer
opened the PDF they were sent and the trade price was not in it.

A second bug lived one layer down: the dealer audience was the single hardcoded
code `{"dealer"}`, but `contact_access_types` gates brands per-tier-per-brand -
CABANA carries `cabana_dealer`, MOCHA carries `mocha_dealer`. A staff-requested
"dealer" export with only the bare code silently dropped every non-Sorento
brand's tiles.
"""

from __future__ import annotations

import pytest

from app.models.access import ContactAccessType
from app.services.dealer_kit.export_service import viewer_for
from tests._pg_fixture import pg_session


@pytest.fixture
def db():
    with pg_session() as session:
        yield session


class _Request:
    """The fields of an ExportRequest that decide who is looking."""

    def __init__(self, audience: str, show_invoice_price: bool = False) -> None:
        self.audience = audience
        self.show_invoice_price = show_invoice_price


def _seed_access_types(db) -> None:
    db.add_all(
        [
            ContactAccessType(code="zzt_dealer", name="ZZT generic dealer", is_active=True),
            ContactAccessType(
                code="zzt_cabana_dealer", name="ZZT brand-tier dealer", is_active=True
            ),
            ContactAccessType(
                code="zzt_nl_dealer", name="ZZT retired dealer tier", is_active=False
            ),
            ContactAccessType(code="zzt_office", name="ZZT non-dealer type", is_active=True),
        ]
    )
    db.flush()


class TestTheAudienceDecidesTheOffer:
    def test_a_dealer_export_carries_every_active_dealer_tier(self, db) -> None:
        # Not just the bare `dealer` code, which means the SORENTO dealer: a
        # brand gated on its own dealer tier would otherwise lose every tile.
        _seed_access_types(db)

        viewer = viewer_for(db, _Request("dealer"))

        assert "zzt_dealer" in viewer.access_codes
        assert "zzt_cabana_dealer" in viewer.access_codes
        assert "zzt_nl_dealer" not in viewer.access_codes  # retired tier
        assert "zzt_office" not in viewer.access_codes  # not a dealer tier
        assert viewer.is_staff is False

    def test_a_consumer_export_carries_the_consumer_code(self, db) -> None:
        # The audience is "consumer"; the access code it grants is "end_user".
        # That asymmetry is real and this was once keyed on the wrong one.
        _seed_access_types(db)

        viewer = viewer_for(db, _Request("consumer"))

        assert viewer.access_codes == frozenset({"end_user"})

    def test_a_consumer_export_cannot_reach_a_dealer_offer(self, db) -> None:
        # The failure this exists to prevent, stated as the rule rather than as
        # the mechanism: a document sent to a consumer must not carry trade
        # pricing, whatever the promotion says.
        _seed_access_types(db)

        viewer = viewer_for(db, _Request("consumer"))

        assert viewer.access_codes.isdisjoint({"zzt_dealer", "zzt_cabana_dealer", "dealer"})


class TestStaff:
    def test_a_staff_export_may_show_the_invoice_price_when_asked(self, db) -> None:
        viewer = viewer_for(db, _Request("staff", show_invoice_price=True))

        assert viewer.is_staff is True
        assert viewer.invoice_price_visible is True

    def test_the_invoice_price_still_needs_the_document_to_ask(self, db) -> None:
        # Two gates, ANDed. The entitlement alone is not permission.
        viewer = viewer_for(db, _Request("staff", show_invoice_price=False))

        assert viewer.is_staff is True
        assert viewer.invoice_price_visible is False

    def test_a_staff_export_is_an_internal_copy_of_the_brochure(self, db) -> None:
        """The office PDF shows what the brochure shows.

        It is a COPY of a published document, so dropping its offer prices would
        leave somebody printing it, reading a list price off it, and quoting a
        number that disagrees with the page the customer has open. Carried by its
        own flag rather than by access codes, because the question "is this the
        brochure" is not the question "which audience is this for".
        """
        viewer = viewer_for(db, _Request("staff"))

        assert viewer.is_internal_copy is True

    def test_a_dealer_or_consumer_export_is_not_an_internal_copy(self, db) -> None:
        # Those are documents FOR an audience and are gated like one.
        assert viewer_for(db, _Request("dealer")).is_internal_copy is False
        assert viewer_for(db, _Request("consumer")).is_internal_copy is False


class TestUnknownAudience:
    def test_an_unrecognised_audience_gets_nothing(self, db) -> None:
        # Fail closed. An audience nobody has taught this function about must not
        # default into the most generous reading.
        viewer = viewer_for(db, _Request("marketing-intern"))

        assert viewer.access_codes == frozenset()
        assert viewer.is_staff is False
