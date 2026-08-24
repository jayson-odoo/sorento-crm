# PLAN - Manual variant link/unlink curation + products-list variant filter/count

**Status:** DRAFT (pre-code) - Phase 1 not started. Update this line as phases land (`Phase 1 in progress` → `Phase 1 done / awaiting sign-off` → `Phase 2 in progress` → `Phase 2 done, tests green` → `Phase 3 review` → `Merged`).

**Owner:** TBD  **Branch:** `feat/variant-manual-curation`
**Related:** `documentation/plans/PLAN-suggest-on-miss-variant-graph.md` (the auto-derivation this layers manual overrides on top of).

---

## 1. Goal & scope

Add **manual curation** on top of the existing auto-derived variant graph (`products.variant_of_id` self-FK), plus a **products-list variant filter and "Variant of" column / child count**.

Two user-facing capabilities:

1. On a product detail page's **Variants tab**: set/change parent, unlink from parent, attach a child, remove a child, and reset a manually-curated row back to auto - with a **Manual** badge when the link is hand-curated.
2. On the **products list**: a Base / Variant / All filter, a human-readable "Variant of" (parent code) column, and a per-row variant (child) count.

This is a **curate-by-hand** feature: we ship the UI and do **not** run the auto-backfill on prod as part of this work.

### Locked decisions (do NOT re-open)

- **D1 - Manual wins, sticky.** New column `products.variant_link_manual boolean not null default false`. When `true`:
  - `reconcile_variant_links` must **not** re-derive that row's own parent.
  - `_adopt_orphans` must **not** steal a manually-linked child away.
  - the backfill script must **skip** manual rows entirely (never overwrite).
  - "Reset to auto" clears the flag and re-runs reconcile for that row.
- **D2 - Ship UI first, curate by hand.** Do **not** run `scripts/backfill_variant_links.py` on prod in this work. The coverage-ratio floor fix to the derivation is **out of scope** (see §11).

---

## 2. Grounding - real code the plan touches

Backend:
- Derivation service - `sorento_crm_backend/app/services/variant_link_service.py`
  - `reconcile_variant_links` (`:140`), `_derive_parent_id` (`:73`), `_adopt_orphans` (`:103`), `child_ids_of` (`:178`), `normalize_code`/`boundary_ok`.
- Product model - `sorento_crm_backend/app/models/product.py:93` (`variant_of_id` at `:110`, indexes at `:171`).
- Product service - `sorento_crm_backend/app/services/product_service.py`
  - `_populate_variant_graph` (`:597`), reconcile call sites: create `:719`, update-on-code-change `:765-773`, delete `:777-787`, wrapper `_reconcile_variant_links` (`:789`), `list_products` (`:394`), `_build_list_query` (called `:450`).
- Product schemas - `sorento_crm_backend/app/schemas/product.py`: `ProductVariantRef` (`:249`), `ProductResponse` (`:273`, variant fields `:282-284`).
- Product router - `sorento_crm_backend/app/api/v1/master_data/products.py`: list GET (`:60`), detail GET (`:233`), PUT (`:267`), DELETE (`:362`). Mounted under `/api/v1/master_data/products` (FE hits `/api/v1/master-data/products`; `lib/api.ts` rewrites the hyphen form).
- Product select - `sorento_crm_backend/app/api/v1/master_data/products_select.py` `GET /select` (reuse for the parent combobox).
- List registry - `sorento_crm_backend/app/services/list_query_registry.py`: `products` adapter (`:79`), `_serialize_products` (`:32`). **No structural change needed** (see §7).
- Backfill - `sorento_crm_backend/scripts/backfill_variant_links.py` (`derive_parents` `:35`, `main` `:67`).
- Migration head confirmed via `alembic heads` = **`267_health_alert_state_and_tasks`**. New migration = **`268_variant_link_manual`**, `down_revision = "267_health_alert_state_and_tasks"`.

