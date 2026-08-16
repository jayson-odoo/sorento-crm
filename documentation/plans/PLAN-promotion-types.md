# PLAN — Maintainable promotion types with per-type expired-promo behaviour

**Status:** built and fully verified — pytest + vitest + MCP suites green, live MCP and
resolve checks green (rerun post-reboot 2026-08-15), and browser verification of the
admin screens complete on a prod build (see the UAC verification log). Awaiting review.

**Process deviation, called out deliberately:** the Phase-1 "FE prototype against mock
data, signed off before any backend" step was collapsed into Phase 2. The two screens
this feature adds are a standard list + modal and one extra field on an existing form,
both straight off ADR-PRODUCT-STANDARDS with no new interaction to discover; the risk in
this piece of work is entirely in the serving semantics, which a mock cannot exercise.
The FE was therefore built against the documented contract in section 3 and covered by
component tests for the loading / empty / error / data states the prototype step exists to
settle. Anything genuinely uncertain about the UX is still open to change - the contract
is in this document, not in the components.
**UAC:** `documentation/plans/UAC-promotion-types.md` (Journey + acceptance criteria)
**Branch:** `fm/promo-type-model`

---

## 1. What exists today (and why it fails)

- `promotions` has no name, no kind, no linkage — `description` holds the uploaded PDF's
  filename (`app/models/marketing.py:26-67`).
- "Live" is defined once, in `app/services/promotion_window.py` (`is_live` + `live_clause`).
  `_promotion_is_expired` (`marketing_service.py:73`) is its negation and stamps `is_expired`.
- `list_promotions` (`marketing_service.py:513`) is active-first with a *fallback to all
  inactive* when a narrowing filter matched zero active rows.
- The resolver's reverse walk `_build_promotions_for_products`
  (`app/api/v1/system/references.py:546`) returns every promotion containing the product,
  active and expired mixed, with `display.is_active` read straight off the raw column.
- Failure (SRTWC286): the A3 flyer is live, so the active gate answers with the flyer and the
  just-ended WC promo — the thing actually asked about — is filtered out silently.

Root cause: one global active/expired rule for populations that have different commercial
rules after the end date.

## 2. Data model

### `promotion_types` (new, `app/models/marketing.py`)

| column | type | notes |
|---|---|---|
| `id` | UUID pk | |
| `type_code` | String(50) unique not null | `special`, `pp`, `focus_item`, `a3_flyer`, `standard` |
| `type_name` | String(150) not null | shown in the UI (never the UUID) |
| `description` | Text null | |
| `show_expired` | Boolean not null default false | the captain's MCP toggle |
| `expired_valid_until_year_end` | Boolean not null default false | usable while `end_date.year == today.year` |
| `expired_max_age_days` | Integer null | usable while `end_date >= today - N days` |
| `match_markers` | JSONB not null default `[]` | lowercase marker phrases for auto-classification |
| `match_priority` | Integer not null default 100 | ascending; first match wins |
| `is_default` | Boolean not null default false | exactly one row; policy for unclassified promotions |
| `sort_order` | Integer not null default 0 | list ordering |
| `created_at` / `updated_at` | timestamps | |

`CompanyScopedMixin`, like `campaign_types`. Bounds AND together when both are set; neither set
+ `show_expired` = unbounded.

### `promotions` additions

- `promotion_type_id` UUID FK → `promotion_types.id` `ON DELETE SET NULL`, nullable, indexed.
- `promotion_type_source` String(10) nullable — `auto` | `manual`.

### Migration

One revision on the current single head. Follow the authoritative Alembic pre-merge guard in
`PRINCIPLES.md`:

1. `create_table promotion_types` + unique index on `type_code` + partial unique index on
   `is_default WHERE is_default` (one default, enforced by the DB).
