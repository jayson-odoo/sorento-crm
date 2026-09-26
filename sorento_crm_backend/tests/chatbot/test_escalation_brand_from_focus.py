"""#865: escalation resolves the brand from the product the conversation is about.

Owner ruling 27 Sep 2026 ("yeah go for escalation"), fix option 1 of the root-cause report
on #865 ("Root cause: null brand on escalation after a spec answer (backup of 25 Sep)").

The defect, measured on the 25 Sep backup: contact 503641482, 24 Sep 2026 09:16 MYT.
Turn 1 asked for the stainless steel grade of SRTKS8650A (a SORENTO product) and was
answered with the product card; turn 2 said "Please esculate to Marketing". The
escalation reached `/external/next-assignee` with `brand_code: null`, drew from the
un-narrowed cursor, and assigned the mocha-only member of Marketing Product. The brand
had been computed on turn 1 and dropped at the end of it: the five-key session holds the
product, not its brand, and nothing re-read it. It survived only when turn 1 happened to
mint an offer that stamped it (#1108's `carried_brand`), i.e. only when the product turn
FAILED.

The fix reads the brand off the product row at the point of use: this turn's named
product, else the product in focus. The focus rules already drop that product on a topic
reset or a newer product, so nothing here decides when the carry ends.

Every test drives the REAL engine (`engine.run_turn`) with the parser stubbed to the
recorded verdicts, over a freshly seeded roster shaped like prod (Marketing Product: Kia
Yee = mocha, Tay Zhi Yang = sorento, cabana; Packing List: Lucas = mocha, Jereen =
sorento, cabana), and the REAL `/external/next-assignee` handler draws the assignee.
Postgres only (`tests/chatbot/conftest.py`'s blank-schema `session_factory`).
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text

from app.services.chatbot import engine as engine_mod
from app.services.chatbot.contracts import SessionVars

from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_engine import CONTACT_ID, _envelope, stub_access, stub_parser  # noqa: F401
from tests.chatbot.test_escalation_agent_carry import (
    _capture_real_next_assignee,
    _capture_sla,
    _second_turn_envelope,
    _seed_contact,
    _seed_escalation_team,
    _seed_packing_list_team,
    _db,
    _seed_product_with_brand,
    _yes_verdict,
)

pytestmark = pytest.mark.usefixtures("_no_real_mcp_calls", "_stub_casual_llm")

MASTER_PRODUCTS_TOOL = "crm_master_products_list"


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def _seed_marketing_product_team(session_factory) -> dict[str, str]:
    """Marketing Product tier 1 as the backup holds it: two round-robin members, Kia Yee
    tagged only `mocha` (sort order 1, so a whole-team draw on a fresh cursor lands on
    her) and Tay Zhi Yang tagged `sorento` and `cabana`."""
    return _seed_escalation_team(
        session_factory,
        agent_code="general_enquiries",
        team_code="marketing_product",
        team_label="Marketing - Product",
        members=[("Kia Yee", ["mocha"]), ("Tay Zhi Yang", ["sorento", "cabana"])],
    )


def _stub_product_card(monkeypatch) -> None:
    """Turn 1's recorded tool answer: the master products tool returns the product card
    for whatever ids it was asked about (a clean HIT, so turn 1 mints no question). Every
    other probe, incoming included, answers nothing."""
    from app.services.ai_assistant_service import MCPRuntimeClient

    def fake_call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        if name == MASTER_PRODUCTS_TOOL:
            return json.dumps(
                {
                    "items": [
                        {
                            "title": "ZZT SORENTO S/STEEL SINK",
                            "fields": [
                                {"key": "product_code", "label": "Product Code", "value": "ZZT"},
                                {"key": "material", "label": "Material", "value": "stainless_steel"},
                            ],
                            "flags": {"discontinued": True},
                        }
                    ],
                    "has_result": True,
                    "attachments": [],
                    "action_links": [],
                }
            )
        return json.dumps({"answers": [], "items": [], "has_result": False})

    monkeypatch.setattr(MCPRuntimeClient, "call_tool", fake_call_tool)


def _spec_verdict(code: str) -> dict[str, Any]:
    """Turn 1 of the 24 Sep conversation, as parsed: a master_products business query
    naming one product, routed to purchasing (the domain's escalation team)."""
    return verdict(
        message_type="business_query",
        domain_hint="master_products",
        intent_hint="check_product",
        entities=[entity(code, hint="product", confident=True)],
        routing={"suggested_team": "purchasing", "suggested_agent": "purchasing"},
    )


def _escalate_to_marketing_verdict(**overrides: Any) -> dict[str, Any]:
    """Turn 2 of the 24 Sep conversation, as parsed: "Please esculate to Marketing". A help
    request naming the team, no entities, no brand word, no confirmation."""
    base = verdict(
        message_type="request_for_help",
        domain_hint=None,
        intent_hint=None,
        entities=[],
        routing={"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
    )
    base.update(overrides)
    return base


def _envelope_for(message_id: str, text_: str) -> Any:
    return _second_turn_envelope(message_id=message_id, text=text_)


def _session_vars(session_factory) -> dict[str, Any]:
    db = session_factory()
    try:
        row = db.execute(
            text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
            {"c": str(CONTACT_ID)},
        ).first()
        return dict(row[0] or {}) if row else {}
    finally:
        db.close()


def _looked_up_routing(session_factory, turn_id: str) -> dict[str, Any] | None:
    from app.models.chatbot_turn import ChatbotTurn

    db = session_factory()
    try:
        row = db.query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()
        records = list(row.trace or []) if row is not None else []
    finally:
        db.close()
    looked_up = [r for r in records if r.get("stage") == "looked_up"]
    assert looked_up, records
    return (looked_up[-1].get("facts") or {}).get("routing")


def _run_spec_hit(session_factory, monkeypatch, stub_parser, stub_access, *, phone: str, code: str):
    _seed_contact(session_factory, phone=phone)
    _stub_product_card(monkeypatch)
    stub_access()
    stub_parser(_spec_verdict(code))
    turn1 = engine_mod.run_turn(_envelope(), session_factory=session_factory)
    assert turn1.branch_kind == "business_query", turn1.branch_kind
    return turn1


# --------------------------------------------------------------------------- #
# 1. The 24 Sep replay: spec answered, then "escalate to marketing". RED on main.
# --------------------------------------------------------------------------- #


class TestReplay24SepSpecHitThenEscalate:
    def test_24sep_replay_spec_hit_then_escalate_to_marketing_draws_the_sorento_member(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_product_with_brand(session_factory, code="SRTKS8650A", brand_code="SORENTO")
        _seed_marketing_product_team(session_factory)
        _run_spec_hit(
            session_factory, monkeypatch, stub_parser, stub_access, phone="+60000865001", code="SRTKS8650A"
        )
        # Turn 1 minted nothing (a clean HIT asks nothing), exactly as recorded.
        assert _session_vars(session_factory).get("open_question") is None

        stub_parser(_escalate_to_marketing_verdict())
        calls = _capture_real_next_assignee(monkeypatch)
        _capture_sla(monkeypatch)
        turn2 = engine_mod.run_turn(
            _envelope_for("ZZT-msg-865-2", "Please esculate to Marketing"),
            session_factory=session_factory,
        )

        assert turn2.branch_kind == "out_of_scope", turn2.branch_kind
        assert len(calls) == 1, calls
        body, response = calls[0]["body"], calls[0]["response"]
        assert body["team_code"] == "marketing_product", body
        assert body["brand_code"] == "sorento", (
            f"the escalation is about SRTKS8650A, a SORENTO product; the brand must reach "
            f"next-assignee (24 Sep: it arrived null): {body!r}"
        )
        assert response.get("assignee_name") == "ZZT Tay Zhi Yang", (
            f"a SORENTO product escalated to marketing must draw the sorento-tagged member, "
            f"not the mocha one on the whole-team cursor: {response!r}"
        )
        assert response.get("brand_matched") is True, response

    def test_24sep_replay_the_trace_records_the_next_assignee_body_and_cursor_key(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_product_with_brand(session_factory, code="SRTKS8650A", brand_code="SORENTO")
        _seed_marketing_product_team(session_factory)
        _run_spec_hit(
            session_factory, monkeypatch, stub_parser, stub_access, phone="+60000865002", code="SRTKS8650A"
        )

        stub_parser(_escalate_to_marketing_verdict())
        _capture_real_next_assignee(monkeypatch)
        _capture_sla(monkeypatch)
        turn2 = engine_mod.run_turn(
            _envelope_for("ZZT-msg-865-2", "Please esculate to Marketing"),
            session_factory=session_factory,
        )

        routing = _looked_up_routing(session_factory, turn2.turn_id)
        assert routing is not None, "the escalation trace must record the next-assignee routing"
        assert routing["team_code"] == "marketing_product", routing
        assert routing["brand_code"] == "sorento", routing
        assert routing["routing_source"] == "focus_product", routing
        # The brand-narrowed pool keeps its own cursor (`user_service.brand_pool_key`).
        assert routing["cursor_key"] == "~b:sorento", routing
        assert routing["assignee_name"] == "ZZT Tay Zhi Yang", routing


# --------------------------------------------------------------------------- #
# 2. The proven path still holds: an offer accepted with a stamped brand.
# --------------------------------------------------------------------------- #


class TestProvenPathOfferAcceptedWithStampedBrand:
    def test_photo_miss_offer_accepted_with_a_stamped_brand_still_draws_the_brand_member(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        """Contact 445239384, 24 Sep 16:25 MYT: a spec/photo MISS minted "escalate to
        marketing product?", its `team_pick` stamped `brand_code: sorento`, and "Yes"
        drew Tay Zhi Yang. It must keep doing so, and the payload still carries the brand
        the offer turn resolved."""
        from tests.chatbot.test_escalation_agent_carry import _stub_incoming_probe_empty
        from tests.chatbot.test_product_attachment_picker_stamp import _seed_attachment_type

        _seed_contact(session_factory, phone="+60000865003")
        _seed_product_with_brand(session_factory, code="SRTUB6503", brand_code="sorento")
        _seed_attachment_type(session_factory, "Product Photos")
        _seed_marketing_product_team(session_factory)
        _stub_incoming_probe_empty(monkeypatch)
        stub_access()
        stub_parser(
            verdict(
                domain_hint="product_attachment",
                intent_hint="check_product_attachment",
                entities=[
                    entity("SRTUB6503", hint="product", confident=True),
                    entity("product photos", hint="attachment_type", canonical_code="photo", confident=True),
                ],
                routing={"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"},
            )
        )
        turn1 = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert turn1.branch_kind == "business_query", turn1.branch_kind
        offer = _session_vars(session_factory).get("open_question") or {}
        assert offer.get("kind") == "team_pick", offer
        assert (offer.get("payload") or {}).get("brand_code") == "sorento", offer

        stub_parser(_yes_verdict())
        calls = _capture_real_next_assignee(monkeypatch)
        _capture_sla(monkeypatch)
        turn2 = engine_mod.run_turn(_second_turn_envelope(), session_factory=session_factory)

        assert turn2.branch_kind == "out_of_scope", turn2.branch_kind
        assert len(calls) == 1, calls
        assert calls[0]["body"]["brand_code"] == "sorento", calls[0]["body"]
        assert calls[0]["response"].get("assignee_name") == "ZZT Tay Zhi Yang", calls[0]["response"]


# --------------------------------------------------------------------------- #
# 3. The sibling: "eta" after a product turn. RED on main.
# --------------------------------------------------------------------------- #


def _seed_settled_focus(session_factory, monkeypatch, stub_access, *, phone: str) -> None:
    """The session a product turn leaves when its product is SETTLED (the focus entry
    carries the row `uuid`): SRTKS7646, a SORENTO product, over the Packing List roster.
    Seeded directly, the pattern `test_escalation_agent_carry.py` uses for turn 1."""
    from app.models.product import Product

    from tests.chatbot.test_escalation_agent_carry import _stub_incoming_probe_empty

    _seed_contact(session_factory, phone=phone)
    _seed_product_with_brand(session_factory, code="SRTKS7646", brand_code="SORENTO")
    _seed_packing_list_team(session_factory)
    _stub_incoming_probe_empty(monkeypatch)
    stub_access()
    db = _db(session_factory)
    product_id = db.query(Product.id).filter(Product.product_code == "SRTKS7646").scalar()
    db.execute(
        text("UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) WHERE respond_io_id = :c"),
        {
            "sv": json.dumps(
                {
                    "focus": {
                        "products": [
                            {
                                "raw": "SRTKS7646",
                                "hint": "product",
                                "canonical_code": "SRTKS7646",
                                "uuid": product_id,
                                "current_message": False,
                            }
                        ],
                        "domains": ["master_products"],
                    },
                    "open_question": None,
                    "ideation": None,
                    "access_levels": [],
                    "contains_flyer": False,
                }
            ),
            "c": str(CONTACT_ID),
        },
    )
    db.commit()


class TestSiblingEtaAfterAProductTurn:
    def _eta_then_yes(self, session_factory, stub_parser, monkeypatch) -> tuple[dict[str, Any], list]:
        stub_parser(
            verdict(
                domain_hint="incoming",
                intent_hint="check_incoming",
                entities=[],
                routing={"suggested_team": "purchasing", "suggested_agent": "incoming_stock_enquiries"},
            )
        )
        eta = engine_mod.run_turn(_envelope_for("ZZT-msg-865-eta", "eta"), session_factory=session_factory)
        assert eta.branch_kind == "business_query", eta.branch_kind
        offer = _session_vars(session_factory).get("open_question") or {}

        stub_parser(_yes_verdict())
        calls = _capture_real_next_assignee(monkeypatch)
        _capture_sla(monkeypatch)
        yes = engine_mod.run_turn(_envelope_for("ZZT-msg-865-yes", "yes"), session_factory=session_factory)
        assert yes.branch_kind == "out_of_scope", yes.branch_kind
        return offer, calls

    def test_eta_after_a_settled_product_mints_the_offer_with_the_focus_products_brand(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        """Contact 477071889, 23 Sep 13:03 MYT: "SRTKS7646" answered (SORENTO), then "eta"
        named no product; the incoming lane used the focus product, missed, and offered
        purchasing with `payload.brand_code: null`, because the gate's brand comes only
        from rows resolved on THAT turn and a SETTLED focus product (one carrying its row
        `uuid`) is never re-resolved (`with_carried_entities(unsettled_only=True)`). "Yes"
        then drew the mocha-only Packing List member. The focus is seeded as the product
        turn left it, the pattern `test_escalation_agent_carry.py` uses for turn 1."""
        _seed_settled_focus(session_factory, monkeypatch, stub_access, phone="+60000865004")

        offer, calls = self._eta_then_yes(session_factory, stub_parser, monkeypatch)

        assert offer.get("kind") == "team_pick", offer
        assert (offer.get("payload") or {}).get("brand_code") == "sorento", (
            f"the offer minted on the 'eta' turn must carry the focus product's brand: {offer!r}"
        )
        assert len(calls) == 1, calls
        assert calls[0]["body"]["team_code"] == "purchasing", calls[0]["body"]
        assert calls[0]["body"]["brand_code"] == "sorento", calls[0]["body"]
        assert calls[0]["response"].get("assignee_name") == "ZZT Jereen", calls[0]["response"]

    def test_a_fanned_out_miss_after_a_settled_product_stamps_every_team_option_with_its_brand(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        """The `_team_pick_question` mint site (`turn/compose.py`): "stock and eta?" after
        the same settled product fans out to two domains, both miss, and the multi-team
        pick is minted by compose rather than the bridge. No resolver runs on this turn,
        so its brand comes from the focus product (`TurnContext.routing_brand`)."""
        _seed_settled_focus(session_factory, monkeypatch, stub_access, phone="+60000865009")
        stub_parser(
            verdict(
                asks=[{"domain": "inventory"}, {"domain": "incoming"}],
                domain_hint=None,
                intent_hint=None,
                entities=[],
                routing={"suggested_team": "purchasing", "suggested_agent": "incoming_stock_enquiries"},
            )
        )
        turn = engine_mod.run_turn(
            _envelope_for("ZZT-msg-865-fan", "stock and eta?"), session_factory=session_factory
        )
        assert turn.branch_kind == "business_query", turn.branch_kind

        question = _session_vars(session_factory).get("open_question") or {}
        assert question.get("kind") == "team_pick", question
        stamped = [
            (o.get("payload") or {}).get("brand_code")
            for o in question.get("options") or []
            if not (o.get("payload") or {}).get("hold")
        ]
        if not stamped:  # a single missed team is yes/no, stamped on the top-level payload
            stamped = [(question.get("payload") or {}).get("brand_code")]
        assert stamped and all(b == "sorento" for b in stamped), (
            f"every team option compose mints must carry the focus product's brand: {question!r}"
        )

    def test_eta_after_a_typed_product_hit_keeps_carrying_the_brand(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        """The same journey with turn 1 run for real: today's focus keeps the typed code
        unsettled, the resolver re-resolves it on "eta" and the gate already carries the
        brand. A guard that the focus fill does not disturb that path."""
        from tests.chatbot.test_escalation_agent_carry import _stub_incoming_probe_empty

        _seed_product_with_brand(session_factory, code="SRTKS7646", brand_code="SORENTO")
        _seed_packing_list_team(session_factory)
        _run_spec_hit(
            session_factory, monkeypatch, stub_parser, stub_access, phone="+60000865008", code="SRTKS7646"
        )
        _stub_incoming_probe_empty(monkeypatch)

        offer, calls = self._eta_then_yes(session_factory, stub_parser, monkeypatch)

        assert (offer.get("payload") or {}).get("brand_code") == "sorento", offer
        assert calls[0]["body"]["brand_code"] == "sorento", calls[0]["body"]
        assert calls[0]["response"].get("assignee_name") == "ZZT Jereen", calls[0]["response"]


# --------------------------------------------------------------------------- #
# 4. When the carry ends: a topic reset, or a newer product.
# --------------------------------------------------------------------------- #


class TestTheCarryEndsOnATopicResetOrANewerProduct:
    def test_a_topic_reset_escalation_carries_no_brand(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_product_with_brand(session_factory, code="SRTKS8650A", brand_code="SORENTO")
        _seed_marketing_product_team(session_factory)
        _run_spec_hit(
            session_factory, monkeypatch, stub_parser, stub_access, phone="+60000865005", code="SRTKS8650A"
        )

        stub_parser(_escalate_to_marketing_verdict(topic_reset=True))
        calls = _capture_real_next_assignee(monkeypatch)
        _capture_sla(monkeypatch)
        turn2 = engine_mod.run_turn(
            _envelope_for("ZZT-msg-865-2", "different thing, escalate to marketing"),
            session_factory=session_factory,
        )

        assert turn2.branch_kind == "out_of_scope", turn2.branch_kind
        assert len(calls) == 1, calls
        assert calls[0]["body"]["brand_code"] is None, (
            f"a topic reset ends the conversation about SRTKS8650A; its brand must not "
            f"leak into the new topic's escalation: {calls[0]['body']!r}"
        )
        routing = _looked_up_routing(session_factory, turn2.turn_id)
        assert routing["routing_source"] == "none", routing

    def test_a_newer_product_replaces_the_focus_and_its_brand_is_the_one_drawn(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        """A second product turn about a MOCHA code replaces the SORENTO one in focus, so
        "escalate to marketing" after it draws the mocha member. (A help request that names
        its own product is retyped to a business query by the head today, #866's D1, which
        this lane does not take on; the newer product is therefore named on its own turn.)"""
        _seed_product_with_brand(session_factory, code="SRTKS8650A", brand_code="SORENTO")
        _seed_product_with_brand(session_factory, code="MWC7625", brand_code="MOCHA")
        _seed_marketing_product_team(session_factory)
        _run_spec_hit(
            session_factory, monkeypatch, stub_parser, stub_access, phone="+60000865006", code="SRTKS8650A"
        )
        stub_parser(_spec_verdict("MWC7625"))
        newer = engine_mod.run_turn(
            _envelope_for("ZZT-msg-865-newer", "and MWC7625?"), session_factory=session_factory
        )
        assert newer.branch_kind == "business_query", newer.branch_kind

        stub_parser(_escalate_to_marketing_verdict())
        calls = _capture_real_next_assignee(monkeypatch)
        _capture_sla(monkeypatch)
        turn3 = engine_mod.run_turn(
            _envelope_for("ZZT-msg-865-3", "Please esculate to Marketing"),
            session_factory=session_factory,
        )

        assert turn3.branch_kind == "out_of_scope", turn3.branch_kind
        assert len(calls) == 1, calls
        assert calls[0]["body"]["brand_code"] == "mocha", calls[0]["body"]
        assert calls[0]["response"].get("assignee_name") == "ZZT Kia Yee", calls[0]["response"]


class TestAStatedBrandOutranksTheFocusProduct:
    def test_a_mocha_catalogue_escalation_after_a_sorento_spec_answer_draws_the_mocha_member(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        """Round 2, S1 (reviewer pass at df577453): turn 1 answers a SORENTO spec, turn 2
        says "I need the Mocha catalogue, escalate to marketing" (`query_brands: ["mocha"]`,
        no entities). The customer's explicit brand on THIS turn is the `stated_brand` rung,
        which works on main; the product carried from turn 1 must not outrank it."""
        _seed_product_with_brand(session_factory, code="SRTKS8650A", brand_code="SORENTO")
        _seed_marketing_product_team(session_factory)
        _run_spec_hit(
            session_factory, monkeypatch, stub_parser, stub_access, phone="+60000865010", code="SRTKS8650A"
        )

        stub_parser(_escalate_to_marketing_verdict(query_brands=["mocha"]))
        calls = _capture_real_next_assignee(monkeypatch)
        _capture_sla(monkeypatch)
        turn2 = engine_mod.run_turn(
            _envelope_for("ZZT-msg-865-mocha", "I need the Mocha catalogue, escalate to marketing"),
            session_factory=session_factory,
        )

        assert turn2.branch_kind == "out_of_scope", turn2.branch_kind
        assert len(calls) == 1, calls
        assert calls[0]["body"]["brand_code"] == "mocha", (
            f"the customer named Mocha on this turn; a SORENTO product carried from the "
            f"previous turn must not outrank it: {calls[0]['body']!r}"
        )
        assert calls[0]["response"].get("assignee_name") == "ZZT Kia Yee", calls[0]["response"]
        routing = _looked_up_routing(session_factory, turn2.turn_id)
        assert routing["routing_source"] == "stated_brand", routing


class TestTheDryRunPreviewsTheSameBrand:
    def test_24sep_replay_as_a_console_dry_run_previews_the_sorento_member(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        """Round 2, S2 (kill test K9 at df577453): the console runs dry (`is_test`), and
        `_preview_routing` must apply the same focus-brand rung as the live draw, or the
        preview the owner checks drifts from the draw it previews."""
        _seed_product_with_brand(session_factory, code="SRTKS8650A", brand_code="SORENTO")
        _seed_marketing_product_team(session_factory)
        _run_spec_hit(
            session_factory, monkeypatch, stub_parser, stub_access, phone="+60000865011", code="SRTKS8650A"
        )

        stub_parser(_escalate_to_marketing_verdict())
        calls = _capture_real_next_assignee(monkeypatch)
        sla = _capture_sla(monkeypatch)
        envelope = _envelope_for("ZZT-msg-865-dry", "Please esculate to Marketing")
        envelope.is_test = True
        assert envelope.dry_run is True
        turn2 = engine_mod.run_turn(envelope, session_factory=session_factory)

        assert turn2.branch_kind == "out_of_scope", turn2.branch_kind
        assert len(calls) == 1, calls
        assert calls[0]["body"].get("preview") is True, calls[0]["body"]
        assert calls[0]["body"]["brand_code"] == "sorento", calls[0]["body"]
        assert calls[0]["response"].get("assignee_name") == "ZZT Tay Zhi Yang", calls[0]["response"]
        assert sla == [], "a dry run writes no SLA row"
        routing = _looked_up_routing(session_factory, turn2.turn_id)
        assert routing["brand_code"] == "sorento", routing
        assert routing["routing_source"] == "focus_product", routing
        assert routing["cursor_key"] == "~b:sorento", routing


class TestTheFocusBrandIsReadOnlyWhenAnOfferIsMinted:
    def test_a_hit_turn_over_a_settled_product_never_reads_the_focus_brand(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        """Round 2, N2: the products x brands read feeds only a minted `team_pick`. A turn
        over a settled focus product that is answered (a HIT) mints nothing, so the read
        must not run at all."""
        _seed_settled_focus(session_factory, monkeypatch, stub_access, phone="+60000865012")
        _stub_product_card(monkeypatch)
        reads: list[Any] = []
        real = engine_mod._focus_brand

        def counting(db: Any, focus: Any) -> Any:
            reads.append(focus)
            return real(db, focus)

        monkeypatch.setattr(engine_mod, "_focus_brand", counting)
        stub_parser(
            verdict(
                message_type="business_query",
                domain_hint="master_products",
                intent_hint="check_product",
                entities=[],
                routing={"suggested_team": "purchasing", "suggested_agent": "purchasing"},
            )
        )
        turn = engine_mod.run_turn(
            _envelope_for("ZZT-msg-865-hit", "what grade is it?"), session_factory=session_factory
        )

        assert turn.branch_kind == "business_query", turn.branch_kind
        assert _session_vars(session_factory).get("open_question") is None
        assert reads == [], f"no offer was minted, so the focus brand must not be read: {len(reads)}"

    def test_the_fanned_out_miss_reads_it_once_when_it_mints(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_settled_focus(session_factory, monkeypatch, stub_access, phone="+60000865013")
        reads: list[Any] = []
        real = engine_mod._focus_brand

        def counting(db: Any, focus: Any) -> Any:
            reads.append(focus)
            return real(db, focus)

        monkeypatch.setattr(engine_mod, "_focus_brand", counting)
        stub_parser(
            verdict(
                asks=[{"domain": "inventory"}, {"domain": "incoming"}],
                domain_hint=None,
                intent_hint=None,
                entities=[],
                routing={"suggested_team": "purchasing", "suggested_agent": "incoming_stock_enquiries"},
            )
        )
        engine_mod.run_turn(_envelope_for("ZZT-msg-865-fan2", "stock and eta?"), session_factory=session_factory)

        assert (_session_vars(session_factory).get("open_question") or {}).get("kind") == "team_pick"
        assert len(reads) == 1, len(reads)


# --------------------------------------------------------------------------- #
# 5. Contract 129: the five-key session wire shape is unchanged.
# --------------------------------------------------------------------------- #


class TestContract129FiveKeySessionUnchanged:
    def test_the_session_written_by_both_turns_is_exactly_the_five_keys_with_no_brand_on_focus(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_product_with_brand(session_factory, code="SRTKS8650A", brand_code="SORENTO")
        _seed_marketing_product_team(session_factory)
        _run_spec_hit(
            session_factory, monkeypatch, stub_parser, stub_access, phone="+60000865007", code="SRTKS8650A"
        )
        five = {"focus", "open_question", "ideation", "access_levels", "contains_flyer"}
        assert set(SessionVars.model_fields) == five

        after_turn1 = _session_vars(session_factory)
        assert set(after_turn1) == five, after_turn1
        SessionVars.model_validate(after_turn1)  # extra="forbid": nothing new rides along

        stub_parser(_escalate_to_marketing_verdict())
        _capture_real_next_assignee(monkeypatch)
        _capture_sla(monkeypatch)
        engine_mod.run_turn(
            _envelope_for("ZZT-msg-865-2", "Please esculate to Marketing"),
            session_factory=session_factory,
        )

        after_turn2 = _session_vars(session_factory)
        assert set(after_turn2) == five, after_turn2
        SessionVars.model_validate(after_turn2)
        for snapshot in (after_turn1, after_turn2):
            for product in (snapshot.get("focus") or {}).get("products") or []:
                assert "brand_code" not in product and "brand" not in product, (
                    f"the brand is read off the product row, never persisted beside the "
                    f"product (option 3 was rejected): {product!r}"
                )


# --------------------------------------------------------------------------- #
# 6. The rung itself, pure.
# --------------------------------------------------------------------------- #


class _Seams:
    def __init__(self, brand: Any) -> None:
        self.brand = brand
        self.asked: list[Any] = []

    def product_brand(self, products: Any) -> Any:
        self.asked.append(products)
        if isinstance(self.brand, Exception):
            raise self.brand
        return self.brand


class TestApplyFocusBrand:
    FOCUS = [{"raw": "SRTKS8650A", "hint": "product", "canonical_code": "SRTKS8650A"}]

    def _item(self, source: str, brand: Any = None) -> dict[str, Any]:
        return {"routing_source": source, "brand_code": brand, "focus_products": self.FOCUS}

    def test_it_replaces_none_and_the_offer_carry(self) -> None:
        from app.services.chatbot.lanes.escalation import _apply_focus_brand

        for source, before in (("none", None), ("carried_brand", "mocha")):
            out = _apply_focus_brand(self._item(source, before), _Seams("SORENTO"))
            assert out["brand_code"] == "sorento", (source, out)
            assert out["routing_source"] == "focus_product", (source, out)

    def test_a_brand_the_customer_stated_this_turn_keeps_its_own_brand(self) -> None:
        """Round 2, S1: `stated_brand` is this turn's own `query_brands`, the customer's
        explicit word. The focus product, named this turn or carried, never outranks it."""
        from app.services.chatbot.lanes.escalation import _apply_focus_brand

        for current in (False, True):
            seams = _Seams("sorento")
            item = {
                "routing_source": "stated_brand",
                "brand_code": "mocha",
                "focus_products": [{**self.FOCUS[0], "current_message": current}],
            }
            assert _apply_focus_brand(item, seams) == item, current
            assert seams.asked == [], current

    def test_a_roster_arm_keeps_its_own_brand(self) -> None:
        from app.services.chatbot.lanes.escalation import _apply_focus_brand

        for source in ("picked_member", "company_pick", "prior_state", "multi_company_unpicked"):
            seams = _Seams("sorento")
            item = self._item(source, "mocha")
            assert _apply_focus_brand(item, seams) == item, source
            assert seams.asked == [], source

    def test_no_brand_no_focus_no_seam_or_a_failed_read_leave_the_item_alone(self) -> None:
        from app.services.chatbot.lanes.escalation import _apply_focus_brand

        item = self._item("carried_brand", "mocha")
        assert _apply_focus_brand(item, _Seams(None)) == item
        assert _apply_focus_brand(item, _Seams(RuntimeError("boom"))) == item
        assert _apply_focus_brand(item, object()) == item
        bare = {"routing_source": "none", "brand_code": None, "focus_products": []}
        assert _apply_focus_brand(bare, _Seams("sorento")) == bare


class TestFocusProductBrandRead:
    def test_products_that_disagree_on_a_brand_name_none(self, session_factory) -> None:
        from app.services.chatbot.lanes.escalation_services import focus_product_brand

        _seed_product_with_brand(session_factory, code="ZZT865-SRT", brand_code="SORENTO")
        _seed_product_with_brand(session_factory, code="ZZT865-MCH", brand_code="MOCHA")
        _seed_product_with_brand(session_factory, code="ZZT865-NONE", brand_code=None)
        db = _db(session_factory)  # the turn's own sessions carry the contact's company scope
        try:
            one = [{"raw": "zzt865-srt", "hint": "product", "canonical_code": None}]
            assert focus_product_brand(db, one) == "sorento"
            two = one + [{"raw": "ZZT865-MCH", "hint": "product", "canonical_code": "ZZT865-MCH"}]
            assert focus_product_brand(db, two) is None
            assert focus_product_brand(db, [{"raw": "ZZT865-NONE", "hint": "product"}]) is None
            # A malformed uuid falls back to the code instead of aborting the transaction.
            bad = [{"uuid": "not-a-uuid", "raw": "ZZT865-SRT", "hint": "product"}]
            assert focus_product_brand(db, bad) == "sorento"
            assert focus_product_brand(db, []) is None
        finally:
            db.close()

    def test_a_settled_entry_matches_by_its_uuid_alone(self, session_factory) -> None:
        """Round 2, N1: a settled focus entry names its row by `uuid`. When its `raw` is
        not the product code and it carries no `canonical_code`, the uuid alone must still
        find the row, or the settled product would lose its brand."""
        from app.models.product import Product
        from app.services.chatbot.lanes.escalation_services import focus_product_brand

        _seed_product_with_brand(session_factory, code="ZZT865-UID", brand_code="SORENTO")
        db = _db(session_factory)
        try:
            product_id = db.query(Product.id).filter(Product.product_code == "ZZT865-UID").scalar()
            settled = [
                {"uuid": str(product_id), "raw": "the kitchen sink", "canonical_code": None, "hint": "product"}
            ]
            assert focus_product_brand(db, settled) == "sorento"
            no_code = [{"uuid": str(product_id).upper(), "hint": "product"}]
            assert focus_product_brand(db, no_code) == "sorento"
        finally:
            db.close()
