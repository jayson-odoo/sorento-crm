"""CHATBOT-FAIL-TRIAGE-B2 AC-5 (owner ruling 31 Oct 2026): a dealer's "my cost" is the promotion lookup.

A DEALER is a contact with an ACTIVE tag whose `settings.chatbot.tier` is "dealer" (never the access
levels: dealers and staff hold the same ones). A dealer without the `purchase_orders.cost` grant who asks
for cost (parser: purchase_cost / check_po_cost + a product) is answered by the EXISTING promotion lookup and
presentation, links included, never a `dealer_cost` number. Every other contact without the grant keeps the
denial; a contact with the grant keeps the supplier cost.

The core assertion is EQUALITY with the promotion path: the same contact and product, parsed once as
promotion / check_promotion and once as purchase_cost / check_po_cost, get the same reply and the same tools.
Stubbed parser, canned MCP, fake names. Postgres only.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from app.services.chatbot.lanes.business.services import ResolveGateServices
from tests.chatbot import test_outstanding_lane as lane_harness
from tests.chatbot.conftest import session_factory, validating_resolve_entity  # noqa: F401
from tests.chatbot.test_engine import CONTACT_ID, _parser_output, stub_access, stub_parser  # noqa: F401
from tests.chatbot.test_last_cost_gate import TOOL as COST_TOOL, _granted_cost_row
from tests.chatbot.test_outstanding_lane import PRODUCT_CODE, PRODUCT_UUID, _run_turn, _seed_contact
from tests.chatbot.test_promo_subject_filter import PROMO_TOOL, _pick_qf, _use_mcp

DENIAL = "Sorry, you are not allowed to access purchase cost"
BANNED = ("busy right now", "problem understanding", "not allowed to access purchase cost")
DEALER = {"chatbot": {"tier": "dealer"}}
ONE_TIER = ["Sorento Dealer"]
TWO_TIERS = ["Sorento Dealer", "Sorento End User"]
DEALER_COST = "88.50"

PROMO_A = {
    "description": "ZZT Dealer Promo A",
    "attachments": [{"filename": "zzt-a.pdf", "url": "https://example.test/zzt-a.pdf"}],
    "dealer_cost": DEALER_COST,
}
PROMO_B = {"description": "ZZT Dealer Promo B", "attachments": [{"filename": "zzt-b.pdf", "url": "https://example.test/zzt-b.pdf"}]}
ONE_PROMO = {"has_result": True, "items": [PROMO_A]}
TWO_PROMOS = {"has_result": True, "items": [PROMO_A, PROMO_B]}
NO_PROMO = {"has_result": False, "items": []}
EXPIRED = {"has_result": True, "items": [{**PROMO_B, "end_date": "2020-01-01", "status": "expired_but_usable"}]}
NO_DATE = {"has_result": True, "items": [{**PROMO_B, "start_date": None, "end_date": None}]}


# ---------------------------------------------------------------- seeding / driving


def _tag(session_factory, settings: dict | None, *, active: bool = True, name: str | None = None) -> None:
    db = session_factory()
    pk = db.execute(text("SELECT id FROM respond_contacts WHERE respond_io_id = :c"), {"c": str(CONTACT_ID)}).scalar()
    tid = str(uuid.uuid4())
    db.execute(
        text("INSERT INTO contact_tags (id, name, is_active, settings) VALUES (:i, :n, :a, CAST(:s AS jsonb))"),
        {"i": tid, "n": name or f"ZZT tag {tid[:8]}", "a": active, "s": json.dumps(settings or {})},
    )
    db.execute(text("INSERT INTO respond_contact_tags (contact_id, tag_id) VALUES (:c, :t)"), {"c": pk, "t": tid})
    db.commit()


def _reset_session(session_factory) -> None:
    db = session_factory()
    db.execute(
        text("UPDATE respond_contacts SET session_vars = CAST(:s AS jsonb) WHERE respond_io_id = :c"),
        {"s": json.dumps({"variables": {}}), "c": str(CONTACT_ID)},
    )
    db.commit()


def _services(levels: list[str]) -> ResolveGateServices:
    def _resolve(body: dict[str, Any]) -> dict[str, Any]:
        asked = list(body.get("tokens") or [])
        hit = [t for t in asked if t == PRODUCT_CODE]
        return {
            "tokens": asked,
            "resolutions": [
                {"raw": t, "token": t, "matches": [{"uuid": PRODUCT_UUID, "entity_type": "product", "canonical_code": PRODUCT_CODE}]}
                for t in hit
            ],
            "unresolved_tokens": [t for t in asked if t not in hit],
        }

    return ResolveGateServices(
        access_types=lambda **_: [{"name": n} for n in levels],
        resolve_entity=validating_resolve_entity(_resolve),
        probe=lambda **_: None,
    )


def _qf(kind: str) -> dict[str, Any]:
    entity = [{"raw": PRODUCT_CODE, "hint": "product", "canonical_code": None, "current_message": True, "confident": True}]
    if kind == "cost":
        return _parser_output(domain_hint="purchase_cost", intent_hint="check_po_cost", user_goal="my cost", entities=entity)
    return _parser_output(domain_hint="promotion", intent_hint="check_promotion", user_goal="promotion", entities=entity)


def _say(session_factory, monkeypatch, kind, behaviour, *, levels=ONE_TIER, attributes=None, msg="m", qf=None):
    captured = _use_mcp(monkeypatch, behaviour)
    result, _ = _run_turn(
        session_factory, monkeypatch, qf=qf or _qf(kind), text_body=f"{kind} {PRODUCT_CODE}",
        msg_id=f"zzt-dmc-{msg}-{kind}-{uuid.uuid4().hex[:6]}", attributes=attributes, resolve_services=_services(levels),
    )
    return (result.reply or {}).get("text") or "", list(captured), result


def _pair(session_factory, monkeypatch, payload, **kw):
    """The same contact and product, parsed as promotion then as cost; the contact's state reset between."""
    behaviour = lambda name, args: payload  # noqa: E731
    promo_text, promo_calls, _ = _say(session_factory, monkeypatch, "promo", behaviour, **kw)
    _reset_session(session_factory)
    cost_text, cost_calls, _ = _say(session_factory, monkeypatch, "cost", behaviour, **kw)
    return (promo_text, promo_calls), (cost_text, cost_calls)


