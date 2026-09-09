/**
 * ============================================================================
 * "Supplied with" companion rules - feature service
 * ============================================================================
 * Layering: UI -> hooks (useProductCompanions) -> THIS service -> lib/api-client
 * -> backend. No component fetches directly.
 *
 * Phase 2 (S3/S4) built `product_companion_rules` + these routes - this file no
 * longer mocks anything (the Phase-1 in-memory store, `lib/productCompanionMock.ts`,
 * is deleted).
 *
 * ── BACKEND CONTRACT (mounted under require_module_enabled_with_api_key, gated
 *    `master_data.products.edit` for writes / `master_data.products.view` for
 *    reads - the products permission, per the plan's S4) ──────────────────────
 *
 *  GET    /api/v1/master-data/product-companion-rules?companion_product_id={id}
 *  GET    /api/v1/master-data/product-companion-rules?host_product_id={id}
 *    -> { data: ProductCompanionRuleRow[] }
 *    Exactly one of the two query params. `companion_product_id` powers the
 *    companion's own "Supplied with" section (UAC A1); `host_product_id`
 *    powers a host's read-only "Ships with" list (UAC A5). A rule with two
 *    hosts (SC-RL with X + Y) is returned by BOTH hosts' queries, each time
 *    naming every host on it - not only the one that was asked about - so the
 *    reader can see it takes the pair.
 *
 *  POST   /api/v1/master-data/product-companion-rules
 *    body ProductCompanionRuleWrite -> ProductCompanionRuleRow (201)
 *    409 when (company, companion_product_id, supplier_id) already has an
 *    active rule (UAC A4) - message names the existing rule's hosts + supplier.
 *    422 when host_product_ids is empty, or the companion appears in its own
 *    host list.
 *
 *  DELETE /api/v1/master-data/product-companion-rules/{id} -> 204
 *    Hard delete. NOT what the UI calls directly - Delete is a deferred action
 *    (D7: no confirmation dialog, a 10s server-parked grace window instead),
 *    dispatched through /api/v1/pending-actions with action_key
 *    `product_companion_rule.delete` (registered in `app/services/
 *    record_actions.py`). This raw route stays for API-key callers and admin
 *    tooling, matching every other hard-deletable record (`deleteProduct` in
 *    productService.ts is the same shape).
 *
 * Deleting a product that is named as a host or a companion of an active rule
 * is refused (RESTRICT on the FK, UAC A6) - that error surfaces through the
 * existing product-delete flow, not through this file.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  ProductCompanionRuleRow,
  ProductCompanionRuleWrite,
} from '../types/productCompanion.types';

const BASE = '/api/v1/master-data/product-companion-rules';

export async function listCompanionRulesForCompanion(
  companionProductId: string,
): Promise<ProductCompanionRuleRow[]> {
  const params = new URLSearchParams({ companion_product_id: companionProductId });
  const res = await apiFetch(`${BASE}?${params.toString()}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load supplied-with rules'));
  const body = (await res.json()) as { data?: ProductCompanionRuleRow[] };
  return body.data ?? [];
}

export async function listCompanionRulesForHost(
  hostProductId: string,
): Promise<ProductCompanionRuleRow[]> {
  const params = new URLSearchParams({ host_product_id: hostProductId });
  const res = await apiFetch(`${BASE}?${params.toString()}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load "ships with" rules'));
  const body = (await res.json()) as { data?: ProductCompanionRuleRow[] };
  return body.data ?? [];
}

export async function createProductCompanionRule(
  write: ProductCompanionRuleWrite,
): Promise<ProductCompanionRuleRow> {
  const res = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(write),
  });
  if (!res.ok) {
    throw new Error(
      await extractApiError(
        res,
        res.status === 409
          ? 'This companion already has a rule for that supplier'
          : 'Failed to add the rule',
      ),
    );
  }
  return (await res.json()) as ProductCompanionRuleRow;
}

/**
 * The raw hard delete. The UI never calls this directly - see the DELETE contract
 * note above; `useDeferredRowAction` parks the action and the server calls this
 * service method's own real counterpart (`ProductCompanionService.delete`) at
 * commit time. Kept for parity with `deleteProduct`.
 */
export async function deleteProductCompanionRule(id: string): Promise<void> {
  const res = await apiFetch(`${BASE}/${encodeURIComponent(id)}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to delete the rule'));
}
