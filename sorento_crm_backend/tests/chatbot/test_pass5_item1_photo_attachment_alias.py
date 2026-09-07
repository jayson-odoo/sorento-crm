"""Owner console pass 5, item 1 (TOP, 7 Sep 2026, prod regression against #713):
"send me the photo of SRTWC8517-SH-UF" (biz-attach-d) stopped resolving the "photo"
attachment-type alias deterministically. Production turns
a5317cf4-3e87-45c9-89e1-cdc0e9eab7a0 and b4369aba-7bf3-45f7-9e98-6e8597393de0 (two cold,
byte-identical runs, `turns-lane3`; pre-deploy control `008676fc-e1d6-4504-8715-84aa54c81bb2`,
same request 3 minutes earlier, resolved clean and sent the file), vendored at
`tests/fixtures/chatbot/`. Both post-deploy runs reply "Couldn't find some items:\\n\\n
\"photo\" (attachment type) - did you mean:\\n  1. Product Photos ...", one
`send_message`, no `send_attachments`.

**ROOT CAUSE, found by the captain and verified here.** The deploy that shipped #713
(043e2a0be) also carried #707, whose migration `485_shipment_line_photo_type.py` seeds a
NEW `attachment_types` row - `code="shipment_line_photo",
type_name="Shipment Line Photo"` (and `code="proforma_invoice",
type_name="Proforma Invoice"`, `code="packing_list"` update-only). Confirmed by reading the
migration verbatim and by querying the local prod-copy DB read-only (`psql`, no writes):
`attachment_types` carries `90e76894-8384-4186-a3f7-ef73667726ff` "Product Photos" (no
migration seeds it - pre-existing admin data, `code IS NULL`) AND
`96d71584-d305-4054-b246-213cc0bbc79d` "Shipment Line Photo" side by side, and
"Shipment Line Photo" contains the substring "photo" case-insensitively.

**MEASURED, not guessed, exactly what "photo" resolves to today.** In-process,
read-only (`SessionLocal`, a nested transaction rolled back at the end, never committed,
`OPENAI_API_KEY` never set), calling `resolve_reference_post` with the EXACT body
`resolve_gate.resolve_entity_body` builds for this capture (`tokens:
["SRTWC8517SHUF", "photo"]`, `match_mode: "and"`,
`allowed_entity_types: ["product", "attachment_type"]`, `spec_fallback` forced off - the
one seam this Postgres-only harness cannot touch, per
`documentation/agents/chatbot-verification.md`):

* the AND-mode intersection returns ZERO rows and the route falls back to OR-mode
  (`fallback_reason: "AND-mode produced zero intersection; switched to OR-mode..."`,
  `app/api/v1/system/references.py` ~1845-1856);
* in OR-mode, `entity_resolver.py`'s Tier 2 substring probe
  (`_prefix_probe_attachment_type`, ~2381-2483, the `elif token_lower in code_l or
  token_lower in type_l or token_lower in desc_l:` branch ~2460) returns BOTH
  "Product Photos" and "Shipment Line Photo" for "photo" - `resolved: false,
  ambiguous: true`, exactly two matches, both `match_tier: "substring"`.

**Where the ambiguity actually goes: an asymmetry in `gate.py`'s own per-token OR-mode
classifier, `run_gate` ~319-394.** For a `product` token this file's own logic is careful:
several genuinely distinct products stay ambiguous and are handed to the customer as a
numbered pick (`specific_options` / `still_ambiguous`, ~450-495). For a NON-product token
(attachment_type, certificate, ...) the SAME function has no such path - `~360-393`:
`np_exact = [m for m in non_products if match_tier == "exact"]`; when that is empty (no
exact hit - exactly "photo"'s shape, both hits are substring-tier) and the candidates do
not share one code, the function falls to `picks = [non_products[0]]` (line 393) - it
SILENTLY keeps whichever candidate the database happened to return first, with no
`resolved_by` marker, so `miss_suggest.py`'s own miss list still carries "photo" as an
open, unresolved token regardless of what the gate silently picked.

**#713's own diff, for the record.** `git diff 5e8acfef4..043e2a0be --
sorento_crm_backend/app` touches exactly seven files: `head/output_exchange.py`,
`head/parser.py`, `contracts.py`, `lanes/escalation.py`, `tail/compile_state.py`,
`tail/pending.py`, `chatbot_parser_prompt.py`. NONE of `entity_resolver.py`,
`api/v1/system/references.py`, `lanes/business/{gate,answer,miss_suggest,resolve_gate}.py`
changed. `#713`'s own diff is not the cause; `#707`'s migration, deployed the same run,
is.

**The FIX is domain-scoped resolution** (`entity_resolver._product_attachment_type_ids`) -
see that function's own docstring for the two-pass account: the first cut filtered
`attachments.entity_type == 'product'`, which is EMPTY in production (a product's file is
linked via `product_attachments`, never via `attachments.entity_type`) and left "photo"
exactly as ambiguous as before; corrected to join through `product_attachments`.

**How `send_attachments` is actually reached, crossed at the real seam (review of this
item, round 1, B1/Q1/#727).** The first cut's `_no_tool_fetch_services` stubbed
`tool_search` to `[]`, which makes `lanes/business/__init__.py::run_fetch` return
`not_found` at its own `pick.outcome == "not_found"` guard (~289-292) BEFORE `mcp_call` is
ever reached - so the stub's own decision, not a missing fetch mechanism, is what kept
`send_attachments` out of `result.actions`. `product_attachment` DOES have a fetch path:
`crm_master_product_attachments_list`, chosen by `tool_search` (an embedding call, needing
`OPENAI_API_KEY`) and then called over MCP (`mcp_call`, returning a STRING -
`MCPRuntimeClient.call_tool`'s own return shape, `"\n".join(content[].text)`). Both are
`FetchServices` seams (`services.py:95-105`) a test may stub independently: `tool_search`
is faked here (deterministic tool choice, the same test-worthy substitute the resolver
seam tests already make for `embed`/vector search); `mcp_call` uses the REAL production
binding, with only `MCPRuntimeClient.call_tool` monkeypatched to the STRING shape it
actually returns - the same recipe
`test_s6a_gate_dry_run_and_seams.py::TestOwnerRulingATheCustomerPickerReachesTheProductionProbeSeam`
already uses for the resolver's own probe seam. AC-604 (module docstring ~770-773 of
`lanes/business/fetch.py`) says a zero-tool turn gets a DISTINGUISHABLE `not_found`
outcome; it does not claim `product_attachment` has no deterministic fetch, and this file's
first cut over-read it into that claim. Corrected: **Closes #727** (opened, then found
invalid on measurement) - there was no "materially larger, security-relevant" gap to
build; the harness was stubbing the wrong seam.

Below: `TestPass5Item1PhotoAliasAgainstTheRealMigrationSeededData` seeds exactly the rows
migrations `021_add_attachment_type_code_and_complaint_document.py` (pre-existing
"Product Photos" admin row, unaffected) and `485_shipment_line_photo_type.py`
("Shipment Line Photo", "Proforma Invoice") produce, plus the product marked discontinued
(`is_discontinued=True`) as the control dump's own `(PRODUCT DISCONTINUED)` flag shows,
linked through `product_attachments` the way a real product photo actually is (`Attachment`
with `entity_type=None`, the production shape - not `entity_type="product"`, which the
first cut of this file wrongly seeded and no production row carries), and asserts the two
things the AC actually wants: (1) "photo" resolves to Product Photos with NO did-you-mean,
and (2) the product resolves by its exact code and the turn reaches `send_attachments` with
the correct tool call args.
"""
from __future__ import annotations

