# UAC - Certificate register (product certification lifecycle)

**Status:** Draft (pre-code) · **Classification:** CORE (Product Management) · **Domain:** product / resources / automation / mcp
**Plan:** `documentation/plans/certificates/PLAN-certificate-register.md`

**Contract:** certification documents stop being anonymous files and become a **certificate register**. A
certificate is a first-class row with a scheme (`PPS` / `SPAN`), a certifying body (`IKRAM` / `JBC`), a
number, and a chain of **revisions** - one per issue, each with its own PDF and validity window. Products
link to the certificate **identity**, so a renewal causes zero link churn. Validity (`valid` /
`expiring_soon` / `expired` / `not_yet_valid`) is **always derived** from the current revision's dates,
never stored. Expiry reminders ride the existing automation engine, exactly like promotion-expiry. The
register is searchable by certificate number and by covered product from both the CRM UI and the n8n
agent, with no change to the consuming n8n workflow.

Tags: `[BE]` backend · `[FE]` frontend · `[E2E]` playwright · `[T]` unit/service test · `[N8N]` workflow change.

---

## Journey (Phase 0 - governing; every AC below traces to a step here)

**Actor A - staff filing a certificate.** Arrives from **Product Management → Files**, the same upload
dialog they use today. They drop `PPS - IKRAM 04424FC - EXP 23 DEC 2026.pdf` and pick attachment type
`Certification`. **That is the only decision they make.** The system already knows the company (from the
attachment), and reads the scheme, certifying body, number, issue/expiry dates and covered product codes
out of the PDF. Nothing derivable is asked. They end holding a certificate row that already lists 68
covered products and a countdown to 23 Dec 2026.

**Actor B - the same staff member 18 months later, renewing.** Same screen, same two actions: drop the new
PDF, pick `Certification`. The system recognises `PPS` + `04424FC` as an existing certificate and files the
new PDF as **revision 2** - it does not create a second certificate, does not ask "is this a renewal?",
and does not make them re-pick 68 products. Product pages immediately serve the new PDF and stop serving
the superseded one. They end with one certificate showing both PDFs and both validity windows.

**Actor C - whoever owns compliance.** Never browses. Receives an email 90 / 30 / 7 days before any
certificate expires, listing every affected certificate with its covered-product count and a deep link. If
they do open **Product Management → Certificates**, the default view is already scoped to what needs
attention - expiring and expired first, `needs review` badged - not an undifferentiated list.

**Actor D - a dealer on WhatsApp.** Asks "is your PPS cert still valid for WC8038". The reformulator
extracts `PPS`/`WC8038`, the resolver returns the certificate, the agent answers with the real validity
state. If it expired, the agent says **found but expired** - never presents it as live, and never answers
this question from a filename.

**What every other stakeholder is told automatically:** the uploader gets the existing attachment-linked
notification; the compliance owner gets the expiry email; the agent gets structured validity instead of a
PDF name. Nobody maintains a spreadsheet of expiry dates.

---

## Evidence this is built from (live data, `attachments` ⋈ `attachment_types`, 2026-08-03)

Nine `Certification` attachments exist, 239 `product_attachments` links, 185 distinct products:

```
PPS - IKRAM 04424FC     - EXP 23 DEC 2026     68 links
PPS - IKRAM 04324FC     - EXP 23 DEC 2026     16
PPS - IKRAM 04224FC     - EXP 23 DEC 2026      0 links   <- existing silent failure
PPS - IKRAM 04124FC    -   01 APRIL 2027    8
PPS - JBC WCM PC 000321 - EXP 07 JAN 2027     12
PPS - JBC WCM PC 000320 - EXP 07 JAN 2027     90
PPS - JBC WCM PC 000319 - EXP 07 JAN 2027      8
PPS - JBC WCM PC 000318 - EXP 07 JAN 2027     29
SPAN - IKRAM 04124FC - IWC - EXP 05 APRIL 2029    8
```

Three facts drive the design: (1) scheme, body and number are three fields, not one; (2) **`04124FC`
appears under both `PPS` and `SPAN`** with different expiries, so the identity key must include the
scheme; (3) one of nine already has zero product links with nothing recording the failure, which is why
`needs_review` exists.

---

## Code anchors

`Attachment` / `AttachmentType` - `app/models/resources.py:54` / `:31` · `ProductAttachment` -
`app/models/product.py:199` · webhook payload - `app/services/attachment_webhook_helper.py:71` · external
link route - `app/api/v1/external/product_attachments.py` (`create_product_attachment`) · resolver entity
types - `app/api/v1/system/references.py:36` (`_RESOLVER_ENTITY_TYPES`), POST route `:1476` · resolver
internals - `app/services/entity_resolver.py` (`_strip_all_ws:658`, `_ws_insensitive_lower:670`,
`_TIER2_PROBES:2109`, `_EMBEDDING_SOURCE_TYPES:2153`, `_trgm_lookup:2276`) · promotion-expiry precedent -
`app/services/automation_triggers.py:100` + `app/models/marketing.py:40` · MCP catalog -
`sorento_crm_mcp/sorento_crm_mcp/catalog.py:116` · pills - `lib/status-pill.ts` · menu - `config/menu.config.tsx`
Product Management group at **both** ~477 and ~1335 · n8n upload flow - wf `_NbFU3cCoEQwPSbvn14vV` ·
n8n consume flow - wf `9qVyfUxmRQqrpGRMDLRuz`, node `resolve-entity`.

