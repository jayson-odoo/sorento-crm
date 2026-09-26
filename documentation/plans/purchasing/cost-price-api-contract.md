# Cost price Lane A (S1 + S2): API contract

Status: Phase 1 contract, 27 Sep 2026, captain. The FE mock (Phase 1) is built against it, the
tester's red tests (Phase 2) assert it, the coder makes the backend match it. A change to a shape
here is made in this file first. Plan: `PLAN-cost-price-supplier-26sep.md`. UAC:
`cost-price-supplier-acceptance-criteria.md`.

All routes live under `/api/v1/procurement` (the existing `procurement` module guard). Dates are
`YYYY-MM-DD` strings; datetimes are naive UTC ISO strings the FE renders with
`formatDateTimeInMalaysia`. Money is a JSON number with 2 decimals. Errors use the `AppException`
envelope (`{"detail": ..., "code": ...}` as `extractApiError` reads it).

## 1. Change sets

Base: `/api/v1/procurement/cost-price-changes`.

### 1.1 `POST /probe` (multipart: `file`) - permission `procurement.cost_price_changes.upload`

Parses without storing (plan 5.2). 200:

```json
{
  "file_name": "TO SORENTO-19&12&22&28&25 series price list 20260917.xlsx",
  "file_date": "2026-09-17",
  "sheets": [{"name": "19 series", "header_row": 6, "rows": 40, "skipped_reason": null}],
  "total_rows": 258,
  "suggested_supplier": {"id": "...", "supplier_code": "TAIYANG", "supplier_name": "XIAMEN TAIYANG TECHNOLOGY"},
  "currency": {"code": "CNY", "source": "header"}
}
```

`file_date` is an 8-digit `YYYYMMDD` run in the file name, else null. `suggested_supplier` is null
unless the letterhead names exactly one active supplier (AC-S1-06). `currency.source` is
`header` (price header token), `supplier` (the one currency of that supplier's links, only when a
supplier was suggested) or null with `code` null (AC-S1-07). A sheet with no header has
`header_row: null`, `rows: 0`, `skipped_reason: "no_header"` (AC-S1-02). Refusals: 422
`file_too_large` / `file_type` / `too_many_rows` (AC-S1-15), 422 `pick_one_company` (AC-S1-17).

### 1.2 `POST /` (multipart: `file`, `supplier_id`, `currency`, `start_date?`, `end_date?`) - `upload`

Parses, matches, stores a Draft set in one transaction, retains the file. 201 = the set detail
(1.4). 409 `open_set_exists` with `{"open_set": {"id": "...", "code": "CPC-0007"}}` in the body
(AC-S1-14). 422 `end_before_start`, `currency_required`, plus the probe refusals.

### 1.3 `GET /` - permission `procurement.cost_price_changes.view`

Query: `page`, `limit`, `sort` (`code|created_at|applied_at`, default `created_at`), `dir`,
`query` (set code, supplier name or code, file name; case-insensitive contains), `status`
(comma list of `draft,pending_verification,applied`), `supplier_id`. Built with
`buildDataGridParams`. 200 `ListResponse`:

```json
{"data": [{
  "id": "...", "code": "CPC-0007", "status": "draft",
  "supplier": {"id": "...", "supplier_code": "TAIYANG", "supplier_name": "XIAMEN TAIYANG TECHNOLOGY"},
  "channel": "staff_upload", "file_name": "....xlsx", "currency": "CNY",
  "start_date": "2026-10-01", "end_date": null,
  "lines_changed": 212, "uploaded_by_name": "Mei Ling", "created_at": "...",
  "applied_at": null, "verified": null, "verified_by_name": null
}], "total": 7, "page": 1, "limit": 50}
```

`lines_changed` counts `changed` + `new_link` lines not skipped. `verified` is null until applied,
then true/false (AC-S2-17).

### 1.4 `GET /{id}` - `view`

```json
{
  "id": "...", "code": "CPC-0007", "status": "draft", "channel": "staff_upload",
  "supplier": {"id": "...", "supplier_code": "TAIYANG", "supplier_name": "XIAMEN TAIYANG TECHNOLOGY"},
  "currency": "CNY", "start_date": "2026-10-01", "end_date": null,
  "file_name": "...xlsx", "has_source_file": true,
  "sheets": [{"name": "19 series", "header_row": 6, "rows": 40, "skipped_reason": null}],
  "total_rows": 258,
  "uploaded_by_name": "Mei Ling", "created_at": "...",
  "submitted_by_name": null, "submitted_at": null,
  "returned_reason": null, "returned_by_name": null, "returned_at": null,
  "applied_by_name": null, "applied_at": null, "verified": null,
  "verification_enabled": false,
  "counts": {"changed": 212, "unchanged": 38, "new_link": 6, "unmatched": 1,
             "duplicate_code": 1, "needs_attention": 0, "skipped": 0,
             "accepted": 0, "rejected": 0, "undecided": 0},
  "largest_rise": {"supplier_code": "SRTWT1900-BL-DIY", "change_pct": 7.0},
  "actions": {
    "can_apply": false, "apply_blocked_reason": "2 rows still need you: 1 not found, 1 duplicate",
    "apply_count": 212,
    "can_submit": false, "can_decide": false, "can_return": false, "can_discard": true,
    "decide_blocked_reason": null
  }
}
```