from typing import Any

from app.models.product import Product, ProductAttachment, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment, AttachmentType
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.lanes.business import services as business_services_mod
from app.services.chatbot.lanes.business.services import FetchServices
from tests._pg_fixture import unique_code
from tests.chatbot.conftest import set_chatbot_switches
from tests.chatbot.test_engine import _parser_output, stub_access, stub_parser  # noqa: F401
from tests.chatbot.test_engine_company_scope import (
    _scope_envelope,
    _seed_company,
    _seed_contact,
    _seed_workspace,
    _set_completed_lanes,
    _wire_answer_services,
    _wire_real_resolve_entity,
)

PRODUCT_CODE = "SRTWC8517-SH-UF"

# The real local prod-copy uuids/names (psql, read-only, 7 Sep 2026) - not invented.
PRODUCT_PHOTOS_UUID = "90e76894-8384-4186-a3f7-ef73667726ff"
SHIPMENT_LINE_PHOTO_UUID = "96d71584-d305-4054-b246-213cc0bbc79d"
PROFORMA_INVOICE_UUID = "01f3e406-f21d-4423-8602-eefac4a37be2"


def _seed_discontinued_product(session_factory: Any, *, company_id: str, code: str) -> str:
    """`test_engine_company_scope._seed_product`, plus `is_discontinued=True` - the
    control dump's own `(PRODUCT DISCONTINUED)` flag, not invented."""
    db = session_factory()
    category = ProductCategory(
        category_code=unique_code("CAT")[:50], category_name="ZZT photo-alias category", company_id=company_id
    )
    uom = UnitOfMeasure(uom_code=unique_code("UOM")[:20], uom_name="Each", company_id=company_id)
    db.add_all([category, uom])
    db.flush()
    product = Product(
        product_code=code,
        product_name=f"ZZT photo-alias product {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=10,
        is_active=True,
        is_discontinued=True,
        company_id=company_id,
    )
    db.add(product)
    db.commit()
    return product.id


