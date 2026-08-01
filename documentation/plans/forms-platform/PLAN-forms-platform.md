# PLAN - Forms Platform (one engine for every form)

**Status:** Pre-code, **partially grilled**. The engine decision and the port boundary are settled (below). Migration mechanics, revision-chain adoption and per-form cutover are **not** grilled - see "Ungrilled" at the end. No UAC yet; write it before code, per `PRINCIPLES.md`.
**Decided:** 2026-08-01. Two tracks, one dependency - this plan is the platform; `after-sales/PLAN-after-sales-warranty.md` depends on **F0 to F2** and not on F4.
**Related decisions:** `adr/0001` (status engine is core) - `adr/0011` (the after-sales case is a form submission, superseding `adr/0008` narrowly).

## Why

Sorento has five form-shaped things built five ways: `complaints`, `stock_inquiries`, `purchase_requests`, `sponsorship_forms` and marketing forms, each with its own table, routes, portal surface and FE screens. Every new form type has so far meant a new vertical. The goal is **one engine, many definitions** - a new form becomes configuration.

`workflow_forms` already exists in Sorento and is the intended home. It has **never run**: `workflow_form_definitions` 0 rows, `workflow_submissions` 0 rows. It is a skeleton, and its schema-embedded state machine actively conflicts with ADR-0001.

`foundryx-shared-service` has a much better document layer, already solving the parts Sorento's skeleton does badly.

## The port boundary (settled)

```
PORT    form_engine     1,669 LOC - document model, validation, computed expressions
        status_engine   already mandated by adr/0001 as CORE (= after-sales S0)

REUSE   Sorento's form-SLA engine   tiers, escalation, handling lock, per-event/per-channel notify,
                                    team round-robin. NO counterpart exists in the shared service.
        Sorento's notifications, portal (PortalToken + OTP), attachments, rule engine

DON'T   workflow_engine 1,904 LOC - executor/registry/scheduler/worker, a node-graph automation
                        engine. Sorento uses n8n for automation and n8n owns the message pump.
                        Porting it would create a second automation system.
        review_engine · template_engine · import_engine · terminology - not this problem.
```

**Two collisions the port resolves rather than creates:**

- Sorento's `workflow_forms` embeds states in `schema` JSONB; the shared service puts `status_id` on the submission and lets the status engine own the graph. Porting the document layer **and** landing the status engine makes them agree instead of compete.
- The shared service's conditions tree expects a rule engine. Sorento already has one (from the promo-expiry work, node shape `{combinator, rules[]}`), so that arm has a socket to land in. **Watch the known trap:** an empty `rules[]` matches everything silently.

## What `form_engine` brings that Sorento's skeleton lacks

| capability | why it matters here |
|---|---|
| Field taxonomy: composites, uploads, display-only, rating, repeater sub-fields, table columns | the exchange/return request needs line items with uploads per line |
| **Computed expressions with aggregates** - real tokeniser, parser, AST, `SUM` over table rows | quantities and values totalled without bespoke code |
| Conditions tree per field (visibility / requirement) | "if out of warranty, require a charge acknowledgement" becomes configuration |
| Pages | multi-step consumer forms instead of one long scroll |
| `submission_group_id` + `revision_number` + `is_current` | resubmission is first-class rather than an edit-in-place |

## Slices

| slice | delivers | depends on |
|---|---|---|
| **F0** | `form_engine` document model ported; definitions/versions carry the new schema shape | **S0** (status engine) |
| **F1** | submissions carry `status_id`; schema-embedded states retired | F0 |
| **F1a** | **submission lines carry `status_id` + disposition**; header status derived | F1 |
| **F2** | SLA + notifications + portal + attachments wired to submissions | F1 |
| **F3** | FE builder and renderer at parity with the ported document model | F0 |
| **F4** | the four existing forms migrated, dual-run, cut over one at a time | F2, F3 |

**After-sales depends on F0, F1, F1a and F2 only.** It does not wait for F3 (its two flows can ship on a narrower builder) and explicitly does not wait for F4.

### F0 - port the document model

Port `app/form_engine/{schemas,validation,computed}.py` into `sorento_crm_backend/app/form_engine/`. Mandatory deviations, same as every other port here: all ids `UUID(as_uuid=False)` never `Column(String)`; no `tenant_id` behaviour beyond the existing stub.

`workflow_form_versions.schema` changes shape. Zero rows exist, so there is no data migration - the only cost is the FE builder (F3) and any code reading the old shape.

