# Lookup Sets - Generic Dropdown Master Data

**Status:** Draft
**Date:** 2026-04-30
**Owner:** jayson-odoo

## 1. Problem

Many fields across the CRM are dropdown-style enumerations (status, region, priority, type, channel, etc.) that don't warrant their own dedicated master-data table. Today they're either hardcoded enums in code, ad-hoc strings, or one-off tables. Two needs:

1. Admin should configure dropdown values per (table, column) without code changes.
2. n8n / external AI agents pass raw user keywords (synonyms, variants) that must map to the canonical dropdown value before write. The system stores only canonical values; raw keywords are rejected.

Existing domain master data (`ProductCategory`, `Brand`, `UnitOfMeasure`) stays in its own tables and is **out of scope**.

## 2. Decisions (from brainstorming)

| Q | Decision |
|---|----------|
| Set ↔ binding relationship | **Reusable named set + many bindings table.** One set powers N (table, column) pairs. |
| Keyword schema + n8n flow | **Flat keywords per option + backend `/resolve` fallback endpoint.** n8n fetches options w/ keywords and does LLM mapping; backend also exposes deterministic resolve. |
| Existing master data | **Coexist, new system only.** Brand/UoM/ProductCategory untouched. |
| Binding registration | **Eligibility registered in code** (with friendly labels), **bindings stored in DB** so admins can attach sets to columns from the FE without knowing schema names. |
| Write enforcement | **Strict reject (422)** if value ∉ active options for bound column. |
| Tenant scope | **Tenant-scoped now.** `tenant_id` FK on sets. Read via existing stub. |

## 3. Concept

```
LookupEligibility (code-only)            LookupSet  (1) ──── (N) LookupOption ──── (N) LookupOptionKeyword
  table_name                                 │
  column_name                                │
  table_label                                ▼
  column_label                            LookupBinding  (DB)
  data_type                                 set_id
                                            table_name + column_name (must match an eligibility)
                                            tenant_id
```

- **LookupSet** - `set_key` (slug, unique per tenant), `name`, `description`, `tenant_id`.
- **LookupOption** - belongs to one set; `value` (canonical, unique within set), `label`, `sort_order`, `is_active`, `description`.
- **LookupOptionKeyword** - many keywords per option; `keyword` (normalized lowercase), `locale` optional.
- **LookupEligibility** - code-only registry of which (model, column) pairs are bindable and their friendly labels. Devs control. Admins cannot add eligibility.
- **LookupBinding** - DB row created by admin in FE: links one set to one eligible (table, column) within a tenant. Admin chooses (table, column) via dropdowns sourced from eligibility registry.

## 4. Database schema

### `lookup_sets`

| col | type | notes |
|---|---|---|
| id | UUID PK | |
| tenant_id | UUID FK → tenants.id | nullable until multi-tenant lands; populated via `DEFAULT_TENANT_ID` |
| set_key | VARCHAR(80) | snake_case slug |
| name | VARCHAR(150) | display |
| description | TEXT | nullable |
| is_active | BOOLEAN | default true |
| created_at / updated_at | timestamptz | |
| Unique | (tenant_id, set_key) | |

### `lookup_options`

| col | type | notes |
|---|---|---|
| id | UUID PK | |
| set_id | UUID FK → lookup_sets.id ON DELETE CASCADE | |
| value | VARCHAR(150) | canonical, sent to API/stored in bound column |
| label | VARCHAR(255) | UI display |
| sort_order | INT | default 0 |
| is_active | BOOLEAN | default true |
| description | TEXT | nullable |
| created_at / updated_at | timestamptz | |
| Unique | (set_id, value) | case-insensitive via citext or lower() index |
| Index | (set_id, sort_order) | |

### `lookup_bindings`

| col | type | notes |
|---|---|---|
| id | UUID PK | |
| tenant_id | UUID | matches set's tenant |
| set_id | UUID FK → lookup_sets.id ON DELETE CASCADE | |
| table_name | VARCHAR(100) | must match an eligibility entry at runtime |
| column_name | VARCHAR(100) | must match an eligibility entry at runtime |
| created_at / updated_at | timestamptz | |
| Unique | (tenant_id, table_name, column_name) | one set per (table,column) per tenant |
| Index | (set_id) | |

