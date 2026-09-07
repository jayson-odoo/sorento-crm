"""Owner console pass 5, item 1 (TOP, 7 Sep 2026, prod regression flagged against #713):
"send me the photo of SRTWC8517-SH-UF" (biz-attach-d) stopped resolving the "photo"
attachment-type alias deterministically. Production turns
a5317cf4-3e87-45c9-89e1-cdc0e9eab7a0 and b4369aba-7bf3-45f7-9e98-6e8597393de0 (two cold,
byte-identical runs, `turns-lane3`), vendored at
`tests/fixtures/chatbot/a5317cf4-3e87-45c9-89e1-cdc0e9eab7a0.json` and
`tests/fixtures/chatbot/b4369aba-7bf3-45f7-9e98-6e8597393de0.json`. Both reply "Couldn't
find some items:\\n\\n\"photo\" (attachment type) - did you mean:\\n  1. Product Photos
...", one `send_message`, no `send_attachments`, `attachments_src: null`. Before #713
(rounds 5c to 12, per the brief) the same text resolved deterministically and sent the file.

MEASURED, not guessed, per the brief's own instruction to name the stage with file:line or
say plainly it could not be pinned:

1. `git diff 5e8acfef4..043e2a0be -- sorento_crm_backend/app` touches exactly seven files:
   `head/output_exchange.py`, `head/parser.py`, `contracts.py`, `lanes/escalation.py`,
   `tail/compile_state.py`, `tail/pending.py`, `chatbot_parser_prompt.py`. NONE of
   `entity_resolver.py`, `api/v1/system/references.py`,
   `lanes/business/{gate,answer,miss_suggest,resolve_gate}.py` changed - a byte-empty diff
   over that path list, confirmed with `git diff 5e8acfef4..043e2a0be --stat -- <those
   paths>`. Every one of those seven hunks is about team-clarify / escalation-team routing
   (`_team_clarify_pick`, `_is_catalogue_team`), the #708 partial-pick roster merge (gated
   on `prev_state.selection_context == "suggest_offer"`, which is empty on both turns -
   `previous_conversation_state: {}` in both dumps - so that hunk cannot fire here), the
   promo-team routing persist guard, and the member-offer scope-carry (H75). None of the
   seven touches attachment-type matching, the did-you-mean composer, or
   `crm_master_product_attachments_list` argument building. The brief's own suspect,
   `apply_dym_pick` (`head/output_exchange.py` ~1034-1073 in the current file), is called
   ONLY from the #708 merge block just named - unreachable on a cold turn.

2. Reproducing the SAME shape through the real seam (`entity_resolver.py:1706-1767`
   `_probe_attachment_type` Tier 1 exact, `:2381-2483` `_prefix_probe_attachment_type` Tier
   2 substring/prefix/word - both UNTOUCHED by #713) with a freshly seeded product
   `SRTWC8517-SH-UF` and ONE `AttachmentType` row `type_name="Product Photos"` (the real
   local prod-copy row's own name and uuid, `90e76894-8384-4186-a3f7-ef73667726ff`, queried
   read-only via psql 7 Sep 2026 - `select id, code, type_name from attachment_types` lists
   18 rows and exactly one, "Product Photos", contains the substring "photo") resolves
   "photo" -> `resolved: True, ambiguous: False, match_tier: substring` on every seed shape
   tried: a clean single match, a genuinely-ambiguous product token (2 prefix siblings), and
   a cross-company code twin (the SAME shape as production - `SRTWC8517-SH-UF` really is
   owned by both Sorento and Mocha in the local prod-copy DB, and the capture's own contact,
   `respond_io_id 437264483`, really is scoped to both). In every case `gate_passed: True`,
   `require_specific: False`, and `photo` never appears in `resolve_gate`'s
   `unresolved_tokens` - `build_suggest_offer`'s own `_ms_miss_resolutions`
   (`lanes/business/miss_suggest.py` ~140-154) drops any resolution whose `resolved is
   True` before a did-you-mean block is ever built for it (`lanes/business/answer.py:2934
   -2941`, the `d1s` list). This mechanism is unaffected by #713 and, measured here, is not
   what produced the captured reply.

3. **Contradiction with the brief, stated rather than silently adapted around.** Both dumps
   carry `"source": "n8n execution runData"` and an `n8n_exec_id` (`15527110` /
   `15527657`) - these are N8N WORKFLOW EXECUTIONS, not `engine.run_turn` calls. Whether
   this specific turn shape (`product_attachment` / `check_product_attachment`) was even
   inside `chatbot_completed_lanes` at capture time (7 Sep 2026) is not recorded in the
   dump; if it was not, the OLD n8n JS spine composed this reply, not the seven files #713
   touched, and a Python PR cannot be the cause of a JS-composed reply. Separately, the
   dumps' OWN product-side symptom does not fit a resolver defect either: the local
   prod-copy `products` table has `SRTWC8517-SH-UF` in BOTH companies the capture's contact
   is scoped to (an EXACT match, confirmed via psql), yet the reply's product miss is
   labelled with the FULL RAW MESSAGE ("send me the photo of SRTWC8517-SH-UF") and offers
   three string-unrelated codes (SRTFC2031, SRTFP4001, SRTWC6011-RL-BL) - a shape consistent
   with `resolve_entity_body`'s own hardcoded `spec_fallback: True` / `understand_phrase:
   True` (`lanes/business/resolve_gate.py:296-337`) LLM semantic fallback having fired, not
   with any token-level fuzzy probe (which resolves this exact code cleanly, per point 2).
   `spec_fallback` needs `OPENAI_API_KEY`, absent locally, and this test - like
   `test_engine_company_scope.py::_real_resolve_entity`'s own documented reason - forces it
   off, so this half of the capture can be neither reproduced nor ruled out here; per
   `documentation/agents/chatbot-verification.md` it is graded on the production run.

Given (1)-(3), what IS provably, deterministically red on 043e2a0be through `engine.run_turn`
- the only surface #713 could have touched - is not "photo resolves wrong" (measured fine)
but "a product_attachment query with a resolved product AND a resolved attachment_type
still never reaches `send_attachments`": there is no AC-604-style zero-tool deterministic
fetch for this domain, so with the real (unstubbed) fetch/tool-selection path - the only
honest way to drive this without inventing a canned answer that would beg the question -
the turn falls through the zero-MCP-tools branch to a generic no-result reply ("Here's
what you want: ... But no photo matched these. Would you like me to escalate...", measured
by actually running this test - `entities` echo correctly, so the resolver/gate half is
confirmed clean here too, and the gap is purely that nothing ever queried the attachments
table). That is
the one assertion below watched red for a stated, measured reason; the "no did-you-mean"
assertion beside it is a REGRESSION GUARD (already true today, kept so a future change to
the resolver / gate cannot reopen this exact shape silently).
"""
from __future__ import annotations

