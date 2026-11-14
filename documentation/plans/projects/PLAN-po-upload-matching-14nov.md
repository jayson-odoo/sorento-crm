# PLAN: PO upload matching (PO-UPLOAD-MATCHING)

Status: building (size M, LEAD pattern). Card answered by crew 14 Nov 13:05: Q1 b, Q2 a, Q3 a, Q4 a, Q5 a. No migration (suggestion meta lives in `extracted_json.line_matches`).

## Problem (owner, 14 Nov, 134-line customer PO)

1. Products do not need a quotation, and matching never looks at one
   (`api/v1/projects/po_intake.py:112-160`, `services/project_po_intake_lifecycle.py:321-392`).
   Quotation is only used at Confirm for mismatch flags
   (`project_po_confirm.py:234`, `project_po_service.py:556-579`).
2. Matching is string rules only (`project_po_intake_lifecycle.py:917-1095`): exact code, a
   code-shaped token in the description, punctuation dropped, tokens reordered, truncated code
   completed. Brand words and customer prefixes defeat it ("SORENTO BBTSRTWC8518 -SH" vs
   `SRTWC8518-SH`). The description-token rule matched "40MM" (wrong).
3. Qty/UOM can come back empty; Confirm silently saves qty 1 (`project_po_confirm.py:264`).
4. "Document total" is the sum of the amounts read (no printed total is asked for:
   `project_po_reading.py:146-163`, lifecycle `recompute_totals` ~1217), but the banner says
   "the total printed on the document" (`POIntakeConfirmClient.tsx:405`).

## Behaviour card (filed as crew-ask)

See PR comment `crew-ask: behaviour card`. Copy kept here once answered.

## Reuse map (discovery)

| Need | Existing function | Verdict |
| --- | --- | --- |
| Exact code match | `ProjectPOIntakeLifecycle._resolve_product` lifecycle:917 | keep first tier (exact code) |
| Customer-remembered codes | `CustomerItemCodeMap` model `models/project_so.py:384`; `_remembered_codes` / `_remember_code` `project_schedule_service.py:1238, 2060` | lift into ONE shared helper used by schedule + PO |
| Catalogue shortlist (did-you-mean) | `entity_resolver.resolve_references(... alternatives)` `entity_resolver.py:5475`, as used by `ai_extract/extract_service.py:1261` | reuse as is for the shortlist |
| Quotation lines of the project | `project_po_service._quoted_line_for` / `_bind_quotation_version` (`project_po_confirm.py:290`) | reuse to pick the quotation version; read its lines |
| LLM structured call | `llm_provider` + prompt registry (`ai_prompt_registry.py`, `po_extractor` pattern, json_schema) | new prompt key `po_line_matcher`, same call path |
| Manual product pick on a line | lifecycle:1281-1294 (`set line product`) | extend: also writes the customer code map |
| Qty x price arithmetic | `arithmetic_ok`, `_computed_amount` `project_po_reading.py:283-305` | reuse |

## UAC

`po-upload-matching-14nov-acceptance-criteria.md` (answers = the recommended options).

## Contract (tester and coder both work from this)

Backend
- `app/services/customer_code_map.py` (shared; delivery-schedule matcher switches to it):
  `remembered_codes(db, customer_id) -> Dict[str, str]` (UPPER customer code -> product_id),
  `remember_code(db, *, company_id, customer_id, customer_code, product_id, actor_user_id) -> None`
  (insert or overwrite, case-insensitive on code), `customer_id_for_po(db, po) -> Optional[str]`
  (issuing party's customer, else the project's lead customer; lifted from
  `ProjectScheduleService.customer_id_for`).
- `app/services/project_po_matching.py`:
  `MATCH_BATCH_SIZE = 40`;
  `ask_line_matcher(db, lines: list[dict], *, company_id) -> list[dict]` is the ONE model call
  (prompt key `po_line_matcher`, structured output). Input items
  `{line_no, stock_code, description, candidates: [{code, name, source}]}` with source in
  `quotation | customer_map | catalogue`. Output items
  `{line_no, product_code | null, confidence: "high"|"medium"|"low", options: [code, ...]}`.
  Raises on any failure. Tests monkeypatch this function; nothing in tests reaches a provider.
  `suggest_matches(db, version, lines, *, customer_id, quotation_version_id) -> None` builds the
  candidates, batches, calls `ask_line_matcher`, drops picks/options not in that line's
  candidates, writes `resolved_product_id` + `resolution_source="suggested"` and
  `version.extracted_json["line_matches"][str(line_no)] = {confidence, options: [product_id...],
  qty_suggested}`; a raising batch leaves its lines unmatched.
- Lifecycle (`project_po_intake_lifecycle.py`): `_resolve_product` keeps exact code only, then
  the customer map (`resolution_source="map"`); description-token rule and loose tiers removed.
  `persist_pages` calls `suggest_matches` once after all pages, and sets the suggested qty
  (AC-Q2). New: `accept_suggestion(version, line, *, actor_user_id)`,
  `accept_all_suggestions(version, *, actor_user_id) -> int` (calls accept_suggestion per line).
  `update_line(..., actor_user_id=None)`: a product pick writes the map; a typed qty clears
  `qty_suggested`.
- Confirm: 422 `po_version_lines_need_attention`, message names the line numbers, while a live
  line has qty empty, `resolution_source == "suggested"`, or `qty_suggested`. No `or Decimal("1")`.
- Reader: `PO_PAGE_SCHEMA` gains top-level nullable number `printed_total` (prompt asks for the
  printed grand total, null when the page has none); `persist_pages` keeps the last non-null page
  value as `extracted_json["printed_total"]`.
- Routes (`api/v1/projects/po_intake.py`, EDIT permission, return `POVersionDetailResponse`):
  `POST /purchase-order-versions/{po_version_id}/lines/{line_id}/accept-suggestion`,
  `POST /purchase-order-versions/{po_version_id}/accept-suggestions`.
- Serialised line adds `match_confidence: str|null`, `match_options: [{product_id, product_code,
  product_name}]`, `qty_suggested: bool`; version adds `suggestion_count: int`; totals add
  `printed_total_read: bool`.

Frontend (existing screen; reuses Badge, DataGrid context menu, Button; no mock needed)
- `poIntakeService.ts` + intake hook: `acceptSuggestion(versionId, lineId)`,
  `acceptAllSuggestions(versionId)`.
- `POIntakeLinesGrid.tsx`: Flag column shows `Badge` "Suggested" for a suggested product or
  qty; right-click a suggested row -> "Accept suggestion"; secondary button
  "Accept all suggestions (N)" while N > 0; product picker lists `match_options` first.
- `POIntakeConfirmClient.tsx` `TotalsMetaLine`: label "Sum of lines read" and no above/below
  sentence when `printed_total_read` is false.

Standing rules that apply: one main button; plain words; explicit link set by a person;
reuse functions (map helper shared); one bad batch never fails the read; right-click row actions,
no row icon buttons; value that cannot be worked out shows "-"; 375/1280 px.
