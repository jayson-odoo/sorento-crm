"""An internal copy of a brochure is the brochure, not a different document.

A PDF exported for the office is a copy of what was published. If it quietly
dropped the offer prices, somebody would print it, read a list price off it, and
quote a number that disagrees with the page the customer is looking at. That is
the failure: not a leak, a contradiction between two documents that are supposed
to be the same one.

So "this is an internal copy" is its OWN flag rather than a second meaning bolted
onto `is_staff`. `is_staff` decides the invoice price, which is a genuinely
internal figure a dealer must never read. Whether the offer prices are shown is a
different question with a different answer, and collapsing the two is exactly the
mistake the invoice-price gate is split in two to avoid.
"""

from __future__ import annotations

from app.services.dealer_kit.viewer import ANONYMOUS, ViewerContext


class TestTheFlagIsItsOwnConcept:
    def test_it_is_off_by_default(self) -> None:
        # Everything that reaches a customer must be a published view.
        assert ANONYMOUS.is_internal_copy is False
        assert ViewerContext().is_internal_copy is False

    def test_being_staff_does_not_make_a_view_an_internal_copy(self) -> None:
        # A staff member previewing the consumer page must still see the
        # consumer's page, or the preview lies about what is about to be sent.
        staff = ViewerContext(is_staff=True)

        assert staff.is_internal_copy is False

    def test_an_internal_copy_is_not_automatically_staff(self) -> None:
        # The invoice price stays behind its own gate. An internal copy shows the
        # brochure's prices, not the company's cost of goods.
        copy = ViewerContext(is_internal_copy=True)

        assert copy.may_see_invoice_price is False
        assert copy.invoice_price_visible is False

    def test_an_internal_copy_that_is_also_staff_still_needs_the_document_to_ask(
        self,
    ) -> None:
        both = ViewerContext(is_staff=True, is_internal_copy=True)

        assert both.invoice_price_visible is False
        assert ViewerContext(
            is_staff=True, is_internal_copy=True, show_invoice_price=True
        ).invoice_price_visible is True