`actions` is computed server side for the CALLER, so the FE never re-derives the four-eyes rule
(AC-S2-03, AC-S2-15): with verification off a staff Draft set shows `can_apply` for an `upload`
holder; with it on, the uploader gets `can_submit` and the verifier (holding `verify`, not the
uploader or submitter) gets `can_decide`, `can_return`, `can_apply` on a Pending set.
`apply_blocked_reason` / `decide_blocked_reason` carry the tooltip text. `apply_count` counts
the lines Apply would write.

### 1.5 `GET /{id}/lines` - `view`

All lines of the set (at most 5,000, the parse cap), in sheet then row order. The review page
filters, searches and counts on the client (AC-SR-02: counts follow the search).

```json
{"data": [{
  "id": "...", "sheet": "19 series", "row_no": 7, "line_no": "1",
  "supplier_code_raw": "SRTWT1900-BL-DIY", "supplier_code": "SRTWT1900-BL-DIY", "code_note": null,
  "configuration": "304不锈钢 单把 冷热", "flags": ["configuration_from_merge"],
  "match_outcome": "exact", "match_rung": null,
  "product": {"id": "...", "product_code": "SRTWT1900-BL-DIY", "description": "ANGLE VALVE BLUE DIY"},
  "current_unit_cost": 86.0, "current_currency": "CNY", "new_unit_cost": 92.0,
  "change_pct": 7.0,
  "line_state": "changed", "skipped": false, "skip_reason": null,
  "new_link_lead_time_days": null,
  "decision": null, "decision_reason": null, "decided_by_name": null,
  "stale": null
}]}
```

`match_outcome`: `exact | alias | ladder | manual | unmatched`. `line_state`: `changed |
unchanged | new_link | needs_attention | skipped`. The review page's "Not found" filter is
`match_outcome == unmatched` and not skipped; "Duplicate code" is `flags` contains
`duplicate_code` and not skipped; "Needs attention" is `line_state == needs_attention`.
`stale` is `{"live_unit_cost": 90.0, "live_currency": "CNY"}` after an Apply refused a line as
stale (AC-S2-06), else null.

### 1.6 `PATCH /{id}/lines/{line_id}` - `upload`, Draft sets only (409 otherwise)

Body (every key optional, an absent key is left alone):
`{"product_id": "..." | null, "skipped": true | false, "skip_reason": "...",
"new_link_lead_time_days": 45}`. `product_id` maps an unmatched line by hand
(`match_outcome = manual`, `mapped_by`), null unmaps it back to `unmatched`. The response is the
updated line (1.5 shape) plus the set's new `counts` and `actions`:
`{"line": {...}, "counts": {...}, "actions": {...}}`. Mapping re-runs the line state (price in
force, `new_link`) and the duplicate check for the whole set.

### 1.7 Verification (S2)

- `POST /{id}/submit` - `upload`. Verification on + Draft staff set + nothing unresolved, else
  409 `verification_off` / 422 `unresolved_lines`. Returns the set detail.
- `PATCH /{id}/lines/{line_id}/decision` - `verify`. Body `{"decision": "accepted" | "rejected" |
  null, "reason": "..." (<= 500)}`. 403 `SAME_PERSON_CANNOT_VERIFY`. Same response as 1.6.
- `POST /{id}/decide-all` - `verify`. Body `{"decision": "accepted" | "rejected"}`; applies to
  every undecided changed or new-link line not skipped. Returns the set detail.
- `POST /{id}/return` - `verify`. Body `{"reason": "..."}` (required, <= 500). Back to Draft,
  decisions cleared. Returns the set detail.

### 1.8 `POST /{id}/apply` - `upload` (verification off, staff Draft) or `verify` (Pending)

Returns the set detail. 409 `stale_lines` with `{"lines": [{"line_id", "supplier_code",
"recorded_unit_cost", "recorded_currency", "live_unit_cost", "live_currency"}]}`; 409
`already_applied` / `wrong_status`; 409 `submit_first` (verification on, Draft staff set); 422
`unresolved_lines` / `undecided_lines` / `lead_time_required`; 403 `SAME_PERSON_CANNOT_VERIFY`.