def _names(calls) -> list[str]:
    return [n for n, _ in calls]


@pytest.fixture
def dealer(session_factory):
    _seed_contact(session_factory, variables={})
    _tag(session_factory, DEALER, name="ZZT Dealer Tag")


# ---------------------------------------------------------------- 1-5 equality with the promotion path


def test_dealer_cost_ask_calls_the_promotion_tools_never_the_cost_tool(session_factory, monkeypatch, dealer):
    (_pt, promo_calls), (cost_text, cost_calls) = _pair(session_factory, monkeypatch, ONE_PROMO)
    assert PROMO_TOOL in _names(promo_calls), promo_calls
    assert PROMO_TOOL in _names(cost_calls), cost_calls
    assert COST_TOOL not in _names(cost_calls), cost_calls
    assert DENIAL not in cost_text, cost_text


def test_dealer_cost_reply_and_tools_equal_the_promotion_path(session_factory, monkeypatch, dealer):
    (promo_text, promo_calls), (cost_text, cost_calls) = _pair(session_factory, monkeypatch, ONE_PROMO)
    assert cost_text == promo_text, (cost_text, promo_text)
    assert cost_calls == promo_calls, (cost_calls, promo_calls)


def test_dealer_cost_on_several_promotions_equals_the_promotion_path_and_shows_all(session_factory, monkeypatch, dealer):
    (promo_text, promo_calls), (cost_text, cost_calls) = _pair(session_factory, monkeypatch, TWO_PROMOS)
    assert cost_text == promo_text and cost_calls == promo_calls, (cost_text, promo_text)
    assert "1." in cost_text and "2." in cost_text, cost_text  # both promotions listed (the harness renders items as numbered lines)


def test_dealer_cost_with_no_promotion_equals_the_promotion_path(session_factory, monkeypatch, dealer):
    (promo_text, promo_calls), (cost_text, cost_calls) = _pair(session_factory, monkeypatch, NO_PROMO)
    assert cost_text == promo_text and cost_calls == promo_calls, (cost_text, promo_text)
    assert not any(b in cost_text for b in BANNED), cost_text


@pytest.mark.parametrize("payload", [EXPIRED, NO_DATE], ids=["expired_but_usable", "no_date"])
def test_dealer_cost_follows_the_promotion_serving_policy(session_factory, monkeypatch, dealer, payload):
    (promo_text, promo_calls), (cost_text, cost_calls) = _pair(session_factory, monkeypatch, payload)
    assert cost_text == promo_text and cost_calls == promo_calls, (cost_text, promo_text)


# ---------------------------------------------------------------- 6 no dealer_cost number