Frontend (`sorento_crm_frontend/app/(protected)/master-data-management/products/`):
- Variants tab (read-only today) - `[id]/components/ProductVariantsTab.tsx` (+ existing test `ProductVariantsTab.test.tsx`). Fed from `[id]/components/ProductDetail.tsx:376-379` (`variantOf={product.variant_of}`, `variants={product.variants}`).
- Feature service - `services/productService.ts` (note: hand-rolls `response.json().catch(...)` - **pre-existing** debt; new functions MUST use `extractApiError`).
- Hooks - `hooks/useProducts.ts` (raw react-query `useMutation` + `invalidateQueries(['products'])` / `['product', id]` + `toast`; there is **no** shared `useUpdateMutation` symbol in this repo - this file IS the pattern).
- List - `components/ProductsList.tsx` (columns are FE-defined; already has a `variant_type` badge column at `:405`, `tableLayout`/`columnResizeMode` at `:642`). Filters hook `hooks/useProductFilters.ts`.
- Types - `types/product.types.ts` (`ProductVariantRef` `:15`, `Product.variant_of/variants` `:53-57`, `ProductListItem.is_variant` `:315`).

---

## 3. Data model + migration

**Migration `268_variant_link_manual`** (`down_revision = "267_health_alert_state_and_tasks"`):

```python
op.add_column(
    "products",
    sa.Column("variant_link_manual", sa.Boolean(), nullable=False, server_default=sa.text("false")),
)
# Partial index - manual rows are the set reconcile/backfill must skip; keeps the
# "skip manual" scans cheap on a large products table.
op.create_index(
    "ix_products_variant_link_manual",
    "products",
    ["variant_link_manual"],
    postgresql_where=sa.text("variant_link_manual = true"),
)
```
`downgrade` drops the index then the column. Keep the `server_default` on the column (existing rows backfill to `false`); it is safe to leave in place.

**Model** - add to `Product` (`app/models/product.py`), next to `variant_of_id`:
```python
variant_link_manual = Column(Boolean, nullable=False, server_default="false", default=False)
```
and add `Index("ix_products_variant_link_manual", "variant_link_manual", postgresql_where=text("variant_link_manual = true"))` to `__table_args__` (import `text`).

**Schema** - add to `ProductResponse` (`app/schemas/product.py`): `variant_link_manual: bool = False`. (Detail page reads it for the Manual badge + Reset button. Cheap on list rows - plain column.) No new field on `ProductVariantRef`.

---

## 4. API contract (authoritative - Phase 1 builds the FE against exactly this)

All under `/api/v1/master_data/products` (FE: `/api/v1/master-data/products`). Auth: same `Depends(get_current_user)` + module guard as the existing write routes (`create`/`update`/`delete` use an authenticated principal - variant curation is a write, so require the **JWT user**, not read-only api-key; match the PUT at `products.py:267`). Errors flow through `AppException` → global handler → `{ "detail": "<message>" }` (string), consumable by `extractApiError`.

`product_id` in the path accepts a **UUID or product_code** (resolved via `resolve_identifier`, same as `get_product`). The `parent_id` in the body likewise accepts UUID or code.

### 4.1 Set / change parent

```
PUT /api/v1/master-data/products/{product_id}/variant-parent
Body: { "parent_id": "<uuid | product_code>" }
```
Effect: `variant_of_id = <resolved parent>`, `variant_link_manual = true`, `updated_by`/`updated_at` stamped. Commits, then re-populates the variant graph.

- **200** → full `ProductResponse` for `{product_id}` (includes `variant_of`, `variants`, `is_variant`, `variant_link_manual: true`).
- **400** `parent_id is required` - missing/blank body.
- **400** `A product cannot be a variant of itself` - resolved parent == product.
- **400** `Cannot set parent: this would create a variant cycle` - resolved parent is `product` itself or any **descendant** of `product` (walk ancestors of the chosen parent via `variant_of_id`; reject if `product.id` is encountered).
- **404** `Product not found` - `{product_id}` unknown.
- **404** `Parent product not found` - `parent_id` resolves to nothing.

**Attach-a-child reuses this endpoint**: "Add variant" on parent P calls `PUT /{childId}/variant-parent` with `parent_id = P`. No separate endpoint.

### 4.2 Unlink from parent

```
DELETE /api/v1/master-data/products/{product_id}/variant-parent
```
Effect: `variant_of_id = null`, `variant_link_manual = true` (so auto-reconcile will not re-link it), stamp `updated_by`/`updated_at`, commit, re-populate.

