# PLAN - Container status tracking and the query-aware answering agent

**Status:** DRAFT 2026-08-04. Grilled with the user (12 questions). UAC written first:
`container-status-tracking-acceptance-criteria.md`. **Pre-code** - the plan itself still needs a
grill pass before implementation starts.
**Scope:** `sorento_crm_backend` + `sorento_crm_frontend` + `sorento_crm_mcp` + one optional n8n
schema field.

---

## 1. Problem

`Container Status 2026.xlsx` is maintained by hand. Someone visits each liner's website daily by
shipper + container number for ETA and revised ETA, then CIDB ePermit for inspection and approval
dates, and types the results into a 51-column sheet. ~500 containers a year, ~77 open at a time,
407 containers in the current workbook.

Three things follow:

1. The dates n8n needs to answer "what's the ETA delay" are locked in a file.
2. The daily website-checking is exactly the kind of work an integration removes - which is where
   the product value sits.
3. `sorento-consume-main` cannot answer a narrow question narrowly, so even with the data in the
   system the reply would be a record dump.

## 2. What the evidence said

Measured, not assumed:

| Finding | Number |
|---|---|
| Real unique containers in the workbook | **407**, across **9 header blocks in 5 tabs** (several tabs stack more than one titled section). A further 475 numbered rows carry no container number. All 407 distinct, all 407 pass ISO 6346. |
| Containers appearing in more than one tab | **0** - verified, so no cross-tab import precedence problem |
| `inbound_shipments` in the DB | 112 |
| DB containers that appear in the workbook | **111 of 112 (99%)** |
| Open containers in the sheet with no DB row | **34** (26 Ceramic + 8 Fitting) |
| `bill_of_lading_number` populated in the DB | **0** |
| `actual_arrival_date` populated in the DB | **0** |
| Distinct liners | **18** (top 5 = 77% of rows, top 8 = 91%). Counted with `RL` aliased to `LINER`; without the alias Ceramic's 55 rows drop out entirely. |
| CMA share of rows (first adapter) | **79 / 407 = 19%**; WHL is the bigger single win at 116 (28%); top 5 reach 77% |
| Containers sharing each distinct date | 4.2 (ETA) to 5.5 (inspection) |
| `ATA` / `ORI DOC` / `K1 SUB` / `YARD` fill rate | 6 / 4 / 4 / 4 out of 407 |
| Status-engine entities registered in this repo today | **0** |

Two structural facts that shaped everything:

- **`inbound_shipments` already *is* the packing list, and container is already its identity.**
  `PLAN-packing-list-container-match.md`: *"a container carries exactly one not-fully-received
  inbound shipment at a time"*, with dedup on `(container, ETA, shipment_date)`. One sheet row = one
  `inbound_shipments` row. No container table, no BL table.
- **The answer flaw is a schema, not a prompt.** `sub-get-results`' output contract is
  `{response_intro, answers[{description}], attachments[], action_links[], has_result}` and its
  prompt says *"Return EVERY result, never a sample"* / *"NEVER drop, sample, summarize, or cap
  records"* / *"COUNT CHECK ... length of `answers` MUST equal that total"*. There is no field for
  the answer to the question. `intent_hint` and `user_goal` arrive and are ignored for shaping.

## 3. Decision log (grill)

