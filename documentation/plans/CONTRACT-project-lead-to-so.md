# API contract: lead to sales order (phase 2)

> **Table names in this document predate the schema move.** On 2026-08-15 the projects
> module's 47 tables moved into a dedicated `projects` Postgres schema and the 34 that
> carried a `project_` prefix dropped it: `project_leads` is now `projects.leads`,
> `project_quotation_lines` is `projects.quotation_lines`, and so on. The 13 unprefixed
> ones only changed schema. Nothing else in this document changes. See
> [ADR-0011](../adr/0011-project-sales-tables-live-in-the-projects-schema.md) and
> `documentation/plans/PLAN-projects-schema-move.md` for the full mapping.

Status: **binding for the 2026-08-02 build**. Owner: integration.

This exists because several workstreams are building against each other at the same time.
Anything here is fixed; if a slice needs a deviation, change THIS file in the same commit
that deviates, so nobody discovers it from a 422.

Everything mounts under `/api/v1/project-sales`. Auth, RBAC and the `projects` module guard
are as phase 1 (see `app/api/v1/projects/__init__.py`). Routers with literal path segments
mount BEFORE `/projects/{project_id}` or they get captured by it.

Frontend rule, CORRECTED 2026-08-02: the FE calls `apiFetch('/api/v1/project-sales/...')`,
with the version segment written out. An earlier draft of this file said
`apiFetch('/api/project-sales/...')` on the strength of the rewrite table in `lib/api.ts`,
but that table has no `project-sales` entry, so the short form 404s. Every existing
project-sales service uses `const BASE = '/api/v1/project-sales'`; match it. Do not add a
Next route handler for any of this.

Note also that some phase-1 collection routes are declared with a trailing slash
(`${BASE}/projects/`), and calling them without it returns a 307.

## Conventions used below

- Money and quantities are JSON **strings**, never floats. `"392.85"`. They are `Numeric`
  in Postgres and a float round trip loses cents on a 1.8 million ringgit PO.
- Dates are `yyyy-mm-dd`. Timestamps are naive UTC ISO, as everywhere else in this backend.
- List endpoints use the existing DataGrid contract (`buildDataGridParams`, `page`, `limit`,
  `sort`, `dir`, `query`) and return the repo's standard `ListResponse`:
  `{data, pagination: {total, page, limit}, empty}`. CORRECTED 2026-08-02: an earlier
  draft of this file said `{data, total, page, limit}`, which no endpoint in this
  codebase returns. The frontend already reads `pagination.total` from the sibling
  lead and project lists, so matching it was the only honest option.
- No UUID is ever rendered in the UI. Every response that carries an id also carries the
  human label the screen shows (`*_label`, `*_name`, `*_code`).
- Errors: raise `AppException`. The FE reads them with `extractApiError`.

---

## 1. Leads: informant and the acceptance handshake (P1)

Extends the existing lead routes. `customer_id` (the BUYER) is now nullable everywhere.

### Fields added to `ProjectLeadResponse`

```
informant_source          "bci" | "panel" | "referral" | "walk_in" | "consultant"
                          | "architect" | "contractor" | "other" | null
                          -- the union of this file's original list and the UAC's, which
                          -- disagreed. Refusing either set would 422 a screen that was
                          -- following its own spec.
informant_ref             string | null      -- their reference, e.g. a BCI job id
informant_party_id        uuid | null
informant_party_label     string | null      -- resolved name, for the UI
informant_contact_name    string | null      -- a lone informant with no firm is normal
acceptance_state          "assigned" | "accepted" | "declined" | null
assigned_at               timestamp | null
accepted_at               timestamp | null
declined_reason           string | null
declined_at               timestamp | null
can_assign                bool               -- ADDED 2026-08-02. Diverges from can_edit
                          -- exactly where it matters: a decline clears the owner and
                          -- can_edit is owner-or-manager, so whoever raised the lead
                          -- could otherwise not re-assign the lead that just came back
                          -- to them. Sent rather than inferred client-side.
```

`POST` and `PUT` accept `informant_source`, `informant_ref`, `informant_party_id`,
`informant_contact_name`.

### `POST /leads/{lead_id}/assign`

```json
{ "owner_user_id": "…", "note": "optional" }
```

`note` reaches the assignee in their notification and is NOT stored on the lead: there is
no column for it, and appending it to `notes` would corrupt the sighting's own notes.

Sets `owner_user_id`, `acceptance_state="assigned"`, `assigned_at=now`, clears any earlier
decline. Notifies the assignee (in-app always; email and WhatsApp per the user's own
per-event preferences, same matrix as SLA notify). Returns the lead.

Re-assigning an already-assigned lead is allowed and resets the clock.

### `POST /leads/{lead_id}/accept`

No body. Only the assigned owner (or an admin) may call it. Sets
`acceptance_state="accepted"`, `accepted_at=now`. 409 if there is no assignment.

### `POST /leads/{lead_id}/decline`