def _seed_migration_attachment_types(session_factory: Any) -> None:
    """The rows `021_add_attachment_type_code_and_complaint_document.py` (Product Photos
    predates that migration, admin data, `code IS NULL`) and
    `485_shipment_line_photo_type.py` (`_TYPES` tuple, verbatim) produce - same
    uuids/codes/names as the real local prod-copy DB, queried read-only via `psql`."""
    db = session_factory()
    db.add_all(
        [
            AttachmentType(
                id=PRODUCT_PHOTOS_UUID,
                code=None,
                type_name="Product Photos",
                allowed_extensions="jpg,jpeg,png,webp,gif",
                max_file_size_mb=10,
            ),
            AttachmentType(
                id=SHIPMENT_LINE_PHOTO_UUID,
                code="shipment_line_photo",
                type_name="Shipment Line Photo",
                allowed_extensions="jpg,jpeg,png,webp,gif",
                max_file_size_mb=10,
            ),
            AttachmentType(
                id=PROFORMA_INVOICE_UUID,
                code="proforma_invoice",
                type_name="Proforma Invoice",
                allowed_extensions="xlsx,xls,pdf",
                max_file_size_mb=10,
            ),
        ]
    )
    db.commit()


def _seed_product_attachment(session_factory: Any, *, product_id: str, attachment_type_id: str) -> str:
    """The PRODUCTION linkage (review of this item, round 1, blocker B2): a product's own
    file is a `product_attachments` row pointing at an `Attachment` whose OWN
    `entity_type` is NULL - measured against the local prod-copy database (4302 of 4430
    attachment rows carry a NULL `entity_type`; ZERO carry `entity_type='product'`). The
    first cut of this file seeded `Attachment(entity_type="product")` with no
    `product_attachments` row at all, a shape no production row has, which is why
    `_product_attachment_type_ids`'s own first cut (filtering on `entity_type='product'`)
    read as green here while returning an EMPTY set against the real database."""
    db = session_factory()
    attachment = Attachment(
        attachment_type_id=attachment_type_id,
        original_filename=f"{PRODUCT_CODE}-photo.jpg",
        stored_filename="zzt-a5317cf4-stored.jpg",
        file_path="https://example.test/zzt-a5317cf4-stored.jpg",
        entity_type=None,
        entity_id=None,
    )
    db.add(attachment)
    db.flush()
    link = ProductAttachment(product_id=product_id, attachment_id=attachment.id)
    db.add(link)
    db.commit()
    return attachment.id


# The tool the resolved product_attachment domain calls - `sub_answer.py`'s own
# domain -> tool pairing (`"domain": "product_attachment"`).
_PRODUCT_ATTACHMENTS_TOOL = "crm_master_product_attachments_list"


