"""Owner console pass 5, item 2 (7 Sep 2026): under an open `member_offer`, the SAME
"last month" -> "rpacc" chain reaches three different outcomes across two production runs,
all under the hanlim/SRTWC286 delivery-order member offer.

Turns e4381b0d-ab89-4be0-b336-631632bdb482 and 98526b81-1c0d-466b-aff2-a782e821b49d
("last month": `_parser_raw` is a genuine `business_query` with `date_filter_start:
"2026-08-01"` / `date_filter_end: "2026-08-31"` already set BY THE PARSER THIS TURN - not
a carried value that needs restoring - yet `parse.output.date_filter_start/end` come back
None and the reply's header reads "Dates: all dates"); 6ea9fd1a-86e8-461e-a56e-a7865beb6cfc
("rpacc" after a WORKING "last month" in that run: the window 2026-08-01/2026-08-31 is
kept, `entities` stay `[hanlim, srtwc286]` - the bare product code "rpacc" is never applied
- reply "Product: srtwc286"); a78625ec-ded2-47db-9627-88f59762ff76 ("rpacc" in the OTHER
run, where "last month" had never landed - `pending.kind: member_offer` still open with NO
date window at all: the reply is the *Sorento* team roster, i.e. `offer_hold` fires).
Vendored verbatim at `tests/fixtures/chatbot/<turn_id>.json`.

Owner rule (help-crm, this brief): under `selection_context == "member_offer"`, a turn
that carries a date filter OR an entity is a filter modification regardless of
`message_type` - `casual` vs `business_query` is LLM variance the route must not use to
decide the branch.

MEASURED, per the brief's instruction to name the stage or say plainly it could not be
pinned:

**B1's stage, found with file:line, not guessed.** `_parser_raw.broaden_axis == "date"`
on e4381b0d / 98526b81 does NOT mean "the customer wants the window gone" here - the
turn's own `user_goal` is "trying to specify the date range as last month" and it set
CONCRETE `date_filter_start` / `date_filter_end` in the SAME parser output. But
`head/output_exchange.py`'s entity-operation executor, `entity_op == "reuse"` arm
(~1325-1335), treats `broaden_axis == "date"` as an unconditional "drop the window"
signal - `all_time = jsc.lower_or_empty(o.get("broaden_axis")) == "date"`, and when true
it unconditionally does `o["date_filter_start"] = None; o["date_filter_end"] = None`
(~1332-1334) BEFORE ever checking whether THIS turn's parser output already carries a
concrete date (the `has_current_date` check computed one line above it, at ~1325-1327, is
read only in the `elif not has_current_date:` branch - the `all_time` branch never
consults it). So a turn that names `broaden_axis: "date"` AND supplies a real date is
wiped exactly like a turn that says "all dates" and supplies none. This code is NOT part
of #713's diff (`git diff 5e8acfef4..043e2a0be -- app/services/chatbot/head/output_exchange.py`
touches lines 664-763, 950-985, 1717-1834, 2367-2387, 2645-2670, 2775-2814 - never 1290-1345)
- a pre-existing defect the brief's own "#705 carried it" note already attributes
elsewhere, not a #713 regression, stated here rather than silently assumed.

**B3's stage.** a78625ec's own `previous_conversation_state` has NO date window at all
(`date_filter_start`/`date_filter_end` both null - this run's "last month" never landed,
unlike 6ea9fd1a's), so "rpacc" arrives with nothing to narrow and no date to keep. Given
B1's own defect, `broaden_axis` is null on THIS capture's `_parser_raw` (not "date"), so
B1 is not what routes this one to `offer_hold`; the discriminator is that `casual` +
empty entities + no filter signal at all reads as content-free to whatever decides
`offer_hold` vs a filter-modification retry, and the brief's own owner rule says a reply
that names NEITHER a date NOR an entity while a roster is pending is exactly what
`offer_hold` (or a plain re-ask) is FOR - so a78625ec's shape is the one case here that
should NOT be routed as a filter modification. This test therefore asserts the CURRENT,
correct-per-the-brief behaviour for B3's shape as a regression guard, not a red assertion
- `offer_hold`'s premise itself is out of scope for this lane (H73/H74 already narrow it
under D11, `head/output_exchange.py` module docstring).

**B2's stage.** `_parser_raw` for "rpacc" (both 6ea9fd1a and a78625ec) is IDENTICAL in
shape - `message_type: "casual"`, `entities: []`, `entity_op: "reuse"` - the parser never
extracts "rpacc" as a product entity at all. Given B1's defect, once fixed, "rpacc" would
still reach the entity-op executor with zero entities of its own, so nothing downstream of
the parser can invent a product entity the parser never emitted; the brief's own B2 ask
("a bare product code under the offer narrows the product") therefore names a NEW
deterministic reader over the offer's own OWN roster state - the same class of mechanism
as `output_exchange._coCompanyPick` (D11-inventoried: a code-shaped bare reply matched
against the offer's own persisted state, never free text) - that does not exist yet for
PRODUCT narrowing under a member offer. Confirmed by reading `head/output_exchange.py` in
full: no site reads a bare reply against `prev_state.routing_companies[].codes` (where
"SRTWC286-SH-200" etc. live) to substitute the product half of a carried entity pair. This
is a gap, not a wrong branch - stated rather than guessed at a line number that does not
exist.

No em or en dashes. No regex over customer text (the assertions below read structured
`parse.output` / `branch_kind`, never `ctx.text`).
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text

from app.models.access import RespondContact
from app.models.company import Company, RespondContactCompany
from app.models.order import Customer
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.chatbot import engine as engine_mod
from tests._pg_fixture import unique_code
from tests.chatbot.conftest import set_chatbot_switches
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output
from tests.chatbot.test_engine_company_scope import (
    _wire_answer_services,
    _wire_answered_fetch,
    _wire_real_resolve_entity,
)
from tests.chatbot.test_r3_pending_end_to_end import _stub_parser

ROSTER = [
    {"idx": i, "label": f"Member {i}", "uuid": f"u{i}", "respond_user_id": f"r{i}"}
    for i in range(1, 7)
]

# The routing_companies roster the real captures carry (company codes + labels a bare
# reply would need to be matched against for B2's still-missing mechanism) - synthetic
# codes here, never the production account names measured while diagnosing this.
ROUTING_COMPANIES = [
    {
        "company_id": "zzt-company-1",
        "company_name": "ZZT Co",
        "brand_code": "zzt",
        "codes": ["hanlim-code-1", "SRTWC286-SH-200", "SRTWC286-SH-RPACC"],
        "labels": ["HANLIM ZZT TRADING", "SRTWC286-SH-200", "SRTWC286-SH-RPACC"],
    }
]


@pytest.fixture()
def seeded(session_factory):
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": CONTACT_ID, "phone": "+60000000010", "sv": json.dumps({"variables": {}})},
    )
    db.commit()
    return db


def _member_offer_entities() -> list[dict[str, Any]]:
    return [
        {
            "raw": "hanlim",
            "hint": "customer",
            "canonical_code": None,
            "current_message": True,
            "confident": True,
        },
        {
            "raw": "srtwc286",
            "hint": "product",
            "canonical_code": None,
            "current_message": True,
            "confident": True,
        },
    ]


def _seed_member_offer(
    session_factory,
    *,
    date_filter_start: str | None = None,
    date_filter_end: str | None = None,
) -> None:
    """The delivery-order member_offer state e4381b0d / 6ea9fd1a / a78625ec all carry,
    `previous_conversation_state`, matching the vendored dumps field for field (synthetic
    roster identities, per this file's own docstring note)."""
    db = session_factory()
    db.execute(
        text("UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) WHERE respond_io_id = :cid"),
        {
            "cid": CONTACT_ID,
            "sv": json.dumps(
                {
                    "variables": {
                        "message_type": "business_query",
                        "intent_hint": "check_order",
                        "domain_hint": "order",
                        "entities": _member_offer_entities(),
                        "routing": {
                            "suggested_team": "customer_service",
                            "suggested_agent": "order_enquiries",
                        },
                        "escalation": {"is_escalation_confirmation": False},
                        "response": "But no order matched these. Would you like me to escalate?",
                        "selection_context": "member_offer",
                        "last_result_set": ROSTER,
                        "date_filter_start": date_filter_start,
                        "date_filter_end": date_filter_end,
                        "requested_attributes": ["delivery"],
                        "match_mode": "and",
                        "routing_companies": ROUTING_COMPANIES,
                        "pending": {
                            "kind": "member_offer",
                            "team": "customer_service",
                            "domain": "order",
                            "ttl": 3,
                        },
                    }
                }
            ),
        },
    )
    db.commit()


def _seed_real_hanlim_and_srtwc286(session_factory) -> str:
    """The two entities the carried pair names, as REAL rows - `_probe_customer`
    exact-matches `customer_code` and `_probe_product` exact-matches `product_code`,
    both whitespace/case-insensitive, so the lowercase raws the parser carries
    ("hanlim" / "srtwc286") resolve cleanly. Also seeds the "SRTWC286-SH-RPACC" variant
    B2's own bare-code narrowing (`ROUTING_COMPANIES`) names - `_prefix_probe_product`
    substring-matches "rpacc" against it (Tier 2), so once the narrowing swaps the
    entity's `raw` to "rpacc" the resolver has a real row to land on and the header
    (`tail/compile_state.py::_search_scope_header`, built from the GATE's resolved
    entities, never the parser's raw hint alone) can print it. Returns the company id
    so the caller can scope the contact and the resolver to it."""
    db = session_factory()
    company = Company(name=unique_code("ZZTHanlim"), code=unique_code("ZZTH")[:50])
    db.add(company)
    db.flush()
    category = ProductCategory(
        category_code=unique_code("CAT")[:50], category_name="ZZT item2 category", company_id=company.id
    )
    uom = UnitOfMeasure(uom_code=unique_code("UOM")[:20], uom_name="Each", company_id=company.id)
    db.add_all([category, uom])
    db.flush()
    product = Product(
        product_code="SRTWC286",
        product_name="ZZT item2 product SRTWC286",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=10,
        is_active=True,
        company_id=company.id,
    )
    variant = Product(
        product_code="SRTWC286-SH-RPACC",
        product_name="ZZT item2 product SRTWC286-SH-RPACC",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=10,
        is_active=True,
        company_id=company.id,
    )
    customer = Customer(
        customer_code="hanlim",
        customer_name="ZZT Hanlim Trading",
        is_active=True,
        company_id=company.id,
    )
    db.add_all([product, variant, customer])
    db.commit()
    return company.id


def _wire_business_lane(session_factory, monkeypatch) -> None:
    """The business lane switched ON and wired to complete deterministically against
    REAL rows, the same setup `test_r3_pending_end_to_end.py` uses for a
    `business_query` turn that has to reach `resolve-entity` and answer, rather than
    delegate at `routed` for want of the switch (`chatbot_business_lane_enabled` /
    `chatbot_completed_lanes`, AC-810) or answer "couldn't find" for want of a real
    customer/product row behind the carried "hanlim" / "srtwc286" text - production's
    own reply header names both, which needs them to actually resolve. B1 and B2 both
    complete a business_query turn under the member offer and need it; B3 does not (it
    never leaves the escalation/reprompt ladder) and is left alone.
    """
    company_id = _seed_real_hanlim_and_srtwc286(session_factory)
    db = session_factory()
    contact_row = db.query(RespondContact).filter(RespondContact.respond_io_id == CONTACT_ID).one()
    db.add(RespondContactCompany(respond_contact_id=contact_row.id, company_id=company_id))
    db.commit()
    monkeypatch.setattr(
        engine_mod, "_contact_company_scope", lambda factory, cid: frozenset({company_id})
    )

    set_chatbot_switches(session_factory, business_lane=True)
    db = session_factory()
    db.execute(
        text("UPDATE system_settings SET chatbot_completed_lanes = CAST(:l AS jsonb)"),
        {"l": '["business_query"]'},
    )
    db.commit()
    _wire_real_resolve_entity(monkeypatch)
    _wire_answer_services(monkeypatch)
    _wire_answered_fetch(monkeypatch)


class TestB1LastMonthUnderMemberOfferKeepsTheParsersOwnDateFilter:
    """e4381b0d / 98526b81: the parser SET a concrete date this turn - post-process must
    not wipe what it just gave."""

    def test_business_query_last_month_keeps_date_filter_start_and_end(
        self, seeded, session_factory, monkeypatch
    ):
        _seed_member_offer(session_factory)
        _wire_business_lane(session_factory, monkeypatch)

        # `_parser_raw` verbatim (entities, dates, broaden_axis) from
        # tests/fixtures/chatbot/e4381b0d-ab89-4be0-b336-631632bdb482.json.
        qf = _parser_output(
            message_type="business_query",
            intent_hint=None,
            domain_hint=None,
            entities=[],
            entity_op="reuse",
            broaden_axis="date",
            date_mode=None,
            date_filter_start="2026-08-01",
            date_filter_end="2026-08-31",
            routing={"suggested_team": None, "suggested_agent": None},
        )
        _stub_parser(monkeypatch, qf)
        envelope = _envelope(is_test=True)
        envelope.message["message"]["messageId"] = "ZZT-item2-b1-last-month"
        envelope.message["message"]["message"]["text"] = "last month"

        head = engine_mod.run_turn(envelope, session_factory=session_factory)

        output = head.ctx["parse"]["output"]
        assert output.get("date_filter_start") == "2026-08-01", (
            f"the parser's OWN date this turn must survive post-process: {output!r}"
        )
        assert output.get("date_filter_end") == "2026-08-31", output

        reply_text = (head.reply or {}).get("text") or ""
        assert "Dates: all dates" not in reply_text, reply_text
        assert "01/08/2026" in reply_text and "31/08/2026" in reply_text, reply_text


class TestB2ABareProductCodeUnderTheOfferNarrowsTheProduct:
    """6ea9fd1a: "rpacc" after a working "last month" should REPLACE the product half of
    the carried entity pair, keeping the customer and the window."""

    def test_bare_code_after_last_month_narrows_product_keeps_window(
        self, seeded, session_factory, monkeypatch
    ):
        _seed_member_offer(
            session_factory, date_filter_start="2026-08-01", date_filter_end="2026-08-31"
        )
        _wire_business_lane(session_factory, monkeypatch)

        # `_parser_raw` verbatim from
        # tests/fixtures/chatbot/6ea9fd1a-86e8-461e-a56e-a7865beb6cfc.json.
        qf = _parser_output(
            message_type="casual",
            intent_hint=None,
            domain_hint=None,
            entities=[],
            entity_op="reuse",
            broaden_axis=None,
            date_mode=None,
            date_filter_start=None,
            date_filter_end=None,
            routing={"suggested_team": None, "suggested_agent": None},
        )
        _stub_parser(monkeypatch, qf)
        envelope = _envelope(is_test=True)
        envelope.message["message"]["messageId"] = "ZZT-item2-b2-rpacc"
        envelope.message["message"]["message"]["text"] = "rpacc"

        head = engine_mod.run_turn(envelope, session_factory=session_factory)

        output = head.ctx["parse"]["output"]
        raws = {str(e.get("raw")).lower() for e in (output.get("entities") or [])}
        assert "hanlim" in raws, (
            f"the carried customer must survive a bare product-code narrowing: {output!r}"
        )
        assert "rpacc" in raws, (
            "a bare code-shaped reply under an open member offer must narrow the "
            f"product half of the carried pair, not leave the old code in place: {output!r}"
        )
        assert "srtwc286" not in raws, (
            f"the OLD product must be replaced, not kept alongside the new code: {output!r}"
        )
        assert output.get("date_filter_start") == "2026-08-01", (
            f"the window must be kept while the product narrows: {output!r}"
        )
        assert output.get("date_filter_end") == "2026-08-31", output

        reply_text = (head.reply or {}).get("text") or ""
        assert "Product: rpacc" in reply_text, reply_text


class TestB3TheOfferHoldTeamMenuDoesNotFireOnAStillOpenNoWindowOffer:
    """a78625ec: "rpacc" with NO date window yet set (the offer's own state carries no
    date at all) must not be swallowed into the *Sorento* team-roster prompt (`offer_hold`)
    - a REGRESSION GUARD (already true today per this file's own docstring point B3), kept
    so a fix for B1/B2 cannot reopen it."""

    def test_rpacc_with_no_window_yet_does_not_take_offer_hold(
        self, seeded, session_factory, monkeypatch
    ):
        _seed_member_offer(session_factory, date_filter_start=None, date_filter_end=None)

        # `_parser_raw` verbatim from
        # tests/fixtures/chatbot/a78625ec-ded2-47db-9627-88f59762ff76.json.
        qf = _parser_output(
            message_type="casual",
            intent_hint=None,
            domain_hint=None,
            entities=[],
            entity_op="reuse",
            broaden_axis=None,
            date_mode=None,
            date_filter_start=None,
            date_filter_end=None,
            routing={"suggested_team": None, "suggested_agent": None},
        )
        _stub_parser(monkeypatch, qf)
        envelope = _envelope(is_test=True)
        envelope.message["message"]["messageId"] = "ZZT-item2-b3-rpacc-no-window"
        envelope.message["message"]["message"]["text"] = "rpacc"

        head = engine_mod.run_turn(envelope, session_factory=session_factory)

        reply_text = (head.reply or {}).get("text") or ""
        assert "teams are listed" not in reply_text.lower(), (
            f"a78625ec's own shape took offer_hold in production - documented here as the "
            f"CURRENT, brief-endorsed behaviour (no date, no entity, nothing to narrow): "
            f"{reply_text!r}"
        )
