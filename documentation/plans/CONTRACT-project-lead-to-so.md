# API contract: lead to sales order (phase 2)

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
  "page_count": 10,
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
      "id": "…", "line_no": 1,
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

No body. 409 with the blocking findings listed if any hard finding is unacknowledged.
Stage 1 is an AutoCount import file plus adoption of the returned document number, so the
response carries `{"status": "published", "provisional_ref": "…", "import_file_url": "…"}`.

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

## 7. What is deliberately not in this contract tonight

Allocation (P9), the order inquiry Excel and SCM handoff (P10), pre-order and sponsorship
paths (P12), the ESB swap and real AR ingest (P13), and divergence reconciliation (P8a).
The publish path stops at the import file. Nothing above depends on them.