### `lookup_option_keywords`

| col | type | notes |
|---|---|---|
| id | UUID PK | |
| option_id | UUID FK → lookup_options.id ON DELETE CASCADE | |
| keyword | VARCHAR(150) | stored lowercase + trimmed |
| locale | VARCHAR(10) | nullable, e.g. `en`, `zh` |
| created_at | timestamptz | |
| Unique | (option_id, keyword, locale) | |
| Index | (lower(keyword)) | for resolve lookups |

Optional: `pg_trgm` extension + GIN index on `keyword` for fuzzy fallback. Defer to v1.1 unless cheap.

## 5. Eligibility registry (code-only) + bindings table (DB)

### Eligibility registry

`app/services/lookup_eligibility.py`:

```python
from dataclasses import dataclass
from typing import Type, Literal

DataType = Literal["string", "int"]

@dataclass(frozen=True)
class LookupEligibility:
    table_name: str
    column_name: str
    table_label: str          # friendly, surfaced in FE dropdown
    column_label: str         # friendly, surfaced in FE dropdown
    data_type: DataType       # restricts which option `value` types are valid
    nullable: bool

_REGISTRY: dict[tuple[str, str], LookupEligibility] = {}

def register_lookup_eligible(
    *, model: Type, column: str,
    table_label: str, column_label: str,
    data_type: DataType = "string", nullable: bool = True,
) -> None:
    key = (model.__tablename__, column)
    if key in _REGISTRY:
        raise RuntimeError(f"Duplicate lookup eligibility for {key}")
    _REGISTRY[key] = LookupEligibility(
        table_name=model.__tablename__, column_name=column,
        table_label=table_label, column_label=column_label,
        data_type=data_type, nullable=nullable,
    )

def get_eligibility(table: str, column: str) -> LookupEligibility | None:
    return _REGISTRY.get((table, column))

def all_eligibility() -> list[LookupEligibility]:
    return list(_REGISTRY.values())
```

Devs declare in `app/services/lookup_eligibility_registrations.py`, imported at startup:

```python
from app.models.order import Order
from app.services.lookup_eligibility import register_lookup_eligible

register_lookup_eligible(
    model=Order, column="priority",
    table_label="Order", column_label="Priority",
)
register_lookup_eligible(
    model=Order, column="channel",
    table_label="Order", column_label="Channel",
)
# ...
```

### Bindings table (DB)

Admin-managed via FE. Each binding row connects one eligible (table, column) to a set within a tenant. Schema in §4 above.

On every binding create/update:
- Backend validates `(table_name, column_name)` exists in `all_eligibility()`. 422 if not.
- Backend rejects if existing rows in `<table>.<column>` contain values not present (active or inactive) in the chosen set's options. Admin must reconcile data first.

## 6. Write enforcement

Two enforcement points (both read DB bindings table, cached in-process 60s):

1. **Pydantic validator helper** - `validate_lookup_value(table, column, value)` resolves binding from DB cache → loads active option values → raises `AppException` 422 if unknown.
2. **SQLAlchemy `before_insert` / `before_update` listener** - defense-in-depth on every model. Iterates bindings whose `table_name == target.__tablename__`, fetches active option values, rejects unknown writes.

Eligibility registry is consulted only at binding create/update time (not on every write). Per-write hot path reads only the bindings + options cache.

Reject payload shape:

```json
{
  "error": "invalid_lookup_value",
  "message": "'urgent!' is not a valid value for order_priority",
  "set_key": "order_priority",
  "field": "priority",
  "hint": "Call POST /api/v1/lookup/resolve to map a raw keyword."
}
```

NULL allowed iff the eligibility entry has `nullable=True` AND the underlying column is nullable. Inactive options rejected on write but kept on read (so historical rows displaying inactive value still render their label).