- **200** → full `ProductResponse` (`variant_of: null`, `is_variant: false`, `variant_link_manual: true`).
- **404** `Product not found`.

**Remove-a-child reuses this endpoint**: "Remove variant" on child C calls `DELETE /{C}/variant-parent`.

### 4.3 Reset to auto

```
POST /api/v1/master-data/products/{product_id}/variant-reset
```
Effect: `variant_link_manual = false`, then `reconcile_variant_links(db, product_id)` re-derives this row's parent **and** adopts its orphans. Commit is owned by reconcile; re-populate after.

- **200** → full `ProductResponse` (auto-derived `variant_of`, `variant_link_manual: false`).
- **404** `Product not found`.

### 4.4 List additions

`GET /api/v1/master-data/products` gains:
```
&variant_filter=base|variant|all   (default: all)
```
- `base` → `variant_of_id IS NULL`
- `variant` → `variant_of_id IS NOT NULL`
- `all` / omitted → no filter.

Each list row's `ProductResponse` additionally carries (see §7 for how they're populated without N+1):
- `variant_of` - `{ id, product_code, product_name }` of the parent, or `null` (human-readable "Variant of" column).
- `variant_child_count: int` - number of direct children (default `0`).
- `is_variant` - unchanged (already emitted).
- `variant_link_manual` - unchanged plain column.

---

## 5. Backend service changes

### 5.1 `variant_link_service.py` - respect the manual flag (D1)

- `reconcile_variant_links` (`:140`): after loading `product`, **guard self-derivation**:
  ```python
  if not getattr(product, "variant_link_manual", False):
      derived_parent = _derive_parent_id(db, product.id, product.product_code)
      self_changed = product.variant_of_id != derived_parent
      if self_changed:
          product.variant_of_id = derived_parent
  else:
      derived_parent, self_changed = product.variant_of_id, False
  ```
  Still call `_adopt_orphans(db, product)` - a manual row remains a legitimate parent for auto children. (The `product` fetched at `:157` is an ORM `Product`, so `variant_link_manual` is available.)
- `_adopt_orphans` (`:103`): exclude manually-linked children from adoption. Add `AND variant_link_manual = false` to the candidate SELECT (`:116`) so a hand-linked child is never re-pointed:
  ```sql
  ... AND left({n_norm}, :nlen) = :norm_me
      AND variant_link_manual = false
  ```
- `_derive_parent_id` unchanged (manual rows may still be candidate *parents*).

### 5.2 `product_service.py` - new methods + re-populate on write

Add three service methods (mirror `_populate_variant_graph` after mutating, return the ORM product so the route serializes with `variant_of`/`variants`):

- `set_variant_parent(product_id, parent_id, updated_by)`:
  1. `product = self.get_product(product_id)` (404 if missing).
  2. resolve `parent_id` via `resolve_identifier(... Product, code_fields=("product_code",))`; 404 `Parent product not found` if empty; load the parent row.
  3. `parent.id == product.id` → 400 self-parent.
  4. cycle check - walk ancestors of `parent` following `variant_of_id` (bounded loop, guard against pre-existing cycles with a visited-set); if `product.id` seen → 400 cycle.
  5. set `variant_of_id`, `variant_link_manual = True`, `updated_by`, `updated_at`; commit; `_populate_variant_graph(product)`; return.
- `unlink_variant(product_id, updated_by)`: set `variant_of_id = None`, `variant_link_manual = True`, stamp, commit, re-populate, return.
- `reset_variant_auto(product_id)`: set `variant_link_manual = False`, flush; `reconcile_variant_links(self.db, product.id)`; `self.db.refresh(product)`; `_populate_variant_graph(product)`; return.

**Do not** raise from post-commit reconcile in reset - reuse the best-effort `_reconcile_variant_links` wrapper semantics only where a side effect runs after commit; here reset's reconcile IS the operation, so surface its result but keep the existing "never 500 a succeeded op" posture (reconcile already commits its own unit of work and returns a dict).

Existing create/update/delete reconcile call sites (`:719`, `:765-773`, `:777-787`) need **no change** - they route through `reconcile_variant_links`, which now respects the manual guard automatically.

