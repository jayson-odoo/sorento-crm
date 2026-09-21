"""Hand pass 11, defect 4 - "cabana catalog" must answer with the Cabana catalogue file,
never a kind_pick. RED, test-first.

Owner's local chain (clone, v39, contact 437264483): "cabana catalog" -> "Which one do you
mean? 1. cabana (promotion) 2. cabana (attachment)" -> "2" -> "Here's what you want:
attachment: CABANA WASH BASIN PROMO 09092026 END USER.pdf (+14 more). But no
resource_attachment matched these. Would you like me to escalate to customer service team?"

Measured (captain's brief): the recorded verdict is CORRECT - entities [{raw "cabana", hint
brand, canonical_code null}, {raw "catalog", hint attachment, canonical_code "catalogue"}],
domain_hint resource_attachment, intent get_resource_attachment, domain_in_message true,
routing purchasing. `turn/reconcile.py::apply_reconciliation` (D2, "two kinds hitting asks")
re-kinded the BRAND word (brand miss on the clone + name hits in promotion and attachment)
into a kind_pick; the pick then resolved "cabana" as 15 promo PDFs by filename and the
"catalog" class entity was dropped, so the fetch missed. Production never asks: a
brand/company word under resource_attachment is a SCOPE, and the class word reaches the
tool as the document class (`crm_resource_attachments_list` takes `attachment_type_code`;
`crm_resource_attachments_catalogue` defaults `attachment_type_code: catalogue`, takes
`attachment_ids`; `references.py:85-100` resolves catalog/catalogue variants).

Replay, key-free: the recorded verdict verbatim through `stub_parser`, the resolver stubbed
with the clone's real shape (`turn_runtime.resolve_kinds` counts `matches[].entity_type`
per token - so "cabana" carries a promotion hit AND an attachment hit and NO brand hit,
exactly the clone's), the MCP tools stubbed with the clone's real rows (the file
"@ CABANA CATALOG 2025 (RESEARCHABLE).pdf", type "Direct Access").
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
from tests.chatbot.test_r3_pending_end_to_end import _session_of

LIST_TOOL = "crm_resource_attachments_list"
CATALOGUE_TOOL = "crm_resource_attachments_catalogue"
ATTACHMENT_TOOLS = {LIST_TOOL, CATALOGUE_TOOL}

CABANA_FILE = "@ CABANA CATALOG 2025 (RESEARCHABLE).pdf"
CABANA_FILE_ID = "cab00000-0000-0000-0000-000000000001"
SORENTO_FILE = "@ SORENTO CATALOG 2025 (RESEARCHABLE).pdf"
SORENTO_FILE_ID = "sor00000-0000-0000-0000-000000000001"
CATALOGUE_TYPE_UUID = "cat00000-0000-0000-0000-000000000001"
PROMO_UUID = "pro00000-0000-0000-0000-000000000001"
PROMO_FILE_UUID = "pro00000-0000-0000-0000-000000000002"

ATTACHED_INTRO = "I have attached the file(s) below."
KIND_PICK_QUESTION = "Which one do you mean?"


def _name_hits(brand: str) -> list[dict[str, Any]]:
    """The clone's real resolver shape for a brand word that is NOT a brand row: a name
    hit in `promotion` and a name hit in `attachment` (promo PDFs), no `brand` match."""
    return [
        {
            "uuid": PROMO_UUID, "entity_type": "promotion", "match_tier": "substring",
            "canonical_code": f"{brand.upper()} WASH BASIN PROMO 09092026 END USER",
            "display": {"name": f"{brand.upper()} WASH BASIN PROMO 09092026 END USER"},
        },
        {
            "uuid": PROMO_FILE_UUID, "entity_type": "attachment", "match_tier": "substring",
            "canonical_code": f"{brand.upper()} WASH BASIN PROMO 09092026 END USER.pdf",
            "display": {"original_filename": f"{brand.upper()} WASH BASIN PROMO 09092026 END USER.pdf"},
        },
    ]


def _bundle(brand: str, *, class_token: str = "catalog") -> ResolveGateServices:
    def _resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
        return {
            "tokens": [brand, class_token],
            "resolutions": [
                {"raw": brand, "token": brand, "matches": _name_hits(brand)},
                {
                    "raw": class_token, "token": class_token,
                    "matches": [
                        {
                            "uuid": CATALOGUE_TYPE_UUID, "entity_type": "attachment_type",
                            "canonical_code": "catalogue", "match_field": "code",
                            "match_tier": "exact", "display": {"type_name": "Catalogue"},
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


def _catalogue_envelope(filename: str, file_id: str, company: str) -> dict[str, Any]:
    return {
        "result_type": "resource_attachments",
        "intro": ATTACHED_INTRO,
        "items": [
            {
                "fields": [
                    {"key": "original_filename", "label": "File Name", "value": filename},
                    {"key": "company_name", "label": "Company", "value": company},
                    {"key": "uploaded_at", "label": "Uploaded", "value": "2025-03-01"},
                ]
            }
        ],
        "attachments": [
            {
                "id": file_id, "original_filename": filename, "company_name": company,
                "url": f"https://cdn.example.test/{file_id}.pdf", "content_type": "application/pdf",
            }
        ],
        "has_result": True,
    }


EMPTY = {"result_type": "resource_attachments", "intro": "No matching results found.", "items": [], "has_result": False}


def _wire(session_factory, monkeypatch, brand: str):
    """The clone's rows: a Cabana catalogue for a Cabana-scoped ask, a Sorento one for a
    Sorento-scoped ask - so a brand scope that is honoured returns a DIFFERENT file."""
    from app.models.user import SystemSetting

    set_chatbot_switches(session_factory, business_lane=True)
    db = session_factory()
    for row in db.query(SystemSetting).all():
        row.chatbot_completed_lanes = ["business_query"]
    db.commit()

    calls: list[tuple[str, dict[str, Any]]] = []

    def _mcp_call(name: str, args: dict[str, Any]) -> str:
        calls.append((name, dict(args)))
        if name not in ATTACHMENT_TOOLS:
            return json.dumps({"result_type": "unknown", "items": [], "has_result": False})
        blob = json.dumps(args).lower()
        if "sorento" in blob:
            return json.dumps(_catalogue_envelope(SORENTO_FILE, SORENTO_FILE_ID, "Sorento"))
        if "cabana" in blob:
            return json.dumps(_catalogue_envelope(CABANA_FILE, CABANA_FILE_ID, "Cabana"))
        return json.dumps(EMPTY)

    bundle = _bundle(brand)
    monkeypatch.setattr(
        engine_mod.business_services, "production_services", lambda db, *, space_id=None: bundle
    )
    monkeypatch.setattr(
        engine_mod.business_services, "fetch_services", lambda db: FetchServices(mcp_call=_mcp_call)
    )
    return calls


def _recorded_verdict(brand: str, class_word: str = "catalog") -> dict[str, Any]:
    """The owner's recorded verdict, verbatim in every field that matters."""
    return _parser_output(
        intent_hint="get_resource_attachment",
        domain_hint="resource_attachment",
        domain_in_message=True,
        entities=[
            {"raw": brand, "hint": "brand", "canonical_code": None, "current_message": True, "confident": True},
            {"raw": class_word, "hint": "attachment", "canonical_code": "catalogue", "current_message": True, "confident": True},
        ],
        routing={"suggested_team": "purchasing", "suggested_agent": "general_enquiries", "team_source": None},
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


def _sent_files(result) -> list[str]:
    names: list[str] = []
    for a in result.actions or []:
        if isinstance(a, dict) and a.get("kind") == "send_attachments":
            for f in a.get("attachments_src") or a.get("attachments") or []:
                if isinstance(f, dict):
                    names.append(str(f.get("original_filename") or f.get("filename") or f.get("name") or ""))
    return names


class TestBrandWordUnderResourceAttachmentIsAScopeNotAKindPick:
    @pytest.mark.parametrize("text", ["may i hv cabana catalogue", "cabana catalog"])
    def test_no_kind_pick_is_minted(
        self, text, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        """(a) a brand-hinted entity under a resource_attachment plan is never re-kinded."""
        _wire(session_factory, monkeypatch, "cabana")
        stub_access()
        result = _turn(session_factory, stub_parser, _recorded_verdict("cabana"), text=text, msg_id=f"ZZT-r11-cat-{len(text)}")
        assert result.status == "done", result.error
        said = _said(result)
        assert KIND_PICK_QUESTION not in said, said
        assert "(promotion)" not in said and "(attachment)" not in said, said
        assert (_session_of(session_factory).get("open_question") or {}).get("kind") != "kind_pick", (
            _session_of(session_factory).get("open_question")
        )

    def test_the_class_entity_reaches_the_tool_as_the_document_class(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        """(b) canonical_code "catalogue" narrows the tool call - `attachment_type_code`
        or resolved `attachment_ids` - never dropped."""
        calls = _wire(session_factory, monkeypatch, "cabana")
        stub_access()
        _turn(session_factory, stub_parser, _recorded_verdict("cabana"), text="cabana catalog", msg_id="ZZT-r11-cat-tool")
        attachment_calls = [args for name, args in calls if name in ATTACHMENT_TOOLS]
        assert attachment_calls, f"the resource attachment tool must run, no miss without a fetch: {calls}"
        args = attachment_calls[0]
        type_code = str(args.get("attachment_type_code") or "").lower()
        ids = args.get("attachment_ids") or []
        assert type_code.startswith("catalog") or ids, (
            "the document class must reach the tool as attachment_type_code or attachment_ids", args
        )

    def test_the_reply_is_the_attachment_form_with_the_cabana_catalogue(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        """(c) production's attachment reply, the Cabana catalogue in `send_attachments`."""
        _wire(session_factory, monkeypatch, "cabana")
        stub_access()
        result = _turn(session_factory, stub_parser, _recorded_verdict("cabana"), text="cabana catalog", msg_id="ZZT-r11-cat-reply")
        said = _said(result)
        assert ATTACHED_INTRO in said, said
        assert "no resource_attachment matched" not in said.lower(), said
        assert "escalate" not in said.lower(), said
        assert CABANA_FILE in _sent_files(result), (result.actions,)

    def test_sorento_and_cabana_catalogues_are_different_files(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        """(d) the brand scope is honoured: two brands, two files."""
        _wire(session_factory, monkeypatch, "cabana")
        stub_access()
        cabana = _turn(session_factory, stub_parser, _recorded_verdict("cabana", "catalogue"), text="cabana catalogue", msg_id="ZZT-r11-cat-d1")
        _wire(session_factory, monkeypatch, "sorento")
        sorento = _turn(session_factory, stub_parser, _recorded_verdict("sorento", "catalogue"), text="sorento catalogue", msg_id="ZZT-r11-cat-d2")
        cabana_files, sorento_files = _sent_files(cabana), _sent_files(sorento)
        assert CABANA_FILE in cabana_files, (cabana.actions,)
        assert SORENTO_FILE in sorento_files, (sorento.actions,)
        assert set(cabana_files).isdisjoint(sorento_files), (cabana_files, sorento_files)


class TestGenuinelyAmbiguousWordStillAsks:
    def test_control_two_real_kinds_under_a_non_scope_hint_mint_the_kind_pick(
        self, session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        """(e) CONTROL, green today: D2 kept - "cabana" typed as a PRODUCT under a stock ask,
        with a promotion hit and an attachment hit and no product, still asks."""
        _wire(session_factory, monkeypatch, "cabana")
        stub_access()
        result = _turn(
            session_factory, stub_parser,
            _parser_output(
                intent_hint="check_stock", domain_hint="inventory",
                entities=[{"raw": "cabana", "hint": "product", "canonical_code": None, "current_message": True, "confident": True}],
            ),
            text="cabana stock", msg_id="ZZT-r11-cat-control",
        )
        assert result.status == "done", result.error
        assert KIND_PICK_QUESTION in _said(result), _said(result)
        assert (_session_of(session_factory).get("open_question") or {}).get("kind") == "kind_pick"