---

## Group SCH - schema

- **SCH-1 `[BE][T]`** GIVEN the migration, THEN `certificates` exists with `id`, `company_id` (NOT NULL,
  `CompanyScopedMixin`, owned - **not** `__company_shared__`), `attachment_type_id`, `scheme`,
  `certifying_body`, `certificate_number`, `issuer`, `title`, `status`, `current_revision_id`,
  `possible_duplicate_of_certificate_id`, `created_at`, `updated_at`, `created_by`.
- **SCH-2 `[BE][T]`** THEN a UNIQUE index enforces identity on
  `(company_id, upper(regexp_replace(scheme || certificate_number, '[^A-Za-z0-9]', '', 'g')))` - so
  `PPS`/`04124FC` and `SPAN`/`04124FC` are two rows, and `PPS 0119` ≡ `PPS-0119` ≡ `pps0119` are one.
- **SCH-3 `[BE][T]`** THEN `certificate_revisions` exists with `id`, `certificate_id` (FK CASCADE),
  `revision_no` (unique per certificate), `attachment_id` (FK `attachments`, **nullable**), `issued_at`,
  `valid_from`, `valid_until`, `is_current`, `source` (`ai`|`manual`), `needs_review`, `review_reasons`
  (JSONB), `extracted_json` (JSONB), `unmatched_products` (JSONB), `created_at`, `created_by`.
- **SCH-4 `[BE][T]`** THEN a partial unique index guarantees **at most one** `is_current = true` revision
  per certificate.
- **SCH-5 `[BE][T]`** THEN `certificate_products` exists - `certificate_id`, `product_id`, `source`
  (`ai`|`manual`), `created_at`, `created_by` - unique on `(certificate_id, product_id)`.
- **SCH-6 `[BE][T]`** THEN `attachment_types` gains `is_certificate BOOLEAN NOT NULL DEFAULT false` and
  `max_validity_months INTEGER NULL`; migration is idempotent and downgrade is clean.
- **SCH-7 `[BE]`** `certificates.status` is a VARCHAR + CHECK over `active` | `archived` only.
  **No validity value is ever a status** - `expired` / `expiring_soon` are rejected by the CHECK, and so is
  `revoked` (cut; a revoked certificate is archived with a note).
- **SCH-8 `[BE]`** There is **no** `certificates.access_levels` column - visibility is read from the
  current revision's attachment (see Group SEC).

## Group VAL - derived validity (never stored)

- **VAL-1 `[BE][T]`** GIVEN a certificate whose current revision has `valid_until` in the future beyond the
  warn window, THEN the serialized row reports `validity_state='valid'`, `is_expired=false` and an integer
  `days_until_expiry`.
- **VAL-2 `[BE][T]`** GIVEN `valid_until` within the warn window, THEN `validity_state='expiring_soon'`.
  The warn window is `EXPIRING_SOON_DAYS = 30`, a module constant in `certificate_service.py`. It is
  deliberately INDEPENDENT of the 90/30/7 reminder automations: the pill answers "is this close to
  lapsing", the automations answer "who should be emailed today", and coupling them would mean changing a
  colour by editing an automation.
- **VAL-3 `[BE][T]`** GIVEN `valid_until` in the past, THEN `validity_state='expired'` and
  `is_expired=true` - **with no write of any kind** (no cron, no status change, no column update).
- **VAL-4 `[BE][T]`** GIVEN `valid_from` in the future, THEN `validity_state='not_yet_valid'`.
- **VAL-5 `[BE][T]`** GIVEN a NULL `valid_until`, THEN `validity_state='unknown'`, `needs_review=true`, and
  the certificate is **never** matched by any expiry reminder. A missing date is never treated as "no expiry".
- **VAL-5a `[BE][T]`** GIVEN a certificate with **no current revision at all** (hand-created before any
  document arrives), THEN it reads `validity_state='unknown'` AND `needs_review=true` with reason
  `no_revision_on_file`. The serializer and the `needs_review` list filter must default a NULL revision the
  same way: defaulting either to `false` hides the row from the one view meant to surface it, and if the two
  defaults disagree the badge and the filter show different rows.
- **VAL-6 `[BE][T]`** Validity is computed from the **current revision only**; a superseded revision's
  expired window never makes the certificate read expired.