| # | Question | Decision |
|---|---|---|
| D1 | Container, packing list or BL as the row? | **1 sheet row = 1 `inbound_shipments` row.** The codebase already rules container = shipment identity. Joint BL needs nothing - `bill_of_lading_number` is a string, N shipments share it. |
| D2 | 51 columns onto one table? | Ops columns yes. Cost columns deferred (D9). |
| D3 | Milestone child table for the 15 dates? | **No.** Rejected by the user as over-generalized, and correctly - the vocabulary is fixed and named. Flat columns. |
| D4 | Then where do targets and provenance live? | Targets: nowhere in phase 1 (D6). Provenance: `audit_logs` actor + `integration_log` + the observation ledger (D7). |
| D5 | ETA revision history? | **`audit_logs`.** `__audit_track__` gives per-field `old_values`/`new_values` free. No revision table. |
| D6 | Form SLA for chasing? | **Not in phase 1.** The handling lock would disable a container's CTAs on escalation, which is wrong for a logistics record, and `advance_on_event` NULL has a live bug. Chasing is worthless before the dates land daily. |
| D7 | Where do integration values go? | **Append-only `shipment_tracking_observations`.** They never overwrite. Paired `*_observed` columns were rejected: they overwrite per poll and destroy the timing evidence, which is the entire point of the validation period. |
| D8 | Fix the shared answer schema, or pilot? | **Pilot on the new agent.** `direct_answer` added as optional so existing agents stay valid. It lives in `sub-get-results`' schema, i.e. **n8n-side** - the CRM was never asked to narrow prose. Generalise later behind the existing `sorento-regression-*` capture/replay/judge harness. |
| D9 | Cost block? | **Out.** Not needed for Q&A. The retained original file preserves it. Revisit when the export moves to system format. |
| D10 | Generated sheet or uploaded sheet? | **Serve the uploaded original** in phase 1. Generation in system format is a later phase. |
| D11 | `cidb_required` derivation? | **Deferred.** `PRODUCT` in the sheet is opaque (`2406+7547-BL+7547+6047`) and 286 of 408 containers have no lines. Needs `product_categories.cidb_regulated`; lands with the ePermit adapter. |
| D28 | Where does the upload live? | **On Packing Lists, not Resource Management -> Files.** Corrected after review: the first prototype pointed the empty-state CTA at the generic file library, which is how packing-list *documents* are uploaded today but is wrong for this. One sheet row is one packing list, so the workbook belongs to the domain the maintainer is already in. Uses the toolbar's `secondaryActions` slot, documented for exactly this ("Import, attachment links, templates"). The file is still retained as a `Container Status` attachment so the assistant can serve it back - storage stays in the library, the entry point does not. |
| D29 | Dry run before committing? | **Yes.** Reuses the shared `TemplateUploadDialog`, whose `onTest` hook already renders errors, warnings and a summary. Against the current workbook: 407 read / 111 update / 296 create / 0 rejected. An import that restates 407 containers deserves a preview. |
| D30 | How is the workbook parsed? | **Header-anchored with an alias table, never positional.** Corrected after review. Each sheet is scanned for rows reading exactly `CONTAINER`; each opens a block whose columns come from its own header row. The file has **9 blocks in 5 tabs**, not 5 flat sheets - `Fitting` stacks a "JOINT MOCHA CONTAINER" section at row 31, `Ceramic` stacks two more at 69 and 75, `Arrived - Joint Mocha` one at 22. Two consequences the first draft got wrong: (1) those 4 repeated headers are section boundaries, so the true ISO 6346 reject count is **0**, not 4; (2) `Ceramic` names its liner column `RL` while every other tab names it `LINER`, so a positional read of column 4 would have mislabelled 55 liners. Other live aliases: `W/H ARRIVALS`, `CHINA FREIGHT (RMB)`, `10% SST`, `Demurrange`. |
| D31 | Where does the running import show up? | **The Upload Activity drawer, via an optimistic `import_job` session** - `notifyImportQueued()` - what SPO allocation and delivery order imports call - only invalidates the backend feed, and the feed has no row until the worker has created the job, so the drawer opens on an EMPTY panel. `useUploadManager().startSession(...)` now takes `importJobId` / `title` / `jobType` / `totalRows` (previously `import_job_id` was hardcoded null), so the page that queued the import shows its own row immediately and the backend entry replaces it on reconcile. Applies to every import page, not just this one. The toast also carries a "View job" action to `/system-management/import-jobs/{id}`. Consequence: the Packing Lists toolbar now has two secondary actions (Refresh, Import Container Status), so the toolbar collapses them into its "Actions" dropdown exactly as the delivery order list does. |
| D12 | Daily update mechanism? | **Re-upload the sheet.** Bulk-set via `bulk_update_registry` is the natural next step (dates cluster 4-5.5 containers deep) but is not phase 1. No inline grid. |
| D13 | Liner acquisition? | ~~Aggregator~~ **REVISED after review: per-carrier scrapers, CMA first** (`cma-cgm.com/ebusiness/tracking`, container-number search, no carrier account needed). The adapter registry survives unchanged - per-carrier adapters become the implementation rather than the fallback, and an aggregator can still slot in as one more adapter. **Consequences accepted:** coverage becomes the sum of adapters built (CMA alone = 79/407 = 19%, not ~92%); there is no push channel, so acquisition is polled via the existing `scheduled_task_service` + RQ; and each carrier's markup is a permanent maintenance surface. |
| D13a | How does the scraper fetch, given a 403? | **Open - spike required (O1).** Verified: a plain HTTP GET of the CMA tracking URL returns `403 Forbidden`. The backend ships `httpx` only, no HTML parser and no browser, on `python:3.11-slim`. Four candidate answers in O1; do not guess one into the plan. |
| D14 | Cost tool / audience split? | **Dropped** with D9. |
| D15 | New query tool, or extend the existing one? | ~~New `crm_container_status_list` domain~~ **REVERSED after review. Extend `crm_incoming_stock_list`.** My objection was LLM tool-picking ambiguity between two shipment-rooted tools reading one table - that objection only exists if there are two tools. One tool, CRM dumps every field the caller may see, **n8n orchestrates and narrows**. |
| D16 | Then who stops a salesperson seeing gatepass? | **The CRM, server-side, on the caller.** *(Generalised by D20 - the principle stands, but the implementation is data-driven rather than clearance-specific.)* Contact -> `contact_access_types`; staff -> JWT permissions. Unentitled callers get the clearance keys **absent** (not null - null reads as "no gatepass yet"). n8n's safeguard is an additional layer, never the mechanism. Rejected: n8n-only gating - same failure class as "tell the model not to mention costs", and the user named the risk himself. |
| D17 | How do warranty / price-tag-template / container-status coexist on one attachments endpoint? | ~~New type-pinned singleton tool~~ **REVERSED after review. Generic `crm_resource_attachments_list` + attachment-type filter, no new tool.** Two reasons: (1) the RAG side only surfaces the generic list, so a new tool would be **unreachable**; (2) a tool per document does not scale. Attachment type is a filter value, not a tool. |
| D19 | Who enforces `access_levels`? | **The backend. A caller may narrow, never widen.** Today `access_levels` is a caller-supplied Query filter (`app/api/v1/resources/attachments.py:239`) and `sub-get-results` passes a precomputed intersection - so **n8n is the enforcement**. Fix once in a shared helper: when `contact_id`/`space_id` is supplied, resolve the contact's codes via the existing `ContactAccessTypeService.resolve_contact_access_codes` and intersect. This is pre-existing and governs every promotion, catalogue and stock-list file, not just container status. |
| D20 | How do we gate fields without hardcoding each one? | **`resource_field_access (resource_key, field_name, access_levels jsonb)`** - access levels as data, per field, mirroring the `attachments.access_levels` shape that already works at scale. New sensitive field = one row, no deploy. Directly answers "contact may access incoming stock but not certain dates". **Unmapped fields stay visible**, so nothing existing breaks. Supersedes D16's hardcoded clearance-field gating. |
| D22 | Where does the configurable "requested attribute" enum live - n8n or the CRM? | **The CRM, and as a resolver rather than an enum.** Three things are hardcoded in n8n today: the requested-attribute list (parser prompt constant), the document routing words "price tag template"/"catalogue" (parser prompt constant), and the domain-entity matrix (`const ALLOWED = {...}` inside the `disallowed-entity-gate` Code node). All three become data on our side, carried by **two calls consume-main already makes every turn**: `GET /api/v1/external/contact-access-types/active` (the `get-access-types` node) and `POST /api/v1/system/references/resolve` (the `resolve-entity` node). No new n8n nodes, no extra round trip. **Register `attribute` as a reference type** so the parser emits the raw phrase and we canonicalise it to a field key; `attachment_type` is already an allowed entity type in the gate, so documents need only aliases (D21). |
| D25 | Serve the parser prompt text from the registry? | **REJECTED by the user - adds load and a runtime dependency.** It would be one small TTL-cached GET per turn at WhatsApp rates, but it makes n8n depend on our API for its prompt, so a CRM blip would silently degrade every conversation. Prompt text stays in n8n; changing wording stays a workflow edit. |
| D25a | What the parser prompt actually contains | n8n `sub-semantic-parser` (`XTODTw-dJcV0uRdC056hG`), one AI Agent node, **30,906 characters**. `requested_attributes` **already exists** in its output and the prompt states its purpose - *"the user asked about, so downstream shows only those - not the whole record"*. Only the vocabulary is frozen: `master_products: price, dimension` / `order: delivery, items` / `incoming: **eta**` (one value). Adding `eta_delay`, `gatepass`, `inspection`, `approval` currently means editing 31KB of prompt. |
| D25b | How bad is the duplication | **Eight enums in that prompt; three duplicated elsewhere.** `domain_hint` (12) and entity `hint` types (12) also live in `disallowed-entity-gate`'s JS `ALLOWED` map *and* the backend's `allowed_entity_types`; `routing.suggested_agent` (4) is also `sub-get-results`' `escalated_agent` enum. Plus `intent_hint` (11), `requested_attributes` (6), `attachment_type.canonical_code` (5), `suggested_team` (10), promotion brands (3). Adding `container_status_enquiries` today = three hand-synced edits; forgetting one fails silently. |
| D27 | Then how do we de-duplicate the enums at zero added load? | **Pass the vocabulary as workflow INPUT, not as prompt text or a new call.** `get-access-types` already calls `GET /api/v1/external/contact-access-types/active` every turn - extend that response with the vocabulary (attributes, domains, entity types, agents). consume-main passes it into `sub-semantic-parser` via `workflowInputs`; the prompt interpolates `{{ $json.vocabulary }}` instead of listing values inline. `disallowed-entity-gate` and the `escalated_agent` enum read the same object. **No new endpoint, no new call, no new dependency** - and adding an attribute or agent becomes one row instead of three edits. |
| D26 | ~~Prompt-text endpoint~~ | Dropped with D25. |
| D23 | Why not just ship the enum into the parser prompt? | **It would vary the prompt per contact per turn**, breaking prompt caching and - more seriously - the pinning the `sorento-regression-*` capture/replay/judge harness relies on. Resolving keeps the prompt constant. |
| D24 | One `incoming_stock` tool with per-field access - possible? | **Yes, that is D19 + D20.** And the enum and the enforcement derive from the **same** `resource_field_access` rows, so they cannot drift: a contact without gatepass access neither resolves "gate pass date" to anything nor receives the key. |
| D21 | With one generic tool, how does "send me the container status" pick the right file? | **Attachment types get natural-language aliases**, same pattern as `lookup_option_keywords`. One-time build; every future document is then an upload plus a couple of keywords. Skipping it forces a tool per file. |
| D18 | Only keep the latest sheet? | **No - keep every upload.** The endpoint serves the newest by `created_at`. Prior uploads survive as attachments and per-job source bytes, which is what makes a bad re-import reversible. |

