# Container status tracking - acceptance criteria

> Status: DRAFT 2026-08-04, written FIRST per methodology, grilled with the user before any code.
> Source material: `Container Status 2026.xlsx`. **5 tabs holding 9 header blocks and 407
> containers**, because several tabs stack more than one titled section, each with its own header
> row: `Fitting` 17 + 2, `Ceramic` 55 + 0 + 0, `Arrived` 318, `Arrived - Joint Mocha Container`
> 15 + 0, `Arrived (Mocha) Joint BL` 0. A further 475 numbered rows carry no container number at all
> (427 of them in `Arrived`) and are blank scaffolding. **All 407 values are distinct and all 407
> pass ISO 6346** - there are no reject rows. **No container appears in more than one tab** -
> verified, so there is no cross-tab precedence problem on import. CIDB
> `Procedures for Importing Construction Products 5th Edition`, live `sorento-consume-main` +
> `sub-get-results` n8n workflows.
>
> Guardrail: integration-sourced values NEVER overwrite a human-entered value. They land in a
> separate append-only ledger and exist only to validate the system against the Excel before the
> Excel is retired.

## Journey

Four actors. In phase 1 the sheet stays the source of truth and nobody is asked to change how they
work. What changes is that the data stops being trapped in a file.

### The sheet maintainer - purchasing / logistics

Today they check each liner's website daily by shipper + container number to learn ETA and the
revised ETA, then check CIDB ePermit for inspection and approval dates, then type all of it into
`Container Status 2026.xlsx`. Roughly 500 containers a year, ~77 open at any time.

1. **They keep maintaining the Excel exactly as today.** Deliberate. Phase 1 asks them to change
   nothing about their own process, because a cutover before the data is trusted is how dual
   sources of truth get born.
2. **They import the sheet from Procurement -> Packing Lists**, via the toolbar's
   **Import Container Status** action. They fill in nothing else - the file carries every
   field. The upload lives in the domain the data belongs to, NOT in the generic file
   library: one sheet row is one packing list, so this is the screen they are already on.
   The workbook is still retained as an attachment behind the scenes so the assistant can
   hand it back to a contact, but that is storage, not somewhere anyone should navigate to
   in order to upload.
3. **The Upload Activity drawer opens on the queued job** and polls it to completion, the same
   handoff the SPO allocation and delivery order imports already give. The toast links straight to
   the job, and Import Job Details shows per-row outcomes including which rows were rejected and why.
4. **They open Procurement -> Packing Lists** and the containers they already know now carry
   clearance dates. Containers that exist only in the sheet are NOT conjured into packing lists -
   they are reported as skipped, because a packing list without lines, supplier or quantities is not
   a packing list (D32).
5. **What they hold at the end:** they stop answering "where is my container" by hand, and they can
   see for the first time whether the liner and ePermit feeds would have told them sooner.

### The contact asking on WhatsApp - access-gated

1. **They send a question in their own words** - "what's the eta delay for GXYU5106903", "when is
   the Yanggang container reaching", "has the CIDB approval come out".
2. **The system already knows** who they are (Respond contact -> access types -> company) and which
   agents they hold. They supply nothing but the question.
3. **They get the answer they asked for**, one line, with the date it was last known good. Not the
   record, not 51 fields, not a table.
4. **They ask for the sheet** - "send me container status" - and receive the actual uploaded
   workbook as a file in the chat.
5. **A contact without the grant gets neither**, and is never told the data exists.

### The admin

1. **Grants `container_status_enquiries`** to specific contacts. Nothing is visible by default.
2. **Maintains liner and forwarder options** as lookup sets, including aliases so the sheet's dirty
   spellings resolve on import.
3. **Reads the validation report** and gets the one sentence that justifies retiring the Excel:
   how often the feeds agree, how often they disagreed, and how many days earlier they knew.

### The system, unattended

1. **Container tracking aggregator pushes on ETA change** -> one observation row, timestamped. The
   record is not touched.
2. **CIDB ePermit is polled** for inspection and approval -> observation rows. The record is not
   touched.
3. **Every external call writes an `integration_log` row**, success or failure.

---

## Acceptance criteria