## Group ING - ingest from the upload flow

- **ING-1 `[N8N]`** `analyze-product-document` is switched to Gemini **structured output** and additionally
  returns `scheme`, `certifying_body`, `certificate_number`, `issued_at`, `valid_from`, `valid_until`
  (nulls for non-certificates). No node added, no branch rewired - Switch outputs 0/1/2 keep funnelling
  into `switch-attachment-type` as today.
- **ING-2 `[BE]`** `POST /api/v1/external/product-attachments` accepts the optional cert fields alongside
  the existing `attachment_id` / `products` / `access_levels` body. Same URL, same node
  (`technical-attachments-create`), so the workflow's HTTP node is unchanged.
- **ING-3 `[BE][T]`** GIVEN cert fields are supplied AND the attachment's type has `is_certificate=true`,
  THEN the service upserts the identity, appends a revision, records coverage, and writes the projection -
  **in one transaction**.
- **ING-4 `[BE][T]`** GIVEN cert fields are supplied but the attachment's type has `is_certificate=false`,
  THEN the cert fields are **ignored** and only the existing product-attachment linking happens. A
  Technical Specifications sheet quoting "cert PPS 0119" must not mint a certificate. The guard is
  server-side, never in the prompt.
- **ING-5 `[BE][T]`** GIVEN no cert fields, THEN behaviour is byte-identical to today (regression guard for
  the 951 Technical Specifications and all Product Photos rows).
- **ING-6 `[BE][T]`** GIVEN `certificate_number` is absent/blank while the type is cert-bearing, THEN the
  attachment still links to products (no regression) and an `integration_log` warning records why no
  certificate was created.
- **ING-7 `[BE][T]`** `extracted_json` stores the raw model output for every AI-sourced revision, so a
  wrong date is attributable to the model or the PDF after the fact.

## Group RVW - needs_review (deterministic, no model judgement)

- **RVW-1 `[BE][T]`** `needs_review=true` with a machine-readable reason in `review_reasons` when ANY of:
  a required field is missing/unparseable; **any** extracted product string failed to match;
  `valid_until <= valid_from`; `valid_until` already past at ingest; or `valid_until` exceeds
  `attachment_types.max_validity_months` from `valid_from`.
- **RVW-2 `[BE][T]`** GIVEN `max_validity_months = 60` and an extracted `valid_until` 15 years out, THEN
  the revision is created, flagged, and the reason names the implausible span - the hallucination is loud,
  not swallowed.
- **RVW-1a `[BE]`** "Required field" is pinned to `REQUIRED_EXTRACTION_FIELDS = (scheme,
  certificate_number, valid_until)`. `valid_from` is deliberately EXCLUDED: most certificate PDFs state
  only an expiry, so requiring it would flag nearly every genuine ingest and train people to ignore the
  flag. The implausible-span check therefore falls back to `valid_from or issued_at or today`, so a
  15-year hallucination is still caught when no start date was printed.
- **RVW-3 `[BE][T]`** Every unmatched product string is persisted verbatim in
  `revision.unmatched_products`. Reproduces today's silent `PPS - IKRAM 04224FC` zero-link failure as a
  visible flag.
- **RVW-3a `[BE][T]`** A certificate created with ZERO coverage AND ZERO unmatched strings is flagged
  `no_product_coverage`. RVW-3 alone does not catch the live `PPS - IKRAM 04224FC` case: nothing was
  extracted at all, so there is no unmatched string to record and the certificate would look clean while
  covering nothing.
- **RVW-4 `[BE][T]`** A human edit that fixes the flagged field clears `needs_review` and stamps the
  reviewing user; clearing it is never automatic.
- **RVW-5 `[BE]`** `needs_review` does **not** suppress the certificate - per the auto-active decision it
  is live, projected and reminder-eligible. The flag is a signal, not a gate.

## Group REV - revisions and renewal

- **REV-1 `[BE][T]`** GIVEN an upload whose normalized `scheme + certificate_number` matches an existing
  certificate in the same company, THEN a **new revision** is appended (`revision_no = max + 1`,
  `is_current = true`), the previous revision flips to `is_current = false`, and **no new certificate row
  is created**.
- **REV-2 `[BE][T]`** THEN `certificate_products` is **untouched** by a renewal - coverage lives on the
  identity, so 68 product links survive the renewal with zero writes.
- **REV-3 `[BE][T]`** THEN the projection re-points: `product_attachments` rows for the **previous**
  revision's attachment are **hard-deleted**, and rows for the new attachment are inserted for every
  covered product. A dealer can never be served the superseded PDF.
- **REV-4 `[BE][T]`** THEN the superseded attachment row itself is **not** deleted or trashed - it remains
  owned by its revision and downloadable from the certificate detail page.
- **REV-5 `[BE][T]`** GIVEN a revision whose attachment was later trashed (`is_deleted=true`), THEN the
  revision still renders in the timeline with its dates and an explicit "file removed" state - the
  revision row never disappears.