## 7. API surface

All under `app/api/v1/master_data/lookup_sets.py` + cross-cutting `app/api/v1/lookup.py` for resolve.

### Admin CRUD (permission: `master_data.lookup_sets.{view,create,update,delete}`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/master-data/lookup-sets` | list (DataGrid: page/limit/sort/dir/query) |
| POST | `/api/v1/master-data/lookup-sets` | create set |
| GET | `/api/v1/master-data/lookup-sets/{id}` | detail |
| PATCH | `/api/v1/master-data/lookup-sets/{id}` | update set meta |
| DELETE | `/api/v1/master-data/lookup-sets/{id}` | hard delete (cascades options + keywords) |
| GET | `/api/v1/master-data/lookup-sets/{id}/options` | list options (paginated) |
| POST | `/api/v1/master-data/lookup-sets/{id}/options` | create option |
| PATCH | `/api/v1/master-data/lookup-sets/{id}/options/{option_id}` | update option (incl. keyword set replacement) |
| DELETE | `/api/v1/master-data/lookup-sets/{id}/options/{option_id}` | delete option |
| GET | `/api/v1/master-data/lookup-sets/{id}/bindings` | list bindings using this set |
| POST | `/api/v1/master-data/lookup-sets/{id}/bindings` | bind set to (table, column) - body `{table_name, column_name}`, validated against eligibility |
| DELETE | `/api/v1/master-data/lookup-sets/{id}/bindings/{binding_id}` | unbind |
| GET | `/api/v1/master-data/lookup-eligibility` | list code-registered eligible (table, column) pairs w/ friendly labels - powers FE dropdowns. Supports `?available=true` to exclude already-bound pairs |

