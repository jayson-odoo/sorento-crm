"""AC-16, AC-17, AC-18, AC-25, AC-27, AC-28, AC-29 (chatbot-last-purchase-cost): the
whole-domain field-reveal gate, the parser prompt addendum, the gate matrix row, the
`top_n` passthrough, and the migration 513 publish.

`documentation/plans/chatbot/PLAN-chatbot-last-purchase-cost.md`;
`documentation/plans/chatbot/chatbot-last-purchase-cost-acceptance-criteria.md`.

AC-16/AC-17 drive the REAL `engine.run_turn`, mirroring `tests/chatbot/
test_s6c_engine_paths.py`'s `_srtwc8517_resolved_bundle()` pattern (a canned
`ResolveGateServices` that resolves the named product without touching the real DB
resolver) and `tests/chatbot/test_broaden_domain_switch_e2e.py`'s `fetch_services`
recording stub - so the assertions are on OBSERVABLE turn behaviour (reply text, MCP call
count, the persisted trace) rather than on any particular internal call site the domain
grant check ends up living in.

Postgres only (`tests/_pg_fixture.py` via `tests/chatbot/conftest.py`'s
`session_factory`). No em or en dashes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from app.models.chatbot_turn import ChatbotTurn
from app.models.user import SystemSetting
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.lanes.business import fetch
from app.services.chatbot.lanes.business import gate
from app.services.chatbot.lanes.business.services import AnswerServices, FetchServices, ResolveGateServices
from tests.chatbot.conftest import set_chatbot_switches
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output, seeded, stub_access, stub_parser  # noqa: F401

PRODUCT_UUID = "44444444-4444-4444-4444-444444444444"
TOOL = "crm_procurement_po_last_cost_list"
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


# --------------------------------------------------------------------------- #
# AC-16 / AC-17: the whole-domain grant, through a real turn.
# --------------------------------------------------------------------------- #


def _cost_parser_output(**overrides: Any) -> dict[str, Any]:
    return _parser_output(
        domain_hint="purchase_cost",
        intent_hint="check_po_cost",
        user_goal="what did we pay for M218",
        entities=[
            {
                "raw": "M218",
                "hint": "product",
                "canonical_code": None,
                "current_message": True,
                "confident": True,
            }
        ],
        **overrides,
    )


def _m218_resolved_bundle() -> ResolveGateServices:
    def _resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
        return {
            "tokens": ["M218"],
            "resolutions": [
                {
                    "raw": "M218",
                    "matches": [
                        {
                            "uuid": PRODUCT_UUID,
                            "entity_type": "product",
                            "canonical_code": "M218",
                        }
                    ],
                }
            ],
            "unresolved_tokens": [],
        }

    return ResolveGateServices(
        access_types=lambda **_: [{"name": "Sorento Dealer"}],
        resolve_entity=_resolve_entity,
        probe=lambda **_: None,
    )


def _wire(session_factory, monkeypatch, *, mcp_call) -> None:
    set_chatbot_switches(session_factory, business_lane=True)
    db = session_factory()
    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting()
        db.add(row)
    row.chatbot_completed_lanes = ["business_query"]
    db.commit()

    bundle = _m218_resolved_bundle()
    monkeypatch.setattr(
        engine_mod.business_services, "production_services", lambda db, *, space_id=None: bundle
    )
    monkeypatch.setattr(
        engine_mod.business_services, "fetch_services", lambda db: FetchServices(mcp_call=mcp_call)
    )
    monkeypatch.setattr(
        engine_mod.business_services,
        "answer_services_for",
        lambda session_factory: AnswerServices(
            mcp_probe=lambda name, args: {"answers": [], "has_result": False},
            family_fetch=lambda q: {"data": []},
        ),
    )


def _turn_row(session_factory, turn_id: str) -> ChatbotTurn:
    return session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()


def _granted_cost_row() -> dict[str, Any]:
    return {
        "items": [
            {
                "fields": [
                    {"key": "po_number", "label": "PO Number", "value": "PO-2026/09-0013"},
                    {"key": "product_code", "label": "Product Code", "value": "M218"},
                    {"key": "po_quantity", "label": "PO Quantity", "value": 19},
                    {"key": "po_date", "label": "PO Date", "value": "2026-05-01"},
                    {"key": "unit_cost", "label": "Cost / unit", "value": "CNY 110.00"},
                    {"key": "discount_per_unit", "label": "Discount / unit", "value": "CNY 66.00"},
                    {
                        "key": "unit_cost_after_discount",
                        "label": "Cost after discount / unit",
                        "value": "CNY 44.00",
                    },
                    {"key": "warehouse", "label": "Warehouse", "value": "BRW-SMC"},
                ],
            }
        ],
        "has_result": True,
        "intro": "Here is the last purchase cost per product and location.",
        "restricted_fields": {
            "unit_cost": "purchase_orders.cost",
            "discount_per_unit": "purchase_orders.cost",
            "unit_cost_after_discount": "purchase_orders.cost",
        },
    }


class TestAC16DomainRefusedWithoutGrant:
    def test_ac16_domain_refused_without_grant(
        self, session_factory, seeded, stub_parser, stub_access, monkeypatch
    ) -> None:
        """A contact without `purchase_orders.cost` asking "last purchase cost for M218"
        gets the access_denied canned reply for team purchasing; no MCP tool is called;
        the trace carries {"skipped": "not_granted", "needs": "purchase_orders.cost"}."""
        calls: list[tuple[str, dict]] = []

        def mcp_call(name: str, args: dict) -> str:
            calls.append((name, dict(args)))
            raise AssertionError(f"no tool call is expected without the grant: {name}")

        _wire(session_factory, monkeypatch, mcp_call=mcp_call)
        stub_parser(_cost_parser_output())
        stub_access(attributes=[])

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.status == "done", result.error
        assert result.delegate is None
        assert calls == [], f"the tool must never be called without the grant: {calls!r}"

        text = result.reply.get("text") or ""
        assert "not allowed to access" in text, text

        trace = (_turn_row(session_factory, result.turn_id).trace) or []
        skip_events = [
            e
            for e in trace
            if isinstance(e, dict)
            and e.get("skipped") == "not_granted"
            and e.get("needs") == "purchase_orders.cost"
        ]
        assert skip_events, f"no not_granted trace event found: {trace!r}"


class TestAC17GrantedContactGetsCostLines:
    def test_ac17_granted_contact_gets_cost_lines(
        self, session_factory, seeded, stub_parser, stub_access, monkeypatch
    ) -> None:
        """The same contact WITH the key gets the answer; the reply contains
        "Cost / unit" and "Cost after discount / unit" and no UUID."""
        calls: list[tuple[str, dict]] = []

        def mcp_call(name: str, args: dict) -> str:
            calls.append((name, dict(args)))
            assert name == TOOL, name
            return json.dumps(_granted_cost_row())

        _wire(session_factory, monkeypatch, mcp_call=mcp_call)
        stub_parser(_cost_parser_output())
        stub_access(attributes=["purchase_orders.cost"])

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.status == "done", result.error
        assert [c[0] for c in calls] == [TOOL], calls

        text = result.reply.get("text") or ""
        assert "Cost / unit" in text, text
        assert "Cost after discount / unit" in text, text
        assert not _UUID_RE.search(text), text


# --------------------------------------------------------------------------- #
# AC-18: `output_structurer` drops/keeps the three money fields (belt and braces -
# the SAME general mechanism `test_growth_r1_review_fixes.py` already grades for
# `purchase_orders.supplier`, applied to the new field names).
# --------------------------------------------------------------------------- #


class TestAC18OutputStructurerDropsMoneyFieldsWithoutGrant:
    _RESTRICTED = {
        "unit_cost": "purchase_orders.cost",
        "discount_per_unit": "purchase_orders.cost",
        "unit_cost_after_discount": "purchase_orders.cost",
    }

    def _result(self) -> dict[str, Any]:
        return {
            "items": [
                {
                    "fields": [
                        {"key": "po_number", "label": "PO Number", "value": "PO-1"},
                        {"key": "unit_cost", "label": "Cost / unit", "value": "CNY 110.00"},
                        {
                            "key": "discount_per_unit",
                            "label": "Discount / unit",
                            "value": "CNY 66.00",
                        },
                        {
                            "key": "unit_cost_after_discount",
                            "label": "Cost after discount / unit",
                            "value": "CNY 44.00",
                        },
                    ]
                }
            ],
            "has_result": True,
            "intro": "intro",
            "restricted_fields": self._RESTRICTED,
        }

    def test_ac18_drops_without_grant(self) -> None:
        out = fetch.output_structurer(self._result(), {"access": {"attributes": []}})
        keys = {f["key"] for f in out["answers"][0]["fields"]}
        assert keys == {"po_number"}, keys

    def test_ac18_keeps_with_grant(self) -> None:
        out = fetch.output_structurer(
            self._result(), {"access": {"attributes": ["purchase_orders.cost"]}}
        )
        keys = {f["key"] for f in out["answers"][0]["fields"]}
        assert keys == {
            "po_number",
            "unit_cost",
            "discount_per_unit",
            "unit_cost_after_discount",
        }, keys


# --------------------------------------------------------------------------- #
# AC-25: the parser prompt addendum, pinned as literal text - no LLM call.
# --------------------------------------------------------------------------- #

_PHRASES = ["last purchase cost", "what did we pay", "上次采购价", "harga belian terakhir"]


@pytest.mark.parametrize(
    "body_name",
    ["SEMANTIC_PARSER_PROMPT", "SEMANTIC_PARSER_PROMPT_SLIM"],
)
def test_ac25_parser_prompt_teaches_purchase_cost(body_name: str) -> None:
    import app.services.chatbot_parser_prompt as prompt_mod

    body = getattr(prompt_mod, body_name)
    for phrase in _PHRASES:
        assert phrase in body, f"{body_name} missing phrase {phrase!r}"
    assert 'intent_hint "check_po_cost"' in body, body_name
    assert 'domain_hint "purchase_cost"' in body, body_name

    match = re.search(r"domain_hint = ONE of:[^\n]*", body)
    assert match is not None, f"{body_name}: no 'domain_hint = ONE of:' literal found"
    tokens = [t.strip() for t in match.group(0).split(":", 1)[1].split("|")]
    assert "purchase_cost" in tokens, f"{body_name}: {tokens!r}"


# --------------------------------------------------------------------------- #
# AC-27: the gate matrix row.
# --------------------------------------------------------------------------- #


def test_ac27_gate_allows_product_and_warehouse_no_allows_empty() -> None:
    assert gate.ALLOWED["purchase_cost"] == ["product", "warehouse", "category", "brand"]
    assert "purchase_cost" not in gate.ALLOWS_EMPTY

    out = gate.run_gate(
        {},
        parser={"domain_hint": "purchase_cost", "entities": []},
        resolver={"resolutions": []},
    )
    assert out["gate_passed"] is False


# --------------------------------------------------------------------------- #
# AC-28: `top_n` passes straight through, never aliased to `limit`.
# --------------------------------------------------------------------------- #


def test_ac28_top_n_passes_direct() -> None:
    assert TOOL in fetch.TOP_N_DIRECT_TOOLS

    trigger = {
        "entities": [{"entity_type": "product", "uuid": PRODUCT_UUID, "code": "M218"}],
        "tool": TOOL,
        "semantic_input": {"contact_id": "1", "space_id": "s", "top_n": 3},
    }
    out = fetch.entity_ids_transformer(trigger)
    assert out.get("top_n") == 3
    assert "limit" not in out


# --------------------------------------------------------------------------- #
# AC-29: migration 513 publishes both prompt bodies, idempotent, no label moved -
# mirrors `tests/test_chatbot_warehouse_cue_migration.py::
# test_publish_is_idempotent_one_new_version_each_then_none`'s own pin for 487 EXACTLY,
# stale-v1 shape and all.
#
# Why the stale v1: on a genuinely blank schema `seed_prompt_registry` seeds v1 from the
# CURRENT full fallback (`app.services.chatbot_parser_prompt.SEMANTIC_PARSER_PROMPT`),
# which by AC-25 already carries the last-cost vocabulary once this lane ships - so a v1
# seeded from the live constant would make the FULL half of the first `publish()` a
# guaranteed no-op (the template it tries to insert already exists as v1) and the test
# would never see the "adds one new version" behaviour it exists to pin. Seeding v1 with
# a STALE placeholder first, the same way 487's own test does, is what keeps the FULL
# half of `publish()` genuinely exercised regardless of what the live prompt constant
# says.
# --------------------------------------------------------------------------- #

MIGRATION_FILE = "513_chatbot_parser_last_cost.py"


def _load_migration():
    import importlib.util

    path = (
        Path(__file__).resolve().parent.parent.parent
        / "alembic"
        / "versions"
        / MIGRATION_FILE
    )
    spec = importlib.util.spec_from_file_location("migration_under_test_513", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ac29_migration_513_publish_idempotent() -> None:
    from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
    from app.services.ai_prompt_registry import PROMPT_KEYS
    from tests._pg_fixture import blank_session

    module = _load_migration()
    with blank_session() as session:
        from app.services.ai_prompt_seed import seed_prompt_registry

        spec = PROMPT_KEYS["chatbot_semantic_parser"]
        session.add(
            AIPromptVersion(
                name="chatbot_semantic_parser",
                version=1,
                type="text",
                template="STALE FULL PROMPT TEXT (pre last-cost fix)",
                variables=list(spec.variables),
            )
        )
        session.commit()
        # v1 already exists (the stale row above), so this only adds the production
        # label pointing at it - it never overwrites a live row.
        seed_prompt_registry(session.get_bind())

        production_label_before = (
            session.query(AIPromptLabel)
            .filter(
                AIPromptLabel.name == "chatbot_semantic_parser",
                AIPromptLabel.label == "production",
            )
            .first()
        )
        assert production_label_before is not None
        v1 = (
            session.query(AIPromptVersion)
            .filter(
                AIPromptVersion.name == "chatbot_semantic_parser",
                AIPromptVersion.version == 1,
            )
            .first()
        )
        assert production_label_before.version_id == v1.id

        first = module.publish(session)
        assert isinstance(first, dict) and set(first) == {"full", "slim"}
        assert isinstance(first["full"], int) and first["full"] >= 2, (
            "first publish() must create a new FULL version above the stale v1"
        )
        assert isinstance(first["slim"], int) and first["slim"] >= 2, (
            "first publish() must create a new SLIM version above the stale v1"
        )
        assert first["full"] != first["slim"], "FULL and SLIM texts differ, so must be distinct versions"

        second = module.publish(session)
        assert second == {"full": None, "slim": None}, (
            "a second publish() call must add no new version for either body"
        )

        rows = (
            session.query(AIPromptVersion)
            .filter(AIPromptVersion.name == "chatbot_semantic_parser")
            .all()
        )
        versions = [row.version for row in rows]
        assert versions.count(first["full"]) == 1
        assert versions.count(first["slim"]) == 1

        production_label_after = (
            session.query(AIPromptLabel)
            .filter(
                AIPromptLabel.name == "chatbot_semantic_parser",
                AIPromptLabel.label == "production",
            )
            .first()
        )
        assert production_label_after is not None
        assert production_label_after.version_id == v1.id, (
            "publish() must never move the production label off the stale v1 - "
            "promoting is a deliberate, separate action in the admin UI"
        )