```json
{ "reason": "required, free text" }
```

Sets `acceptance_state="declined"`, `declined_at=now`, `declined_reason`, and clears
`owner_user_id` so the lead returns to the unassigned pool. Notifies whoever assigned it.

### `GET /leads/awaiting-acceptance`

The marketing worklist. DataGrid contract. Rows are leads with
`acceptance_state="assigned"`, newest assignment first, each carrying
`hours_since_assigned` so the screen can show the wait without doing date maths.

Query params: `owner_user_id`, `min_hours` (default 0).

---

## 2. Customer PO intake (P4)

The PO row is phase 1's `project_purchase_orders`. There is no `customer_pos` table.
Phase 2 adds versioned documents to that row.

### `POST /projects/{project_id}/purchase-orders/upload`

`multipart/form-data`: `file` (pdf, jpeg or png), optional `po_number`,
optional `purchase_order_id` to add a version to an existing PO.

Synchronous up to the point where the document is stored and a version row exists, then
extraction runs on the RQ `project_docs` queue. Response, `202`:

```json
{
  "purchase_order_id": "…",
  "po_version_id": "…",
  "version_no": 2,
  "extraction_state": "queued",
  "page_count": 10
}
```

If `purchase_order_id` is absent and `po_number` is absent, the PO row is created with
`po_number` empty and `status="draft"`; extraction fills the number and the confirm screen
is where a human agrees to it. If the extracted number matches an existing PO on the same
project, the upload becomes a NEW VERSION of that PO rather than a second PO.

### `GET /purchase-order-versions/{po_version_id}`

```json
{
  "id": "…",
  "purchase_order_id": "…",
  "version_no": 1,
  "extraction_state": "queued" | "running" | "done" | "failed",
  "extraction_error": null,
  "extraction_model": "gemini-2.5-flash",
  "page_count": 10, "pages_extracted": 10, "failed_pages": [],
  "extraction_elapsed_ms": 163420,
  "purchase_order": {
    "approved_by_name": null, "approved_at": null,
    "countersigned_by_name": null, "countersigned_at": null
  },
  "document_url": "…",            // presigned, for the side-by-side viewer
  "header": {
    "po_number": "HQ/26/01/041",
    "po_date": "2026-01-19",
    "term_days": 60,
    "sales_person": "…",
    "customer_order_ref": "…",
    "admin_ref": "PS26-0143",
    "remark": "…"
  },
  "totals": {
    "extracted_total": "1810640.62",
    "lines_total": "1810640.62",
    "arithmetic_passed": 52,
    "arithmetic_total": 52
  },
  "lines": [
    {
      "id": "…", "line_no": 1, "page_no": 1,
      "stock_code_raw": "SRTWC8613-RL", "description_raw": "…",
      "qty": "927", "uom_raw": "SETS",
      "unit_price": "392.85", "amount": "364171.95",
      "arithmetic_ok": true,
      "is_cancelled": false,
      "resolved_product_id": "…", "resolved_product_code": "SRTWC8613-RL",
      "resolution_source": "code" | "description" | "map" | "manual" | null
    }
  ],
  "annotations": [ /* see section 3 */ ],
  "confirmed_at": null
}
```

`arithmetic_ok` is `qty * unit_price == amount` to two decimals, computed by us, never by
the model. `lines_total` is our sum. When `lines_total != extracted_total` the confirm
screen must say so at the top: that difference is the single best signal that a page was
misread.

With one exception, which matters on the client's own PO: when the gap is EXACTLY the value
of the accepted cancellations, it is a fact and not an alarm. Compared exactly, never with a
tolerance. Otherwise accepting the real strike-through on line 7 would leave a correct PO
crying wolf, and `total_mismatch` would block its publish forever.

`interpretation_json` keys are fixed, because a mismatch here is invisible until a human
clicks: `line_nos`, `code`, `description`, `po_number`, `text`. An edit spreads the original
JSON first, so keys the form has no field for survive.

`PUT .../lines/{line_id}` and `POST .../confirm` both return the recomputed version.

### `PUT /purchase-order-versions/{po_version_id}`

ADDED 2026-08-02. Section 2 originally gave a PUT for lines only, but AC-D3 says every
extracted field is editable before approval and the header carries the PO number, date,
term and filing reference. Accepts the `header` block above. Returns the recomputed
version.

### `PUT /purchase-order-versions/{po_version_id}/lines/{line_id}`

Any of `stock_code_raw`, `description_raw`, `qty`, `uom_raw`, `unit_price`, `amount`,
`resolved_product_id`, `is_cancelled`. Recomputes `arithmetic_ok` and the version totals.
Editing a line sets `resolution_source="manual"` when a product is chosen by hand.

### `POST /purchase-order-versions/{po_version_id}/confirm`

No body. Writes the confirmed state onto the phase-1 PO row and its lines
(`project_purchase_order_lines`), which is where the existing quotation cross-check and its
mismatch flags already live. Sets `confirmed_by/at` on the version. The version's extracted
JSON and lines stay untouched forever: they are the record of what the document said.

