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
"Shipment Line Photo" contains the substring "photo" case-insensitively - missed on this
tester's OWN first read of that same `psql` output (a measurement error, corrected here).

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
  ambiguous: true`, exactly two matches, both `match_tier: "substring"`;
* the SAME call also shows the product token `SRTWC8517SHUF` ambiguous - two real EXACT
  matches (one per company the capture's own contact, `respond_io_id 437264483`, is
  really scoped to - Sorento `00000000-...0001`, Mocha `5e2c68f5-...`) merged with several
  prefix-tier variant codes under ONE token entry (`ambiguous` keys off `len(matches) > 1`
  regardless of tier, not on tier alone).

**Where the ambiguity actually goes: an asymmetry in `gate.py`'s own per-token OR-mode
classifier, `run_gate` ~319-394.** For a `product` token this file's own logic is careful:
several genuinely distinct products stay ambiguous and are handed to the customer as a
numbered pick (`specific_options` / `still_ambiguous`, ~450-495). For a NON-product token
(attachment_type, certificate, ...) the SAME function has no such path - `~360-393`:
`np_exact = [m for m in non_products if match_tier == "exact"]`; when that is empty (no
exact hit - exactly "photo"'s shape, both hits are substring-tier) and the candidates do
not share one code (`np_same_key`, ~393's sibling condition - false here, "Product Photos"
and "Shipment Line Photo" are different codes), the function falls to
`picks = [non_products[0]]` (line 393) - it SILENTLY keeps whichever candidate the
database happened to return first, with no `resolved_by` marker
(`lanes/business/miss_suggest.py::gate_resolved_tokens`, ~110-125, only recognises
`"document-class-narrowing"` / `"same-code-collapse"`), so `miss_suggest.py`'s own miss
list still carries "photo" as an open, unresolved token regardless of what the gate
silently picked. Measured directly (debug instrumentation added to `gate.py` for this
investigation, run, then reverted - `git status` on that file confirmed clean before this
commit): with the two real rows seeded, `compatible_entities` narrows to "Product Photos"
alone with `gate_passed: True, require_specific: False` - no did-you-mean YET - and then,
when the (silently, non-deterministically picked) type's own fetch comes back with zero
rows, `lanes/business/answer.py::build_suggest_offer`'s own D1 listing (`~2934-2941`, the
already-cited `d1s` block) DOES fire, because "photo" was never marked resolved -
reproduced here verbatim: stubbing `business.run_fetch` to a genuine zero-row result
(`has_result: False`, the honest stand-in for "the query narrowed to the wrong/unlinked
type found nothing" - not invented data) produces "Couldn't find \"photo\" (attachment
type). Did you mean shipment_line_photo?" - the SAME class of reply as production's own
capture, though not byte-identical (production's picked-and-missed type and this
seed's differ, because the gate's own pick is order-dependent, not because the mechanism
differs). This is the whole account: `#713` itself never touches attachment-type
resolution (confirmed below); the deploy alongside it added a second `attachment_types`
row that collides on the substring "photo", and `gate.py`'s asymmetric non-product
ambiguity handling (silent-first-pick, never flagged) is what turns that data collision
into first a WRONG silent choice and then, once that choice's own query comes up empty, a
customer-facing did-you-mean - never a deterministic delivery of the file that DOES exist.

**#713's own diff, for the record.** `git diff 5e8acfef4..043e2a0be --
sorento_crm_backend/app` touches exactly seven files: `head/output_exchange.py`,
`head/parser.py`, `contracts.py`, `lanes/escalation.py`, `tail/compile_state.py`,
`tail/pending.py`, `chatbot_parser_prompt.py`. NONE of `entity_resolver.py`,
`api/v1/system/references.py`, `lanes/business/{gate,answer,miss_suggest,resolve_gate}.py`
changed. `#713`'s own diff is not the cause; `#707`'s migration, deployed the same run,
is.

