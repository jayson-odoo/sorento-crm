# PLAN - New product application from a stock inquiry: ask, AI draft, match, reserve code (NPA-AI-ASSIST)

Status: Planned (4 Nov 2026), awaiting owner review of UAC + plan before tickets. Track: full (migration, LLM call,
portal routes).

- UAC: `npa-ai-assist-04nov-acceptance-criteria.md` (the journey and every AC; this plan does not restate them).
- Builds on: `PLAN-new-product-application-17oct.md` (merged, PR #1769).

## Owner decisions (grill, 4 Nov 2026)

| # | Question | Decision |
|---|---|---|
| G1 | Who sees matches | Rep sees them at submit when the line has a reference product; purchasing always sees them on review, including the ones the rep turned down |
| G2 | New code format | Decided later. Code suggestion deferred; purchasing types the code, system checks it is free |
| G3 | "Add into list" | Reserve the code in the CRM; AutoCount stays the product master; the line auto-links when the product syncs in |
| G4 | How purchasing asks | New explicit action (checkbox on Update & Reply); the Create button appears only after it |
| G5 | What AI writes | Remark + product lines (type, dimension, material, thickness, packing, qty, brand, reference product) |
| G6 | Rep surface | Portal and staff |
| G7 | Inquiry state | Stays Responded + marker, no new status |

## What already exists (measured, not rebuilt)

- Create from inquiry: `StockInquiryDetail.tsx:600` gear item (status responded + `canCreateApplication`); portal
  `GET /new-product-application/inquiries` + `/prefill` (own responded). Prefill copies text only.
- Purchasing link / close / undo / auto-complete: `new_product_application_service.py` `link_line` etc.
- Generic AI prefill engine: `services/ai_extract/extract_service.py` (provider from `ai_assistant_configs`, usage
  logged to `AIAssistantUsageLog`, lookup canonicalization via `LookupResolverService`).
- Product matching tiers: `services/entity_resolver.py` (exact / prefix / substring / embedding, line 515) and the
  trigram batch in `project_schedule_service.py:1270`; products are embedded (`embedding_worker.py:116`).
- No CRM -> AutoCount product push exists; products arrive via the AutoCount pull apply
  (`autocount_pull_service.py` -> `bulk_import_products`), ESB ingest (`api/v1/external/ingest.py`) and manual
  `POST /master-data/products`.
- No item-code format is written down anywhere; `product_family.family_code_for` is the only code rule.

## Design (simplest thing)

### Ask (S1)

- `StockInquiryUpdate` gains `request_npa: bool = False` (write-only). `update_inquiry_and_reply` sets
  `npa_requested_at/by` when true, and `compose_stock_inquiry_reply_message` appends the NPA start link (portal
  new-form URL with `stock_inquiry_id`, built like `_stock_inquiry_portal_or_view_url`). Deferred-action payload
  already carries `inquiry_data`, so the flag rides through `dispatch_or_defer` unchanged.
- Two columns on `stock_inquiries`; both manual dict builders that serialize the inquiry
  (`get_inquiry_for_response`, `get_inquiry_summary_by_token`) carry them (LESSONS: new column must reach the FE).
- Create gate (staff menu, portal list, both prefill routes) = responded AND `npa_requested_at IS NOT NULL`.
  Backfill: none. Inquiries that already have a linked application keep showing it; owner accepted that older
  responded inquiries lose the button (G4).

### AI draft (S2)

- One function `draft_npa_from_inquiry(db, inquiry) -> (body, drafted_by)` in a new
  `services/npa_draft_service.py`. It calls the same provider factory the extract engine uses
  (`get_provider(...)`, `response_format=json_object`), multimodal with the inquiry's image attachments (reuse the
  engine's image pass-through; PDFs ignored in v1). Prompt asks for the Write line keys only.
- Post-process: brand through `LookupResolverService`; `reference_product_id` from an exact code hit (AC-NAI-41
  normalization) on any code the model returns or the inquiry's `product_code`; drop anything unresolved.
- Any failure -> today's `prefill` copy with `drafted_by: "copy"`. Timeout setting `npa_ai_timeout_seconds` in
  `config.py` (default 20). Synchronous inside the prefill request: one call per form open, no worker queue
  needed (trigger to move it to RQ: p95 over the timeout in the usage log).
- Not registered in `form_schema_registry` (that registry maps uploaded files to form fields; this is
  record-to-record, one caller).

### Matching (S3)

- `services/npa_match_service.py`: `matches_for_line(db, line) -> {exact, similar}`. Exact = normalized code
  equality on proposed_code only; the reference product seeds the ranking (its family ranked up). Similar = `entity_resolver` product probe over the line text,
  trigram then embedding, active products, company-scoped, top 5, `exact` excluded. Computed on read, never
  stored.
- Rep: `use-match` / `reject-matches` routes (staff + portal), owner only, on an unlocked application (draft
  or rejected, `assert_unlocked`). Order in the FE: Submit pressed -> save -> modal (reads matches) -> choices
  posted -> submit call. The submit gate (AC-NAI-44) is one check in `validate_submit`. When the rep's choices
  resolved every line, `submit` moves the application straight to completed (AC-NAI-45) and skips the approver
  notification.
- Purchasing: the Matches cell reads the same route; Link reuses `link_line`.

### Reserve code + auto-link (S4)

- Route `reserve-code` (open_code, approved) with the 409 checks of AC-NAI-50.
- Auto-link: ONE SQLAlchemy `after_flush` session listener (registered next to the audit listeners at startup)
  that, for new `Product` rows in the flush, finds open lines in the same company with a matching normalized
  `reserved_code` and sets `opened_product_id/resolved_at`, then runs the existing auto-complete. One listener
  covers all three insert paths; a test per path (pull apply, ESB ingest, manual create).
- `undo` clears `reserved_*` too.

### Deferred

- System-suggested item codes (G2). Trigger: owner supplies the format. Then it is a pure function
  `suggest_code(line, nearest_product) -> str` feeding the Reserve modal's default value, with a golden set.

## Data (one migration `npa_0003_ai_assist`, additive, `IF NOT EXISTS`)

`stock_inquiries`: `npa_requested_at TIMESTAMP NULL`, `npa_requested_by TEXT NULL`.
`new_product_application_lines`: `reference_product_id UUID NULL -> products SET NULL`,
`rejected_match_product_ids JSONB NULL`, `matches_rejected_at TIMESTAMP NULL`, `reserved_code VARCHAR(255) NULL`,
`reserved_by VARCHAR(100) NULL -> users SET NULL`, `reserved_at TIMESTAMP NULL`.
Parent = main's head at build time via `./scripts/alembic-reparent.sh`.

## Slices

- **S1 Ask** - checkbox, marker, gate, link in the reply (AC-NAI-01..03, 20..23).
- **S2 AI draft** - prefill draft + reference product column + form notice (AC-NAI-04..06, 30..34).
- **S3 Match** - matches route, rep modal, purchasing Matches cell (AC-NAI-07, 08, 40..46).
- **S4 Reserve + auto-link** - (AC-NAI-09, 10, 50..53).
- Migration lands in S1 with all columns (one migration per lane).

## Test list (tester writes red first)

pytest `tests/test_npa_ai_assist.py` (Postgres fixture):
- S1: request_npa sets marker + link in queued message (patch the RQ enqueue); false/omitted keeps it; detail
  payload carries both fields; prefill 409 without marker (staff + portal); portal inquiries list filters.
- S2: provider stub returns JSON -> body fields; unknown brand dropped; other-company product dropped; provider
  raises / times out / bad JSON -> `drafted_by: "copy"`, 200; one usage row tagged `npa_draft`;
  reference_product_id of another company 422.
- S3: golden set (10 products, 6 line texts, expected top-1); exact excluded from similar; inactive excluded;
  company isolation; use-match outside matches 422; use-match on a submitted application 422 (locked); reject stores
  ids; submit 422 on an undecided referenced line; all lines resolved by rep -> submit completes, no approver
  notification.
- S4: reserve 409 on existing product code and on another open reserved code (case/space-insensitive);
  auto-link on manual create, on `bulk_import_products`, on ESB ingest; auto-complete; undo clears reserved;
  audit rows.
- `tests/test_migration_npa_0003_ai_assist.py`: id <= 32, one head, every new model column in the DDL.
vitest: checkbox in the response dialog; marker pill; create action gate; draft notice copy vs AI; reference
product clearable select; matches modal disables Submit until every line chosen; purchasing Matches cell with
struck-through rejected items; reserve modal inline 409 message.

## Risks

- AI quality on sparse inquiries: mitigated by the edit step and the copy fallback; measure by sampling 20 real
  drafts on the crew copy before handoff.
- Embedding tier latency on the matches route: one call per line view; if p95 > 1 s, cache per line for the
  request only.