### 1.9 Discard - `upload`

`DELETE /{id}` hard-deletes a Draft set (409 `not_draft` otherwise). The FE calls it through the
deferred-action route: a `FormAction` `cost_price_change_set.discard`, entity type
`cost_price_change_set`, 10 s window (AC-S1-23).

### 1.10 `GET /{id}/source-file` - `view`

The retained upload, `Content-Disposition: attachment` with the original file name. 404 when the
set has none.

### 1.11 `GET /{id}/history` - `view`

Newest first: `{"data": [{"action": "COST_SET_UPLOAD", "actor_name": "Mei Ling", "at": "...",
"summary": "Uploaded 258 rows from ...xlsx"}]}` (AC-AU-04). Line maps and skips are listed as
`COST_LINE_MAP` / `COST_LINE_SKIP` rows from the line audit trail.

## 2. Cost lists

### 2.1 `GET /api/v1/procurement/suppliers/{supplier_id}/cost-lists` - `procurement.product_suppliers.view`

Query: `query` (product code, description, supplier code), `status` (comma list of
`in_force,scheduled,ended,always,overridden`; a product is kept when any of its rows matches).

```json
{"data": [{
  "product_supplier_id": "...", "product": {"id": "...", "product_code": "CB2500SS-BL", "description": "BASIN MIXER BLUE"},
  "supplier_code": "CB2500SS-BL（彩盒）",
  "unit_cost": 468.0, "currency": "CNY",
  "costs": [{
    "id": "...", "unit_cost": 498.0, "currency": "CNY", "start_date": null, "end_date": null,
    "status": "always", "source": {"change_set_id": "...", "code": "CPC-0004"},
    "created_at": "..."
  }]
}], "today": "2026-09-27"}
```

`unit_cost` / `currency` are `product_suppliers.unit_cost` / `currency` (the price in force).
`supplier_code` is the last raw code seen for this product in this supplier's applied sets (null
if none). `costs[].status`: `in_force` (the price in force today), `scheduled` (start after
today), `ended` (end before today), `always` (no dates, not in force because a dated row
overrides it), `overridden` (dated, covers today, loses to a later start). `source` null means
"Edited by hand". Rows order: start date ascending, nulls first. Every linked product is listed,
including ones with no cost rows (`costs: []`).

### 2.2 `GET /api/v1/procurement/product-suppliers/product/{product_id}` (existing route)

Each entry gains `costs` (2.1 row shape) beside the fields it returns today. The product
Suppliers tab searches it on the client (supplier name, set code).

### 2.3 Hand edits - `procurement.product_suppliers.edit`

- `POST /api/v1/procurement/product-suppliers/{link_id}/costs` body `{"unit_cost": 468.0,
  "currency": "CNY", "start_date": "2026-09-15" | null, "end_date": "2026-09-30" | null}` 201 the
  cost row.
- `PUT /api/v1/procurement/product-suppliers/{link_id}/costs/{cost_id}` same body, 200.
- `DELETE /api/v1/procurement/product-suppliers/{link_id}/costs/{cost_id}` 200; the FE goes
  through the `FormAction` `product_supplier_cost.delete` (entity type `product_supplier_cost`,
  10 s window).

422 `end_before_start`, `negative_price`. Each write recomputes the link's price in force in the
same transaction and writes `SUPPLIER_COST_LIST_EDIT`.

## 3. Setting

`GET /api/v1/user-management/settings/` and `PUT /api/v1/user-management/settings/general` carry
`cost_price_verification_enabled: boolean` (default false). The update writes
`COST_VERIFICATION_SETTING` when the value changes.

## 4. Permissions (for FE gating)

| Slug | FE gate |
| --- | --- |
| `procurement.cost_price_changes.view` | sidebar item Procurement > Cost Price Uploads, list, detail |
| `procurement.cost_price_changes.upload` | Upload price list button (list, supplier Prices tab), map, skip, Discard |
| `procurement.cost_price_changes.verify` | nothing on the FE directly: the detail's `actions` carries it |
| `procurement.product_suppliers.view` | supplier Prices tab |
| `procurement.product_suppliers.edit` | + Price, Edit, Delete on a cost row |

## 5. Mock data (Phase 1)

The FE mock lives at the service boundary (`services/costPriceService.ts`) and uses the mockup's
sample rows: CPC-0007 (Draft, TAIYANG, CNY, from 1 Oct 2026, the four sample lines plus one Not
found `CB2800SS-BK-NEW` and the `CB2500SS-BL` duplicate pair), CPC-0004 (Applied, Not verified)
and the supplier cost lists of `supplier-cost-lists.html`. A `?mockVerification=on` style toggle
is not shipped; the mock reads a module constant.