Below: `TestPass5Item1PhotoAliasAgainstTheRealMigrationSeededData` seeds exactly the rows
migrations `021_add_attachment_type_code_and_complaint_document.py` (pre-existing
"Product Photos" admin row, unaffected) and `485_shipment_line_photo_type.py`
("Shipment Line Photo", "Proforma Invoice") produce, plus the product marked discontinued
(`is_discontinued=True`) as the control dump's own `(PRODUCT DISCONTINUED)` flag shows,
and asserts the two things the AC actually wants: (1) "photo" resolves to Product Photos
with NO did-you-mean, and (2) the product resolves by its exact code and the turn reaches
`send_attachments`. Both are watched red for the reasons measured above - the SECOND
attachment type is what turns (1) red (a genuine did-you-mean, or a wrong silent pick,
depending on row order - either way never a clean single answer), and (2) is red because
`send_attachments` needs a real fetch this harness cannot drive without `OPENAI_API_KEY`,
so it is asserted on the resolved entities + the tool-call args the turn WOULD have sent,
per the captain's own fallback instruction.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.models.resources import Attachment, AttachmentType
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.lanes.business.services import FetchServices
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
from app.models.product import Product, ProductCategory, UnitOfMeasure
from tests._pg_fixture import unique_code

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


def _seed_attachment(session_factory: Any, *, product_id: str, attachment_type_id: str) -> str:
    db = session_factory()
    row = Attachment(
        attachment_type_id=attachment_type_id,
        original_filename=f"{PRODUCT_CODE}-photo.jpg",
        stored_filename="zzt-a5317cf4-stored.jpg",
        file_path="https://example.test/zzt-a5317cf4-stored.jpg",
        entity_type="product",
        entity_id=product_id,
    )
    db.add(row)
    db.commit()
    return row.id