def _photo_fetch_services(db: Any, monkeypatch: Any, *, calls: list[tuple[str, dict]]) -> FetchServices:
    """Crosses the REAL fetch seam (review of this item, round 1, Q1/#727): `tool_search`
    is faked to a deterministic pick (an embedding call needs `OPENAI_API_KEY`, which is
    absent everywhere this suite runs), and `mcp_call` is the PRODUCTION binding
    (`business_services.fetch_services(db).mcp_call`) with only
    `MCPRuntimeClient.call_tool` monkeypatched to the STRING shape it actually returns -
    the same recipe `test_s6a_gate_dry_run_and_seams.py::
    TestOwnerRulingATheCustomerPickerReachesTheProductionProbeSeam` already uses for the
    resolver's own probe seam. `calls` records every `(tool_name, args)` the real
    `entity_ids_transformer` built, so a test can assert on the ACTUAL args sent, not on
    what it expects them to be.
    """
    import json as _json

    from app.services.ai_assistant_service import MCPRuntimeClient

    def _fake_call_tool(self_client: Any, tool_name: str, args: dict[str, Any]) -> str:
        calls.append((tool_name, dict(args)))
        return _json.dumps(
            {
                "items": [
                    {
                        "title": PRODUCT_CODE,
                        "fields": [
                            {"label": "Product Code", "value": PRODUCT_CODE},
                            {"label": "Attachment Type", "value": "Product Photos"},
                        ],
                        "attachments": [
                            {
                                "url": "https://example.test/zzt-a5317cf4-stored.jpg",
                                "filename": f"{PRODUCT_CODE}-photo.jpg",
                                "mimeType": "image/jpeg",
                                "attachmentType": "Product Photos",
                            }
                        ],
                    }
                ],
                "attachments": [
                    {
                        "url": "https://example.test/zzt-a5317cf4-stored.jpg",
                        "filename": f"{PRODUCT_CODE}-photo.jpg",
                        "mimeType": "image/jpeg",
                        "attachmentType": "Product Photos",
                    }
                ],
                "action_links": [],
                "intro": "Here are the product files I found.",
                "has_result": True,
            }
        )

    monkeypatch.setattr(MCPRuntimeClient, "call_tool", _fake_call_tool)

    base = business_services_mod.fetch_services(db)

    def _tool_search(embedding: Any, *, query: str, domain: Any) -> Any:
        return [{"name": _PRODUCT_ATTACHMENTS_TOOL, "similarity": 0.95}]

    return FetchServices(embed=lambda query: [0.0], tool_search=_tool_search, mcp_call=base.mcp_call)


def _photo_attachment_type_entities() -> list[dict[str, Any]]:
    """The two `parse.output.entities` the a5317cf4 / b4369aba `_parser_raw` carry,
    verbatim (raw text, hint and canonical_code copied from the vendored fixture)."""
    return [
        {
            "raw": PRODUCT_CODE,
            "hint": "product",
            "canonical_code": None,
            "current_message": True,
            "confident": True,
        },
        {
            "raw": "photo",
            "hint": "attachment_type",
            "canonical_code": "photo",
            "current_message": True,
            "confident": True,
        },
    ]


def _run_turn_seeded(
    session_factory,
    stub_parser,
    stub_access,
    system_settings_row,
    monkeypatch,
    *,
    contact_id: str,
    calls: list[tuple[str, dict]],
):
    company_id = _seed_company(session_factory, name="ZZT PhotoAlias Co")
    product_id = _seed_discontinued_product(session_factory, company_id=company_id, code=PRODUCT_CODE)
    _seed_migration_attachment_types(session_factory)
    _seed_product_attachment(
        session_factory, product_id=product_id, attachment_type_id=PRODUCT_PHOTOS_UUID
    )
    workspace_id = _seed_workspace(session_factory)
    _seed_contact(
        session_factory,
        contact_id=contact_id,
        phone="+60000000103",
        workspace_id=workspace_id,
        company_ids=[company_id],
    )

    set_chatbot_switches(session_factory, business_lane=True)
    _set_completed_lanes(session_factory, system_settings_row, ["business_query"])
    _wire_real_resolve_entity(monkeypatch)
    _wire_answer_services(monkeypatch)
    fetch_services = _photo_fetch_services(session_factory(), monkeypatch, calls=calls)
    monkeypatch.setattr(
        engine_mod.business_services, "fetch_services", lambda db: fetch_services
    )

    stub_parser(
        _parser_output(
            message_type="business_query",
            intent_hint="check_product_attachment",
            domain_hint="product_attachment",
            entities=_photo_attachment_type_entities(),
            routing={"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"},
        )
    )
    stub_access()

    return engine_mod.run_turn(
        _scope_envelope(
            contact_id, message_id="ZZT-msg-photo-alias-a5317cf4", text=f"send me the photo of {PRODUCT_CODE}"
        ),
        session_factory=session_factory,
    )


