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
        viewer = viewer_for(_Request("end_user"))

        assert "end_user" in viewer.access_codes
        assert "dealer" not in viewer.access_codes

    def test_a_consumer_export_cannot_reach_a_dealer_offer(self) -> None:
        # The failure this exists to prevent, stated as the rule rather than as
        # the mechanism: a document sent to a consumer must not carry trade
        # pricing, whatever the promotion says.
        viewer = viewer_for(_Request("end_user"))

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

    def test_staff_do_not_silently_inherit_a_trade_offer(self) -> None:
        """A staff export shows list prices unless it asks to be a dealer's copy.

        This follows the pricing decision that `is_staff` governs the invoice
        price and NOT a promotion's audience: seeing the trade price is what
        exporting AS a dealer is for. It is recorded as a test because it is a
        commercial choice somebody may want to revisit, not an accident, and the
        next person should find the argument rather than the behaviour alone.
        """
        viewer = viewer_for(_Request("staff"))

        assert viewer.access_codes.isdisjoint({"dealer"})


class TestUnknownAudience:
    def test_an_unrecognised_audience_gets_nothing(self) -> None:
        # Fail closed. An audience nobody has taught this function about must not
        # default into the most generous reading.
        viewer = viewer_for(_Request("marketing-intern"))

        assert viewer.access_codes == frozenset()
        assert viewer.is_staff is False