- **REV-6 `[BE][T]`** Renewal detection is scoped to `(company_id, scheme)`. `SPAN`/`04124FC` must never be
  filed as a revision of `PPS`/`04124FC`.

## Group DUP - near-match and merge

- **DUP-1 `[BE][T]`** GIVEN no exact identity match, THEN a `pg_trgm` similarity probe runs against
  certificates of the same `(company_id, scheme)`. **This applies to the MANUAL create path as well as to
  extraction** - a human typing `04124FG` for `04124FC` forks a certificate exactly the way OCR does, and
  the fork then counts down its own expiry while the original keeps nagging.
- **DUP-2 `[BE][T]`** GIVEN similarity above threshold, THEN a **new certificate is still created** and
  stamped `possible_duplicate_of_certificate_id` + `needs_review`. Auto-merge is never performed - a wrong
  merge would overwrite a real certificate's identity.
- **DUP-3 `[FE]`** The certificate detail renders "may be a renewal of `<scheme> <number>`" with a link to
  the suspected original whenever `possible_duplicate_of_certificate_id` is set.
- **DUP-4 `[BE][T]`** `POST /api/v1/master-data/certificates/{id}/merge-into/{target_id}` moves this
  certificate's revisions onto the target as `revision_no = target max + 1 …`, re-points the projection,
  merges coverage (union, `source` preserved), and hard-deletes the emptied certificate.
- **DUP-5 `[BE][T]`** Merge refuses (422) when target and source differ in `company_id`, or when
  `target_id == id`.
- **DUP-6 `[FE][E2E]`** The merge action sits behind an `AlertDialog` naming both certificates and the
  revision count being moved - never a one-click. Copy: "Confirm merge" / "This action cannot be undone".

## Group COV - coverage and the projection

- **COV-1 `[BE][T]`** `certificate_products` is the **only** authoring surface for coverage.
  `product_attachments` rows for a cert-bearing attachment are written exclusively by the certificate
  service.
- **COV-2 `[BE][T]`** Each coverage row records `source='ai'` for extracted links and `'manual'` for
  human-added ones; the FE shows the split so an inferred link is never presented as confirmed.
