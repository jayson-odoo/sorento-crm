"""Hand pass 11, finding 2 - a CERTIFICATE miss must offer the purchasing certification
team (owner ruling: "for cert is to direct to purchasing certification team"). RED,
test-first.

Owner's local turn: "7408 CERTIFICATE" -> did-you-mean -> "1" (SRTWT7408-HANDLE) -> "But
no attachment matched these. Would you like me to escalate to marketing product team?"
Wrong team.

Measured cause (captain's brief): origin/main's `head/output_exchange.py:85-120` (deleted
by S3) routed `product_attachment` + `is_cert` deterministically to
`purchasing_certification` (else `marketing_product`). The lane reads the parser's
`routing.suggested_team` raw (`answer_bridge.py:580`, `turn_runtime.lane_parse_output`);
the v39 prompt says certificate -> purchasing_certification but the rendered domain block
(from `chatbot_domains.escalation_team_code = marketing_product`) contradicts it and the
parser follows the block. The coder re-attaches the rule POST-LLM keyed on the RESOLVED
attachment type row (`attachment_types.is_certificate`), never a regex over the customer's
text (D11) - so every case below seeds a REAL `attachment_types` row and hands its uuid to
the resolver stub, exactly as `test_product_attachment_picker_stamp.py`'s harness does.

Harness: a real `engine.run_turn` (Postgres blank schema), the parser/access/resolver/MCP
tool stubbed, the escalation lane spied on the "yes" turn the same way
`test_rearch_r4_answering_a_miss.py` does. No live parser, no :8766, no API key.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.chatbot import engine as engine_mod
from app.services.chatbot.lanes.business.services import FetchServices, ResolveGateServices
from tests.chatbot.conftest import set_chatbot_switches, validating_resolve_entity
from tests.chatbot.test_engine import (  # noqa: F401 - fixtures re-exported by name
    _envelope,
    _parser_output,
    seeded,
    stub_access,
    stub_parser,
)
from tests.chatbot.test_product_attachment_picker_stamp import _seed_attachment_type
from tests.chatbot.test_r3_pending_end_to_end import _session_of
from tests.chatbot.test_rearch_r4_answering_a_miss import _fake_escalation_lane

ATTACHMENT_TOOL = "crm_master_product_attachments_list"
PRODUCT_CODE = "SRTWT7408-HANDLE"
PRODUCT_UUID = "74080000-0000-0000-0000-000000000001"

# The clone's real Certification row (tester 38's `_REAL_ATTACHMENT_TYPE_DESCRIPTIONS`).
CERT_TYPE_NAME = "Certification"
CERT_DESCRIPTION = "Certification, Cert, Certificate, Watermark Cert, WCM, PPS, Ikram by Purchasing"
PHOTO_TYPE_NAME = "Product Photos"
SPECS_TYPE_NAME = "Technical Specifications"

CERT_OFFER = "escalate to purchasing certification team"
MARKETING_OFFER = "escalate to marketing product team"


def _bundle(type_uuid: str, type_name: str) -> ResolveGateServices:
    """The product resolves exactly; the attachment-type token resolves to the seeded
    `attachment_types` row (uuid = the real row id, so a post-LLM rule can read
    `is_certificate` off it)."""

    def _resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
        return {
            "tokens": [PRODUCT_CODE, type_name.lower()],
            "resolutions": [
                {
                    "raw": PRODUCT_CODE,
                    "token": PRODUCT_CODE,
                    "matches": [
                        {
                            "uuid": PRODUCT_UUID, "entity_type": "product",
                            "canonical_code": PRODUCT_CODE, "match_tier": "exact",
                        }
                    ],
                },
                {
                    "raw": type_name.lower(),
                    "token": type_name.lower(),
                    "matches": [
                        {
                            "uuid": type_uuid, "entity_type": "attachment_type",
                            "canonical_code": type_name, "match_field": "type_name",
                            "match_tier": "substring", "display": {"type_name": type_name},
                        }
                    ],
                },
            ],
            "unresolved_tokens": [],
        }

    return ResolveGateServices(
        access_types=lambda **_: [{"name": "Sorento Dealer"}],
        resolve_entity=validating_resolve_entity(_resolve_entity),
        probe=lambda **_: None,
    )


def _wire(session_factory, monkeypatch, *, type_uuid: str, type_name: str) -> list[str]:
    from app.models.user import SystemSetting

    set_chatbot_switches(session_factory, business_lane=True)
    db = session_factory()
    for row in db.query(SystemSetting).all():
        row.chatbot_completed_lanes = ["business_query"]
    db.commit()

    probes: list[str] = []

    def _mcp_call(name: str, args: dict[str, Any]) -> str:
        probes.append(name)
        # A MISS: no file of that type for that product.
        return json.dumps(
            {"result_type": "product_attachments", "intro": "No matching results found.", "items": [], "has_result": False}
        )

    bundle = _bundle(type_uuid, type_name)
    monkeypatch.setattr(
        engine_mod.business_services, "production_services", lambda db, *, space_id=None: bundle
    )
    monkeypatch.setattr(
        engine_mod.business_services, "fetch_services", lambda db: FetchServices(mcp_call=_mcp_call)
    )
    return probes


def _miss_verdict(type_word: str, canonical: str, *, suggested_team: str | None) -> dict[str, Any]:
    return _parser_output(
        intent_hint="check_product_attachment",
        domain_hint="product_attachment",
        entities=[
            {"raw": PRODUCT_CODE, "hint": "product", "canonical_code": None, "current_message": True, "confident": True},
            {"raw": type_word, "hint": "attachment_type", "canonical_code": canonical, "current_message": True, "confident": True},
        ],
        routing={"suggested_team": suggested_team, "suggested_agent": "general_enquiries", "team_source": None},
    )


def _turn(session_factory, stub_parser, verdict: dict[str, Any], *, text: str, msg_id: str):
    stub_parser(verdict)
    envelope = _envelope()
    envelope.message["message"]["messageId"] = msg_id
    envelope.message["message"]["message"]["text"] = text
    return engine_mod.run_turn(envelope, session_factory=session_factory)


def _said(result) -> str:
    return "\n".join(
        [((result.reply or {}).get("text") or "")]
        + [a.get("text") or "" for a in (result.actions or []) if isinstance(a, dict)]
    )


# --------------------------------------------------------------------------- #
# The certificate miss names purchasing certification, on the offer AND the pending
# --------------------------------------------------------------------------- #


class TestCertificateMissOffersPurchasingCertification:
    @pytest.mark.parametrize(
        "suggested_team",
        [
            pytest.param(None, id="parser-names-no-team"),
            # The v39 parser FOLLOWS the rendered domain block and says marketing_product
            # for a certificate ask (measured) - the resolved row's own `is_certificate`
            # must win over it.
            pytest.param("marketing_product", id="parser-says-marketing-product"),
        ],
    )
    def test_the_offer_sentence_and_the_pending_team_are_purchasing_certification(
        self, suggested_team, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        type_uuid = _seed_attachment_type(
            session_factory, CERT_TYPE_NAME, description=CERT_DESCRIPTION, is_certificate=True
        )
        probes = _wire(session_factory, monkeypatch, type_uuid=type_uuid, type_name=CERT_TYPE_NAME)
        stub_access()

        result = _turn(
            session_factory, stub_parser,
            _miss_verdict("certificate", "certification", suggested_team=suggested_team),
            text=f"{PRODUCT_CODE} CERTIFICATE", msg_id="ZZT-r11-cert-miss-1",
        )
        assert result.status == "done", result.error
        assert ATTACHMENT_TOOL in probes, "the attachment tool must be asked before a miss is declared"
        said = _said(result)
        assert CERT_OFFER in said, said
        assert MARKETING_OFFER not in said, said

        open_question = _session_of(session_factory).get("open_question") or {}
        assert open_question.get("team") == "purchasing_certification", (
            "the pending's team stamp must be the team the sentence named", open_question
        )

    def test_yes_over_the_certificate_offer_escalates_to_purchasing_certification(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        type_uuid = _seed_attachment_type(
            session_factory, CERT_TYPE_NAME, description=CERT_DESCRIPTION, is_certificate=True
        )
        _wire(session_factory, monkeypatch, type_uuid=type_uuid, type_name=CERT_TYPE_NAME)
        stub_access()
        _turn(
            session_factory, stub_parser,
            _miss_verdict("certificate", "certification", suggested_team="marketing_product"),
            text=f"{PRODUCT_CODE} CERTIFICATE", msg_id="ZZT-r11-cert-yes-1",
        )

        calls: list[tuple[Any, Any]] = []
        monkeypatch.setattr(engine_mod, "run_escalation_lane", _fake_escalation_lane(calls))
        result = _turn(
            session_factory, stub_parser,
            _parser_output(
                message_type="casual", intent_hint=None, domain_hint=None, entities=[],
                is_affirmative=True,
            ),
            text="yes", msg_id="ZZT-r11-cert-yes-2",
        )
        assert result.branch_kind == "out_of_scope", (result.branch_kind, result.error)
        assert len(calls) == 1, calls
        ctx, _item = calls[0]
        output = ((ctx.get("parse") or {}).get("output")) or {}
        assert (output.get("routing") or {}).get("suggested_team") == "purchasing_certification", (
            output.get("routing")
        )


# --------------------------------------------------------------------------- #
# CONTROL, green today: a non-certificate type keeps the marketing product team
# --------------------------------------------------------------------------- #


class TestNonCertificateMissKeepsMarketingProduct:
    @pytest.mark.parametrize(
        "type_name,type_word,canonical",
        [
            pytest.param(PHOTO_TYPE_NAME, "photo", "photo", id="photo"),
            pytest.param(SPECS_TYPE_NAME, "technical specs", "technical_specifications", id="technical-specs"),
        ],
    )
    def test_photo_and_specs_misses_offer_marketing_product(
        self, type_name, type_word, canonical, session_factory, seeded, stub_parser, stub_access,
        system_settings_row, monkeypatch,
    ) -> None:
        type_uuid = _seed_attachment_type(session_factory, type_name, is_certificate=False)
        _wire(session_factory, monkeypatch, type_uuid=type_uuid, type_name=type_name)
        stub_access()
        result = _turn(
            session_factory, stub_parser,
            _miss_verdict(type_word, canonical, suggested_team="marketing_product"),
            text=f"{PRODUCT_CODE} {type_word}", msg_id=f"ZZT-r11-{canonical}-miss-1",
        )
        assert result.status == "done", result.error
        said = _said(result)
        assert MARKETING_OFFER in said, said
        assert CERT_OFFER not in said, said
        open_question = _session_of(session_factory).get("open_question") or {}
        assert open_question.get("team") == "marketing_product", open_question