### Public/n8n consumption

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/lookup/{set_key}/options` | flat read: `[{value,label,keywords:[..],is_active}]` for active options. Supports `?include_inactive=true`. Cacheable. |
| POST | `/api/v1/lookup/resolve` | body: `{set_key, raw, locale?}` → `{value, label, matched_keyword, match_type, score}` or 404 if unresolved |

`match_type` ∈ `exact_value` | `exact_label` | `exact_keyword` | `normalized` | `trigram` (if pg_trgm enabled). Resolve only returns active options.

### MCP exposure

`sorento_crm_mcp` adds two read-only tools:
- `lookup_options(set_key)` → wraps GET `/lookup/{set_key}/options`
- `lookup_resolve(set_key, raw, locale?)` → wraps POST `/lookup/resolve`

Both gated by `EXTERNAL_API_KEY` per existing MCP pattern. n8n agent fetches options once per conversation, resolves in LLM, sends canonical value back through normal CRM API.

## 8. Resolve algorithm

Order of attempts (first hit wins, returns score):

1. `value` exact (**case-sensitive** - value is a canonical key) → score 1.0, type `exact_value`
2. `label` exact (case-insensitive) → 0.95, `exact_label`
3. `keyword` exact (case-insensitive, optional locale match) → 0.9, `exact_keyword`
4. Normalized (strip punctuation, collapse whitespace, lowercase) match against value/label/keywords → 0.8, `normalized`
5. (v1.1) `pg_trgm` similarity ≥ 0.6 against keywords → score = similarity, `trigram`

If none → 404 `{error: "lookup_unresolved", set_key, raw}`. n8n LLM is expected to pre-map; this is fallback for deterministic cases.

## 9. Frontend

Route: `/master-data-management/lookup-sets` (sibling to `brands`, `categories`, `units-of-measure`). Follows existing master-data folder convention.

### List page

- DataGrid columns: Set key, Name, Option count, Bindings count, Active, Actions.
- Search by set_key/name. Toolbar "Add lookup set" button → modal.
- Row actions: View, Edit, Delete (ConfirmDeleteDialog, hard delete copy).
- Standard `tableLayout: { width: 'fixed', columnsResizable: true }` per ADR.

### Create set - modal (binding-driven)

Admins do not type raw table/column names. Flow:

1. **Where will this dropdown appear?**
 - "Module / Table" select - populated from `GET /master-data/lookup-eligibility` grouped by `table_label`. Friendly label only.
 - "Field / Column" select - filtered to eligible columns of the chosen table that are not yet bound. Shows `column_label`.
 - Optional: "Skip - create unbound set" toggle (admin can bind later from detail page).
2. **Set details** (auto-prefilled, editable):
 - `set_key` suggested as `<table_name>_<column_name>` slug.
 - `name` suggested as `"{table_label} - {column_label}"`.
 - `description`, `is_active`.
3. Save → atomically creates set + first binding (unless skipped). Redirect to detail page.

### Edit set - modal

Edits set meta only (`name`, `description`, `is_active`, `set_key` rename guarded - warn if MCP/n8n callers reference it). Bindings managed on detail page, not in this modal.

### Detail page - `/master-data-management/lookup-sets/{id}`

Always renders all sections per ADR:

1. **Set info** card (name/key/description + Edit button).
2. **Options** section: DataGrid of options. Columns: value, label, sort order, active, keyword count, actions. Toolbar "Add option" → modal.
3. **Bindings** section: DataGrid of bindings. Columns: Table (friendly), Column (friendly), Actions (Unbind w/ ConfirmDeleteDialog). Toolbar "Add binding" → modal w/ same Table+Column dropdowns from create flow. Empty state: "Not yet bound to any field. Click Add binding to choose where this dropdown appears."
4. **Test resolve** card (admin convenience): text input + "Resolve" button → calls POST `/lookup/resolve`, shows match result. Helps admin validate keyword coverage.

### Option create/edit - modal

Fields: `value`, `label`, `sort_order`, `is_active`, `description`, **Keywords** (multi-input chip component, allows free text add; optional locale per chip via small select). Save replaces full keyword set for that option (idempotent).

### UI rules followed

- Hard delete + ConfirmDeleteDialog (count in bulk).
- No UUIDs displayed - surface `set_key` and option `value` as identifiers.
- All sections render with empty states.
- `extractApiError` + `buildDataGridParams` per ARCHITECTURE-RULES.

## 10. Permissions

New permission slugs (added to permission seed):

- `master_data.lookup_sets.view`
- `master_data.lookup_sets.create`
- `master_data.lookup_sets.update`
- `master_data.lookup_sets.delete`

Resolve + options public endpoints reuse `master_data.lookup_sets.view` (or `EXTERNAL_API_KEY` for MCP). No write permission needed for resolve.

## 11. Module guard

Routes mounted under existing `master_data` module key in `app/api/v1/__init__.py`. No new module entry needed.

## 12. Migration

Single Alembic migration creates four tables (`lookup_sets`, `lookup_options`, `lookup_option_keywords`, `lookup_bindings`) + indexes. No data migration (new system, coexist).

## 13. Testing

- **Unit:** eligibility registry add/duplicate/get; resolver match-type ordering; validator rejects unknown values; cascade delete; binding rejects unknown (table,column).
- **Integration:** end-to-end set+option CRUD; binding create/delete; bound write rejected w/ correct error payload; resolve happy + miss + each match_type; eligibility endpoint reflects code registry.
- **FE:** vitest for option keyword chip input; resolve test card calls correct endpoint.

## 14. Out of scope (v1)

- Hierarchical / nested options (use ProductCategory pattern if needed elsewhere).
- Embedding-based semantic resolve (pgvector). Defer; n8n LLM handles fuzzy.
- Per-option attachments / icons.
- Localized `label` per locale (only `keyword.locale` is locale-aware in v1).
- Auto-suggesting bindings from existing string columns (admin must opt in via FE).
- Editing eligibility from FE (devs only via code).

## 15. Open questions

- Cache strategy for option lookups in validator hot path: in-process LRU vs Redis. Default to in-process LRU 60s; revisit if multi-process consistency bites.
- Should `set_key` be globally unique (ignoring tenant) for simpler MCP URLs? Decision: keep tenant-scoped uniqueness; MCP infers tenant from API key act-as user.