### A. Capture - upload and import (journey: maintainer 2-4)

- **A1.** The import entry point is the **Packing Lists** toolbar "Actions" dropdown
  (`secondaryActions`, the slot documented for Import actions), NOT the generic file library.
  Uploading there enqueues a container-status import on the `imports` RQ queue and returns
  immediately. The file is still stored as a `Container Status` attachment so AC group D can serve
  it back.
- **A1a.** A **dry run** is available before committing: it reports rows read, how many packing
  lists would be updated, how many rows have no packing list to update, and which rows are rejected,
  without writing anything. Against the current workbook that is 407 read / 111 update /
  0 create / 296 with no packing list / 0 rejected.
- **A1b.** The "no container status imported yet" empty state on a packing list links to the
  import action itself (`?import=container-status` opens the dialog), never to a page where the
  user has to hunt for the upload.
- **A1c.** The queued import is **visible while it runs**. The upload pushes an `import_job`
  session through `useUploadManager().startSession(...)`, so the Upload Activity drawer opens
  **already showing this import** - filename, row count, and a row that navigates to its import-job
  page - and the toast carries the same link. `notifyImportQueued()` on its own is not enough: it
  only invalidates the backend feed, and the feed has no row until the worker has created the job,
  so the drawer opens on an empty panel. The backend entry replaces the optimistic one through the
  normal reconcile path once it exists.
- **A2.** The import reads **all 5 tabs**. The tab name is recorded on each row for traceability
  and is **never** used to derive status.
- **A2a.** Parsing is **header-anchored, never positional**. Each sheet is scanned for rows whose
  cell text is exactly `CONTAINER`; each such row OPENS a block and that block's columns are
  resolved from its own header row. The current workbook has 9 such blocks across 5 tabs (`Fitting`
  rows 2 and 31, `Ceramic` 2, 69 and 75, `Arrived` 2, `Arrived - Joint Mocha` 2 and 22,
  `Arrived (Mocha) Joint BL` 2), so a repeated header is a section boundary, not a data row. A
  numbered row with no container number is blank scaffolding and is skipped without an error; there
  are 475 of them.
- **A2b.** Header names are matched **by name with an alias table**, because they drift between
  tabs. Known aliases today: `LINER` <- `RL` (Ceramic, 55 rows), `WAREHOUSE ARRIVALS` <-
  `W/H ARRIVALS` (Arrived), `CHINA FORWARDING COST (RMB)` <- `CHINA FREIGHT (RMB)` (Arrived),
  `SST` <- `10% SST` (Joint Mocha), `DEMURRAGE` <- `Demurrange`. Reading Ceramic's column 4 by
  position would have mislabelled 55 liners. An unrecognised header is reported, not guessed at.
- **A3.** Rows are matched to `inbound_shipments` on **normalized container number** (uppercase,
  separators stripped) across **every** `shipment_status`, including `fully_received` and
  `completed` - the clearance history of a container that already completed still belongs on its
  row.
- **A3a.** The import is **update-only. It never creates a packing list** (decision D32). REVISED
  after review: the first version created a shipment for every unmatched row, and on the real
  workbook that put **296 hollow rows** into the list with no shipment number, no supplier, no lines
  and a guessed shipment date. The sheet carries none of those things, so a row for an unknown
  container is not a packing list. A packing list is created from an actual packing list; this sheet
  annotates the ones that already exist.
- **A3b.** An unmatched row is **skipped, counted and named** - never silently dropped. The dry run
  says how many rows have no packing list and samples five container numbers, the job result carries
  `skipped_no_packing_list`, and each row gets an Import Job Details entry saying the fix is a
  packing list for that container, not a re-upload.
- **A4.** Given the current workbook and the current database (112 shipments, 111 of which appear in
  the workbook), an import updates **111** in place, skips **296**, and leaves the shipment count at
  **112**. A second import of the same file changes no row count and no field value.
- **A4a.** The coverage consequence is accepted and must stay visible: only **111 of 407** sheet
  containers (27%) can be answered about through the CRM until the other 296 have packing lists.
  Those 296 are mostly the archived `Arrived` tab; 34 of them are open containers.