### F1 - status on the submission, not in the schema

`workflow_submissions.status_id` -> `statuses`, with `workflow_submission` registered as a status-engine entity type carrying a default graph. Delete state definitions from the schema document. Reporting groups by status `key`, never by id and never by `category`.

### F1a - status on submission **lines**, not only on the submission

Required by the after-sales exchange/return flow (`REQUIREMENTS-inbox-2026-08-01.md` R1/R3): Customer
Service approves **some lines and rejects others**, each line carries its own **disposition**, and the
submission's status is **derived** from its lines.

`workflow_submission_lines` today carries `line_group_id`, `sort_order` and `row_data` JSONB - no state. It
needs `status_id` -> `statuses` plus a disposition FK, and the header recompute needs to be a service
concern rather than a stored truth.

Precedent for the derived header: `complaint_fulfilment_service` already recomputes a header from its
children **including the reopen case** (a `processed_by_cs` complaint becomes `fulfilled` when every
non-cancelled linked DO is delivered, and reopens if a non-delivered DO links). Follow that shape.

### F2 - the integration layer (this is what after-sales actually needs)

- **`workflow_submission` added to `FORM_SLA_TYPES`.** Unlocks stage clocks, escalation, handling lock and the pending-task dashboard for every form definition. Today the tuple is `(stock_inquiry, purchase_request, sponsorship_form, complaint, ticket)` and submissions are absent, which is why none of the SLA machinery reaches them.
- **Portal submission.** `respondent_contact_id` -> `respond_contacts`, plus `source_entity_type` / `source_entity_id` (already specified for the survey in after-sales S8). A definition declares whether it is portal-submittable and by which party kind.
- **Attachments.** Submission-level and line-level linkage, reusing `attachments` and the existing storage router.
- **Notifications.** Submissions emit through the one notification spine (after-sales S4), so a form transition can notify a contact, not only a user.

### F3 - FE parity

`WorkflowFormBuilder.tsx` and the submission renderer already exist against the thin schema. They must grow: repeaters, table columns, computed (read-only, live-recalculating), conditions, pages, uploads, display-only blocks. Every dropdown uses `SearchableSelect`; every surface usable at 375px and 1280px.

### F4 - migrate the four, dual-run

Per form: define it in the new engine, dual-write, reconcile, then cut reads over, then retire the bespoke table. **One form at a time**, never together. Order by risk, easiest first: `sponsorship_form` -> `purchase_request` -> `stock_inquiry` -> `complaints`.

`complaints` is last and hardest: it carries the Respond conversation panel, fulfilment-order linkage, root causes, resolutions and 50 live rows whose `customer_type` values are incoherent. It also keeps **project** complaints after the migration (`adr/0011`), so its bespoke surface may survive longer than the other three.

## Risks

| risk | mitigation |
|---|---|
| **After-sales blocked behind a platform programme** | after-sales depends on F0-F2 only, never F4. If F2 slips, after-sales slips; if F4 slips, it does not |
| **Dual-run divergence** during F4 - two stores, one truth | dual-write with a reconciliation report per form, and a hard cutover date per form rather than an indefinite both-ways state |
| **`form_engine` was written for another schema and another tenant model** | port, do not vendor. Rewrite ids to `UUID(as_uuid=False)`; do not import the shared service's tenant semantics |
| **Empty `rules[]` matches everything** (known rule-engine trap) | explicit guard plus a test asserting an empty condition group matches nothing in this context |
| **Two status systems during F1** | F1 deletes schema states in the same slice that adds `status_id`. No release ships with both |
| **FE builder lags the backend model**, so a definition can be authored only by hand-editing JSON | acceptable for after-sales' two flows (F3 not required); not acceptable before F4 |

## Ungrilled - do not implement these parts

- **Migration and dual-run mechanics** (F4): dual-write versus backfill-and-switch, reconciliation shape, how long both run, who signs each cutover.
- **Revision chain**: whether Sorento adopts `submission_group_id` / `revision_number` / `is_current`, or keeps edit-in-place. It changes what "resubmit" means on the portal and how SLA clocks attach across revisions.
- **Definition-level permissions**: the shared service has its own `permissions` engine; Sorento has `user_role_permissions` plus `permission_module_map`. Which governs a form definition?
- **Numbering**: the shared service has a `numbering` engine; Sorento has `document_numbering_rules`. Two numbering systems must not both own form numbers.

Grill these before F4. F0 to F2 can proceed on what is settled.