409 if any annotation is still `proposed`. A human must have looked at the pencil first.

### `POST /purchase-orders/{po_id}/approve` and `/countersign`

No body. Stamps `approved_by/at` and `countersigned_by/at`, `status="approved"` on approve.
Countersign requires an approved PO and a different user.

---

## 3. Handwriting review cards (P5)

Annotations are proposals. Nothing on the scan changes a line until a person accepts a card.

```json
{
  "id": "…", "page_no": 3,
  "crop_url": "…",                  // presigned crop of just that region
  "raw_text": "cancel - refer to New P/O HQ/26/05/087",
  "written_date": "26/1/26",
  "refers_to_lines": [7],
  "interpretation": "cancel_line" | "amend_code" | "amend_description" | "successor_po" | "signature" | "other",
  "interpretation_json": { "…": "shape depends on interpretation" },
  "state": "proposed" | "accepted" | "edited" | "rejected",
  "actioned_by_name": null, "actioned_at": null, "action_note": null
}
```

### `POST /po-annotations/{annotation_id}/accept`

Optional `{"note": "…"}`. Applies the interpretation:

- `cancel_line` sets `is_cancelled=true` on the named lines
- `amend_code` / `amend_description` overwrite those fields on the named lines
- `successor_po` sets `supersedes_po_number` on the successor and
  `superseded_by_po_id` once that PO exists; until then the text pointer stands alone
- `signature` / `other` record only

### `POST /po-annotations/{annotation_id}/edit`

`{"interpretation": "…", "interpretation_json": {…}, "note": "…"}`. Human's reading wins,
then applies exactly as accept does. State becomes `edited`.

### `POST /po-annotations/{annotation_id}/reject`

`{"note": "required"}`. Nothing is applied.

Dedup: `dedup_key` is `(written_date, sorted refers_to_lines, sha1 of normalised raw_text)`.
Re-uploading a re-scanned PO must not propose the same pencil note twice, and the state of
an already-actioned annotation carries forward to the new version.

---

## 4. Delivery schedule intake (P6)

### `POST /purchase-orders/{po_id}/delivery-schedules/upload`