- **COV-3 `[BE][T]`** Adding coverage manually inserts the projection row for the current revision's
  attachment (with that attachment's `access_levels`); removing coverage hard-deletes it.
- **COV-4 `[BE][T]`** An **idempotent reconciler** (JOIN-based "set to the correct value where it differs",
  not "insert where missing") brings `product_attachments` back into agreement with
  `certificate_products` × current revision, and is safe to re-run.
- **COV-5 `[BE][T]`** Deleting a certificate hard-deletes its revisions, coverage and projection rows; the
  underlying `attachments` rows survive.
- **COV-6 `[FE][E2E]`** Certificate delete and any coverage unlink are both confirmed via `AlertDialog`
  (standing rule: confirm before delete **or** detach).

## Group LIF - lifecycle

- **LIF-1 `[BE][T]`** A new certificate is created `status='active'` - there is no draft/approval gate.
- **LIF-2 `[BE][T]`** `archived` is terminal for reminder purposes: an archived certificate is **never**
  matched by an expiry reminder, regardless of dates.
- **LIF-3 `[FE]`** `archived` drops out of the list's default filter and renders its pill from
  `lib/status-pill.ts` (no bespoke colour map).
- **LIF-4 `[BE]`** The status set is exactly `active` | `archived`. There is **no** `revoked` value: a
  revoked certificate is archived, with the reason carried in the free-text note. Two values is also why
  this is a VARCHAR + CHECK rather than a status-engine graph.

## Group REM - expiry reminders (promotion parity)

- **REM-1 `[BE][T]`** A trigger `days_before_certificate_expiry` is registered with config
  `{days_before: int}` and `fact_sources=("certificate",)`, matching
  `current_revision.valid_until == today + days_before` in the automation's timezone - the same exact-date
  semantics as `_trigger_days_before_promotion_end`.
- **REM-2 `[BE][T]`** Matches exclude: `status != 'active'`, NULL `valid_until`, and non-current revisions.
- **REM-3 `[BE][T]`** Three automation rows with `days_before` 90 / 30 / 7 produce three independent
  reminders with **no new code**; `group_matches=true` collapses a multi-certificate day into one email per
  recipient.
- **REM-4 `[BE][T]`** Email context exposes `scheme`, `certificate_number`, `certifying_body`,
  `valid_until`, `days_until_expiry`, covered-product count, and an **internal** deep link
  (`/master-data-management/certificates/{id}`) - staff recipients get the in-system page, never a public
  `/view?token=` link.
- **REM-5 `[BE][T]`** `expiry_notify_batch_id` is stamped on notified certificates and the list accepts it
  as a filter, so the email's link opens exactly the set that was emailed (mirrors the promotion pattern).
- **REM-6 `[BE][T]`** `conditions_json` over the `certificate` fact source can scope an automation to a
  scheme or a company; an **empty** tree matches everything (documented, per the rule-engine trap).
- **REM-7 `[T]`** Documented and tested limitation: a scheduler outage on the exact match day means that
  window's email never fires. Mitigation is FE-1 (the list always shows derived countdowns), not a stamp.

## Group RES - entity resolution (consume flow)

- **RES-1 `[BE][T]`** `certificate` is added to `_RESOLVER_ENTITY_TYPES`; `POST /api/v1/system/references/resolve`
  returns `entity_type='certificate'` rows. **No change to n8n wf `9qVyfUxmRQqrpGRMDLRuz`** -
  `fallback_to_all_types: true` and reformulator hints already carry it.
- **RES-2 `[BE][T]`** `_probe_certificate` matches the number whitespace- and punctuation-insensitively via
  the existing `_strip_all_ws` / `_ws_insensitive_lower` helpers: `PPS 0119`, `PPS0119`, `pps-0119` and
  `WCM PC 000321` all resolve.
- **RES-3 `[BE][T]`** A token matching a number under two schemes (`04124FC`) returns **both** candidates
  for disambiguation - never silently one.
- **RES-4 `[BE][T]`** `_prefix_probe_certificate` is registered in `_TIER2_PROBES`; `certificate` is added
  to `_EMBEDDING_SOURCE_TYPES` so tier-3 prose ("water fitting approval for angle valves") resolves.
- **RES-5 `[BE][T]`** Certificates emit `source_type='certificate'` into `embedding_queue` on create/update
  (number, scheme, body, issuer, title, covered product codes). Dates are **not** embedded - validity is
  answered by SQL, per the pipeline rule that numerics stay out of embeddings.

## Group MCP - agent tools

- **MCP-1 `[BE]`** `GET /api/v1/master-data/certificates` supports `certificate_ids`, `certificate_number`
  (raw; normalized server-side), `product_ids`, `scheme`, `status`, `validity_state`,
  `expiring_within_days`, `valid_on`, `needs_review`, `expiry_notify_batch_id`, `resolve_signed_urls`,
  `page`, `limit`, `sort`, `dir`, `contact_id`, `space_id`.
- **MCP-2 `[MCP]`** `crm_certificates_list` is added to `CATALOG` with `domain="products"`,
  `related_tools=("crm_master_product_attachments_list", "crm_master_products_list")`, and a description
  carrying the **FOUND-BUT-EXPIRED** instruction verbatim from the promotion tools.
- **MCP-3 `[MCP]`** Every row carries `valid_from`, `valid_until`, `validity_state`, `is_expired`,
  `covered_product_count`. `updated_at` is emitted as **naive Malaysia wall-clock**, not `+08:00`.
- **MCP-4 `[MCP]`** `crm_master_product_attachments_list` rows whose attachment type is cert-bearing gain a
  nested `certificate { id, scheme, certificate_number, valid_until, validity_state, is_expired }`; rows of
  other types are unchanged. Confirmed inline (over a second tool call) so "is WC8038's cert still valid" is
  one call; the cost is a join on a hot tool.
  **Additive only:** `certificate` is a THIRD sibling key beside the existing `product` and `attachment`
  objects on `ProductAttachmentResponse` (`app/schemas/product.py:406`). No existing key changes name, type
  or meaning, and the key is `null` on every non-cert row, so the 951 Technical Specifications rows and all
  Product Photos rows serialize byte-identically to today. `validity_state` is shipped alongside
  `valid_until` deliberately: handing the model a bare date makes it do calendar arithmetic to decide
  whether the certificate is live.
- **MCP-4a `[BE][T]`** Regression: a response for a non-cert-bearing attachment type is asserted equal to
  the pre-change serialization, key for key.
- **MCP-7 `[BE][T]`** **view = render.** `resolve_signed_urls=true` resolves the **current revision's**
  attachment into `preview_url` + `download_url`, signed via `storage_router.resolve_signed_url` so both
  `s3` and `r2` rows work. This is what feeds the consume flow's `send-message-files` node, so a dealer
  asking for the certificate receives the PDF rather than metadata. A row whose current revision has a NULL
  or trashed `attachment_id` returns nulls for both, never a broken URL.
- **MCP-8 `[BE][T]`** Superseded revisions are **never** URL-resolved by the tool. Historical PDFs are
  reachable only from the certificate detail page, so no agent path can hand out an expired document.

### `view=render` (the presenter envelope) - do NOT skip

`view=render` is a real opt-in mode in `sorento_crm_mcp/presenters.py`: it transforms the sanitized raw
response into ONE uniform envelope (`result_type` / `intro` / `items[{title,fields,flags}]` / `attachments` /
`action_links`). `crm_master_product_attachments_list` is already in `PRESENTER_TOOLS`, and its presenter
(`_product_attachments`, `presenters.py:430`) **whitelists** fields - Product Code, Product Name,
Description, Dimensions, Attachment Type, File Name, plus `b.attach(att)` for url / filename / mimeType /
attachmentType. A nested `certificate{}` on the raw response is therefore **silently dropped in render
mode**, which is the mode the n8n consumer actually uses.

- **MCP-9 `[MCP][T]`** `_product_attachments` gains a `("Valid Until", certificate.valid_until)` pair and
  passes `expired=certificate.is_expired` into `b.item(...)`. This reuses the envelope's **existing**
  `flags.expired` - the same mechanism `_promotions` uses (`presenters.py:383`) - so the envelope shape does
  not change and the n8n renderer needs no update. Non-cert rows are unaffected (no field, flag stays false).
- **MCP-10 `[MCP][T]`** `crm_certificates_list` is added to `PRESENTER_TOOLS`, `_RESULT_TYPE`
  (`"certificates"`) and `_DEFAULT_INTRO`, with a `_certificates` presenter that emits scheme / number /
  certifying body / valid-until fields, sets `expired` from `is_expired`, and calls `b.attach()` on the
  **current revision's** attachment so render mode actually delivers the PDF. Superseded revisions are never
  attached (MCP-8).
- **MCP-11 `[MCP][T]`** A `view=render` call on a certificate whose current revision has no usable file
  returns the item with its fields and an **empty** `attachments` array - never a null or broken url entry.
- **MCP-5 `[BE][T]`** The new tool is auto-linked into `agent_mcp_tools` by the startup hook - never left
  for an admin to wire.
- **MCP-6 `[BE]`** The MCP process must be restarted for the tool to appear in the assistant dropdown
  (`list_tools()` is read from the live server, not the DB catalog) - called out in the deploy notes.

## Group FE - screens

- **FE-1 `[FE][E2E]`** **Product Management → Certificates** (`/master-data-management/certificates`,
  `master_data.certificates.view`) added to **both** menu arrays in `config/menu.config.tsx`. Reached by
  clicking through the sidebar, not by deep link.
- **FE-2 `[FE]`** List is a shared `DataGrid` with `tableLayout: {width:'fixed', columnsResizable:true}`,
  `columnResizeMode:'onChange'`, explicit `size` per column, `truncate` + `title` on long text. Columns:
  scheme, number, certifying body, covered products, valid until, validity pill, status pill, needs-review
  badge.
- **FE-2a `[FE]`** **No bespoke type scale.** Typography comes from the shared components as-is: table base
  `text-sm font-normal` (`data-grid-table.tsx:60`), head cells `h-12 px-4 font-normal text-muted-foreground`
  on a `bg-muted/40` row (`ui/table.tsx:50`, `data-grid-table.tsx:97`), body cells `p-4 align-middle`, pills
  via `STATUS_PILL_BASE` (`rounded-full px-2 py-0.5 text-xs font-semibold`). No uppercase column headers, no
  hand-rolled font sizes, no local table markup - the certificate list and detail must be visually
  indistinguishable in type and spacing from the existing list and form views.
- **FE-3 `[FE][E2E]`** ~~The default filter is **validity-scoped** (expiring + expired first), not "all".~~
  **Superseded after live use.** The list opens **unfiltered**: its row count must equal the whole register,
  so it can be reconciled against the certification files on file. The scoped default withheld rows on
  arrival and made the two counts disagree with nothing on screen to explain it. "Needs attention
  (expiring + expired)" stays the first option in the Filters popover, one click away, so REM-7 is still
  mitigated - by a filter the user chooses, not one applied behind their back.
- **FE-4 `[FE]`** Filters: `validity_state`, `expiring_within_days`, `scheme`, `status`, `needs_review`,
  plus search by number. All dropdowns use the searchable-select standard (`ui/select.tsx` is banned).
- **FE-5 `[FE][E2E]`** Detail page at `/master-data-management/certificates/{id}` renders **every** section
  even when empty, each with an explicit empty state + next-step CTA: header (scheme · number · validity
  pill · status pill), revision timeline, covered products, unmatched strings, suspected duplicate,
  reminder history.
- **FE-6 `[FE]`** Revision history renders as a **delivery-tracking timeline** (parcel-tracking / version-history
  reading order: newest first, top-down, one node per event - Issued / Renewed / Superseded), NOT a plain
  list. Reuse the existing rail-and-dot pattern from `ActivityTimeline.tsx` rather than inventing a
  component: `ol.relative.space-y-4.ps-4` with `before:absolute before:inset-y-1 before:start-[5px]
  before:w-px before:bg-border`, and `li.relative.ps-6` carrying an `absolute start-0 size-2.5 rounded-full
  ring-4 ring-background` dot. Current revision's dot is primary; superseded dots are muted.
- **FE-6a `[FE]`** Each node shows what happened, when (absolute date plus relative "7 months ago" via the
  shared `timeAgo`), the revision number and validity window, the file with preview / download (or "file
  removed"), and that revision's `access_levels` - so a renewal that widened visibility is visible rather
  than silent.
- **FE-7 `[FE]`** Covered products list encodes `source` **by colour, not by a text badge on every row**: a
  small colour dot plus chip border (muted = inferred by AI, primary = human-confirmed) with **one** legend
  above the list. The words "ai" / "manual" must not be repeated per row. Add (searchable product select) and
  unlink (confirmed) actions. No UUID is ever rendered.
- **FE-8 `[FE]`** Create / edit is a **modal**; delete and merge are `AlertDialog`-confirmed with
  destructive styling. No browser `confirm()`.
- **FE-9 `[FE]`** Detail header uses `flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between`
  with `min-w-0 break-words` on the title and `flex-wrap` on actions; verified at ~375px with no page-wide
  horizontal overflow.
- **FE-10 `[FE]`** Attachment-type admin dialog gains `is_certificate` + `max_validity_months` (blank =
  unlimited), beside the existing `max_count_per_entity`.
- **FE-11 `[FE]`** Product detail's attachment tab shows the validity pill on cert-bearing attachments, so
  an expired certificate is obvious from the product page.
- **FE-12 `[FE]`** No feature explanation text inside the UI - it goes in the user guide.

## Group SEC - company scope and visibility

- **SEC-1 `[BE][T]`** `company_id` is taken from the attachment's company via the existing
  `scope_to_attachment_company` path; a product in another company is never linked (mirrors AC-G2).
- **SEC-2 `[BE][T]`** Certificate reads are company-scope filtered fail-closed; a cross-company
  `certificate_id` returns 404, not 403-with-data.
- **SEC-2a `[BE][T]` (security-critical)** `certificate_revisions` and `certificate_products` carry no
  `company_id`, so they are NOT `CompanyScopedMixin` models and the automatic scope predicate does not
  reach them. Isolation holds ONLY because every read path enters through `Certificate`. Any query on a
  child table MUST join or filter through `Certificate`; a direct child query is unscoped and leaks across
  companies. Tests must include a cross-company child-table probe.
- **SEC-3 `[BE][T]`** Projection rows inherit `access_levels` from the **current revision's attachment**;
  there is no certificate-level override.
- **SEC-4 `[BE][T]`** Endpoint tests cover happy path, auth denial, and validation error for every new
  route.

## Group BF - backfill

- **BF-1 `[BE][T]`** An idempotent script parses the 9 existing `Certification` filenames
  (`{scheme} - {body} {number} - [EXP] {date}`) into certificates + one revision each.
- **BF-2 `[BE][T]`** Coverage is adopted from the existing 239 `product_attachments` rows with
  `source='ai'`; the projection is left byte-identical (rows already exist and already match).
- **BF-3 `[BE][T]`** Every backfilled revision is stamped `needs_review=true` with reason
  `backfilled_from_filename` - no filename-derived date is presented as verified.
- **BF-4 `[BE][T]`** `PPS - IKRAM 04224FC` (zero links) backfills as a certificate with **zero** coverage
  and a review reason naming it - the pre-existing failure becomes visible instead of inherited.
- **BF-5 `[BE][T]`** `PPS - IKRAM 04124FC` and `SPAN - IKRAM 04124FC` backfill as **two** certificates.
  This is the regression test for the identity key.
- **BF-6 `[BE][T]`** Re-running the script changes nothing (idempotent, JOIN-based).
- **BF-7 `[BE][T]`** The script is **dry-run by default**: it prints a parse table (filename to scheme /
  certifying_body / certificate_number / issued / valid_until / adopted coverage count) and **writes
  nothing**, assigning no ids. A real run happens only behind an explicit flag, on explicit approval. A
  dry-run that writes anything is a defect (see the batch-script dry-run rule).

## Group T - test substrate (non-negotiable)

- **T-1** Postgres only. No sqlite engine, no `@compiles(..., "sqlite")`, no mutation of shared
  `Base.metadata` column types.
- **T-2** **Every test seeds its own chain** - attachment type → attachment → certificate → revision →
  coverage - each with a marker prefix. No `LIMIT 1` off an existing table, no assertion about a production
  row, no dependence on the 9 real certificates.
- **T-3** Marker-scoped cleanup deletes children before parents (projection → coverage → revisions →
  certificate → attachment → type).
- **T-4** The suite is verified against a **freshly created empty scratch DB** (`createdb`,
  `CREATE EXTENSION vector`, `Base.metadata.create_all`) before pushing - CI's database has no data.
- **T-5** Vitest covers loading / empty / error / data states for every new component and both new hooks.
- **T-6** Playwright covers: sidebar → Certificates → detail → revision timeline; upload → certificate
  appears; renewal → revision 2 + product page serves the new PDF only; merge behind its dialog. Verified
  against a prod build.

---

## DEFERRED after Phase 3 review (written up so they do not read as shipped)

Found by the Phase 3 review: the MCP side was written against a backend contract the
backend never implemented, and its tests hand-fed the imaginary shape, so they passed.

- **MCP-4 / MCP-4a / MCP-9 are NOT shipped.** `presenters.py:_product_attachments` reads
  `row["certificate"]`, but `ProductAttachmentResponse` (`app/schemas/product.py`) was never
  given a nested `certificate` key. So the `("Valid Until", ...)` pair is always None and
  `flags.expired` is always false. The one-call "is WC8038's cert still valid" path does not
  exist. The presenter is written defensively (no-op when the key is absent), so nothing is
  broken - it is simply inert. To ship: add the nested key to `ProductAttachmentResponse` and
  its serializer, then rewrite `test_presenters_certificates.py` against real serializer output
  instead of a hand-built dict.
- **MCP-10 / MCP-11 are only partly shipped.** `_certificate_file` looks for
  `current_revision.attachment` / `row.attachment` / `revisions[is_current].attachment`, none of
  which `CertificateResponse` emits (list rows carry `current_revision: None`; only `get_detail`
  populates it, and revisions have no nested attachment object). The url fallback then reads
  `attachment_filename` / `mime_type`, which are not fields on `CertificateResponse` either, so
  render mode would hand n8n `{url, filename: null, mimeType: null}`. To ship: add
  `attachment_filename` + `mime_type` to `CertificateResponse` beside the signed urls in
  `_attach_signed_urls`, and re-point the presenter tests at the real output.
- **Cross-company probes (SEC-2 / SEC-2a) have no test.** All 30 child-table query sites were
  traced by review and none leak - every one enters through a scope-resolved `Certificate` - but
  that is unpinned. Needs: company-B certificate is 404 for a company-A principal; deleting a
  coverage row belonging to another certificate is 404; `_attach_signed_urls` never signs
  another company's revision.
- **Group BF has no test.** `parse_filename` is pure and trivially testable; at minimum pin BF-5
  (`PPS`/`SPAN` `04124FC` becomes two rows) and BF-4 (`04224FC` yields zero coverage plus the
  `no_product_coverage` reason). The dry run WAS exercised against live data and the apply path
  proven in a rolled-back transaction (9 certificates, coverage exactly 239), but by hand.
- **`e2e/certificates.spec.ts` is written but never executed.** Ports move between worktrees on
  this machine, so it has only been `--list`ed. The `[E2E]` tags on FE-1 / FE-3 / FE-5 / DUP-6 /
  COV-6 are therefore not yet evidenced by a run.
- **BF-2's "byte-identical" claim is FALSE, and here is the measured reason.** Checked against
  live data: **335 of 342** certification projection rows have `access_levels` differing from
  their attachment, so `reconcile_certificate` (which sets each row to the attachment's value per
  SEC-3) WILL rewrite them. The direction is benign though - every differing row has
  `access_levels = NULL`, i.e. legacy rows written before the column default existed, not a
  deliberate narrowing that would be widened. So the backfill fills in inheritance rather than
  relaxing an intentional restriction. **Amend BF-2 to say "coverage is adopted and the
  projection's access levels are backfilled from the attachment (335 NULL rows), not left
  untouched."** Re-check before running in live, where the numbers may differ:
  `SELECT count(*) FROM product_attachments pa JOIN attachments a ON a.id = pa.attachment_id
   JOIN attachment_types t ON t.id = a.attachment_type_id
   WHERE t.type_name = 'Certification' AND pa.access_levels <> a.access_levels;`
  If any differing row ever has a non-NULL narrower list, stop and decide before applying.

## Explicitly out of scope

- **Renewal process management.** No task/assignment/SLA around chasing an issuer. The system reports
  what expires and when; the chasing happens outside it.
- **Status engine adoption.** `certificates.status` is a VARCHAR + CHECK. The engine (migration
  `308_status_engine`) has no routes, no admin UI and no registered entities in this repo; with the review
  gate removed there is no per-client lifecycle variance left to justify being its first adopter. Swapping
  later is one migration plus a bounded read sweep.
- **`certificate_types` master table.** Cut - scheme is an extracted field, and `is_certificate` on
  `attachment_types` carries the cert-bearing signal.
- **Catch-up / stamped reminders.** Exact-date parity with promotions, accepted with REM-7 recorded.
- **Capability-based n8n routing.** `attachment_types.code` is NULL for `Certification` today; sending
  type capabilities in the webhook so n8n can branch on `creates_certificate` instead of a hardcoded name
  is a later, independent improvement.
- **Multi-certificate PDFs.** One attachment yields at most one certificate; a scanned bundle is split by
  staff first.