class TestPass5Item1PhotoAliasAgainstTheRealMigrationSeededData:
    """The real seed - `Product Photos` (pre-existing) PLUS `Shipment Line Photo` /
    `Proforma Invoice` (`485_shipment_line_photo_type.py`) - production's actual shape,
    linked through `product_attachments` the way a real product photo actually is.
    Watched red on 043e2a0be."""

    def test_photo_resolves_to_product_photos_with_no_did_you_mean(
        self, session_factory, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        result = _run_turn_seeded(
            session_factory,
            stub_parser,
            stub_access,
            system_settings_row,
            monkeypatch,
            contact_id="ZZT-contact-photo-alias-1",
            calls=[],
        )
        reply_text = (result.reply or {}).get("text") or ""

        # THE RED ASSERTION (1): today, a second real attachment_types row that shares
        # the substring "photo" ("Shipment Line Photo", migration 485) makes this
        # ambiguous - gate.py's own non-product ambiguity handling (~360-393) either
        # silently keeps whichever row the DB returns first (no did-you-mean, but a
        # SILENT, non-deterministic pick - not the deterministic "Product Photos" the AC
        # wants either) or, once that picked type's own fetch comes up empty, surfaces
        # a did-you-mean. Neither is the AC's ask: a DETERMINISTIC resolution, asserted
        # here as a same-turn absence of any did-you-mean AND explicit confirmation the
        # gate landed on Product Photos specifically (not merely "landed on something").
        assert "did you mean" not in reply_text.lower(), (
            "an ambiguous 'photo' either silently mis-picks or falls to a did-you-mean - "
            f"see this test's docstring for the measured mechanism: {reply_text!r}"
        )
        db = session_factory()
        from app.models.chatbot_turn import ChatbotTurn

        row = db.query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()
        looked_up = next(r for r in row.trace if r["stage"] == "looked_up" and r["status"] == "ok")
        gate = looked_up["raw"]["resolve_gate"]["ctx"]["gate"]
        compatible_codes = {
            e["code"] for e in gate.get("compatible_entities", []) if e.get("entity_type") == "attachment_type"
        }
        assert compatible_codes == {"Product Photos"}, (
            "the turn must land on Product Photos deterministically, not on whichever "
            f"candidate the DB happened to return first: {compatible_codes!r}"
        )

        # THE ACTUAL KILL TEST (review round 2): `compatible_codes` alone does not kill,
        # because gate.py:393's silent `non_products[0]` pick can ALSO land on "Product
        # Photos" by DB row order with the domain scoping removed - measured, this seed
        # order does exactly that, so the assertion above stays green with
        # `entity_resolver._product_attachment_type_ids` disabled and proves nothing about
        # this item's own fix. What the fix actually changes is the RESOLVER's own
        # candidate set for the "photo" token - two matches (Product Photos AND Shipment
        # Line Photo) without the scoping, one WITH it - so pin that directly, on the
        # resolver's own `resolutions`, which is what gate.py's non-product branch reads.
        photo_resolution = next(r for r in gate.get("resolutions", []) if r.get("token") == "photo")
        photo_matches = photo_resolution.get("matches") or []
        assert len(photo_matches) == 1, (
            "the RESOLVER itself must return exactly one candidate for \"photo\" once "
            "domain-scoped - two candidates (Product Photos AND Shipment Line Photo) is "
            f"the pre-fix shape, and gate.py's own silent pick can land on either by row "
            f"order regardless of this test's other assertions: {photo_matches!r}"
        )
        assert photo_matches[0].get("canonical_code") == "Product Photos", photo_matches


    def test_product_resolves_exact_and_send_attachments_is_reached(
        self, session_factory, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        """THE FIX end to end, crossing the real fetch seam (review round 1, Q1/#727):
        the resolved product + attachment_type reach `crm_master_product_attachments_list`
        with the correct filter args, and the turn's own actions carry `send_attachments`
        with the file the seeded `product_attachments` link names."""
        calls: list[tuple[str, dict]] = []
        result = _run_turn_seeded(
            session_factory,
            stub_parser,
            stub_access,
            system_settings_row,
            monkeypatch,
            contact_id="ZZT-contact-photo-alias-2",
            calls=calls,
        )

        db = session_factory()
        from app.models.chatbot_turn import ChatbotTurn

        row = db.query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).first()
        looked_up = next(r for r in row.trace if r["stage"] == "looked_up" and r["status"] == "ok")
        gate = looked_up["raw"]["resolve_gate"]["ctx"]["gate"]
        product_entities = [
            e for e in gate.get("compatible_entities", []) if e.get("entity_type") == "product"
        ]
        assert any(e.get("code") == PRODUCT_CODE for e in product_entities), (
            f"the exact product code must resolve: {product_entities!r}"
        )

        assert calls, f"the MCP tool was never called: actions={result.actions!r}"
        tool_name, args = calls[0]
        assert tool_name == _PRODUCT_ATTACHMENTS_TOOL, tool_name
        product_uuid = next(e["uuid"] for e in product_entities if e.get("code") == PRODUCT_CODE)
        assert args.get("product_ids") == [product_uuid], args
        assert args.get("attachment_type_ids") == [PRODUCT_PHOTOS_UUID], args

        kinds = [a["kind"] for a in result.actions]
        assert "send_attachments" in kinds, (
            f"a cleanly resolved photo request must reach send_attachments: actions={result.actions!r}"
        )


class TestPass5Item1IsolatedMechanismCheckSingleAttachmentType:
    """An unrealistic, single-row seed the first pass of this investigation used before
    the real migration-seeded ambiguity (above) was found. Kept as a narrower guard:
    with the ambiguity removed entirely, `send_attachments` still fires - isolating the
    domain-scoping finding from the fetch-seam finding stays provably independent."""

    def test_single_attachment_type_reaches_send_attachments(
        self, session_factory, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        company_id = _seed_company(session_factory, name="ZZT PhotoAlias Solo Co")
        product_id = _seed_discontinued_product(session_factory, company_id=company_id, code=PRODUCT_CODE)
        db = session_factory()
        db.add(
            AttachmentType(
                id=PRODUCT_PHOTOS_UUID,
                code=None,
                type_name="Product Photos",
                allowed_extensions="jpg,png",
                max_file_size_mb=10,
            )
        )
        db.commit()
        _seed_product_attachment(session_factory, product_id=product_id, attachment_type_id=PRODUCT_PHOTOS_UUID)
        workspace_id = _seed_workspace(session_factory)
        contact_id = "ZZT-contact-photo-alias-solo"
        _seed_contact(
            session_factory, contact_id=contact_id, phone="+60000000104", workspace_id=workspace_id,
            company_ids=[company_id],
        )
        set_chatbot_switches(session_factory, business_lane=True)
        _set_completed_lanes(session_factory, system_settings_row, ["business_query"])
        _wire_real_resolve_entity(monkeypatch)
        _wire_answer_services(monkeypatch)
        calls: list[tuple[str, dict]] = []
        fetch_services = _photo_fetch_services(session_factory(), monkeypatch, calls=calls)
        monkeypatch.setattr(
            engine_mod.business_services, "fetch_services", lambda db: fetch_services
        )
        stub_parser(
            _parser_output(
                message_type="business_query",
                intent_hint="check_product_attachment",
                domain_hint="product_attachment",
                entities=_photo_attachment_type_entities(),
                routing={"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"},
            )
        )
        stub_access()

        result = engine_mod.run_turn(
            _scope_envelope(contact_id, message_id="ZZT-msg-photo-alias-solo", text=f"send me the photo of {PRODUCT_CODE}"),
            session_factory=session_factory,
        )

        assert result.status == "done", result.error
        reply_text = (result.reply or {}).get("text") or ""
        assert "did you mean" not in reply_text.lower(), reply_text

        kinds = [a["kind"] for a in result.actions]
        assert "send_attachments" in kinds, (
            f"a cleanly resolved photo request must reach send_attachments: actions={result.actions!r}"
        )