`multipart/form-data`: `file`, optional `issuer_party_id`, optional `revision_label`,
optional `delivery_schedule_id` to add a version to an existing schedule,
optional `po_version_id` (defaults to the PO's latest confirmed version).

`po_version_id` is what the checksum reconciles AGAINST. A schedule issued before a
handwritten cancellation reconciles to the PO as it stood, and rejecting it would reject a
document the customer considers correct.

Response `202`, same shape as the PO upload (`delivery_schedule_id`, `schedule_version_id`,
`version_no`, `extraction_state`).

### `GET /projects/{project_id}/delivery-schedules` and `GET /delivery-schedules/{id}/versions`

ADDED 2026-08-02. Without these there is no way to reach a `version_id` starting from a
project, which the first draft of this file simply missed. Both on the standard
`ListResponse`, modelled on the quotation pair phase 1 already ships. Schedule rows carry
the PO number, the issuer label, the latest version number and its reconciliation counts,
so a list renders without a UUID on it.

### `GET /delivery-schedule-versions/{version_id}`

```json
{
  "id": "…", "delivery_schedule_id": "…", "version_no": 2,
  "revision_label": "REVISED 1 - 23/7/2026",
  "issuer_party_label": "SLG Construction Sdn Bhd",
  "po_version_id": "…", "po_version_no": 1,
  "extraction_state": "queued" | "running" | "done" | "partial" | "failed",
  "extraction_error": null,
  "page_count": 3,
  "pages_extracted": 3,
  "extraction_elapsed_ms": 41200,
  "purchase_order_id": "…", "po_number": "HQ/26/01/121",
  "uploaded_by_name": "…", "confirmed_by_name": null, "created_at": "…",
  "document_url": "…",
  "schedule_date": "2026-07-23",
  "phases": [
    { "id": "…", "area_group": "TOWER", "sequence": 1,
      "label": "Level 2 & 7", "delivery_date": "2026-07-01" }
  ],
  "products": [
    { "product_index": 1,
      "product_id": "…", "product_code": "SRTWC8613-RL", "product_name": "…",
      "customer_code_raw": "BUI-HB-SRTWC8613-RL",
      "resolution_source": "map" | "code" | "manual" | null,
      "column_total": "927",
      "reported_total": "927",        // the schedule's own TOTAL QTY row, transcribed
      "po_qty": "927",
      "reconciled": true }
  ],
  "cells": [ { "phase_id": "…", "product_index": 1, "product_id": "…", "qty": "135" } ],
  "reconciliation": { "reconciled_columns": 35, "total_columns": 38 },
  "confirmed_at": null
}
```

Reconciliation is **per column, never per document**. A wholesale reject would reject nearly
every real schedule (measured: 29/37 columns on R1, 35/38 on R2 reconciled on the first
pass). The confirm screen shows the failing columns and lets a person fix those cells.

`reconciled` is true when `column_total == po_qty` and, where the document has one,
`column_total == reported_total`.

### `PUT /delivery-schedule-versions/{version_id}/cells`

```json
{ "cells": [ {"phase_id": "…", "product_index": 1, "product_id": "…", "qty": "140"} ] }
```

Upsert by `(phase_id, product_index)`, with `product_id` accepted as an alternative once
the column is resolved. Keying on `product_id` ALONE cannot address a column whose product
is still unidentified, and such a column renders blank while showing a non-zero total,
which looks like a bug rather than an unresolved column. A `qty` of `"0"` deletes the cell.

Recomputes column totals and reconciliation, and RETURNS the recomputed version in the
same shape as the GET. So do `PUT .../products/{product_index}` and `POST .../confirm`: the
frontend writes the response straight into its cache rather than refetching, so returning
anything else blanks the grid mid-edit.

### `PUT /delivery-schedule-versions/{version_id}/products/{product_index}`

`{"product_id": "…"}` to resolve a column a human had to identify. Also writes
`customer_item_code_map` for that customer so the next schedule resolves it automatically.

### `POST /delivery-schedule-versions/{version_id}/confirm`

Promotes phases to `project_delivery_phases` on the project, keyed on
`(area_group, sequence)` and NOT the label: the COMMON AREA rows carry no label at all, and
matching by label collapsed three phases into one. 409 while any column is unreconciled
unless `{"acknowledge_unreconciled": true, "reason": "…"}` is sent.

---

## 5. SO draft (P7)

### `POST /purchase-orders/{po_id}/build-sales-orders`

`{"schedule_version_id": "…"}`. Idempotent per `(po_version, schedule_version)`: calling it
again replaces the drafts it previously produced and leaves published ones alone.

Produces one or more `project_sales_orders` in `draft` or `blocked`, then returns the list
shape of section 5.2. The area split is a PROPOSAL: one real PO produced three SOs, one of
them an early product subset with no area logic at all, so the response says where each
grouping came from (`grouping_origin`) and the screen lets a person regroup.

### `GET /purchase-orders/{po_id}/versions` and `GET /purchase-orders/{po_id}/delivery-schedule-versions`

ADDED 2026-08-02. Nothing enumerated versions, yet both "build drafts from a schedule
version" and "compare against a version" require the user to pick one. A strict subset of
the single-version body is enough: id, version number, label, confirmed-at, plus the
reconciliation counts for schedules.

### `GET /projects/{project_id}/sales-orders`

DataGrid contract. Row:

```json
{
  "id": "…", "provisional_ref": "PSO-000123",
  "autocount_doc_no": null,
  "area_group": "TOWER",
  "status": "draft" | "blocked" | "ready" | "published" | "amended",
  "grouping_origin": "area" | "learned" | "manual" | "subset",
  "line_count": 99, "total_amount": "1611107.81",
  "hard_findings": 0, "warn_findings": 3,
  "is_pre_order": false, "is_sponsorship": false,
  "customer_name": "…",
  "purchase_order_id": "…", "po_number": "HQ/26/01/121",
  "import_file_url": null,
  "created_at": "…"
}
```

### `GET /sales-orders/{pso_id}`

Adds `lines[]` and `findings[]`:

```json
{
  "lines": [
    { "id": "…", "line_no": 1,
      "product_id": "…", "product_code": "SRTWC8613-RL", "description": "…",
      "qty": "135", "uom": "SET", "unit_price": "392.85", "amount": "53034.75",
      "delivery_date": "2026-07-01",
      "phase_id": "…", "phase_label": "Level 2 & 7",
      "explosion_source": "package" | "quotation" | "none",
      "source_po_line_no": 1,
      "parent_line_id": null, "is_companion": false,
      "stock_location": "…" }
  ],
  "findings": [
    { "id": "…", "severity": "hard" | "warn" | "info",
      "code": "…", "detail": "human sentence",
      "line_id": "…", "line_no": 1,
      "acknowledged_by_name": null, "acknowledged_reason": null }
  ]
}
```

Set explosion is why 52 PO lines become 99 SO lines: the PO speaks in SETS, the SO in
components (a priced parent plus zero-priced companions). `item_packages` is authoritative;
the quotation grouping is the fallback and must reproduce the quoted quantities exactly.

### Finding codes

ONLY HARD findings block a publish. A warning with no reason on it does not block: it is
recorded as unacknowledged and named in the publish confirmation, so the person publishing
sees what they are waving through. CLARIFIED 2026-08-02, because "publishes once
acknowledged" and "refused with the blocking findings listed" read differently and the
frontend had to guess. Enabling a button the server then 409s on is the worse failure.

Hard stops, five of them, all arithmetic. A draft carrying any unacknowledged hard finding
cannot publish:

| code | means |
|---|---|
| `line_arithmetic` | `qty * unit_price != amount` on a PO line |
| `total_mismatch` | our line sum differs from the document total |
| `schedule_short` | scheduled quantity is less than the PO quantity |
| `schedule_over` | scheduled quantity exceeds the PO quantity |
| `unresolved_product` | a line has no product |

Warnings, acknowledged with a reason and then publishable: `price_vs_quotation`,
`code_vs_quotation`, `missing_delivery_date`, `phase_unmatched`, `credit_exposure`,
`no_package_mapping`, `pre_order_overlap`.

### `POST /sales-orders/{pso_id}/findings/{finding_id}/acknowledge`

`{"reason": "required"}`. Hard findings can be acknowledged too, but only by a user with
the override permission, and the reason is mandatory and shown on the SO forever.

### `PUT /sales-orders/{pso_id}/lines/{line_id}` and `POST /sales-orders/{pso_id}/regroup`

Regroup body: `{"groups": [{"area_group": "TOWER", "line_ids": ["…"]}]}`. Re-splits the
draft's lines into the given groups, sets `grouping_origin="manual"`, and remembers the
shape for that customer so the next PO proposes it.

### `POST /sales-orders/{pso_id}/publish`

Body optional. 409 with the blocking findings listed if any hard finding is unacknowledged.
Stage 1 is an AutoCount import file plus adoption of the returned document number, so the
response carries `{"status": "published", "provisional_ref": "…", "import_file_url": "…"}`.

`{"acknowledge_blocking": true, "reason": "required"}` publishes past every open hard
finding in one decision (ADDED 2026-08-18). It is the same override the per-finding
acknowledge carries, asked once: the override permission is required (403 without it), the
reason must be at least 3 characters (422), and it is recorded on EVERY finding it clears
alongside the actor and the timestamp, prefixed `Published anyway (N blocking findings):`.
The response adds `acknowledged_findings`, how many were waved through (0 on the ordinary
path). Clearing 15 to 30 findings one at a time to publish an order the manager had already
decided to publish was the constraint this removes. The other three refusals are NOT
overridable, because none of them is a finding: already published, awaiting costing (D28)
and no lines.

---

## 6. Revision, delta, OCN (P11)

Uploading a revised PO or schedule is just section 2 or 4 again: a new version of the same
commitment. What is new is the diff.

### `POST /sales-orders/{pso_id}/amendments/preview`

`{"po_version_id": "…"}` or `{"schedule_version_id": "…"}`. Computes the difference between
the version the SO was built from and the named one. Nothing is written.

```json
{
  "from": { "kind": "schedule_version", "id": "…", "version_no": 1, "label": "…" },
  "to":   { "kind": "schedule_version", "id": "…", "version_no": 2, "label": "REVISED 1" },
  "verb_summary": { "DELAY": 12, "ADVANCE": 0, "ORDER": 0, "CANCEL BALANCE": 3 },
  "rows": [
    { "so_line_id": "…", "line_no": 4,
      "product_code": "SRTWC8613-RL", "description": "…",
      "verb": "DELAY",
      "field": "delivery_date",
      "from_value": "2026-07-01", "to_value": "2026-08-15",
      "qty": "135",
      "phase_label_from": "Level 2 & 7", "phase_label_to": "Level 2 & 7" }
  ],
  "unmatched": [
    { "reason": "phase not found in the new version", "detail": "…" }
  ]
}
```

Verbs are the client's own vocabulary, not ours: `ORDER`, `RESERVE & ORDER`, `ADVANCE`,
`DELAY`, `CHANGE SO NO`, `CANCEL BALANCE`.

A revision that moves dates must leave quantities alone, and the preview must show that
plainly, because "did anything other than the dates change?" is the only question the
reviewer actually has. `unmatched` is never silently empty: a phase that cannot be matched
is shown, not dropped.

### `POST /sales-orders/{pso_id}/amendments`

Same body as preview, plus `{"reason": "…"}`. Persists the amendment with its
`delta_json`, auto-drafts an `order_change_notices` row from the same delta, and leaves both
in `proposed` for review. Returns `{amendment_id, ocn_id, ocn_number, verb_summary}`.

### `GET /amendments/{amendment_id}` / `POST /amendments/{amendment_id}/publish`

Publish applies the delta to the SO lines, stamps the OCN approved, and moves the SO to
`amended`. 409 if the OCN has no approver.

---

## 6b. Allocation (P9)

AC-H1 to AC-H5. Base `/api/v1/project-sales`.

**Ranked candidates are computed live on every request and never stored.** A stored
snapshot of another project's on-hand goes stale the moment they ship, and acting on a
stale figure is the failure this slice exists to prevent. Only the DECISION persists, in
`so_line_allocations`.

BRW-BB is identified by warehouse CODE, from `settings.project_allocation_brw_warehouse_code`
(default `BRW-BB`), resolved against `warehouses.warehouse_code` at request time. All four
sites run a `-BB` bin, so the site prefix is what makes BRW-BB the master. No matching row
means no `brw` candidate rather than a blank screen.

### `GET /sales-orders/{pso_id}/allocations`

`ListResponse` of one row PER LINE, sourced or not:

```json
{ "line_id": "…", "line_no": 1, "product_code": "SRTWC8613-RL", "description": "…",
  "qty": "135", "uom": "SET", "delivery_date": "2026-07-01",
  "state": "unallocated" | "pending_claim" | "refused" | "partial" | "confirmed",
  "stock_location": "BRW-BB + MWH" | null,
  "allocated_qty": "135", "outstanding_qty": "0",
  "sources": [
    { "id": "…", "source_type": "brw" | "own" | "other_project" | "order",
      "warehouse_code": "BRW-BB", "source_project_code": null,
      "source_project_cs_name": null, "qty": "135",
      "confirmed": true, "confirmed_by_name": "Eling", "confirmed_at": "…",
      "claim_id": null, "claim_state": null, "claim_reason": null }
  ] }
```

`stock_location` counts CONFIRMED sources only, which is what makes it the stock location
the order inquiry carries (AC-H5, feeding P10).

### `GET /sales-order-lines/{line_id}/allocation-candidates`

```json
{ "line_id": "…", "line_no": 1, "qty": "135", "project_code": "PS26-0143",
  "brw_warehouse_code": "BRW-BB",
  "candidates": [
    { "rank": 1, "source_type": "brw", "warehouse_code": "BRW-BB",
      "on_hand": "80", "reserved": "0", "held_for_this_project": "0",
      "held_for_other_projects": "0", "committed": "0", "available": "80",
      "allocatable": "80", "claimable": "0", "requires_claim": false,
      "is_project_location": false, "holders": [],
      "open_claim_id": null, "open_claim_state": null },
    { "rank": 2, "source_type": "other_project", "warehouse_code": "MWH",
      "available": "0", "claimable": "135", "requires_claim": true,
      "holders": [ { "project_code": "PS26-0201", "cs_name": "Farah", "qty": "200" } ] },
    { "rank": 3, "source_type": "order", "warehouse_code": null, "allocatable": "55" }
  ],
  "plan": [ { "warehouse_id": "…", "warehouse_code": "BRW-BB", "qty": "80" } ],
  "shortfall": "55", "covered": false }
```

Rank order: `brw`, then `own` (this project's own locations first, then any location whose
stock nobody has spoken for), then `other_project`, then `order`. Ties inside a bucket go
to the larger free balance, then to the warehouse code. `plan` is a greedy fill over FREE
stock only and never includes an `other_project` holding.

### `PUT /sales-order-lines/{line_id}/allocation`

`{"sources": [{"source_type", "warehouse_id"?, "source_project_id"?, "qty"}]}`. Replaces the
whole decision and stamps `confirmed_by` / `confirmed_at` (AC-H3). Refusals:

- 422 when the sources exceed the line quantity, when a stock source names no location, or
  when `order` names one.
- 409 when a source exceeds what the location holds free, or when it names stock held for
  another project with no ACCEPTED claim behind it.

### `DELETE /sales-order-lines/{line_id}/allocation`

204. Hard delete, and any still-open claim it raised is withdrawn with it.

### `POST /sales-order-lines/{line_id}/allocation-claims`

`{"warehouse_id", "to_project_id", "qty"}` -> 201 with the claim row. Writes the claim in
`requested` PLUS an unconfirmed allocation, so the line shows what it is waiting on.
Nothing moves on silence: the line reads `pending_claim`, gets no stock location, and the
pending row grants no hold on a third project's screen. 409 when more is asked than that
project holds, or when the same request is already open; 422 when a project claims from
itself or asks for more than the line needs.

### `GET /allocation-claims?direction=incoming|outgoing|all&state=…`

The worklist. `incoming` = claims against projects this user may act for (owner,
collaborator, or the manage grant).

### `POST /allocation-claims/{claim_id}/accept` and `/refuse`

Only the HOLDING project's CS may answer, checked in the service. Accept confirms the
allocation it backed and stamps the line's stock location. Refuse requires
`{"reason": "…"}` of at least three characters (422 otherwise) and leaves the allocation
unconfirmed so the refusal and its reason stay on the line.

---

## 6c. Order inquiry and the SCM handoff (P10)

AC-I1 to AC-I7. Base `/api/v1/project-sales`.

**Rows are DERIVED, never authored.** Publishing a sales order or an amendment writes one
`order_inquiries` row and its `order_inquiry_rows`, in the same transaction as the publish.
There is no create endpoint and there should not be one: an instruction typed by hand is
the email this slice exists to replace. Derivation is idempotent per (sales order) and per
(amendment), enforced by two partial unique indexes (migration
`322_order_inquiry_derivation`), so republishing cannot double what purchasing is told to
buy.

**Committed demand is untouched** (AC-I6). `sales_order_lines` remains the only source of
demand and the SCM reorder engine is not changed. Inquiry rows are read back for exactly
one thing: the coverage ledger, which stops a pre-order being promised to two publishes.

`POST /sales-orders/{pso_id}/publish` and `POST /amendments/{amendment_id}/publish` both
gain `"order_inquiry_id"` in their response.

### Netting (AC-I3, AC-I3a)

Before rows are written, NEW and INCREASED demand is netted against two covering pools:

- **pre-order** - published `is_pre_order` sales orders on the SAME PROJECT (the project
  is the anchor, not the customer), excluding the order being published.
- **inbound SPO** - `spo_allocations` on shipments with no `actual_arrival_date`, at
  `allocated_quantity - quantity_received`.

The pool is consumed **FIFO by delivery date** (earliest dated demand first; undated
demand last). Rows still PRINT in line order. A partly covered line splits into a covered
row naming its pool in `covered_by` and an uncovered balance; a zero balance emits nothing.
Amendment instructions (DELAY, ADVANCE, CANCEL BALANCE, CHANGE SO) never consume a pool.

### Verbs (AC-I2)

`(change, coverage) -> exactly one verb`:

| change | coverage | verb |
|---|---|---|
| new / qty_increase | pre_order | `PRE_ORDERED_DO_NOT_ORDER` |
| new / qty_increase | inbound | `ALREADY_INBOUND` (+ `spo_ref`) |
| new / qty_increase | none, delivery within 60 days | `RESERVE_AND_ORDER` |
| new / qty_increase | none, beyond 60 days or undated | `ORDER` |
| date_later | any | `DELAY` |
| date_earlier | any | `ADVANCE` |
| qty_decrease | any | `CANCEL_BALANCE` |
| repoint | any | `CHANGE_SO` |

`ORDER` and `RESERVE_AND_ORDER` are unreachable for a covered quantity, which is AC-I3.

### `GET /projects/{project_id}/order-inquiry-rows`

`ListResponse`, filters `query`, `verb`, `state`, `sales_order_id`, sorted by
`delivery_date` by default.

```json
{ "id": "…", "order_inquiry_id": "…", "sales_order_ref": "SO397450",
  "so_date": "2026-04-02T…", "project_customer": "BUIMACO / TUJU RESIDENCE",
  "is_amendment": false,
  "item_code": "CB6633", "qty": "600", "delivery_date": "2027-01-07",
  "stock_location": "BRW-BB" | null,
  "verb": "ORDER", "remark": "ORDER", "spo_ref": null,
  "covered_by": "Pre-order SO383057" | null, "note": "Was 2026-07-01" | null,
  "state": "raised" | "actioned" | "cancelled",
  "actioned_at": null, "actioned_by_name": null }
```

`stock_location` is the warehouse code on a CONFIRMED `so_line_allocations` row (AC-H5),
joined with ` / ` when the line is split across two. **Null when nothing is confirmed**,
and the screen and the spreadsheet both leave it blank rather than defaulting.

`remark` is the verb in the client's own spelling (`RESERVE & ORDER`, `CHANGE SO NO`), or
the SPO reference itself on an `ALREADY_INBOUND` row, matching their file.

### `GET /projects/{project_id}/order-inquiry-summary`

`{"total": 341, "raised": 300, "actioned": 40, "cancelled": 1}`.

### `GET /sales-orders/{pso_id}/order-inquiry`

The latest inquiry raised on one sales order, its rows, and `task_id` / `task_name` for the
purchasing task. 404 with `order_inquiry_not_raised` before the order publishes.

### `POST /order-inquiry-rows/mark`

`{"row_ids": ["…"], "state": "actioned" | "cancelled" | "raised"}`. Requires
`projects.order_inquiry.action`, which is PURCHASING's grant, not the project owner's:
gating it on project edit would mean granting purchasing the right to edit every pursuit
in the company. Stamps `actioned_by` / `actioned_at`; `raised` is the undo and clears both.
The parent inquiry's state follows its rows (open while any row is still raised).

### `GET /projects/{project_id}/order-inquiry-export`

The same rows and the same filters, as `.xlsx`. Generated per request, exactly as the
AutoCount import file is: a stored copy goes stale the moment an amendment publishes.
Sheet `NEW`, title row `ORDER INQUIRY`, then the client's own headings, read off
`e2e/fixtures/project-cs/expected-order-inquiry-2026-03-04.xlsx`:

```
SO DATE | S/O NO | ITEM CODE | QTY | DELIVERY DATE | PROJECT/CUSTOMER | STOCK LOCATION | REMARK
```

### The SCM handoff (AC-I4)

Purchasing is handed a `project_tasks` row on the DELIVERY phase, category `Purchasing`,
`linked_entity_type="order_inquiry"` pointing at the inquiry, plus an in-app notification
to everyone holding the `purchasing` role (the role SCM's permissions are granted through).
Deliberately **no email**: the task is the record, and a mailbox is the thing it replaces.
Both are best-effort, because the sales order is already published when they run.

---

## 7. What is deliberately not in this contract tonight

Allocation (P9) has since landed and is section 6b above; the order inquiry and SCM
handoff (P10) is section 6c; divergence reconciliation (P8a) is section 6d. Still out:
pre-order and sponsorship paths (P12), and the ESB swap plus real AR ingest (P13).
The publish path stops at the import file. Nothing above depends on them.

---

## 6d. Divergence reconciliation (P8a)

Full design in `PLAN-project-so-divergence.md`. What the wire looks like:

### `POST /sales-orders/ingest` and `POST /sales-orders/ingest-file`

The first takes the canonical document and is the seam the ESB takes in stage 2; the second
takes the AutoCount export a CS uploads today (CSV or XLSX, 10 MB ceiling) and parses it
into the same shape. **Both mount before `/sales-orders/{pso_id}`**, which is the same path
shape, so the router would otherwise read `ingest` as a document id.

Match back is a natural key - customer + customer PO number + area group - with the line
fingerprint as the TIE BREAKER only. A divergent document has a different fingerprint by
definition, so keying on it would report every divergence as unmatched.

```json
{ "outcome": "matched | divergent | ambiguous | unmatched",
  "project_sales_order_id": "…", "divergence_id": "…",
  "differing_count": 4, "candidate_ids": [], "message": "" }
```

Always 200, never a 404 for an unmatched document: the caller has to tell a person WHY, and
`message` carries the key that was tried. `ambiguous` writes nothing at all.

Re-ingesting is idempotent: one OPEN divergence per sales order, recomputed rather than
stacked. A document that now agrees RESOLVES the open one, which is how a difference is
retired when somebody fixes it on their side.

### `GET /divergences` and `GET /divergences/{id}`

The list carries `age_days` (AC-N6). The detail carries every compared row including the
ones that AGREE, with `needs_answer` false on them: the screen collapses them behind a
count, and a count nobody wrote down is not a count.

### `POST /divergences/{id}/rows/{row_id}/resolve`

`{"resolution": "accept_theirs" | "keep_ours", "reason": "…"}`. The reason is required
(422 without it). Accept theirs applies their values and recomputes the order total, EXCEPT
on a header row, where the decision is recorded and nothing is rewritten - the customer's
own document is not AutoCount's to edit. A line AutoCount dropped goes to quantity 0 rather
than being deleted, because allocations, claims and inquiry rows point at it. Keep ours sets
`corrective_publish_required`.

### `GET /divergences/{id}/corrective-import-file`

Our values going back to AutoCount, as CSV. 409 `divergence_no_corrective_publish` when
nothing was answered KEEP OURS. Generated per request and stamped when taken, exactly as
the original import file is.

### The amendment block (AC-N5)

`assert_amendable` runs on amendment CREATE and on PUBLISH, not only create: a divergence
can land between proposing an amendment and publishing it, which is when publishing it does
the damage. Refusal is 409 `so_divergence_unresolved`.

---

## 8. Amendments after the first client review

Recorded here because the contract is what the next person reads, not the transcript.

**A9. `extraction_elapsed_ms` on both version responses.** How long the model actually
took, in milliseconds; null on documents read before it was recorded. The client asked to
be told the processing time once a read finishes ("you need to display the processed time
after done to let the user know how long you took"). Column added to
`project_po_versions` and `delivery_schedule_versions` by migration
`320_extraction_elapsed_ms`. The frontend renders it through
`_shared/lib/readingTime.ts` ("Read in 2m 15s") and never beside a running spinner, where
a duration would read as a total it is not yet.

**A10. Document reads are logged as AI usage.** Every extraction writes an
`ai_assistant_usage_logs` row with `feature="ai_document_extract"`, `form_key` set to the
prompt key, `tool_calls_count` set to the page count (one model call per page) and
`response_time_ms` set to the elapsed time. `ai_document_extract` is a THIRD feature
value beside `ai_assistant` and `ai_extract`, and had to be added to the usage screen's
filter and label map or the rows appeared only under "All" and were mislabelled as chat.
The row carries no principal: extraction runs on the worker with no request behind it and
neither version table records who uploaded the document, so there is nothing truthful to
attribute it to. Giving it one needs an uploader column, which is a separate change.

**A11. A wrapped description is folded, not counted.** A description that spills past the
bottom of a page finishes above the next numbered item on the following page. That tail
is rejoined to the line it belongs to. A payload is a continuation when it has
description text, no printed item number and no qty, unit price or amount; the stock code
cell is explicitly not part of the test, because the model reads ink bleeding through from
the row above into it. With no line above it, a fragment is still kept, so nothing is ever
dropped silently.

**A12. One file-drop surface.** Every upload in the product renders
`components/common/FileDropzone.tsx` ("i want to standardize our file dropping UI in the
whole system"). It replaces the picking surface only; preflight, validation, progress and
routing stay in each call site.