2. `add_column promotions.promotion_type_id` / `promotion_type_source` + index.
3. Seed the five rows (idempotent: `INSERT ... WHERE NOT EXISTS` on `type_code`).
4. Backfill: classify every existing promotion from its `description`, stamping `auto`.
   JOIN-based and re-runnable (house rule: idempotent "set to the correct value where
   mismatch", never "update where NULL").

`downgrade` drops the columns then the table.

## 3. Backend modules

### `app/services/promotion_classifier.py` (new)

```
classify_promotion_type(db, *, description, filename=None) -> PromotionType | None
```

- Candidate text = `filename or description` (n8n posts the filename as the description;
  the linked attachment's `original_filename` is preferred when present because the upload
  path sanitises `@ ( ) , &` out of the stored name).
- Normalise: uppercase, non-alphanumerics → single spaces.
- Iterate types ordered by `match_priority`, `type_code`; a type matches when any marker
  matches on **word boundaries** (`\bPP\b`, multi-word markers matched as a token sequence).
- No marker match → the `is_default` type. No types at all → `None`.
- Markers are read from the DB (UAC C6), cached per-request only.

### `app/services/promotion_serving.py` (new — the one definition, per Q3 precedent)

```
servable_promotion_ids(db, candidate_ids, today) -> ServingVerdict
  .served_ids: set[str]
  .expired_but_usable_ids: set[str]
  .type_by_promotion: dict[str, PromotionType|None]
```

Algorithm over the candidate set (the promotions the caller's filters already narrowed to):

1. Partition by live (`promotion_window.is_live`) vs expired.
2. Every live row is served.
3. Group expired rows by resolved type (NULL → the `is_default` type).
4. Skip a type that has a live row in the candidate set (per-type suppression, UAC D4/S5).
5. Skip a type with `show_expired = false` (special, UAC S3).
6. Drop rows failing the type's bounds (year-end and/or max-age, ANDed).
7. Order the remainder `end_date DESC, created_at DESC`; take the top row, plus any exact
   `end_date` tie, capped at 2 per type; mark them `expired_but_usable`.

Rows with no `end_date` are, by definition of `is_live`, live — so they never reach step 3.

The helper is import-free of `marketing_service` / `references` so both can use it without a
cycle (same discipline as `promotion_window`).

### `/api/v1/marketing/promotions` (E1)

- New query param `serving_policy: bool = False`.
- When true: skip the active gate and the inactive fallback; collect candidate ids from the
  filtered query (capped at 500 rows, logged when the cap bites — no silent truncation), run
  the helper, filter to `served_ids`, then paginate. Payload gains
  `serving_policy_applied: true`; `fallback_used` stays `false`.
- Response rows gain `promotion_type_id`, `promotion_type_code`, `promotion_type_name`,
  `expired_but_usable` (`PromotionListItemResponse`, plus `PromotionResponse` for detail).
- When false: untouched (UAC N1).

Same treatment for `list_promotion_products` and `list_promotion_attachments`: compute the
servable **parent** promotion id set from the same helper and filter on it.

### `/api/v1/system/references` resolve (E3)

`_build_promotions_for_products` runs the helper over the promotions it found (after the
access-level intersection) and drops non-served rows. `display` gains `start_date`, `end_date`,
`is_expired` (live definition — fixes today's raw `is_active` read), `promotion_type_code`,
`promotion_type_name`, `expired_but_usable`. Existing keys unchanged: the n8n gate only reads
`{uuid, entity_type, canonical_code}`, so the wire contract survives.

### `/api/v1/external/promotions/` (C1-C5)

After the promotion row is built, stamp `promotion_type_id` from the classifier with
`promotion_type_source = "auto"` — except on the update-in-place path when the existing row is
`manual`, which is left alone (C5). The create response echoes the type code + source.

### `promotion_types` CRUD

`app/api/v1/marketing/promotion_types.py` + `PromotionTypeService` in `marketing_service.py`,
mirroring `campaign_types.py` (list / get / create / update / delete). Mounted in
`app/api/v1/marketing/__init__.py` at `/promotion-types`. Delete is a hard delete; deleting the
`is_default` row → 409. Duplicate `type_code` → 409.

## 4. Frontend

Phase 1 is a mock-data prototype of both screens; Phase 2 wires them to the real API.

- **`/marketing-management/promotion-types`** — `page.tsx` + `components/PromotionTypesList.tsx`
  (shared DataGrid, `tableLayout: { width: 'fixed', columnsResizable: true }`,
  `columnResizeMode: 'onChange'`, explicit `size`, truncate + title),
  `PromotionTypeFormModal.tsx`, `ConfirmDeleteDialog`, `services/promotionTypeService.ts`
  (via `lib/api-client`, `extractApiError`, `buildDataGridParams`),
  `hooks/usePromotionTypes.ts` (shared `useCreateMutation` / `useUpdateMutation` /
  `useDeleteMutation`).
- **Menu**: a "Promotion Types" entry under Marketing Management → Promotions in
  `config/menu.config.tsx` (both nav blocks — the file carries two copies).
- **Promotions list**: a Type column rendering `promotion_type_name` (never the id).
- **Promotion form / detail**: a clearable `SearchableSelect` for the type, in the same
  position on both views (view-and-edit-are-the-same-layout rule), with the
  "Unclassified — treated as Standard" empty state on the detail.

## 5. MCP (E2)

- `crm_marketing_promotions_list`: pin `serving_policy=true` via `TOOL_DEFAULT_QUERY_PARAMS`
  (the `crm_resource_attachments_catalogue` hard-pin precedent) — deliberately NOT in
  `query_params`, so the agent cannot switch the policy off. Same pin for
  `crm_marketing_promotion_products_list` and `crm_marketing_promotion_attachments_list`.
- Descriptions updated: when `expired_but_usable` is true, say the promotion **has expired but
  still applies** (and give the end date); when a row is merely `is_expired`, the existing
  "found but expired" wording stands.
- **Restart the MCP process** after the catalog change — FastMCP registers tools at startup
  (CLAUDE.md gotcha).

## 6. Tests

**pytest** (`sorento_crm_backend/tests/`, Postgres only, every test seeds its own chain with a
marker prefix — never `LIMIT 1` off an existing table):

- `test_promotion_classifier.py` — C1-C6.
- `test_promotion_serving_policy.py` — S1-S6 against the helper.
- `test_promotions_serving_policy_endpoint.py` — E1, N1.
- `test_references_promotion_serving.py` — E3, plus E4 (both surfaces agree on one fixture).
- `test_promotion_types_crud.py` — T1, T5, T6.
- `test_external_promotion_type_classification.py` — C1, C5.

**vitest** (`sorento_crm_frontend/`): `PromotionTypesList` (loading / empty / error / data),
`PromotionTypeFormModal` (validation, submit, delete confirmation copy), the promotions list
Type column, the promotion form's type select. `useListingColumnPreferences` mocked so
DataGrid rows mount.

**MCP** (`sorento_crm_mcp/tests/`): the pinned `serving_policy` default reaches the outbound
query for all three tools.

**Live check (E5, mandatory):** backend :8000 + MCP :8765 against the local prod-copy DB, with
this feature's own seeded promotions (never touching other rows) — one MCP call proving an
expired-but-usable row is served with `expired_but_usable: true`, one proving an expired
`special` is not. Transcript into the UAC verification log.

## 7. Order of work

1. UAC + PLAN (this document). ✔
2. FE prototype of both screens against mock fixtures; document the API contract.
3. Migration + models + classifier + serving helper + CRUD + endpoint wiring.
4. FE off mocks; MCP catalog + restart.
5. pytest / vitest / live MCP proof; verification log.
6. `/no-mistakes` (firstmate drives the gates).

## 8. Risks

- **Migration graph drift** - follow the authoritative Alembic pre-merge guard in
  `PRINCIPLES.md`.
- **Candidate-set cap** — the serving policy is a Python post-pass; bounded at 500 candidate
  rows with a log line when it bites, never a silent truncation.
- **Marker collisions** — resolved conservatively by `match_priority` (special first), and
  fixable as data.
- **Shared prod-copy DB** — only this feature's own seeded rows are written; the migration is
  the only schema change applied.
