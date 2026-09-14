/**
 * ============================================================================
 * Product combos - feature service
 * ============================================================================
 * Layering: UI -> hooks (useProductCombos) -> THIS service -> lib/api-client
 * -> backend. No component fetches directly.
 *
 * Plan: `documentation/plans/dealer-kit/PLAN-price-tag-combos.md` D1 (slice S1).
 * UAC: `documentation/plans/dealer-kit/price-tag-combos-acceptance-criteria.md`.
 *
 * ── BACKEND CONTRACT (S1 Phase 2 builds this; everything below is served by the
 *    in-file mock at the bottom until then) ───────────────────────────────────
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
 *
 * ── PHASE 1 MOCK - DEBT, NOT DONE ──────────────────────────────────────────
 * Everything below `--- mock ---` is an in-memory store that lives as long as
 * the tab does. It exists so the Combos and Sold-with sections can be tuned and
 * browser-verified before any backend code is written (PRINCIPLES.md Phase 1),
 * and it is DELETED in Phase 2 when each function's body becomes the `apiFetch`
 * call its contract above describes.
 *
 * Two things the mock cannot stand in for, both Phase 2:
 *   * the two deferred-action keys (`product_combo.delete`,
 *     `product_combo_part.delete`) have to be registered in
 *     `app/services/record_actions.py` before a countdown can commit - the
 *     grace window is parked on the SERVER by design (D7), so there is nothing
 *     in the browser for a mock to intercept;
 *   * company scoping (AC-S1-7) is a server rule and is not simulated.
 * ============================================================================
 */
import type {
  ProductComboCreate,
  ProductComboPartCreate,
  ProductComboPartRow,
  ProductComboPartUpdate,
  ProductComboRow,
  ProductSoldWithRow,
} from '../types/productCombo.types';
import { getProduct } from './productService';

export async function listProductCombos(productId: string): Promise<ProductComboRow[]> {
  return mockListCombos(productId);
}

export async function listProductSoldWith(productId: string): Promise<ProductSoldWithRow[]> {
  return mockListSoldWith(productId);
}

export async function createProductCombo(
  productId: string,
  write: ProductComboCreate,
): Promise<ProductComboRow> {
  return mockCreateCombo(productId, write);
}

export async function addProductComboPart(
  comboId: string,
  write: ProductComboPartCreate,
): Promise<ProductComboPartRow> {
  return mockAddPart(comboId, write);
}

export async function updateProductComboPart(
  partId: string,
  write: ProductComboPartUpdate,
): Promise<ProductComboPartRow> {
  return mockUpdatePart(partId, write);
}

/**
 * The raw hard deletes. The UI never calls these - see the DELETE contract notes
 * above; `useDeferredRowAction` parks the removal and the server runs the real
 * service method when the window lapses. Kept for parity with
 * `deleteProductCompanionRule`.
 */
export async function deleteProductCombo(comboId: string): Promise<void> {
  return mockDeleteCombo(comboId);
}

export async function deleteProductComboPart(partId: string): Promise<void> {
  return mockDeletePart(partId);
}

// ---------------------------------------------------------------------------
// --- mock --- everything below goes away in Phase 2.
// ---------------------------------------------------------------------------

/** Enough latency for the section's own skeleton to be a real state, not a flash. */
const MOCK_LATENCY_MS = 250;

const combos: ProductComboRow[] = [];

function sleep(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, MOCK_LATENCY_MS));
}

function newId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `mock-${Math.random().toString(36).slice(2)}`;
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

/** `800 x 500 x 220 mm`, the backend's `format_dimensions_mm` rule. */
function formatDimensions(
  length?: number | null,
  width?: number | null,
  height?: number | null,
): string | null {
  const parts = [length, width, height];
  if (!parts.some((part) => part != null)) return null;
  return `${parts.map((part) => (part == null ? '-' : String(part))).join(' x ')} mm`;
}

async function mockListCombos(productId: string): Promise<ProductComboRow[]> {
  await sleep();
  return clone(combos.filter((combo) => combo.host_product_id === productId));
}

async function mockListSoldWith(productId: string): Promise<ProductSoldWithRow[]> {
  await sleep();
  const rows: ProductSoldWithRow[] = [];
  for (const combo of combos) {
    if (!combo.parts.some((part) => part.product_id === productId)) continue;
    // The real route resolves the host's own code and name; the mock asks the
    // product endpoint, which is already live on the lane backend.
    const host = await getProduct(combo.host_product_id);
    rows.push({
      host_product_id: combo.host_product_id,
      host_code: host.product_code,
      host_name: host.product_name,
      combo_id: combo.id,
      combo_name: combo.name,
    });
  }
  return rows;
}

async function mockCreateCombo(
  productId: string,
  write: ProductComboCreate,
): Promise<ProductComboRow> {
  await sleep();
  const name = write.name.trim();
  const taken = combos.some(
    (combo) =>
      combo.host_product_id === productId &&
      combo.name.toLowerCase() === name.toLowerCase(),
  );
  if (taken) throw new Error(`This product already has a combo called "${name}"`);
  const now = new Date().toISOString();
  const combo: ProductComboRow = {
    id: newId(),
    host_product_id: productId,
    name,
    sort_order: combos.filter((c) => c.host_product_id === productId).length,
    parts: [],
    created_at: now,
    updated_at: now,
  };
  combos.push(combo);
  return clone(combo);
}

async function mockAddPart(
  comboId: string,
  write: ProductComboPartCreate,
): Promise<ProductComboPartRow> {
  const combo = combos.find((c) => c.id === comboId);
  if (!combo) throw new Error('That combo no longer exists');
  if (write.part_product_id === combo.host_product_id) {
    throw new Error('A product cannot be a part of its own combo');
  }
  if (combo.parts.some((part) => part.product_id === write.part_product_id)) {
    throw new Error('That product is already on this combo');
  }
  // The real route reads the part's code, name and dimensions off the product
  // row it just linked; the mock asks the live product endpoint for the same
  // three, so the section renders real codes instead of invented ones.
  const product = await getProduct(write.part_product_id);
  const part: ProductComboPartRow = {
    id: newId(),
    combo_id: comboId,
    product_id: write.part_product_id,
    code: product.product_code,
    product_name: product.product_name,
    dimensions: formatDimensions(
      product.dimensions_length,
      product.dimensions_width,
      product.dimensions_height,
    ),
    choice_group: write.choice_group?.trim() || null,
    sort_order: combo.parts.length,
  };
  combo.parts.push(part);
  combo.updated_at = new Date().toISOString();
  return clone(part);
}

async function mockUpdatePart(
  partId: string,
  write: ProductComboPartUpdate,
): Promise<ProductComboPartRow> {
  await sleep();
  for (const combo of combos) {
    const part = combo.parts.find((p) => p.id === partId);
    if (!part) continue;
    if ('choice_group' in write) part.choice_group = write.choice_group?.trim() || null;
    if (write.sort_order != null) part.sort_order = write.sort_order;
    combo.updated_at = new Date().toISOString();
    return clone(part);
  }
  throw new Error('That part no longer exists');
}

async function mockDeleteCombo(comboId: string): Promise<void> {
  await sleep();
  const index = combos.findIndex((combo) => combo.id === comboId);
  if (index >= 0) combos.splice(index, 1);
}

async function mockDeletePart(partId: string): Promise<void> {
  await sleep();
  for (const combo of combos) {
    const index = combo.parts.findIndex((part) => part.id === partId);
    if (index >= 0) {
      combo.parts.splice(index, 1);
      return;
    }
  }
}