- **A5.** A blank cell **never clears** an existing value. Sheet value wins only when non-empty.
- **A6.** A row whose container number fails ISO 6346 (4 letters + 7 digits) is rejected, not
  silently skipped, and appears in Import Job Details with a reason. In the current workbook
  **zero rows fail it** - all 407 values match. The 4 rows an earlier draft counted as rejects were
  the repeated header rows of A2a, which a header-anchored reader consumes as section boundaries and
  never offers to this rule. A non-zero reject count on this file means the block detection broke.
- **A6a.** The importer asserts container uniqueness within a single import run and reports any
  collision rather than last-write-wins. Verified today at zero collisions; the assertion is what
  keeps that true if a future workbook changes.
- **A7.** The original uploaded bytes are retained (`import_jobs.source_file_key`) and the
  attachment row persists. Re-uploads accumulate; nothing is overwritten or deleted.
- **A8.** Cost columns are **not** imported in phase 1 (decision D9). The retained original file is
  what preserves them.

### B. Storage shape (journey: maintainer 4)

- **B1.** The 29 operational columns land as flat columns on `inbound_shipments`. No milestone
  table, no milestone-policy table (decisions D3, D4).
- **B2.** `LINER`, `CHINA FORWARDER`, `MALAYSIA FORWARDER` and `LOC` resolve through
  `lookup_sets` / `lookup_options`, bound to their columns, with `lookup_option_keywords` carrying
  aliases so `KAIDILA`/`Kaidila` and `MAE`/`Maersk` both resolve. No new reference tables.
- **B3.** `InboundShipment` carries `__audit_track__ = True`, so every ETA revision writes an
  `audit_logs` row with `old_values`/`new_values`. There is no revision table (decision D5).
- **B4.** `REMARKS 1/2/3` become `activity_events` rows with `kind='user_update'` - the shared
  feed, **not** `internal_notes` (which is private to its author and would hide them).
- **B5.** `inbound_shipment` is registered as a status entity, but as a **timeline of independent
  checkpoints** - it does NOT carry `status_id` and has no `status_transitions` (decision D33). A
  container reaches whichever checkpoints its dates say it reached, in any combination, because the
  real workbook has containers with a gatepass and no inspection. `shipment_status` is untouched.
- **B5a.** The checkpoint list is **configuration, not code**: eleven `statuses` rows whose `key` is
  the date column and whose `label`, caption, group, order, colour and visibility are edited in
  System Management -> Status Graphs. `key` is frozen server-side, so renaming a checkpoint can never
  break its link to a column. Verified live: renaming "Gatepass" to "Released from port" and
  deactivating "ETC" changed the timeline from 11 checkpoints to 10 with no deploy.
- **B5b.** Deleting a checkpoint that containers have already reached is blocked by `count_records`;
  `migrate_records` is a no-op, because moving every container's gatepass onto its inspection date
  would be corruption rather than a migration.
- **B6.** Auto-transitions key on `ETA DELAY <= today` or `W/H ARRIVALS`, **never** on `ATA` -
  which is populated in 6 of 407 rows because `ETA DELAY` does double duty as the de-facto arrival
  date.
- **B7.** `ATA`, `ORI DOC RECEIVED`, `K1 SUBMISSION` and `YARD ARRIVALS` are **not in the system at
  all** - not columns, not parsed, not displayed (decision D34). REVISED: they were briefly stored
  "for round-tripping" behind a muted block, but fill rates of 6 / 4 / 4 / 4 out of 407 with nothing
  reading them makes that a column nobody maintains plus a UI nobody reads. The retained original
  file preserves them.
- **B8.** The clearance timeline shows **only checkpoints that were reached**, as one flat vertical
  list in configured order (D35, D36). No grouping, because group names would have to be hardcoded
  somewhere and an admin-added checkpoint would have nowhere to belong. No "Not reached" rows,
  because an unreached checkpoint is unrecorded rather than pending - the header count carries that.
- **B9.** The packing list detail page is organised into **tabs** (Timeline / Details / Documents /
  Shipment Lines), matching the users form, with `?tab=` keeping a tab linkable across a refresh.

