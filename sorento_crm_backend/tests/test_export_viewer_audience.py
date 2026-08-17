"""A PDF exported for dealers has to be the dealer's PDF.

`viewer_for` built a ViewerContext from the export request's `audience` but only
ever set `is_staff`, leaving `access_codes` empty. Access codes are the one knob
that decides whether a promotion applies to a reader (ADR 0008) and which
imagery they may see (`product_images._may_see`), so a request that said
"dealer" produced a document priced and illustrated for a consumer.

Nobody would notice from the export screen. They would notice when a dealer
opened the PDF they were sent and the trade price was not in it.
"""

from __future__ import annotations

from app.services.dealer_kit.export_service import viewer_for


class _Request:
    """The fields of an ExportRequest that decide who is looking."""

    def __init__(self, audience: str, show_invoice_price: bool = False) -> None:
        self.audience = audience
        self.show_invoice_price = show_invoice_price


class TestTheAudienceDecidesTheOffer:
    def test_a_dealer_export_carries_the_dealer_code(self) -> None:
        viewer = viewer_for(_Request("dealer"))

        assert "dealer" in viewer.access_codes
        assert viewer.is_staff is False

    def test_a_consumer_export_carries_the_consumer_code(self) -> None:
        # The audience is "consumer"; the access code it grants is "end_user".
        # That asymmetry is real and this map was keyed on the wrong one.
        viewer = viewer_for(_Request("consumer"))

        assert "end_user" in viewer.access_codes
        assert "dealer" not in viewer.access_codes

    def test_a_consumer_export_cannot_reach_a_dealer_offer(self) -> None:
        # The failure this exists to prevent, stated as the rule rather than as
        # the mechanism: a document sent to a consumer must not carry trade
        # pricing, whatever the promotion says.
        viewer = viewer_for(_Request("consumer"))

        assert viewer.access_codes.isdisjoint({"dealer"})


class TestStaff:
    def test_a_staff_export_may_show_the_invoice_price_when_asked(self) -> None:
        viewer = viewer_for(_Request("staff", show_invoice_price=True))

        assert viewer.is_staff is True
        assert viewer.invoice_price_visible is True

    def test_the_invoice_price_still_needs_the_document_to_ask(self) -> None:
        # Two gates, ANDed. The entitlement alone is not permission.
        viewer = viewer_for(_Request("staff", show_invoice_price=False))

        assert viewer.is_staff is True
        assert viewer.invoice_price_visible is False

    def test_a_staff_export_is_an_internal_copy_of_the_brochure(self) -> None:
        """The office PDF shows what the brochure shows.

        It is a COPY of a published document, so dropping its offer prices would
        leave somebody printing it, reading a list price off it, and quoting a
        number that disagrees with the page the customer has open. Carried by its
        own flag rather than by access codes, because the question "is this the
        brochure" is not the question "which audience is this for".
        """
        viewer = viewer_for(_Request("staff"))

        assert viewer.is_internal_copy is True

    def test_a_dealer_or_consumer_export_is_not_an_internal_copy(self) -> None:
        # Those are documents FOR an audience and are gated like one.
        assert viewer_for(_Request("dealer")).is_internal_copy is False
        assert viewer_for(_Request("consumer")).is_internal_copy is False


class TestTheMapMatchesTheRealAudiences:
    def test_every_declared_audience_is_mapped(self) -> None:
        """No audience may fall through to the empty default by accident.

        This map was keyed on "end_user" while the declared audience is
        "consumer", so consumer exports matched nothing and only worked because
        empty codes fall back to the public code downstream. A silent fallback
        that happens to be right is the worst kind, so the mapping is asserted
        against the declared list rather than trusted.
        """
        from app.services.dealer_kit.export_service import (
            AUDIENCES,
            _AUDIENCE_ACCESS_CODES,
        )

        assert set(_AUDIENCE_ACCESS_CODES) == set(AUDIENCES)


class TestUnknownAudience:
    def test_an_unrecognised_audience_gets_nothing(self) -> None:
        # Fail closed. An audience nobody has taught this function about must not
        # default into the most generous reading.
        viewer = viewer_for(_Request("marketing-intern"))

        assert viewer.access_codes == frozenset()
        assert viewer.is_staff is False
