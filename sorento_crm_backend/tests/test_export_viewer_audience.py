"""A PDF exported for dealers has to be the dealer's PDF.

`viewer_for` built a ViewerContext from the export request's `audience` but only
ever set `is_staff`, leaving `access_codes` empty. Access codes are the one knob
that decides whether a promotion applies to a reader (ADR 0008) and which
imagery they may see (`product_images._may_see`), so a request that said
"dealer" produced a document priced and illustrated for a consumer.

Nobody would notice from the export screen. They would notice when a dealer
opened the PDF they were sent and the trade price was not in it.

A second bug lived one layer down: `_AUDIENCE_ACCESS_CODES["dealer"]` was the
single hardcoded code `{"dealer"}`, but `contact_access_types` gates brands
per-tier-per-brand - CABANA carries `cabana_dealer`, MOCHA carries
`mocha_dealer`, and so on. A staff-requested "dealer" export with only the bare
code silently dropped every non-Sorento brand's tiles. `audience_access_codes`
resolves the dealer set from the table at call time instead: every ACTIVE code
that is exactly `dealer` or ends with `_dealer`.
"""

from __future__ import annotations

from app.services.dealer_kit.export_service import audience_access_codes, viewer_for
from tests._pg_fixture import pg_session

# What test cases below pass as `audience_codes` unless a test needs the real,
# database-backed mapping (the `TestTheMapMatchesTheRealAudiences` and
# `TestDealerAudienceSpansEveryBrandsDealerTier` classes).
_MAP = {
    "dealer": frozenset({"dealer"}),
    "consumer": frozenset({"end_user"}),
    "staff": frozenset(),
}


class _Request:
    """The fields of an ExportRequest that decide who is looking."""

    def __init__(self, audience: str, show_invoice_price: bool = False) -> None:
        self.audience = audience
        self.show_invoice_price = show_invoice_price


class TestTheAudienceDecidesTheOffer:
    def test_a_dealer_export_carries_the_dealer_code(self) -> None:
        viewer = viewer_for(_Request("dealer"), _MAP)

        assert "dealer" in viewer.access_codes
        assert viewer.is_staff is False

    def test_a_consumer_export_carries_the_consumer_code(self) -> None:
        # The audience is "consumer"; the access code it grants is "end_user".
        # That asymmetry is real and this map was keyed on the wrong one.
        viewer = viewer_for(_Request("consumer"), _MAP)

        assert "end_user" in viewer.access_codes
        assert "dealer" not in viewer.access_codes

    def test_a_consumer_export_cannot_reach_a_dealer_offer(self) -> None:
        # The failure this exists to prevent, stated as the rule rather than as
        # the mechanism: a document sent to a consumer must not carry trade
        # pricing, whatever the promotion says.
        viewer = viewer_for(_Request("consumer"), _MAP)

        assert viewer.access_codes.isdisjoint({"dealer"})


class TestStaff:
    def test_a_staff_export_may_show_the_invoice_price_when_asked(self) -> None:
        viewer = viewer_for(_Request("staff", show_invoice_price=True), _MAP)

        assert viewer.is_staff is True
        assert viewer.invoice_price_visible is True

    def test_the_invoice_price_still_needs_the_document_to_ask(self) -> None:
        # Two gates, ANDed. The entitlement alone is not permission.
        viewer = viewer_for(_Request("staff", show_invoice_price=False), _MAP)

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
        viewer = viewer_for(_Request("staff"), _MAP)

        assert viewer.is_internal_copy is True

    def test_a_dealer_or_consumer_export_is_not_an_internal_copy(self) -> None:
        # Those are documents FOR an audience and are gated like one.
        assert viewer_for(_Request("dealer"), _MAP).is_internal_copy is False
        assert viewer_for(_Request("consumer"), _MAP).is_internal_copy is False


class TestTheMapMatchesTheRealAudiences:
    def test_every_declared_audience_is_mapped(self) -> None:
        """No audience may fall through to the empty default by accident.

        This map was keyed on "end_user" while the declared audience is
        "consumer", so consumer exports matched nothing and only worked because
        empty codes fall back to the public code downstream. A silent fallback
        that happens to be right is the worst kind, so the mapping is asserted
        against the declared list rather than trusted.
        """
        from app.services.dealer_kit.export_service import AUDIENCES

        with pg_session() as db:
            assert set(audience_access_codes(db)) == set(AUDIENCES)


class TestDealerAudienceSpansEveryBrandsDealerTier:
    def test_dealer_codes_are_every_active_code_ending_in_dealer_not_just_the_bare_one(
        self,
    ) -> None:
        from app.models.access import ContactAccessType

        with pg_session() as db:
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

            codes = audience_access_codes(db)

            assert "zzt_dealer" in codes["dealer"]
            assert "zzt_cabana_dealer" in codes["dealer"]
            assert "zzt_nl_dealer" not in codes["dealer"]
            assert "zzt_office" not in codes["dealer"]
            assert codes["consumer"] == frozenset({"end_user"})
            assert codes["staff"] == frozenset()


class TestUnknownAudience:
    def test_an_unrecognised_audience_gets_nothing(self) -> None:
        # Fail closed. An audience nobody has taught this function about must not
        # default into the most generous reading.
        viewer = viewer_for(_Request("marketing-intern"), _MAP)

        assert viewer.access_codes == frozenset()
        assert viewer.is_staff is False