### 5.3 List query - `variant_filter` + parent ref + child count

- `products.py` GET (`:60`): add `variant_filter: Optional[str] = Query("all", pattern="^(base|variant|all)$")`; thread into `service.list_products(...)`.
- `list_products` (`:394`) + `_build_list_query`: add `variant_filter` param; apply `Product.variant_of_id.is_(None)` (base) / `.isnot(None)` (variant).
- Populate list-row variant fields **without N+1**, mirroring `_populate_field_attachments` (`list_products:501`). After the page `products` are fetched, run two small queries:
  1. parent refs: `SELECT id, product_code, product_name FROM products WHERE id IN (:page_variant_of_ids)` → stash `p._variant_of_ref` per row (reuses the existing `ProductResponse.variant_of` alias - human-readable, no UUID in UI).
  2. child counts: `SELECT variant_of_id, count(*) FROM products WHERE variant_of_id IN (:page_ids) GROUP BY variant_of_id` → stash `p._variant_child_count`.
  Add `variant_child_count: int = Field(default=0, validation_alias="_variant_child_count")` to `ProductResponse`. (Detail getter `_populate_variant_graph` can also set `_variant_child_count = len(children)` for symmetry.)

This keeps LIST rows free of per-row lazy loads (two bounded queries per page), consistent with the existing "no N+1 on list" design note at `schemas/product.py:276-281`.

---

## 6. Frontend changes

### 6.1 Types (`types/product.types.ts`)
- `Product`: add `variant_link_manual?: boolean;` and `variant_child_count?: number;`.
- `ProductListItem`: add `variant_of?: ProductVariantRef | null;` and `variant_child_count?: number;` (for the "Variant of" column + count).

### 6.2 Feature service (`services/productService.ts`) - new functions, `extractApiError`
Add (new code follows ARCHITECTURE-RULES - use `extractApiError`, not the hand-rolled `.catch`):
- `setVariantParent(productId, parentId): Promise<ProductDetail>` → `PUT .../{productId}/variant-parent`.
- `unlinkVariant(productId): Promise<ProductDetail>` → `DELETE .../{productId}/variant-parent`.
- `resetVariantAuto(productId): Promise<ProductDetail>` → `POST .../{productId}/variant-reset`.
- Parent combobox source: add `getProductsForVariantSelect(query): Promise<ProductVariantRef[]>` hitting the existing `GET /api/v1/master-data/products/select` (map to `{id, product_code, product_name}`); the component filters out the current product client-side (server still enforces self/cycle).
- `getProducts` (`:50`): add `variant_filter?: 'base' | 'variant' | 'all'` to `GetProductsParams` and append `...(variant_filter && variant_filter !== 'all' ? { variant_filter } : {})` to `queryParams` (same shape as the sibling `category_id`/`status` params - do not rewrite the whole function to `buildDataGridParams`; that pre-existing deviation is out of scope, see §11).

### 6.3 Hooks (`hooks/useProducts.ts`) - three mutation hooks
Mirror the existing `useUpdateProduct` pattern (raw `useMutation` + `queryClient.invalidateQueries` + `toast`):
- `useSetVariantParent()` → `mutationFn: ({ productId, parentId }) => setVariantParent(...)`; onSuccess invalidate `['product', productId]` **and** `['products']`, toast "Variant parent updated".
- `useUnlinkVariant()` → invalidate `['product', productId]` + `['products']`, toast "Variant unlinked".
- `useResetVariantAuto()` → invalidate `['product', productId]` + `['products']`, toast "Reset to auto-linking".
- For **attach/remove child** the same hooks are reused with the **child's** id, and onSuccess must also invalidate the **parent's** `['product', parentId]` so the parent detail's Variants list refreshes. (Pass both ids through the mutation variables.)
- onError: `toast.error(error.message ...)` (message already extracted in the service via `extractApiError`).

