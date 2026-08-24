# PLAN: Configurable field-based CS routing (predicate engine)

**Status:** Design locked (grill 2026-07-19). Not built.
**Classification:** CORE (extends existing form-SLA CS pin + lookup system; `public` schema; no new
tables - 2 columns on an existing table + 1 column on `lookup_bindings` + 1 new lookup set/binding).
**Domain:** forms / procurement / sla
**UAC:** `documentation/plans/forms/form-cs-routing-conditions-acceptance-criteria.md` (written first)
**Owner:** Claude + Jayson · **Created:** 2026-07-19
**Builds on:** `PLAN-procurement-cs-handoff-and-pinpoint-routing.md` (the `respond_contact_cs_routing`
pin + `_resolve_pinned_assignee` this plan generalizes).

## Problem

The CS pin (`_resolve_pinned_assignee`, `form_sla_service.py:859`) keys only on
`(respond_contact_id, use_case)`. Business need: route a Purchase Request to different CS people by
**project vs cash sales**, and - generally - by **any** form field in future, configured, not
hardcoded.

## Solution

Two parts.

### A. `sales_type` field (first concrete routable dimension)

- `purchase_requests.sales_type VARCHAR(50)`, bound to a new lookup set `procurement_sales_type`
  (options `project` / `cash_sales`), stored as the string value code - same pattern as
  `sponsor_subject` (migration 243).
- **Required** on the PR form (form-schema level); **Sponsorship Form ignores it** (shared table, no
  SF field, persists NULL).
- Default sourced from a **new generic `lookup_bindings.default_value`** = `project`.

### B. Generic predicate routing engine

- `respond_contact_cs_routing` gains `match_conditions JSONB DEFAULT '[]'` (array of
  `{field, operator, value}`, AND-combined) + `priority INT DEFAULT 0`.
- Operators v1: `equals`, `not_equals`, `contains`, `not_contains` (`contains`/`not_contains`
  string-only). Fields = the form's user-facing input fields (exclude system/audit/status columns).
- Applies to all use_cases (today only PR configured; others use `[]` wildcard rows).

### Resolution algorithm (in `_resolve_pinned_assignee`, evaluated against the form header row)

```
rows = active routing rows for (respond_contact_id, use_case)
matches = [r for r in rows if all(predicate_passes(p, form) for p in r.match_conditions)]
if matches:
    pick = min(matches, key=lambda r: (r.priority, r.created_at))   # pure admin priority
    if pick.cs_pic_user_id is active tier-1 member of the CS team: return that assignee
# any miss / stale pin → existing round-robin (get_next_assignee), + logger.warning
```

Pure admin-ordered `priority`; wildcard `[]` is NOT auto-deprioritized (admin orders it last). UI
warns when a wildcard shadows a specific row.

## Decisions

| # | Decision |
|---|----------|
| D1 | **Field `sales_type`** (`project`/`cash_sales`) on `purchase_requests`; PR captures (required), SF ignores (NULL). |
| D2 | **Generic predicate engine, not a hardcoded column.** `match_conditions JSONB` → future dimensions = new predicates, zero schema change. |
| D3 | **Operators v1** = `equals`, `not_equals`, `contains`, `not_contains`; AND-only within a row; "OR" = a second row; no nested groups. |
| D4 | **Fields = form's user-facing input fields**, exclude system/audit/status; value input adapts by type (lookup → option dropdown). |
| D5 | **Pure admin-ordered `priority`** (no auto-specificity); `created_at` tiebreak → else round-robin. Wildcard-shadow warning in UI. |
| D6 | **`default_value` on `lookup_bindings`** (generic, validated ∈ set options); FE pre-selects on NEW forms only. `procurement_sales_type` → `project`. |
| D7 | **`sales_type` required at PR form-schema level** (not a generic binding feature). |
| D8 | **Uniqueness** = expression unique `(respond_contact_id, use_case, md5(canonical_json(match_conditions)))`; old 2-col unique dropped. |
| D9 | **Evaluation = form header fields, header-level only**, at `_resolve_pinned_assignee` (CS-stage spawn). |
| D10 | **Migration additive + backward-safe.** Existing routing rows → `[]` (wildcard, identical to today); existing PRs → `sales_type` NULL, no backfill. |