## 4. Domain notes worth keeping

- **CIDB applicability is per-consignment, driven by HS code.** Fourth Schedule category 2 is
  *"Ceramic Products (Sanitary Wares) & Unglazed and Glazed Ceramic Tiles, Plastic Flushing"* (HS
  6906.00-6910.10, 3922.90). Brass taps (HS 8481) are not listed. That is why `Fitting` rows have
  empty inspection/approval and `Ceramic` rows do not - and why 25 Ceramic rows still don't (COA
  exemptions) and 1 Fitting row does (plastic cisterns are regulated). Not a per-category rule.
- **The sheet's targets are statutory.** CIDB: *"approves COA within 3 working days after
  verification"*. Sheet row 1 of `Arrived`: `APPROVAL` = "3 DAYS (NOT INCL INSP.)". Same number.
  `INSPECTION` = physical port verification by the CIDB Verification Officer; `APPROVAL` = COA
  issuance.
- **ePermit is the National Single Window, not a CIDB site.** COA is applied for at
  `epermit.dagangnet.com.my`; approved permits transmit to SMK (Customs), which is why
  inspection -> approval -> K1 submission is one chain. Staging exists at
  `epermitdev.dagangnet.com.my`. DagangNet sells system-to-system integration, so ask before
  scraping (O4).