### C. Answering (journey: contact 1-3)

- **C0.** Clearance fields are served by the EXISTING `/api/v1/incoming-stock/list` and
  `crm_incoming_stock_list`. No new endpoint, no new tool, no new domain.
- **C1.** Entitlement is decided **server-side** (decision D38). With a `contact_id`, the contact
  must hold the `container_status_enquiries` grant; without one, the staff user's role must hold
  `procurement.packing_lists.view_clearance`. The API key's own privileges never launder a contact's
  question into a privileged answer.
- **C2.** An unentitled caller's response is **byte-identical to today's** - the clearance keys are
  absent, not null. Asserted by a regression test, because null reads as "not reached yet" to
  anything consuming the response, an LLM included.
- **C3.** `estimated_arrival_date` is NOT gated: it is the public ETA those agents already read.
- **C4.** Fails closed on an unresolvable caller, an inactive agent, a revoked or expired grant, or a
  lookup that raises.
- **C5.** The `container_status_enquiries` agent is seeded by a startup bootstrap, active but held by
  nobody, so an admin has something to grant on day one without a manual insert.

**Division of labour (decision D15-revised): the CRM is the answer provider, n8n is the
orchestrator.** The CRM exposes every field the caller is entitled to see and enforces who may see
what. n8n knows which attribute was asked for and decides what to say. Narrowing is n8n's job;
visibility is ours.

- **C1.** A new access agent `container_status_enquiries` exists. No contact holds it by default;
  it is granted per contact via `contact_agent_access`.
- **C2.** **No new query tool.** `crm_incoming_stock_list` (existing, at
  `/api/v1/incoming-stock/list`) is extended with the clearance fields. There is exactly one
  shipment-rooted list tool, so there is no tool-picking ambiguity to design against.
- **C3.** **Clearance fields are gated server-side on the caller**, never by prompt and never by n8n
  alone. For a contact caller, entitlement resolves from `contact_id` -> `contact_access_types`; for
  a staff caller, from the JWT principal's permissions. A caller without entitlement receives the
  response **with the clearance keys absent**, not null-filled and not empty-stringed - absence is
  the only shape that cannot be mistaken for "no gatepass yet".
- **C4.** A salesperson-equivalent contact calling `crm_incoming_stock_list` today receives byte-for-
  byte what they receive before this change. Regression-tested explicitly, because this is the
  failure the user flagged: *"once deployed, all the eta delay, gate pass will be visible to
  salesperson"*.
- **C5.** n8n's safeguard is an **additional** layer on top of C3, not the mechanism. If the n8n
  safeguard were removed entirely, an unentitled caller would still receive no clearance field.
- **C6.** `sub-get-results`' output schema gains an **optional** `direct_answer` field carrying the
  answer to `user_goal`. Existing agents' outputs remain valid without it. Only the new agent's
  intents populate it.
- **C7.** The `answers[]` "return every record, never a sample" rule is **not** relaxed. List intents
  keep it; point lookups answer through `direct_answer`. **Consequence to accept:** if n8n does not
  implement the narrowing, a point lookup still renders a full record - the dump is prevented in n8n,
  not in the CRM.
- **C8.** `escalated_agent` in the `sub-get-results` prompt enum is extended to include the new
  agent, or escalation to it silently fails.
- **C9.** Asked "what's the eta delay for GXYU5106903", an entitled contact receives the ETA delay
  date and its as-of date as the reply. They do not receive a field dump, and no caller ever receives
  a cost field (no cost column is imported in phase 1).
- **C10.** Server-side `view=answer` projection via `PRESENTER_TOOLS` is **deferred**, not built.
  With n8n narrowing, it is redundant in phase 1. Revisit only if n8n-side narrowing proves
  unreliable across paraphrases.

### D. Serving the sheet (journey: contact 4)

**Access as data, not code (D19/D20/D21).** The scalability requirement is that a new file or a
newly-sensitive field must be *configuration*, never a deploy. `attachments.access_levels` already
proves the shape works at scale - Promotion files split `["dealer"]` 198 / `["end_user"]` 96 /
`["sorento_office"]` 59 rows today with no code. What is missing is enforcement, and one generic tool
rather than one tool per document.

