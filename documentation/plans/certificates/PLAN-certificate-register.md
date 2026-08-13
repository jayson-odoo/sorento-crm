# PLAN - Certificate register (product certification lifecycle)

**Status:** Draft (pre-code) · **Classification:** CORE (Product Management) · **Owner:** jayson
**UAC:** `documentation/plans/certificates/certificate-register-acceptance-criteria.md`
**Grilled:** 2026-08-03, 13 decision branches resolved against live data and both n8n workflows.

---

## Problem

`Certification` is currently just an `attachment_types` row. A cert PDF uploads, n8n's Gemini node extracts
product codes, and the file becomes `product_attachments` rows. **Nothing captures that the document
expires.** Expiry dates live only in filenames (`PPS - IKRAM 04424FC - EXP 23 DEC 2026.pdf`), there is no
concept of the same certificate over time, and a renewal is an unrelated second file. Four certificates
expire 23 Dec 2026 and four more 07 Jan 2027, and the only thing that would surface that today is somebody
reading filenames.

The current pipeline is also already failing silently: of nine certification attachments, `PPS - IKRAM
04224FC` has **zero** product links while its three siblings have 68 / 16 / 8. Nothing recorded it.

---

## Shape

Two tables plus a link table, sitting **behind the existing write path**:

```
certificates            identity   scheme + certifying_body + number, company-owned
  └─ certificate_revisions         one per issue: attachment_id + valid_from/valid_until
  └─ certificate_products          coverage, source-tagged (ai | manual)
        └─ product_attachments     PROJECTION, written only by the cert service
```

Identity is `(company_id, normalized(scheme + certificate_number))`. Products link to the **identity**, so a
renewal appends a revision and touches zero coverage rows. Validity is **derived at read time** from the
current revision; nothing about expiry is ever stored as state.

### Why the identity/revision split (not a chain of certificate rows)

Renewal must be traceable - open one certificate, see every historical PDF. If each renewal were its own
certificate row chained by `supersedes_id`, then "which certificate does product WC8038 hold" has N answers
over time and every consumer has to pick the latest. With identity + revisions, coverage is written once and
survives every renewal, and the timeline is a child query.

### Why `product_attachments` stays (and becomes a projection)

It has real consumers that must not break: `crm_master_product_attachments_list`, `field_attachments` on
`crm_master_products_list`, `access_levels` dealer gating, `synced_to_excel`, and the **embedding pipeline**
(`embedding_change_listener`, `embedding_worker`, `embedding_backfill_service` all read `ProductAttachment`).
So it stays as the file-level read surface - but `certificate_products` becomes the only authoring surface,
with an idempotent JOIN-based reconciler. One writer, two read surfaces, no second UI for the same fact.