### 6.4 Variants tab (`[id]/components/ProductVariantsTab.tsx`)
Extend the existing read-only tab (keep the prefix-dimming `renderCode`). New props: `productId: string`, `variantLinkManual?: boolean`. New UI, all **mobile-first** (modals `max-h` + `overflow-y-auto` per the shared dialog; buttons `flex-wrap`):
- **Manual badge**: when `variantLinkManual`, render a `Badge` "Manual" next to the "Variant of" heading; when auto, no badge.
- **Set / Change parent**: button opens a modal with a **product search combobox** (resolves to `product_code - product_name`, **never a raw UUID**; excludes self). Confirm → `useSetVariantParent`. Show inline validation errors (self/cycle) surfaced from the 400 toast.
- **Unlink** (shown when `variantOf` exists): `AlertDialog` confirm ("Unlink from parent?" / "This product will no longer be a variant of {parentCode}. You can re-link it later.") - **confirm before unlink**, per the "confirm before delete OR unlink" rule. Destructive-styled confirm button.
- **Add variant** (attach a child): button → modal with the same combobox (pick a child, excludes self + current children) → `useSetVariantParent({ productId: childId, parentId: currentId })`.
- **Remove variant** per child row: an icon button → `AlertDialog` confirm ("Remove variant?" / "{childCode} will no longer be a variant of this product.") → `useUnlinkVariant({ productId: childId, parentId: currentId })`.
- **Reset to auto** (shown only when `variantLinkManual`): button → `AlertDialog` confirm ("Reset to automatic linking?" / "This clears the manual override and re-derives the variant link from the product code.") → `useResetVariantAuto`.
- Empty states preserved (base product line; "No variants of this product") with the new "Add variant" CTA in the empty state (per empty-state standard).
- Wire in `ProductDetail.tsx:376` - pass `productId={product.id}` and `variantLinkManual={product.variant_link_manual}`.

### 6.5 Products list (`components/ProductsList.tsx` + `hooks/useProductFilters.ts`)
- **Base / Variant / All filter**: a segmented control / select in the toolbar; state lives in `useProductFilters` (or local like `selectedCategory`); passed as `variant_filter` into `getProducts` params and into the `useProducts` **query key** (add it to the key array at `hooks/useProducts.ts:41` so refetch triggers).
- **"Variant of" column**: new column `id: 'variant_of'` rendering `row.variant_of?.product_code` (human-readable) with `truncate` + `title="{code} - {name}"`, explicit `size` (~160), empty state "-" for bases. Keep the existing `variant_type` badge column.
- **Variant count**: render `variant_child_count` - either as a small column (`id: 'variant_child_count'`, size ~90, right-aligned) or appended to the `variant_type` badge (e.g. "Base · 4"). Pick the dedicated column for sortability/clarity.
- Respect ARCHITECTURE-RULES: every new column has explicit `size`; `tableLayout`/`columnResizeMode` already set at `:642`. New column ids are stable so column personalization keeps working.

---

## 7. list_query_registry / RBAC / other cross-cutting

