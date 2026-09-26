"""Phase 2 RED tests - issue #1262 (the Samantha case), GROUP C brand slice, slice 9
(finding F1a), UAC `chatbot-samantha-slices-26sep-acceptance-criteria.md` AC-S9-3 /
AC-S9-6, "Rulings assumed" 7 and 8. Round 3 section 6 step 4 (the brand resolve): a
verdict entity `{raw, hint: "brand"}` that matches a live brand resolves to that
brand's ids INSIDE the chatbot - never re-typed to customer/transporter, never sent
through the shared resolver's order-domain fan-out
(`app.services.entity_resolver._DOMAIN_HINT_EXPANSIONS["order"]["brand"]`, which stays
in place for n8n/MCP callers, ruling 7) - and the order-domain gate admits a brand; the
report tools take a `brand_ids` filter (ruling 8: "other order reports" = the orders
list / by-product tools that already take `product_ids`).

T2/T3 of the trace (round 2 explainer, `samantha-chat-diagnosis.html` section 1):
"brand Sorento" + dealer "Cheng Huat Sentul" must never ask "which customer" over ten
SORENTO names and never ask "transporter or customer?".

Written before any of the resolve step exists. No implementation looked at beyond what
is read here to confirm the RED reason.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import text

from app.models.base import set_company_scope
from app.models.product import Brand
from app.services.chatbot.lanes.business import fetch as fetch_mod
from app.services.chatbot.lanes.business import gate as gate_mod
from app.services.chatbot.lanes.business.services import FetchServices, ResolveGateServices
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.conftest import set_chatbot_switches, validating_resolve_entity
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output, stub_access  # noqa: F401


class TestGateAdmitsBrandForOrder:
    """AC-S9-3's gate half: `order` must admit a `brand` entity - today's matrix does
    not (S4 point 7 only added `warehouse`)."""

    def test_brand_is_an_allowed_type_for_order(self) -> None:
        assert "brand" in gate_mod.ALLOWED["order"], (
            f"the order-domain gate must admit a brand entity: {gate_mod.ALLOWED['order']}"
        )


class TestEntityIdsTransformerMapsBrandToBrandIds:
    """AC-S9-4/AC-S9-6: once a brand entity carries a resolved uuid, the transformer
    must turn it into `brand_ids` the same way `product`/`customer` already become
    `product_ids`/`customer_ids` - `TYPE_TO_PARAM` has no `brand` entry today."""

    BRAND_UUID = "11111111-1111-1111-1111-111111111111"

    def _trigger(self, *, tool: str) -> dict[str, Any]:
        return {
            "entities": [
                {"uuid": self.BRAND_UUID, "entity_type": "brand", "canonical_code": "Sorento"},
            ],
            "tool": tool,
            "semantic_input": {"contact_id": "1", "space_id": "s"},
        }

    def test_outstanding_report_gets_brand_ids(self) -> None:
        out = fetch_mod.entity_ids_transformer(self._trigger(tool="crm_outstanding_report"))
        assert out.get("brand_ids") == [self.BRAND_UUID], out

    def test_orders_list_gets_brand_ids(self) -> None:
        out = fetch_mod.entity_ids_transformer(
            self._trigger(tool="crm_order_management_orders_list")
        )
        assert out.get("brand_ids") == [self.BRAND_UUID], out

    def test_orders_by_product_gets_brand_ids(self) -> None:
        out = fetch_mod.entity_ids_transformer(
            self._trigger(tool="crm_order_management_orders_by_product_list")
        )
        assert out.get("brand_ids") == [self.BRAND_UUID], out


class TestSharedResolverFanoutUnchangedForOtherCallers:
    """Guard, ruling 7 - may already be green: the shared resolver's OWN order-domain
    brand fan-out (n8n / MCP callers) is untouched by this slice. Kept here, named,
    so a coder does not "fix" F1a by deleting it."""

    def test_domain_hint_expansion_still_fans_brand_out_to_customer_and_transporter(self) -> None:
        from app.services.entity_resolver import _DOMAIN_HINT_EXPANSIONS

        assert _DOMAIN_HINT_EXPANSIONS["order"]["brand"] == frozenset(
            {"customer", "customer_order", "transporter"}
        )


def _seed_brand(session_factory, *, name: str, code: str, company_id: str = DEFAULT_COMPANY_ID) -> str:
    db = session_factory()
    set_company_scope(db, frozenset({company_id}))
    row = Brand(id=str(uuid.uuid4()), brand_name=name, brand_code=code, is_active=True, company_id=company_id)
    db.add(row)
    db.commit()
    return row.id


def _seed_contact_scoped_to_sorento(session_factory) -> None:
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_workspaces (id, space_id, name, api_key_ciphertext) "
            "VALUES (gen_random_uuid(), :sid, 'ZZT s9 workspace', 'ZZT-cipher') ON CONFLICT DO NOTHING"
        ),
        {"sid": "364817"},
    )
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars, workspace_id) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb), "
            "(SELECT id FROM respond_workspaces WHERE space_id = :sid LIMIT 1))"
        ),
        {"cid": str(CONTACT_ID), "phone": "+60000000032", "sv": json.dumps({"variables": {}}), "sid": "364817"},
    )
    db.execute(
        text(
            "INSERT INTO respond_contact_companies (id, respond_contact_id, company_id) "
            "SELECT gen_random_uuid(), id, :company_id FROM respond_contacts WHERE respond_io_id = :cid"
        ),
        {"cid": str(CONTACT_ID), "company_id": DEFAULT_COMPANY_ID},
    )
    db.commit()


def _open_question_of(session_factory) -> dict[str, Any]:
    db = session_factory()
    row = db.execute(
        text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :cid"),
        {"cid": str(CONTACT_ID)},
    ).first()
    raw = row.session_vars if row is not None else {}
    parsed = json.loads(raw) if isinstance(raw, str) else (raw or {})
    return parsed.get("open_question") or {}


class TestT2BrandTokenNotResolvedAsCustomerInOrderDomain:
    """T2/T3 end to end (AC-S9-3, AC-S9-5): "brand Sorento" + dealer "Cheng Huat
    Sentul" under `domain_hint: order`. Today NOTHING intercepts a `brand`-hinted
    entity before the shared resolver, so this stub - built to mimic exactly what
    T2/T3's own trace measured (`_DOMAIN_HINT_EXPANSIONS["order"]["brand"]` fanning
    "Sorento" out to a customer AND a transporter match) - is asked about "Sorento"
    at all, and no `brand_ids` ever reaches the tool call. Once the slice lands,
    "Sorento" must resolve locally against the live `brands` table and never reach
    this resolver stub.

    TWO real turns, not one (coordinator round, 26 Sep 2026): granting the SO reveal
    and naming no document word is exactly Contract 38 / AC-1130's own bare-outstanding
    override - `test_outstanding_lane.py::TestCustomerOnlyOutstandingAskReachesTheReport
    ::test_bare_outstanding_customer_only_arms_the_scope_question` pins that a
    customer-only (or, now, customer+brand) subject on the bare word "outstanding"
    arms `outstanding_scope` ("Outstanding for which document?") rather than calling
    the report directly - so turn 1 here grades the brand-resolve half only (no
    tool call yet, brand never reaches the shared resolver, no customer/kind pick),
    and turn 2 answers the scope question ("3" = Both) and grades that the CARRIED
    brand reaches `crm_outstanding_report` alongside the carried customer. Turn 2 is
    the one this file expects to find still red: Samantha's real chat went through
    this exact question (T2), and the coder's own brand-resolve wiring
    (`lanes/business/__init__.py`'s `outstanding_brand_ids` on `semantic_input`) does
    not yet carry it into the scope-ask's own stored `filters`.
    """

    CUSTOMER_UUID = "22222222-2222-2222-2222-222222222222"
    TRANSPORTER_UUID = "33333333-3333-3333-3333-333333333333"
    CHENG_HUAT_UUID = "44444444-4444-4444-4444-444444444444"

    def _resolve_entity(self, asked: list[str]):
        def _fn(body: dict[str, Any]) -> dict[str, Any]:
            tokens = list(body.get("tokens") or [])
            asked.extend(tokens)
            resolutions = []
            for token in tokens:
                if token == "Sorento":
                    # The T2/T3 fan-out, reproduced verbatim (never what a fixed
                    # chatbot should still be asking this seam about).
                    resolutions.append(
                        {
                            "token": token,
                            "resolved": False,
                            "matches": [
                                {
                                    "uuid": self.TRANSPORTER_UUID,
                                    "entity_type": "transporter",
                                    "canonical_code": "Sorento",
                                    "match_tier": "exact",
                                },
                                {
                                    "uuid": self.CUSTOMER_UUID,
                                    "entity_type": "customer",
                                    "canonical_code": "Sorento",
                                    "match_tier": "exact",
                                },
                            ],
                        }
                    )
                elif token == "Cheng Huat Sentul":
                    resolutions.append(
                        {
                            "token": token,
                            "resolved": True,
                            "matches": [
                                {
                                    "uuid": self.CHENG_HUAT_UUID,
                                    "entity_type": "customer",
                                    "canonical_code": "Cheng Huat Sentul",
                                    "match_tier": "exact",
                                }
                            ],
                        }
                    )
            return {"tokens": tokens, "resolutions": resolutions, "unresolved_tokens": []}

        return _fn

    def test_sorento_never_reaches_the_shared_resolver_and_the_report_gets_brand_ids(
        self, session_factory, monkeypatch
    ) -> None:
        from app.services.chatbot import engine as engine_mod
        from app.services.chatbot.head import parser as parser_mod
        from app.services.chatbot.lanes.business.services import AnswerServices

        _seed_contact_scoped_to_sorento(session_factory)
        brand_id = _seed_brand(session_factory, name="Sorento", code="SRT")

        set_chatbot_switches(session_factory, business_lane=True)
        from app.models.user import SystemSetting

        db = session_factory()
        row = db.query(SystemSetting).first()
        if row is None:
            row = SystemSetting()
            db.add(row)
        row.chatbot_completed_lanes = ["business_query"]
        db.commit()

        monkeypatch.setattr(engine_mod, "default_space_id", lambda db: "364817")
        monkeypatch.setattr(
            engine_mod,
            "check_access",
            lambda db, *, agent_code, contact_id, space_id: {
                "allowed": True,
                "decision": "allow",
                "agent_name": "General",
                "attributes": ["sales_orders.outstanding"],
                "all_attributes_allowed": None,
            },
        )

        def fake_resolve_config(db, *, current_date, override_version_id=None):
            return parser_mod.ParserConfig(
                system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test",
            )

        monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
        qf = _parser_output(
            domain_hint="order",
            intent_hint="check_order",
            order_status="outstanding",
            entities=[
                {"raw": "Sorento", "hint": "brand", "canonical_code": None, "current_message": True, "confident": True},
                {
                    "raw": "Cheng Huat Sentul",
                    "hint": "customer",
                    "canonical_code": None,
                    "current_message": True,
                    "confident": True,
                },
            ],
        )
        monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: qf)

        asked: list[str] = []
        resolve_services = ResolveGateServices(
            access_types=lambda **_: [{"name": "Sorento Dealer"}],
            resolve_entity=validating_resolve_entity(self._resolve_entity(asked)),
            probe=lambda **_: None,
        )
        captured: list[tuple[str, dict[str, Any]]] = []

        def mcp_call(name: str, args: dict) -> str:
            captured.append((name, dict(args)))
            return json.dumps({"has_result": False, "items": []})

        monkeypatch.setattr(
            engine_mod.business_services, "production_services", lambda db, *, space_id=None: resolve_services
        )
        monkeypatch.setattr(engine_mod.business_services, "fetch_services", lambda db: FetchServices(mcp_call=mcp_call))
        monkeypatch.setattr(
            engine_mod.business_services,
            "answer_services_for",
            lambda session_factory: AnswerServices(
                mcp_probe=lambda name, args: {"data": []}, family_fetch=lambda query: {"data": []}
            ),
        )

        # -- turn 1: "outstanding brand Sorento dealer Cheng Huat Sentul" -------- #
        envelope = _envelope()
        envelope.message["message"]["message"]["text"] = "outstanding brand Sorento dealer Cheng Huat Sentul"
        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        assert "Sorento" not in asked, (
            f"the brand token must resolve locally against the live brands table and "
            f"never reach the shared resolver's order-domain fan-out: asked={asked!r}"
        )
        assert "Cheng Huat Sentul" in asked, asked

        reply_text = ((result.reply or {}).get("text") or "")
        assert "transporter" not in reply_text.lower(), reply_text
        assert "which customer" not in reply_text.lower(), reply_text

        # Contract 38 / AC-1130: a customer-only (now customer+brand) subject on the
        # BARE "outstanding" word arms the scope question rather than calling the
        # report this turn - `TestCustomerOnlyOutstandingAskReachesTheReport::
        # test_bare_outstanding_customer_only_arms_the_scope_question` pins the
        # identical shape for a customer alone.
        assert captured == [], (
            f"no report/order tool may be called while the scope question is open: {captured}"
        )
        assert "Outstanding for which document?" in reply_text, reply_text
        open_question = _open_question_of(session_factory)
        assert open_question.get("kind") == "outstanding_scope", (
            f"a customer+brand outstanding ask must arm the scope question exactly "
            f"like a product/customer ask does: {open_question!r}"
        )

        # -- turn 2: "3" (Both) answers the scope question ----------------------- #
        qf_turn2 = _parser_output(
            message_type="casual", intent_hint=None, domain_hint=None, entities=[],
            reference_positions=[3],
        )
        monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: qf_turn2)
        envelope2 = _envelope()
        envelope2.message["message"]["messageId"] = "ZZT-s9-brand-scope-answer-1"
        envelope2.message["message"]["message"]["text"] = "3"
        engine_mod.run_turn(envelope2, session_factory=session_factory)

        assert captured, (
            "the scope answer must run crm_outstanding_report on the carried "
            "customer AND brand - it never called any tool at all"
        )
        name, args = captured[-1]
        assert name == "crm_outstanding_report", (name, args)
        assert args.get("customer_ids") == [self.CHENG_HUAT_UUID], (
            f"the carried customer must survive the scope answer: {args}"
        )
        assert args.get("brand_ids") == [brand_id], (
            f"the carried BRAND must survive the scope answer too - the scope-ask's "
            f"own stored filters do not carry `outstanding_brand_ids` yet: {args}"
        )
