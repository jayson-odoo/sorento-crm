/**
 * Suppliers — whitelisted bulk-update service (Phase-2 REAL wiring).
 *
 * =========================================================================
 * CONTRACT (mirrors app/services/bulk_update_registry.py on the backend)
 * =========================================================================
 *
 *   POST /api/v1/procurement/suppliers/bulk-update
 *   body: { ids: string[] (1..500, deduped server-side); field: string; value: any }
 *   resp: {
 *     updated: number;
 *     skipped: { id: string; label: string; reason: string }[];
 *   }
 *   400: field not on the suppliers whitelist, or value not allowed for the field
 *
 * KEY CONSTRAINTS (the whole point of the reframe — do NOT loosen):
 *  - The backend keeps a per-resource WHITELIST of editable fields (+ allowed
 *    values). `field` MUST be one of the caller's whitelisted BulkEditableField
 *    keys; anything else is a 400. There is no generic "write any column" path.
 *  - Each id runs through the resource's NORMAL update service method
 *    (SupplierService.update_supplier) so validation, business rules, side
 *    effects and audit (Supplier.__audit_track__) all fire — not a raw write.
 *  - Rows the normal path rejects (e.g. not found) come back in `skipped` with a
 *    human `label` + `reason`; the rest commit. Partial success, not all-or-nothing.
 *
 * Currently whitelisted field: `is_active` (Status = Active / Inactive).
 * =========================================================================
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { BulkUpdateResult } from '@/components/common/BulkUpdateDialog';

export async function bulkUpdateSuppliers(
  ids: string[],
  field: string,
  value: string,
): Promise<BulkUpdateResult> {
  const response = await apiFetch('/api/v1/procurement/suppliers/bulk-update', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids, field, value }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to bulk-update suppliers'));
  }
  return response.json();
}