- **`ETA DELAY` does double duty** - revised ETA and de-facto arrival. Explains `ATA` 6/407 and
  `actual_arrival_date` 0/112.

## 5. Hygiene finding, unrelated but real

Live `sorento-consume-main` (`9qVyfUxmRQqrpGRMDLRuz`) calls workflow `rysSPgUssLDf6xJc`, whose name
is **"sub-get-results TEST"**, and it is active. Production depends on a workflow named TEST. Not
part of this build; worth a separate ticket before anyone renames or archives it.

---

## 6. Phase 0 - journey

Done. See the UAC's `Journey` section. Every AC traces to a step.

## 7. Phase 1 - frontend prototype (mocks only, no backend)

Per the three-phase loop, build against mock fixtures and stub hooks first.

1. **Packing Lists list page** - add the operational columns to the existing DataGrid, hidden by
   default, `tableLayout: { width: 'fixed', columnsResizable: true }`, explicit `size`, `truncate` +
   `title` on long text. Column personalization through the existing `listing_key` config.
2. **Detail page** - new "Clearance & Delivery" section, every milestone rendered, explicit empty
   state, status pill from `lib/status-pill.ts`.
3. **Upload** - `Container Status` type in the existing Files upload dialog. Mock the job response
   including `queued`, `processing`, `partial`, `failed`.