from typing import Any

from app.models.resources import Attachment, AttachmentType
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.lanes.business.services import FetchServices
from tests.chatbot.conftest import set_chatbot_switches
from tests.chatbot.test_engine import _parser_output, stub_access, stub_parser  # noqa: F401
from tests.chatbot.test_engine_company_scope import (
    _entity_for,
    _scope_envelope,
    _seed_company,
    _seed_contact,
    _seed_product,
    _seed_workspace,
    _set_completed_lanes,
    _wire_answer_services,
    _wire_real_resolve_entity,
)

PRODUCT_CODE = "SRTWC8517-SH-UF"
# The real local prod-copy row's own name/uuid (psql, read-only, 7 Sep 2026) - not invented.
ATTACHMENT_TYPE_UUID = "90e76894-8384-4186-a3f7-ef73667726ff"
ATTACHMENT_TYPE_NAME = "Product Photos"


def _seed_attachment_type(session_factory: Any) -> str:
    db = session_factory()
    row = AttachmentType(
        id=ATTACHMENT_TYPE_UUID,
        type_name=ATTACHMENT_TYPE_NAME,
        allowed_extensions="jpg,png",
        max_file_size_mb=10,
    )
    db.add(row)
    db.commit()
    return row.id


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
    """AC-604's own zero-tool wiring: `embed`/`tool_search` are the ONLY things that would
    need `OPENAI_API_KEY` (real embeddings, a real tool-RAG catalog), so they are stubbed
    to "nothing matched" here - the same seam `test_s6_s7_integration.py::_no_tool_fetch_services`
    uses. `mcp_call` stays a hard failure: `tool_search` returning `[]` means `run_fetch`
    must exit before ever calling a tool."""

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


