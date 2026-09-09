/**
 * ============================================================================
 * "Supplied with" companion rules - feature service
 * ============================================================================
 * Layering: UI -> hooks (useProductCompanions) -> THIS service -> lib/api-client
 * -> backend. No component fetches directly.
 *
 * ── PHASE-1 / PHASE-2 SWAP ──────────────────────────────────────────────────
 * `USE_COMPANION_MOCKS` is the single flag that toggles this feature between the
 * deterministic in-memory store (`lib/productCompanionMock.ts`) and the live
 * backend. Phase 1 = true (no backend yet - PLAN-scm-supplied-with-companions.md
 * S3/S4 build `product_companion_rules` + the routes). Phase 2 flips it to
 * false; every mock branch below already has its real `apiFetch` counterpart
 * wired to the contract, so the swap is one line + deleting the mock import.
 *
 * ── PHASE-2 BACKEND CONTRACT (mounted under
 *    require_module_enabled_with_api_key, gated `master_data.products.edit` for
 *    writes / `master_data.products.view` for reads - the products permission,
 *    per the plan's S4) ────────────────────────────────────────────────────────
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
 *    `product_companion_rule.delete` once Phase 2 registers that action in
 *    `app/services/record_actions.py`. This raw route stays for API-key
 *    callers and admin tooling, matching every other hard-deletable record
 *    (`deleteProduct` in productService.ts is the same shape).
 *
 * Deleting a product that is named as a host or a companion of an ACTIVE rule
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
import {
  MockCompanionRuleConflict,
  mockCreateRule,
  mockDeleteRule,
  mockListRulesForCompanion,
  mockListRulesForHost,
} from '../lib/productCompanionMock';

/** Phase-1 flag - true = deterministic mock store, false = live backend. */
export const USE_COMPANION_MOCKS = true;

const BASE = '/api/v1/master-data/product-companion-rules';

/**
 * Labels for the picked companion / hosts / supplier. The mock store has no backend to
 * resolve ids against, so the caller (which already has these records from the shared
 * product search and `useSupplierSelectQuery`) hands them along. Dropped once
 * `USE_COMPANION_MOCKS` flips false - the real POST returns the whole row itself.
 */
export interface CreateCompanionRuleInput {
  write: ProductCompanionRuleWrite;
  mockRefs: {
    companion: { item_code: string; product_name: string };
    hosts: { product_id: string; item_code: string; product_name: string }[];
    supplier: { supplier_code: string; supplier_name: string } | null;
  };
}

export async function listCompanionRulesForCompanion(
  companionProductId: string,
): Promise<ProductCompanionRuleRow[]> {
  if (USE_COMPANION_MOCKS) return mockListRulesForCompanion(companionProductId);
  const params = new URLSearchParams({ companion_product_id: companionProductId });
  const res = await apiFetch(`${BASE}?${params.toString()}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load supplied-with rules'));
  const body = (await res.json()) as { data?: ProductCompanionRuleRow[] };
  return body.data ?? [];
}

export async function listCompanionRulesForHost(
  hostProductId: string,
): Promise<ProductCompanionRuleRow[]> {
  if (USE_COMPANION_MOCKS) return mockListRulesForHost(hostProductId);
  const params = new URLSearchParams({ host_product_id: hostProductId });
  const res = await apiFetch(`${BASE}?${params.toString()}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load "ships with" rules'));
  const body = (await res.json()) as { data?: ProductCompanionRuleRow[] };
  return body.data ?? [];
}

export async function createProductCompanionRule(
  input: CreateCompanionRuleInput,
): Promise<ProductCompanionRuleRow> {
  if (USE_COMPANION_MOCKS) {
    try {
      return mockCreateRule(input.write, input.mockRefs);
    } catch (error) {
      if (error instanceof MockCompanionRuleConflict) throw new Error(error.message);
      throw error;
    }
  }
  const res = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input.write),
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
 * The raw hard delete. The UI never calls this - see the DELETE contract note above.
 * Kept for parity with `deleteProduct` and for the mock branch the Phase-1 local
 * deferred-delete timer (`useProductCompanions.ts`) calls at commit time.
 */
export async function deleteProductCompanionRule(id: string): Promise<void> {
  if (USE_COMPANION_MOCKS) {
    mockDeleteRule(id);
    return;
  }
  const res = await apiFetch(`${BASE}/${encodeURIComponent(id)}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to delete the rule'));
}