- **D1.** **No new attachment tool and no new endpoint.** `crm_resource_attachments_list` +
  `attachment_type_id` filter serves container status. A type-pinned tool would be unreachable anyway:
  the RAG side only surfaces the generic list.
- **D2.** **Caller may narrow, never widen.** When `contact_id`/`space_id` is supplied, the backend
  resolves that contact's codes via the existing
  `ContactAccessTypeService.resolve_contact_access_codes` and **intersects** them with the caller's
  requested `access_levels`. A caller that omits `access_levels`, or asks for codes the contact does
  not hold, receives only what the contact is entitled to.
  - Today `access_levels` is a caller-supplied Query filter (`app/api/v1/resources/attachments.py:239`)
    and `sub-get-results` passes a precomputed intersection, so **n8n is the enforcement**. This AC
    closes a pre-existing gap affecting every promotion, catalogue and stock-list file - not only
    container status.
- **D3.** **Field visibility is data:** `resource_field_access (resource_key, field_name,
  access_levels jsonb)`. The serializer intersects with the caller's entitlement and **omits**
  non-permitted keys. A newly-sensitive field is one row, no deploy. This is what satisfies "a contact
  may access incoming stock but not certain dates".
- **D4.** **Unmapped fields stay visible.** Absence of a policy row means no restriction, so existing
  responses are unchanged. Proven by a test asserting today's responses are byte-identical.
- **D5.** **Attachment types carry natural-language aliases** (same pattern as
  `lookup_option_keywords`), so "send me the container status", "price tag template" and "warranty"
  each resolve to a type without a tool per document. This is the one-time build that makes every
  future document configuration-only.
- **D6.** Container status attachments carry `access_levels = ["sorento_office"]`.
- **D7.** **Every upload is retained**; the list returns the newest by `created_at`. Prior uploads
  remain as attachments and as per-job `import_jobs.source_file_key` bytes, which is what makes a bad
  re-import reversible.
- **D8.** Delivery uses the existing path with **zero n8n changes on the file-send leg**: the agent
  maps `file_path` -> `url`, `stored_filename` -> `filename`, `mime_type` -> `mimeType`, sets
  `response_intro` to "I have attached the file(s) below.", and consume-main's `get-presigned-url` +
  `send-message-files` nodes carry it to Respond.

### E. Integrations - observe, never overwrite (journey: system 1-3)

- **E1.** `shipment_tracking_observations (shipment_id, field_key, observed_value, source,
  source_ref, observed_at, fetched_at)` is append-only. Only integrations write it. No human write
  path exists.
- **E2.** No integration write ever mutates a column on `inbound_shipments`. Verified by a test
  that runs a full observation ingest and asserts the shipment row is byte-identical.
- **E3.** Container tracking runs through one adapter registry keyed on carrier. **Per-carrier
  adapters are the implementation** (decision D13-revised), starting with CMA
  (`https://www.cma-cgm.com/ebusiness/tracking`, searched by container number). The registry shape is
  unchanged from the aggregator design, so an aggregator or a third-party per-carrier API can be
  dropped in later as just another adapter without touching callers.
- **E3a.** Because a scraper has no push channel, acquisition is **polled, not webhooked**. The
  scheduler home is the existing `scheduled_task_service.register_handler(key, handler)` + RQ
  dispatch. Scope is open containers only (~77), one pass per day, staggered.
- **E3b.** A carrier adapter that cannot fetch (403, bot challenge, markup drift, timeout) records the
  failure in `integration_log` and writes **no** observation. It must never write a guessed or
  partially-parsed value, and it must not mark the carrier unsupported on a transient failure -
  `unsupported` is for carriers with no adapter, not for adapters that broke.
- **E4.** Lookup is **by container number only**. The sheet's `LINER` value selects the adapter and is
  also cross-checked against whatever carrier identity the page returns; a mismatch is reported as a
  data-quality flag.
- **E5.** A carrier with **no adapter built** produces an observation row with `source='unsupported'`
  and flags the carrier's lookup option. Coverage is now the sum of adapters built, not ~92% - with
  CMA alone it is **79 of 407 rows (19%)**. The uncovered remainder must never appear covered. No
  silent caps.
