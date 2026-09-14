/**
 * ============================================================================
 * Product combos - feature service
 * ============================================================================
 * Layering: UI -> hooks (useProductCombos) -> THIS service -> lib/api-client
 * -> backend. No component fetches directly.
 *
 * Phase 2 (S1) built `product_combos` + `product_combo_parts` and these routes -
 * this file no longer mocks anything, and the Phase-1 in-memory store that stood
 * in for them is deleted.
 *
 * Plan: `documentation/plans/dealer-kit/PLAN-price-tag-combos.md` D1 (slice S1).
 * UAC: `documentation/plans/dealer-kit/price-tag-combos-acceptance-criteria.md`.
 *
 * ── BACKEND CONTRACT (built, S1 Phase 2) ────────────────────────────────────
 *
 * Router `app/api/v1/master_data/product_combos.py`, registered beside
 * `product_companions.py`, no dedicated permission slug (AC-X-5): reads take
 * `master_data.products.view`, writes take `master_data.products.edit`. Combos
 * are company scoped THROUGH the host product - a caller scoped to another
 * company gets 404 on the host, never an empty list (AC-S1-7).
 *
 *  GET    /api/v1/master-data/products/{product_id}/combos
 *    -> { data: ProductComboRow[] }
 *    Combos of that host, `sort_order` then `name`, each with its parts in
 *    `sort_order`. A part carries the product's own `code`, `product_name` and
 *    `dimensions` (`800 x 500 x 220 mm`, the `format_dimensions_mm` rule the
 *    tag data service already uses), so the reader never sees an id.
 *
 *  POST   /api/v1/master-data/products/{product_id}/combos
 *    body ProductComboCreate -> ProductComboRow (201)
 *    409 `COMBO_NAME_TAKEN` when the host already has a combo of that name
 *    (UNIQUE (host_product_id, name), AC-S1-2). The combo is created EMPTY;
 *    parts are added one at a time below.
 *
 *  PATCH  /api/v1/master-data/product-combos/{combo_id}
 *    body { name?, sort_order? } -> ProductComboRow
 *    No UI consumer in S1 (nothing in the UAC renames or reorders a combo) -
 *    documented here because the route is part of D1's table.
 *
 *  DELETE /api/v1/master-data/product-combos/{combo_id} -> 204
 *    Hard delete, cascading its parts (AC-S1-5). NOT what the UI calls: Delete
 *    is a deferred action (D7 - no confirmation dialog, a server-parked grace
 *    window instead), dispatched through /api/v1/pending-actions with
 *    action_key `product_combo.delete`. Kept for API-key callers and admin
 *    tooling, exactly as `deleteProductCompanionRule` is.
 *
 *  POST   /api/v1/master-data/product-combos/{combo_id}/parts
 *    body ProductComboPartCreate -> ProductComboPartRow (201)
 *    422 `COMBO_PART_IS_HOST` when the part is the host itself, 422
 *    `COMBO_PART_DUPLICATE` when the product is already on this combo
 *    (UNIQUE (combo_id, part_product_id)) - both surfaced inline, AC-S1-3.
 *
 *  PATCH  /api/v1/master-data/product-combo-parts/{part_id}
 *    body ProductComboPartUpdate -> ProductComboPartRow
 *    The choice-group control on a part row (AC-S1-4). `choice_group: null`
 *    clears it back to a fixed part.
 *
 *  DELETE /api/v1/master-data/product-combo-parts/{part_id} -> 204
 *    Same deferred-action note as the combo delete, action_key
 *    `product_combo_part.delete`.
 *
 *  GET    /api/v1/master-data/products/{product_id}/sold-with
 *    -> { data: ProductSoldWithRow[] }
 *    The mirror, on the PART's own page (AC-S1-6): every host + combo naming
 *    this product, across hosts. Read-only; a combo is only ever edited from
 *    its host.
 *
 * A product named as a host or a part of a combo is RESTRICT on both FKs, so
 * deleting it is refused through the existing product-delete flow, not here.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  ProductComboCreate,
  ProductComboPartCreate,
  ProductComboPartRow,
  ProductComboPartUpdate,
  ProductComboRow,
  ProductSoldWithRow,
} from '../types/productCombo.types';

const PRODUCTS = '/api/v1/master-data/products';
const COMBOS = '/api/v1/master-data/product-combos';
const PARTS = '/api/v1/master-data/product-combo-parts';

export async function listProductCombos(productId: string): Promise<ProductComboRow[]> {
  const res = await apiFetch(`${PRODUCTS}/${encodeURIComponent(productId)}/combos`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load combos'));
  const body = (await res.json()) as { data?: ProductComboRow[] };
  return body.data ?? [];
}

export async function listProductSoldWith(productId: string): Promise<ProductSoldWithRow[]> {
  const res = await apiFetch(`${PRODUCTS}/${encodeURIComponent(productId)}/sold-with`);
  if (!res.ok) {
    throw new Error(await extractApiError(res, 'Failed to load what this is sold with'));
  }
  const body = (await res.json()) as { data?: ProductSoldWithRow[] };
  return body.data ?? [];
}

export async function createProductCombo(
  productId: string,
  write: ProductComboCreate,
): Promise<ProductComboRow> {
  const res = await apiFetch(`${PRODUCTS}/${encodeURIComponent(productId)}/combos`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(write),
  });
  if (!res.ok) {
    throw new Error(
      await extractApiError(
        res,
        res.status === 409
          ? 'This product already has a combo with that name'
          : 'Failed to add the combo',
      ),
    );
  }
  return (await res.json()) as ProductComboRow;
}

export async function addProductComboPart(
  comboId: string,
  write: ProductComboPartCreate,
): Promise<ProductComboPartRow> {
  const res = await apiFetch(`${COMBOS}/${encodeURIComponent(comboId)}/parts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(write),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to add the part'));
  return (await res.json()) as ProductComboPartRow;
}

export async function updateProductComboPart(
  partId: string,
  write: ProductComboPartUpdate,
): Promise<ProductComboPartRow> {
  const res = await apiFetch(`${PARTS}/${encodeURIComponent(partId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(write),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to save the choice group'));
  return (await res.json()) as ProductComboPartRow;
}

/**
 * The raw hard deletes. The UI never calls these - see the DELETE contract notes
 * above; `useDeferredRowAction` parks the removal and the server runs
 * `ProductComboService.delete` / `.delete_part` when the window lapses
 * (`app/services/record_actions.py`). Kept for parity with
 * `deleteProductCompanionRule`.
 */
export async function deleteProductCombo(comboId: string): Promise<void> {
  const res = await apiFetch(`${COMBOS}/${encodeURIComponent(comboId)}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to delete the combo'));
}

export async function deleteProductComboPart(partId: string): Promise<void> {
  const res = await apiFetch(`${PARTS}/${encodeURIComponent(partId)}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to remove the part'));
}
