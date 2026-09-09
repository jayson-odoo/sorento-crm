/**
 * ============================================================================
 * "Supplied with" companion rules - DETERMINISTIC MOCK BACKING STORE (Phase 1 only)
 * ============================================================================
 * No network, no `Math.random`, no `Date.now` beyond a fixed seed - every rule is
 * either hand-authored or created through the UI, and the shape matches exactly
 * what `product_companion_rules` (+ `product_companion_rule_hosts`) will return.
 *
 * Phase 2 deletes this file (or keeps it for vitest fixtures) once
 * `master_data/product_companions.py` exists and flips `USE_COMPANION_MOCKS` to
 * false in `services/productCompanionService.ts`. Mutations here act on an
 * in-memory array so Add/Delete feel real within a session; a page reload resets
 * to the seed below (empty - hosts/companions are real products picked through
 * the shared product search, so a hand-authored seed would only ever match a
 * fixture id nobody's dev product page carries).
 * ============================================================================
 */
import type {
  ProductCompanionRuleRow,
  ProductCompanionRuleWrite,
} from '../types/productCompanion.types';

let seq = 0;
function nextId(): string {
  seq += 1;
  return `companion-rule-mock-${seq}`;
}

let rules: ProductCompanionRuleRow[] = [];

export function mockListRulesForCompanion(companionProductId: string): ProductCompanionRuleRow[] {
  return rules.filter((r) => r.companion_product_id === companionProductId);
}

export function mockListRulesForHost(hostProductId: string): ProductCompanionRuleRow[] {
  return rules.filter((r) => r.hosts.some((h) => h.product_id === hostProductId));
}

/** Mirrors the backend's 409 shape (`AppException`) - a thrown object, not a rejected promise
 * from `fetch`, so the service's mock branch and its real branch answer the caller identically. */
export class MockCompanionRuleConflict extends Error {}

export function mockCreateRule(
  write: ProductCompanionRuleWrite,
  refs: {
    companion: { item_code: string; product_name: string };
    hosts: { product_id: string; item_code: string; product_name: string }[];
    supplier: { supplier_code: string; supplier_name: string } | null;
  },
): ProductCompanionRuleRow {
  const duplicate = rules.find(
    (r) =>
      r.companion_product_id === write.companion_product_id &&
      r.supplier_id === write.supplier_id,
  );
  if (duplicate) {
    const supplierName = duplicate.supplier_name ?? 'any supplier';
    // Owner ruling 9 Sep (UAC D10): never the word "host" in the UI, including error
    // copy - "included with" is the same vocabulary the cell and the modal both use.
    throw new MockCompanionRuleConflict(
      `${duplicate.companion_item_code} already has a rule for ${supplierName} (included with ${duplicate.hosts
        .map((h) => h.item_code)
        .join(' + ')}).`,
    );
  }
  const now = new Date(2026, 8, 9).toISOString();
  const row: ProductCompanionRuleRow = {
    id: nextId(),
    companion_product_id: write.companion_product_id,
    companion_item_code: refs.companion.item_code,
    companion_product_name: refs.companion.product_name,
    supplier_id: write.supplier_id,
    supplier_code: refs.supplier?.supplier_code ?? null,
    supplier_name: refs.supplier?.supplier_name ?? null,
    ratio: write.ratio,
    is_active: true,
    hosts: refs.hosts,
    created_at: now,
    updated_at: now,
  };
  rules = [...rules, row];
  return row;
}

export function mockDeleteRule(id: string): void {
  rules = rules.filter((r) => r.id !== id);
}