def test_no_dealer_cost_number_reaches_the_reply(session_factory, monkeypatch, dealer):
    _, (cost_text, cost_calls) = _pair(session_factory, monkeypatch, ONE_PROMO)
    assert DEALER_COST not in cost_text and "dealer_cost" not in cost_text, cost_text
    assert DEALER_COST not in json.dumps(cost_calls), cost_calls


def test_mcp_still_strips_dealer_cost_from_promotion_products():
    src = (Path(__file__).resolve().parents[3] / "sorento_crm_mcp" / "sorento_crm_mcp" / "server.py").read_text(encoding="utf-8")
    block = re.search(r"_PROMO_PRODUCT_DROP_KEYS\s*=\s*frozenset\((.*?)\)\n", src, re.S)
    assert block and "dealer_cost" in block.group(1), block


# ---------------------------------------------------------------- 7 denials stay


@pytest.mark.parametrize(
    "tags",
    [
        [],  # end user / untagged, holding dealer levels (levels do not decide)
        [{}],  # office staff style tag, no tier
        [{"chatbot": {"tier": "office"}}],
        [{"chatbot": {"tier": "dealer"}, "_inactive": True}],  # handled below: inactive dealer tag
    ],
    ids=["untagged_with_dealer_levels", "tag_without_tier", "tier_office", "inactive_dealer_tag"],
)
def test_a_non_dealer_keeps_the_denial_and_calls_no_promotion_tool(session_factory, monkeypatch, tags):
    _seed_contact(session_factory, variables={})
    for settings in tags:
        inactive = settings.pop("_inactive", False)
        _tag(session_factory, settings, active=not inactive)
    reply, calls, result = _say(session_factory, monkeypatch, "cost", lambda n, a: ONE_PROMO, levels=TWO_TIERS)
    assert reply == DENIAL, reply
    assert calls == [], calls


def test_two_tags_one_of_them_dealer_is_a_dealer(session_factory, monkeypatch):
    _seed_contact(session_factory, variables={})
    _tag(session_factory, {}, name="ZZT Office Staff")
    _tag(session_factory, DEALER, name="ZZT Dealer Tag Two")
    reply, calls, _ = _say(session_factory, monkeypatch, "cost", lambda n, a: ONE_PROMO)
    assert PROMO_TOOL in _names(calls) and COST_TOOL not in _names(calls), calls
    assert reply != DENIAL, reply


def test_conflicting_tiers_dealer_and_office_is_not_a_dealer(session_factory, monkeypatch):
    """Conflict fails closed, as `contact_llm_choice` treats a tag conflict."""
    _seed_contact(session_factory, variables={})
    _tag(session_factory, DEALER, name="ZZT Dealer Tag Three")
    _tag(session_factory, {"chatbot": {"tier": "office"}}, name="ZZT Office Tag Three")
    reply, calls, _ = _say(session_factory, monkeypatch, "cost", lambda n, a: ONE_PROMO)
    assert reply == DENIAL, reply
    assert calls == [], calls


# ---------------------------------------------------------------- 8 grant wins


def test_the_grant_wins_over_the_dealer_tag(session_factory, monkeypatch, dealer):
    reply, calls, _ = _say(
        session_factory, monkeypatch, "cost", lambda n, a: _granted_cost_row() if n == COST_TOOL else ONE_PROMO,
        attributes=["purchase_orders.cost"],
    )
    assert _names(calls) == [COST_TOOL], calls
    assert "Cost / unit" in reply, reply


# ---------------------------------------------------------------- 10 multi-level dealer: same pick, same continuation


def test_multi_level_dealer_gets_the_same_tier_pick_and_continues_to_the_promotion_result(session_factory, monkeypatch, dealer):
    behaviour = lambda n, a: ONE_PROMO  # noqa: E731
    p1, pc1, _ = _say(session_factory, monkeypatch, "promo", behaviour, levels=TWO_TIERS, msg="t1")
    p2, pc2, _ = _say(session_factory, monkeypatch, "promo", behaviour, levels=TWO_TIERS, msg="t2", qf=_pick_qf(1))
    _reset_session(session_factory)
    c1, cc1, _ = _say(session_factory, monkeypatch, "cost", behaviour, levels=TWO_TIERS, msg="t1")
    c2, cc2, _ = _say(session_factory, monkeypatch, "cost", behaviour, levels=TWO_TIERS, msg="t2", qf=_pick_qf(1))
    assert c1 == p1 and cc1 == pc1, (c1, p1)
    assert c2 == p2 and cc2 == pc2, (c2, p2)
    assert DENIAL not in c1 + c2