## Critical files

- BE: `app/models/procurement.py` (PR `sales_type` col near `sponsor_subject` `:332`),
  `app/models/access.py:239` (`RespondContactCsRouting` + `match_conditions`/`priority`),
  `app/models/lookup.py:72` (`LookupBinding.default_value`),
  `app/services/form_sla_service.py:859` (`_resolve_pinned_assignee` - engine),
  `app/services/lookup_binding_service.py` (validate `default_value`),
  `app/api/v1/lookup.py:16` (`by-binding` returns `default_value`),
  CS-routing service/endpoints (from the pin-point plan), `schemas/procurement.py` (`sales_type`),
  new alembic migration (243-pattern for lookup; separate for routing cols).
- FE: `PurchaseRequestForm.tsx:457` (`sales_type` `LookupBoundField`),
  `LookupBoundField.tsx` (consume `default_value`), `LookupBoundLabel.tsx` (display),
  `BindingsSection.tsx` (`default_value` editor), the contact CS-routing table
  (`ContactCsRoutingTable.tsx` from the pin-point plan) → add the predicate builder + drag-order.

## Phase mapping

- **Phase 1 (FE prototype):** build the **predicate builder + draggable priority list** and the
  `sales_type` field against **mock** hooks - nail the field/operator/value UX, the wildcard-shadow
  warning, ordered-list drag, empty/error states. Document the request/response contract for the
  routing PUT (shape of `match_conditions` + `priority`) and the `by-binding` `default_value` addition.
  Playwright MCP sidebar-click verify. NO backend, NO tests yet.
- **Phase 2 (BE, test-FIRST):** author ME-*/RES-* as failing tests first (the predicate engine +
  resolution ordering are pure functions - golden cases before code), then the migration + columns +
  engine + `default_value`; swap FE mocks for real hooks; land pytest + vitest + one Playwright E2E.
  RES-5 regression is a hard gate.
- **Phase 3:** `/code-review`; reviewer checks JSONB uniqueness canonicalization, NULL-field predicate
  behaviour (ME-6), round-robin fallback resilience (RES-6), and DoD (backfill of routing rows → `[]`,
  new-column-reaches-FE for `sales_type`, searchable dropdowns).

## DoD-gate specifics (PRINCIPLES)

- **Backfill:** routing rows → `match_conditions=[]` via migration DEFAULT + explicit UPDATE for any
  pre-existing NULL; `sales_type` left NULL on existing PRs (documented, not a silent gap).
- **New column reaches FE:** `sales_type` added to PR create/update/response schemas AND any manual
  dict builder; `default_value` added to the `by-binding` payload.
- **No new permission** for the engine itself (reuses the existing CS-routing config permission); if
  the predicate builder needs a finer grant, sweep existing roles.

## Risks

- **R1 - canonical JSON for the unique index:** predicate order/whitespace must be normalized before
  `md5` (sort keys, stable separators) or logically-equal condition-sets collide/duplicate. Provide a
  single `canonical_json(match_conditions)` helper used by BOTH the write path and the index
  expression (generated column or expression index over the same normalization).
- **R2 - field whitelist source:** deriving "user-facing fields" - prefer an explicit per-form field
  registry (safe, curated) over raw SQLAlchemy column introspection, to keep audit/status columns out
  of the UI (CFG-2). Decide the registry location in Phase 1 contract.
- **R3 - type coercion:** `contains` on a numeric field is nonsense; the operator list must be gated
  by field type both in UI (hide) and BE (reject) to avoid silent mismatches.
- **R4 - SF shares the table:** ensure the required-`sales_type` rule is scoped to `request_type =
  purchase_request` only; SF create must not 422 on a missing `sales_type`.