On renewal the projection **re-points**: the superseded attachment's rows are hard-deleted and the new
revision's are inserted. A dealer is never served an expired PPS certificate. The superseded attachment row
itself survives, owned by its revision, downloadable from the certificate page where the context ("Revision
1, expired 23 Dec 2026") is visible.

---

## n8n impact: smaller than it looks

**Upload flow** (wf `_NbFU3cCoEQwPSbvn14vV`, `system-upload-attachments`): `Switch` already has a
`Certification` output (index 2) funnelling into `switch-attachment-type` → `analyze-product-document` →
`analyze_document_output_parser1` → `technical-attachments-create` (POST `/api/v1/external/product-attachments`).

Changes: **one prompt edit.** `analyze-product-document` moves to structured output and also returns
`scheme` / `certifying_body` / `certificate_number` / `issued_at` / `valid_from` / `valid_until` (null for
non-certs); the parser passes them through; the HTTP node's URL and body expression are unchanged. No node
added, no branch rewired.

The server-side guard is what makes sharing the prompt across branches safe:
`attachment_types.is_certificate` must be true or the cert fields are dropped. A Technical Specifications
sheet quoting "cert PPS 0119" cannot mint a certificate.

**Consume flow** (wf `9qVyfUxmRQqrpGRMDLRuz`, `sorento-consume-main`): **zero changes.** Its `resolve-entity`
node POSTs `/api/v1/system/references/resolve` with `fallback_to_all_types: true` and reformulator-supplied
`allowed_entity_types`. Registering `certificate` in `_RESOLVER_ENTITY_TYPES` plus the probe functions makes
"PPS 0119" resolvable with no workflow edit. Number matching reuses the existing `_strip_all_ws` /
`_ws_insensitive_lower` helpers - the same mechanism that already makes `WC 8038` match `WC8038` - so no
normalized column is needed.

---

## Decision log (13 branches, grilled)

| # | Decision | Rationale |
|---|---|---|
| 1 | First-class `certificates` entity; noun "certificate", not "compliance document" | Sidecar columns on `attachments` cannot express renewal; EAV register cannot be indexed by number, validated per kind, or described to a UUID-first agent |
| 2 | Identity + revisions split; products link to identity | Renewal traceability with zero coverage churn |
| 3 | `certificate_products` = SoT; `product_attachments` = projection with reconciler | Keeps every existing consumer working with one authoring path |
| 4 | On renewal the projection re-points; superseded rows **hard-deleted** | Never serve an expired certificate; a projection with its own soft-delete state becomes a second SoT |
| 5 | Validity **derived**; lifecycle stored as VARCHAR + CHECK over `active`/`archived` only | A stored `expired` is a lie the day the cron doesn't run. Status engine reconsidered and dropped once the review gate went, then `revoked` was cut too - see below |
| 6 | **No** draft/confirm gate; auto-active + deterministic `needs_review` | User decision. Mitigated by plausibility checks (`max_validity_months`, date sanity, unmatched products) so a hallucinated date is loud |
| 7 | Reminders = promotion parity, exact-date match | Reuses `days_before_promotion_end` shape exactly; miss-a-day risk accepted and recorded (REM-7), mitigated by the validity-scoped default list filter |
| 8 | **No** `certificate_types` table; scheme is an extracted field | Live data has two schemes (`PPS`, `SPAN`) under one attachment type; a scheme table would duplicate the taxonomy |
| 9 | `attachment_types.is_certificate` bool (+ `max_validity_months`) | Forced by #8 - with no cert-type FK, something must mark the type. Sits beside `supports_field_linkage` / `is_direct_access`; guard is server-side |
| 10 | `access_levels` inherited from the current revision's attachment; no cert column | User decision. Drift made visible in the revision timeline rather than prevented |
| 11 | Identity key includes **scheme** | `04124FC` exists under both `PPS` and `SPAN` with different expiries - number alone would merge them and silence the earlier expiry |
| 12 | Exact match → revision; trigram near-match → new cert + `possible_duplicate_of` + review; **never** auto-merge; "Merge as revision of…" ships in v1 | OCR will mangle `WCM PC 000321`; a wrong auto-merge overwrites a real identity, and detection without a fix means hand-editing rows |
| 13 | Lives in **Product Management** → `/master-data-management/certificates`, `moduleKey: 'product'`, `master_data.certificates.*` | User decision (over a dedicated `compliance` module) |

### On not adopting the status engine

Recommended twice, then withdrawn. The engine is ported (migration `308_status_engine`, `app/models/status.py`,
`app/status_engine/registry.py`, `app/services/status_service.py`) but has **no API routes, no FE admin and no
registered entities** in this repo. Its value here was per-client lifecycle configurability - and decision #6
removed the only rung clients would differ on (a review/approval gate). Cutting `revoked` in review leaves
`active`/`archived`: a two-value VARCHAR + CHECK rendered through `lib/status-pill.ts`. A configurable state
machine for two states would be pure ceremony. Recorded so this is a considered choice, not an oversight.

---

## Phase 0 - Journey

Written as the `Journey` section at the top of the UAC. Four actors: staff filing (two actions, zero
questions asked), staff renewing (same two actions, system recognises the number), compliance owner (never
browses - receives 90/30/7 emails), dealer on WhatsApp (resolver → tool → real validity, found-but-expired
never presented as live). Every AC traces to a step there.

---

## Phase 1 - Frontend prototype (mock data, no backend)

Build against fixtures, no endpoints. Deliverable: clickable screens + the contract this doc pins.

1. **Certificates list** - `DataGrid` (fixed layout, resizable, explicit `size`, `truncate` + `title`).
   Validity-scoped default filter. Filters: `validity_state`, `expiring_within_days`, `scheme`, `status`,
   `needs_review`, number search. Searchable selects only.
2. **Certificate detail** - header (scheme · number · validity pill · status pill), revision timeline,
   covered products (with `ai`/`manual` source), unmatched strings, suspected duplicate, reminder history.
   Every section renders always, with an explicit empty state + CTA. Responsive header pattern; verified at
   ~375px.
3. **Create/edit modal**, **delete** and **merge** `AlertDialog`s.
4. **Attachment-type dialog** gains `is_certificate` + `max_validity_months`.
5. Fixtures cover: valid, expiring_soon, expired, not_yet_valid, unknown (NULL date), needs_review,
   suspected duplicate, three-revision chain, zero-coverage certificate, trashed-attachment revision.
6. Verify via Playwright MCP by **clicking through the sidebar** from `/` - never a deep URL. Screenshot the
   golden path and each edge state. Check `browser_console_messages`. `browser_close` when done.

No backend code, no tests yet - the shape may still move after you look at it.

---

## Phase 2 - Backend + wiring + tests (test-first)

Slices, each independently shippable, red→green→refactor:

**S1 - Schema.** Migration: `certificates`, `certificate_revisions`, `certificate_products`, plus
`attachment_types.is_certificate` / `max_validity_months`. Identity unique index on the normalized
expression, partial unique on one `is_current` per certificate. Idempotent, clean downgrade. Chain onto a
**committed** head and verify `alembic heads` is single afterwards.

**S2 - Service core.** Identity upsert, revision append, coverage write, projection write/re-point,
reconciler, derived-validity serializer, `needs_review` rules. All of Groups SCH / VAL / RVW / REV / COV.

**S3 - Ingest.** Extend `/api/v1/external/product-attachments` with the optional cert fields; the
`is_certificate` server-side guard; regression tests proving a no-cert-fields payload behaves identically to
today (951 Technical Specifications + all Product Photos rows depend on it).

**S4 - Duplicate + merge.** Trigram near-match probe, `possible_duplicate_of_certificate_id`, the
merge-into endpoint with its cross-company refusal.

**S5 - CRUD API + list-query.** `GET /api/v1/master-data/certificates` with all filters, detail, create,
update, delete; register in `list_query_registry` so column personalization works; permissions CSV
(`master_data.certificates.{view,create,update,delete}`).

**S6 - Reminders.** `days_before_certificate_expiry` trigger + `certificate` fact source +
`expiry_notify_batch_id` + email template context with the **internal** deep link.

**S7 - Resolver + embeddings.** `_probe_certificate`, `_prefix_probe_certificate`, `_TIER2_PROBES`,
`_EMBEDDING_SOURCE_TYPES`, `embedding_queue` producer. Two-schemes-one-number returns both candidates.

**S8 - MCP.** `crm_certificates_list` ToolSpec (FOUND-BUT-EXPIRED wording, naive-MYT `updated_at`),
`resolve_signed_urls` returning `preview_url` / `download_url` for the **current revision only** so the
consume flow's `send-message-files` node can actually deliver the PDF, nested `certificate{}` on
`crm_master_product_attachments_list`, `agent_mcp_tools` startup auto-link. **Restart the MCP process** or
the tool won't appear in the assistant dropdown.

**S8 also owns the `view=render` presenters, which are easy to miss.** `presenters.py` whitelists fields per
tool, so nesting `certificate{}` on the raw response alone is invisible to the n8n consumer, which calls in
render mode. `_product_attachments` gains a `Valid Until` pair and passes `expired=is_expired` into the
envelope's existing `flags.expired` (same mechanism as `_promotions`, no envelope change);
`crm_certificates_list` joins `PRESENTER_TOOLS` / `_RESULT_TYPE` / `_DEFAULT_INTRO` with a `_certificates`
presenter that attaches the current revision's file. See MCP-9 / MCP-10 / MCP-11.

**S9 - FE off mocks.** Real hooks/services via `lib/api-client`; `extractApiError` and
`buildDataGridParams` (never hand-rolled). Delete fixtures not reused by tests.

**S10 - Backfill.** Filename parser for the 9, coverage adopted from the 239 existing links, all stamped
`needs_review` + `backfilled_from_filename`. Idempotent. `04124FC` must land as two certificates.
**Dry-run by default** (BF-7): prints the parse table, writes nothing, assigns no ids. Real run only behind
an explicit flag with explicit approval.

**S11 - n8n.** Prompt edit on `analyze-product-document` (structured output + cert fields); parser
pass-through. Test on a real fixture PDF end to end.

Tests land **here**, not deferred: pytest (endpoint happy/denial/validation + service logic), vitest
(every component and hook, all four states), playwright (sidebar → list → detail → renewal → merge).
Postgres only; every test seeds its own chain with marker prefixes; verified against a **fresh empty
scratch DB** before pushing.

---

## Phase 3 - Review

`/code-review` on the combined diff, then `/simplify` where it earns it, then PR. Checklist: CRUD pattern,
`AlertDialog` on delete **and** unlink, every detail section renders when empty, no duplicated
`extractApiError` / `buildDataGridParams` / user-select helpers, no UUIDs in the UI, no in-UI feature
explanations, no em-dashes anywhere.

---

## Risks

| Risk | Mitigation |
|---|---|
| Gemini hallucinates `valid_until`; no gate catches it (decision #6) | Deterministic plausibility: `max_validity_months`, `valid_until > valid_from`, not-already-past; `needs_review` + badge + default filter; `extracted_json` kept for attribution |
| Scheduler outage on the exact match day loses that window's email | Validity-scoped default list filter means the countdown is always visible (FE-3); recorded as REM-7 |
| OCR mangles a number → duplicate certificate, old one keeps nagging | Trigram near-match flag + "may be a renewal of" + merge action (decision #12) |
| Projection drifts from coverage | Single writer + idempotent JOIN-based reconciler (COV-4) |
| Renewal silently widens dealer visibility (decision #10) | Per-revision `access_levels` shown side by side in the timeline (FE-6) |
| Menu entry added to only one of the two `menu.config.tsx` trees | FE-1 requires both (~477 and ~1335); Playwright reaches it via the sidebar, which catches a miss |
| Raw-mode field added but the `view=render` presenter is not, so the n8n consumer sees nothing while raw mode looks complete | MCP-9 / MCP-10 / MCP-11 make the presenter work explicit, and render-mode assertions are part of S8's tests rather than an afterthought |
| Adding a new cert-bearing attachment type still needs an n8n Switch rule | Out of scope, noted: send type capabilities in the webhook payload later so n8n branches on `is_certificate` instead of a hardcoded name (`attachment_types.code` is NULL for `Certification` today) |

---

## Deploy notes

- Migration chains onto a committed head; verify a single `alembic head` after merge (dual-head forks break deploy).
- Restart the **MCP process** after S8, or `crm_certificates_list` is invisible to the assistant dropdown.
- Worker restart is not required (no `app/tasks/*` change); the automation trigger runs in the scheduler.
- Backfill script (S10) is run once in live after deploy, and is safe to re-run.
- No push to prod/CI without an explicit per-deploy go.
