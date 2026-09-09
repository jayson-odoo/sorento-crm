/**
 * "Supplied with" companion rules (PLAN-scm-supplied-with-companions.md).
 *
 * A rule says a COMPANION product rides inside its HOST(s) when the supplier ships
 * them together - CKSW015 (seat cover) inside CKS1050's own line, never its own PO
 * line. A rule with two hosts (SC-RL with the X + Y pair) requires BOTH present on
 * the same order before it bites. Configured on the companion product's Suppliers
 * tab; read-only on each host's own Suppliers tab ("Ships with").
 */

/** One host on a rule, as a human reads it - never a bare id. */
export interface ProductCompanionHostRef {
  product_id: string;
  item_code: string;
  product_name: string;
}

export interface ProductCompanionRuleRow {
  id: string;
  companion_product_id: string;
  companion_item_code: string;
  companion_product_name: string;
  /** Null = any supplier (the "just in case" scope, owner ruling 9 Sep). */
  supplier_id: string | null;
  supplier_code: string | null;
  supplier_name: string | null;
  /** Companion units per ONE host unit. Fractional allowed (NUMERIC on the backend). */
  ratio: number;
  is_active: boolean;
  hosts: ProductCompanionHostRef[];
  created_at: string;
  updated_at: string;
}

export interface ProductCompanionRuleWrite {
  companion_product_id: string;
  host_product_ids: string[];
  supplier_id: string | null;
  ratio: number;
}