class TestPass5Item1ProductAttachmentPhotoAliasResolvesWithoutADidYouMean:
    def test_photo_alias_resolves_clean_and_the_turn_never_reaches_send_attachments(
        self, session_factory, stub_parser, stub_access, system_settings_row, monkeypatch
    ) -> None:
        company_id = _seed_company(session_factory, name="ZZT PhotoAlias Co")
        product_id = _seed_product(session_factory, company_id=company_id, code=PRODUCT_CODE)
        attachment_type_id = _seed_attachment_type(session_factory)
        _seed_attachment(
            session_factory, product_id=product_id, attachment_type_id=attachment_type_id
        )
        workspace_id = _seed_workspace(session_factory)
        contact_id = "ZZT-contact-photo-alias"
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
        # `business.run_fetch` runs FOR REAL here (unlike every other file in this suite,
        # which cans a fetch success): the point of this test is whether a cleanly-resolved
        # product_attachment query reaches `send_attachments` on its own, and canning the
        # fetch would beg exactly that question. Only `embed` / `tool_search` are stubbed
        # (AC-604's own zero-tool wiring - no OPENAI_API_KEY needed since no real embedding
        # or tool-RAG catalog is touched); `mcp_call` stays a hard failure so a tool
        # actually being selected is a wiring drift, not a silent pass.
        monkeypatch.setattr(
            engine_mod.business_services, "fetch_services", lambda db: _no_tool_fetch_services()
        )

        stub_parser(
            _parser_output(
                message_type="business_query",
                intent_hint="check_product_attachment",
                domain_hint="product_attachment",
                entities=_photo_attachment_type_entities(),
                routing={
                    "suggested_team": "marketing_product",
                    "suggested_agent": "general_enquiries",
                },
            )
        )
        stub_access()

        result = engine_mod.run_turn(
            _scope_envelope(
                contact_id,
                message_id="ZZT-msg-photo-alias-a5317cf4",
                text=f"send me the photo of {PRODUCT_CODE}",
            ),
            session_factory=session_factory,
        )

        assert result.status == "done", result.error
        reply_text = (result.reply or {}).get("text") or ""

        # REGRESSION GUARD (green today, measured point 2 above): the attachment-type
        # alias itself resolves cleanly through the real, #713-untouched resolver seam -
        # this is NOT where the captured defect lives, and a future change that reopens it
        # must fail HERE, not be attributed to a different lane.
        assert "did you mean" not in reply_text.lower(), (
            "the photo alias regressed at the resolver/gate seam - re-read this test's "
            f"docstring point 2 before assuming this is the #713 defect: {reply_text!r}"
        )
        assert '"photo" (attachment type)' not in reply_text

        # THE RED ASSERTION: a cleanly resolved product_attachment query - product AND
        # attachment_type both resolved, gate passed - still never reaches
        # `send_attachments` today, because there is no AC-604-style zero-tool
        # deterministic fetch for this domain (unlike, say, a stock/order answer). Today
        # this comes back `not_found` instead.
        kinds = [a["kind"] for a in result.actions]
        assert "send_attachments" in kinds, (
            "product_attachment has no deterministic zero-tool fetch path today, so a "
            f"cleanly resolved photo request never emits send_attachments: actions={result.actions!r}"
        )