- **E5a.** Adapter build order follows volume, not convenience: **WHL 116, CMA 79, OOCL 72, MSC 25,
  COSCO 22** (= 77% cumulative), then EMC 21, YML 19, TCLC 19, SITC 12. CMA first is accepted as the
  *pattern* sample; WHL is the largest single win.
- **E6.** CIDB ePermit (`epermit.dagangnet.com.my`, Sorento's own account) is an authenticated
  adapter producing `inspection` and `approval` observations. Credentials live in
  `Integration.credentials_json`. Built and tested against `epermitdev.dagangnet.com.my` first.
- **E7.** Every external call writes an `integration_log` row on success **and** failure, with
  `business_table='inbound_shipments'` and `business_id` = the shipment UUID.
- **E8.** `coa_permit_no` exists on `inbound_shipments`.

### F. Validation surface (journey: admin 3)

- **F1.** A read-only page under `system-management` (sibling to `api-call-logs` / `import-logs`)
  lists container, field, sheet value, observed value, verdict and lag in days.
- **F2.** Verdict is one of `agree`, `disagree`, `integration_led`. `integration_led` carries the
  lag: observed on the 2nd, typed on the 5th = 3 days.
- **F3.** The page shows one aggregate line - "over N containers: X% agree, Y% integration led by
  avg Z days, W% disagree".
- **F4.** Observed values are **not** rendered on the packing-list detail page in phase 1. Nothing
  invites a user to treat them as authoritative.

### G. Read surface (journey: maintainer 4)

- **G1.** The existing `procurement-management/packing-lists` list and detail pages are extended.
  No second page is created for the same entity.
- **G2.** New operational columns are added to the DataGrid **hidden by default** and surfaced
  through the existing `list_query` column-config personalization keyed by `listing_key`.
- **G3.** The detail page gains a "Clearance & Delivery" section rendering every milestone date,
  always shown, with an explicit empty state per the CRUD UX standard.
- **G4.** Status pills come from `lib/status-pill.ts`, driven by the status graph.
- **G5.** No inline editing and no bulk-set in phase 1. The upload is the update mechanism
  (decision D12).

---

## Explicitly out of scope in phase 1

| Item | Why |
|---|---|
| 22 cost columns | Not needed for Q&A; retained original file preserves them (D9) |
| Generated Excel export in system format | Phase 1 serves the uploaded original (D10) |
| Bulk-set / inline date editing | Upload is the update path; `bulk_update_registry` is ready when wanted (D12) |
| Form SLA chasing and escalation | Worthless until dates land daily; handling lock is wrong for a container (D6) |
| `cidb_required` derivation | Cannot be derived from the sheet; lands with the ePermit adapter (D11) |
| Making `direct_answer` required for all agents | Needs the golden-master regression harness first (D8) |
| A new `container_status` query tool / domain | Reversed. One shipment-rooted list tool; n8n orchestrates (D15-revised) |
| Server-side `view=answer` projection | Redundant while n8n narrows (C10) |
| Cutover off the Excel | Deliberate. The validation report is what earns it. |

## Open items requiring the user or a third party

| # | Item | Blocks |
|---|---|---|
| O1 | **How the CMA scraper fetches.** A plain HTTP GET of `https://www.cma-cgm.com/ebusiness/tracking` returns **403 Forbidden**, so `httpx` alone cannot do it. The backend has `httpx` and no HTML parser and no browser; the image is `python:3.11-slim` (pango/cairo were already added for WeasyPrint, same class of native-dependency cost). Pick one: (a) headless Chromium in the backend/worker image, (b) a separate scraper container the worker calls, (c) a rendering/unblocking proxy, (d) a third-party per-carrier API. This is a spike, not a guess. | E3, E3a, E3b, E4 |
| O2 | ePermit login for Sorento's account | E6 - the screen scrape cannot be designed unseen |
| O3 | Which contacts get `container_status_enquiries` | C1 configuration only, not the build |
| O4 | Ask DagangNet (careline, 1300 133 133) for a supported system-to-system feed | Would replace the E6 scraper entirely |