def _no_tool_fetch_services() -> FetchServices:
    """AC-604's own zero-tool wiring - `embed`/`tool_search` are the only things that
    would need `OPENAI_API_KEY`, so they are stubbed to "nothing matched"; `mcp_call`
    stays a hard failure so an actual tool call is a wiring drift, not a silent pass."""

    def _mcp_call(name: str, args: dict) -> Any:
        raise AssertionError("no MCP tool matched - tool_filter must return before this runs")

    return FetchServices(
        embed=lambda query: [0.0, 0.0, 0.0],
        tool_search=lambda embedding, *, query, domain: [],
        mcp_call=_mcp_call,
    )


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
    session_factory, stub_parser, stub_access, system_settings_row, monkeypatch, *, contact_id: str
):
    company_id = _seed_company(session_factory, name="ZZT PhotoAlias Co")
    product_id = _seed_discontinued_product(session_factory, company_id=company_id, code=PRODUCT_CODE)
    _seed_migration_attachment_types(session_factory)
    _seed_attachment(
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
    monkeypatch.setattr(
        engine_mod.business_services, "fetch_services", lambda db: _no_tool_fetch_services()
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
    not the single-row seed the first pass of this investigation wrongly measured as
    clean. Watched red on 043e2a0be."""

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

    def test_product_resolves_exact_and_the_would_be_fetch_args_are_correct(
        self, session_factory, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        """The FIX, at this item's actual measured scope: the resolver-level domain
        scoping (`entity_resolver._product_attachment_type_ids`) makes "photo" resolve
        to the product exactly and the attachment_type deterministically - no
        did-you-mean (test above), no wrong silent pick. Asserted here on the args the
        turn WOULD hand `crm_master_product_attachments_list`, built the exact same way
        `run_fetch` builds them (`entity_ids_transformer`), rather than on
        `send_attachments` actually firing - this harness cannot drive the real MCP
        call (no `OPENAI_API_KEY`), and whether `product_attachment` has ANY
        deterministic path to `send_attachments` that skips MCP entirely is a separate,
        larger, security-relevant gap (duplicating/rerouting the access-level /
        company-scope logic `/api/v1/master-data/product-attachments` already carries)
        that this item's brief never asked for. See the xfail test below and
        https://github.com/jayson-odoo/sorento-crm/issues/727.
        """
        result = _run_turn_seeded(
            session_factory,
            stub_parser,
            stub_access,
            system_settings_row,
            monkeypatch,
            contact_id="ZZT-contact-photo-alias-2",
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

        from app.services.chatbot.lanes.business import fetch as fetch_mod

        trigger = {
            "tool": "crm_master_product_attachments_list",
            "entities": gate.get("compatible_entities", []),
            "semantic_input": {},
        }
        would_be_args = fetch_mod.entity_ids_transformer(trigger)
        product_uuid = next(e["uuid"] for e in product_entities if e.get("code") == PRODUCT_CODE)
        assert would_be_args.get("product_ids") == [product_uuid], would_be_args
        assert would_be_args.get("attachment_type_ids") == [PRODUCT_PHOTOS_UUID], would_be_args

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "product_attachment has no deterministic zero-tool fetch path - it needs "
            "the MCP tool-search-then-call pipeline (run_fetch), which needs "
            "OPENAI_API_KEY to pick a tool, and this harness has none. A domain-known "
            "tool-name shortcut would still call mcp_call, which this harness makes a "
            "hard failure on purpose. Tracked as issue #727, not fixed here - it is a "
            "materially larger, security-relevant change (duplicating or rerouting the "
            "access-level / company-scope logic /api/v1/master-data/product-attachments "
            "already carries) than the attachment-type ambiguity this item's brief "
            "scoped."
        ),
    )
    def test_send_attachments_is_reached(
        self, session_factory, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        result = _run_turn_seeded(
            session_factory,
            stub_parser,
            stub_access,
            system_settings_row,
            monkeypatch,
            contact_id="ZZT-contact-photo-alias-3",
        )
        kinds = [a["kind"] for a in result.actions]
        assert "send_attachments" in kinds, (
            "product_attachment has no deterministic zero-tool fetch path today, so a "
            f"cleanly resolved photo request never emits send_attachments: actions={result.actions!r}"
        )


class TestPass5Item1IsolatedMechanismCheckSingleAttachmentType:
    """NOT a regression guard - an unrealistic, single-row seed the first pass of this
    investigation used before the real migration-seeded ambiguity (above) was found.
    Kept only to isolate the `send_attachments`-gap finding from the ambiguity finding:
    even with the ambiguity removed entirely, `send_attachments` still never fires,
    because there is no AC-604-style zero-tool deterministic fetch for this domain -
    tracked as its own issue (#727), out of THIS item's scope. See the class-level
    docstring on `TestPass5Item1PhotoAliasAgainstTheRealMigrationSeededData`'s
    `test_send_attachments_is_reached` for the full reasoning; this is the same xfail,
    proven again on the unrealistic single-type seed so the ambiguity finding and the
    fetch-gap finding stay provably independent."""

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "product_attachment has no deterministic zero-tool fetch path - see "
            "TestPass5Item1PhotoAliasAgainstTheRealMigrationSeededData."
            "test_send_attachments_is_reached and issue #727. Not fixed here: a "
            "materially larger, security-relevant change than the attachment-type "
            "ambiguity this item's brief scoped."
        ),
    )
    def test_single_attachment_type_still_never_reaches_send_attachments(
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
        _seed_attachment(session_factory, product_id=product_id, attachment_type_id=PRODUCT_PHOTOS_UUID)
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
        monkeypatch.setattr(
            engine_mod.business_services, "fetch_services", lambda db: _no_tool_fetch_services()
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
            "even with the ambiguity removed, send_attachments still never fires - the "
            f"gap is the missing zero-tool fetch, not (only) the alias data collision: "
            f"actions={result.actions!r}"
        )