- **list_query_registry**: **no structural change.** The products list data is served by `products.py` GET (not the list-query endpoint); `variant_filter` is a first-class query param like `status`. The registry `products` adapter (`:79`) is used for column-config personalization + export metadata only; the new columns are FE-defined, so personalization keeps working via their stable `id`s. (If a future need arises to expose `variant_filter` in the advanced-filter builder, that's a separate registry `compile_prefix` field - out of scope here.)
- **RBAC / module guard**: no new permission slug. Variant curation is a product **write** - gate the three endpoints with the same `master_data` module guard + authenticated-user dependency the existing PUT/DELETE use. Anonymous / read-only api-key principal → the standard 401/403 (covered by an auth-denial test per endpoint).
- **Embedding pipeline**: variant link is a relational edge, not embedded text. `variant_of_id`/`variant_link_manual` are **not** in the embedded field set - do **not** add them to `publish_embedding_event` changed_fields. No embedding impact.
- **Worker / RQ**: none. All operations are synchronous request-path writes.
- **Audit**: `Product.__audit_track__ = True` - `variant_of_id` and the new `variant_link_manual` column changes are auto-audited by the existing listener. No extra work; note it so reviewers expect audit rows on link/unlink/reset.
- **Backfill script** (`scripts/backfill_variant_links.py`): make it skip manual rows. `main` already selects `variant_of_id` (`:75`) - also select `variant_link_manual`, and exclude manual ids from the computed `changes` dict (`:81`) so a re-run never overwrites a hand-curated row. Manual rows still participate as candidate **parents** in `derive_parents`' index (they exist), just never get their own value changed. Per **D2 this script is NOT run on prod in this work** - the guard is a correctness fix for when it eventually is.

---

## 8. Three-phase breakdown (CLAUDE.md methodology)

### Phase 1 - FE prototype against mocks (no backend)
- Build the extended `ProductVariantsTab` + list filter/columns against **mock fixtures** and stubbed hooks returning synthetic `ProductDetail` (base / variant-with-parent / manual-badge cases) and list rows (with `variant_of` + `variant_child_count`).
- Stub the three mutation hooks to resolve/reject synthetically to exercise success + validation-error (self/cycle) + confirm-dialog flows.
- Verify via Playwright MCP: **navigate through the sidebar** (Master Data → Products → open a product → Variants tab); screenshot golden path + every state (base, variant, manual, unlink confirm, add/remove child, reset confirm) and the list filter.
- Output: this contract (§4) is the signed-off shape. **No backend code, no tests yet.**

### Phase 2 - BE wiring + FE off-mocks + tests (all three suites land here)
- BE: migration `268_variant_link_manual`; model + schema fields; `variant_link_service` manual guards; three `ProductService` methods + three routes; `variant_filter` + list variant fields; backfill skip.
- FE: replace mocks with real service/hooks/api-client; delete mock fixtures (keep any reused by tests).
- Tests (see §9). Re-verify with Playwright MCP against the live stack (`:3000`+`:8000`).

### Phase 3 - Code review
- `/code-review` on the combined diff; address findings; confirm the PR description carries the Phase 1 screenshots, the three test suites, and that shipped == contract (§4).

---

## 9. Tests (Phase 2)

**pytest** (`sorento_crm_backend/tests/`) - one endpoint file for the three routes:
- Set-parent: happy path (sets `variant_of_id` + `variant_link_manual=true`); auth denial (401/403); validation - missing `parent_id` (400), self-parent (400), **cycle** (400: A→B then attempt B→A / A as descendant), missing parent (404), missing product (404).
- Unlink: happy path (nulls parent, sets manual=true); auth denial; missing product (404).
- Reset: happy path (clears manual, re-derives via reconcile); auth denial; missing product (404).
- Service tests (`variant_link_service`): (a) `reconcile_variant_links` does **not** re-derive a `variant_link_manual=true` row's own parent but still adopts its orphans; (b) `_adopt_orphans` does **not** steal a manually-linked child; (c) backfill `main`/`derive_parents` skips manual rows (no overwrite on re-run). Use the sqlite-fixture caveats from CLAUDE.md (pg `UUID` ok; ensure `variant_link_manual` in DDL; listener tables).
- List: `variant_filter=base|variant|all` returns the right set; a row exposes `variant_of` + `variant_child_count`.

**vitest** (`sorento_crm_frontend/`) - extend `ProductVariantsTab.test.tsx` + new hook/list tests:
- Tab states: base (no parent, "Add variant" CTA), variant-with-parent (Unlink shown), **Manual badge** present when `variantLinkManual`, Reset button visibility.
- Actions fire the right hook: set-parent modal → `setVariantParent`; unlink `AlertDialog` confirm → `unlinkVariant`; add-child → `setVariantParent(childId, parentId)`; remove-child confirm → `unlinkVariant(childId)`; reset confirm → `resetVariantAuto`.
- Confirm dialogs render standard copy and require confirmation (no one-click destructive/unlink).
- No raw UUID rendered in the combobox or "Variant of" column.
- List: `variant_filter` control changes the query param / triggers refetch; "Variant of" column renders parent code; count renders.
- Guard `scrollIntoView` per the jsdom caveat if the combobox uses it.

**Playwright** (`sorento_crm_frontend/e2e/`) - one spec, sidebar-driven:
- Master Data → Products → open a product → Variants tab → set a parent (assert it renders + Manual badge) → unlink with confirm (assert gone) → reset-to-auto → assert the expected `/api/v1/master-data/products/{id}/variant-parent` (PUT/DELETE) and `.../variant-reset` (POST) calls via `browser_network_requests`. Exercise the list Base/Variant filter and assert the `variant_filter` query param on the products GET.

---

## 10. UAC checklist (self-verify FE **and** BE against every line before handoff)

Data / migration:
- [ ] BE: `alembic upgrade head` applies `268_variant_link_manual`; `products.variant_link_manual` exists, default `false`, existing rows `false`; partial index present. `alembic downgrade -1` clean.
- [ ] BE: `variant_link_manual` appears in `ProductResponse` (detail GET + list rows).

Manual override (D1):
- [ ] BE: set-parent sets `variant_of_id` + `variant_link_manual=true`; a subsequent `product_code` edit does **not** re-derive the parent (sticky).
- [ ] BE: `reconcile_variant_links` on a manual row leaves its parent untouched but still adopts auto orphans.
- [ ] BE: `_adopt_orphans` does not re-point a `variant_link_manual=true` child.
- [ ] BE: backfill dry-run/apply reports **0** changes for manual rows; a re-run never overwrites them.
- [ ] BE: reset clears `variant_link_manual` and re-derives via reconcile.

Endpoints & validation (§4):
- [ ] BE: set-parent rejects self (400), cycle (400), missing parent (404), missing product (404), missing body (400); accepts UUID or code for both ids.
- [ ] BE: unlink nulls parent + sets manual; reset returns auto-derived parent.
- [ ] BE: all three deny unauthenticated / read-only principal.
- [ ] FE: each success invalidates `['product', id]` + `['products']` (and parent's `['product', parentId]` for child ops) and toasts; each error toasts the extracted message.

Variants tab UX:
- [ ] FE: Manual badge shows iff `variant_link_manual`; Reset button shows only when manual.
- [ ] FE: Set/Change parent combobox shows human-readable `code - name`, **never a UUID**, excludes self.
- [ ] FE: Unlink and Remove-variant require an `AlertDialog` confirm (not one-click, not `window.confirm`); Reset requires confirm.
- [ ] FE: Add-variant attaches a child (calls set-parent with child id); Remove-variant detaches it.
- [ ] FE: all sections render with empty states (base line, "No variants" + Add CTA); works at ~375px width; modals scroll to the confirm button.

List:
- [ ] FE: Base/Variant/All filter sends `variant_filter` and refetches (in query key); default All.
- [ ] BE: `variant_filter` filters correctly; rows carry `variant_of` + `variant_child_count`.
- [ ] FE: "Variant of" column shows parent code (human-readable, truncate+title, explicit size); count renders; column personalization unbroken.

Cross-cutting:
- [ ] Audit rows written on link/unlink/reset (auto via `__audit_track__`).
- [ ] No embedding event field added for variant columns.
- [ ] Browser-verified via Playwright MCP through the **sidebar**, console clean, correct `/api/v1/*` calls observed.

---

## 11. Follow-ups / out of scope (do NOT do here)

- **Coverage-ratio floor fix to the derivation** (the auto `_derive_parent_id` accepting weak/low-coverage prefixes). Deferred - this plan only adds manual override; the derivation heuristic is unchanged. Track separately (see `PLAN-suggest-on-miss-variant-graph.md`).
- **Running the auto-backfill on prod.** D2: not part of this work. The backfill's manual-skip guard is added defensively for when it is eventually run. Manual curation is the interim path.
- **Existing garbage variant families** from brand/category-prefix stubs - the codes `SRTSC`, `CH`, `SRTG`, `SRTC`, `BF`, `BRSC`, `SRTPC` (and similar brand-prefix stubs) currently anchor spurious families under the existing derivation. Cleaning these up = hand-curation via this feature's Unlink/Reset + the coverage-ratio fix above; not addressed programmatically here.
- **`productService.getProducts` not using `buildDataGridParams`** - pre-existing deviation; the new `variant_filter` param follows the file's existing hand-built pattern for consistency. Migrating the whole function to `buildDataGridParams` is a separate cleanup.
- **Exposing `variant_filter` in the list-query advanced-filter builder / registry** - not needed for the first-class param; separate if ever required.