4. **Tracking validation page** under `system-management` - DataGrid over mocked observation rows
   covering all three verdicts, plus the aggregate line.
5. Verify every state with Playwright MCP by **clicking through the sidebar from `/`**, never a deep
   URL. Screenshot golden path plus empty/error/partial. `browser_close` when done.
6. Output: the FE contract documented at the top of the service file. No backend code. No tests yet.

## 8. Phase 2 - backend + tests (test-first)

Ordered so each slice is independently verifiable.

**S1 - schema.** Migration: ops columns + `coa_permit_no` + `status_id` on `inbound_shipments`;
`shipment_tracking_observations`; `__audit_track__` on the model. Seed the lookup sets (liner, china
forwarder, malaysia forwarder, loc) with aliases from the workbook's dirty values. Verify a single
alembic head afterwards.

**S2 - status engine adoption.** `inbound_shipments` becomes the **first registered status entity in
this repo** - `register_status_entity` with `count_records`, `migrate_records`, `fact_attrs` for the
date columns, and a seeded graph. Auto-edges via `conditions_json` keyed on `ETA DELAY <= today` /
`W/H ARRIVALS`, never `ATA`. Keep `shipment_status` as a write-through cache.

**S3 - importer.** New container-status import on the `imports` queue. Own matcher (normalized
container, all statuses - explicitly not the packing-list matcher's not-fully-received rule).
Blank-never-clears. ISO 6346 row validation with reported rejects, plus an in-run uniqueness
assertion (0 collisions today; the assertion is what keeps that true). `import_source_store`
retention. Idempotency test: import twice, assert zero diff. Golden test against the real workbook
asserting **111 updated / 296 created / 408 total**.

**S4 - extend the existing query tool + gate fields.** Add the clearance fields to
`/api/v1/incoming-stock/list` and `crm_incoming_stock_list`. **No new tool, no new domain.** The
substance here is the server-side entitlement gate (D16): resolve the caller (contact access types /
staff permissions) and **omit** the clearance keys entirely when unentitled. Regression test that an
unentitled caller's response is byte-identical to today's. Agent `container_status_enquiries` seeded
and `agent_mcp_tools` wired **by the startup hook**, not left to an admin. Restart the MCP process so
FastMCP re-registers. `view=answer` projection deferred - n8n narrows.

**S5 - sheet retrieval, and the access model that makes it scale.** **No new endpoint and no new
tool** (D17-revised). Instead:
- `Container Status` attachment type + natural-language aliases so it resolves from
  "send me the container status" (D21). This is the one-time build; every future document is then an
  upload plus keywords.
- **Narrow-never-widen enforcement** in a shared helper (D19): when `contact_id`/`space_id` is
  supplied, resolve the contact's codes and intersect with the caller's `access_levels`. Fixes a
  pre-existing gap affecting every promotion, catalogue and stock-list file.
- `resource_field_access` table + serializer hook (D20) so field visibility is data. Unmapped fields
  stay visible - a test must prove existing responses are unchanged.
- Container status rows get `access_levels = ["sorento_office"]`; every upload retained, newest
  served (D18).

**S6 - carrier scraper adapters.** `integrations` row of type `container_tracking`; adapter registry
keyed on carrier; **CMA adapter first** as the pattern; **polled** via
`scheduled_task_service.register_handler` + RQ over open containers only (~77/day, staggered) since a
scraper has no push channel; `unsupported` observations for carriers with no adapter;
`integration_log` on every attempt including failures; liner cross-check flag. Fetch mechanism is
blocked on the O1 spike - **S6 splits into S6a (spike: prove one successful CMA fetch end to end) and
S6b (adapter + polling + observations)**, and S6b's estimate is not credible until S6a lands.

**S7 - ePermit adapter.** Blocked on O2. Authenticated session against `epermitdev` first;
`inspection` / `approval` observations; `coa_permit_no` capture.

**S8 - validation report.** Read-only endpoint computing `agree` / `disagree` / `integration_led`
plus lag, and the aggregate.

**S9 - n8n orchestration (grew after review).** With D15 reversed, narrowing lives here, so this is
no longer a one-field change: the parser must surface *which attribute was asked for*,
`sub-get-results` gains the optional `direct_answer` and must answer from the dumped record rather
than render it, and the new agent is added to the `escalated_agent` enum. The pre-deploy n8n
safeguard also sits here - as a second layer on top of the server-side gate, never as the mechanism.
**If this slice is skipped, a point lookup still returns a full record**: the CRM prevents the leak,
n8n prevents the dump.

**Tests, landing in this phase, not deferred:**
- **pytest** - every new route (happy path, auth denial, validation error), the importer golden +
  idempotency cases, E2's "observation ingest leaves the shipment byte-identical" assertion, status
  auto-transition cases. **Postgres only, never sqlite.** Every test seeds its own chain with a
  marker prefix - no `LIMIT 1` off an existing table, no assertion about a production row. Verify on
  an empty scratch DB before pushing.
- **vitest** - each new component across loading / empty / error / data.
- **playwright** - upload -> import -> row appears with clearance dates; validation page renders all
  three verdicts.
- **MCP pytest** - presenter `view=answer` projection.

## 9. Phase 3 - review

`/code-review` on the combined diff, then `docs/PR-CHECKLIST.md`, then PR.

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| First status-engine adopter in this repo | Admin UI, routes and rule bridge already exist and are unused, not unbuilt. Keep `shipment_status` as a cache so nothing existing depends on the new column. |
| ePermit scrape fragility (gov portal, session, possible OTP) | Staging first; O4 asks DagangNet for a supported feed; observations are validation-only so a broken scraper degrades nothing. |
| **CMA tracking page returns 403 to a plain HTTP GET** (verified) | O1 spike before any estimate. Backend has `httpx` only, no parser, no browser, on `python:3.11-slim`. Four candidate fetch mechanisms; S6 split into spike + build. |
| **Bot protection / markup drift breaks a scraper silently** | Failure writes `integration_log` and **no** observation - never a guessed value. Transient failure must not flip a carrier to `unsupported`. Precedent in this codebase: Cloudflare **1010** already hit once (bad UA on the embed path), so the failure mode is known. |
| **Coverage is now the sum of adapters built, not ~92%** | CMA alone = 79/407 = **19%**. Build order by volume (WHL 116 > CMA 79 > OOCL 72 > MSC 25 > COSCO 22 = 77% cumulative). Uncovered carriers carry `unsupported` observations so the gap is visible. |
| Carriers with no adapter | Explicit `unsupported` observations + flagged lookup options. No silent coverage claim. |
| Re-import overwrites good data with a stale sheet | Blank-never-clears; every overwrite lands in `audit_logs`; retained source file per job. |
| `direct_answer` regresses list answers | Optional field; "never drop records" untouched; regression harness before making it required. |
| Raw sheet leaks costs/margins to a dealer | `access_levels = ["sorento_office"]` plus agent grant. Two independent gates. |
| **Extending `crm_incoming_stock_list` exposes ETA delay + gatepass to every existing salesperson-facing agent on deploy** (user-flagged) | Server-side entitlement gate omits the keys for unentitled callers (D16), plus a regression test asserting an unentitled caller's response is byte-identical to today's. n8n safeguard is a second layer, not the mechanism. |
| Narrowing now lives entirely in n8n, so a skipped S9 silently reverts to record dumps | S9 is on the critical path for the *answer-quality* goal even though S4 alone satisfies the *data* goal. Do not ship S4 and call the feature done. |

## 11. Next action

Grill **this plan** before writing code (per methodology: grill -> plan -> grill the plan -> user
grill -> code). O1 is now a **spike, not a procurement item** (S6a: prove one successful CMA fetch
end to end, then estimate S6b). O2 is still a credentials request. S6b and S7 cannot start without
them; S1-S5 and S8-S9
are unblocked.
