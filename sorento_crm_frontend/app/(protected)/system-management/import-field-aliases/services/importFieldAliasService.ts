/**
 * ============================================================================
 * Import column mappings (S5) - feature service
 * ============================================================================
 * Layering: ImportFieldAliasesList / ImportFieldAliasFormDialog / the upload dialogs'
 * "Map to..." chip -> THIS service -> lib/api-client -> backend.
 *
 * ── BACKEND CONTRACT (app/api/v1/system/import_field_aliases.py) ───────────────
 *
 *  GET    /api/v1/system/import-field-aliases?doc_type=
 *    -> 200 ImportFieldAliasGroup[], one row per system field of that doc type (even a
 *       field with no alias yet), each carrying every header that resolves to it.
 *  POST   /api/v1/system/import-field-aliases
 *    body { doc_type, field, alias, locale? } -> 201 ImportFieldAliasGroup (the field's
 *    whole row, so the grid can replace it in place). 409 on the (doc_type, alias) pair
 *    already mapped - a header can mean only one field.
 *  DELETE /api/v1/system/import-field-aliases/{id}
 *    -> 204.
 *  GET    /api/v1/system/import-field-aliases/fields?doc_type=
 *    -> 200 ImportFieldAliasFieldOption[] - the canonical field list the reader asks for,
 *       built from each reader's own declared field set (never hand-typed).
 *
 *  Permissions: `system.import_field_aliases.view` / `.edit`, granted to the roles that
 *  hold `system.numbering_rules.view` / `.edit` in the grant sweep (AC-E1).
 *
 * `unmapped_headers: string[]` on the supplier-document preview response (AC-E2) is a
 * separate contract addition, documented at the top of `fulfilmentService.ts` and
 * `proformaInvoiceService.ts` - this file owns only the mapping CRUD and the field list.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  ImportFieldAliasDocType,
  ImportFieldAliasFieldOption,
  ImportFieldAliasGroup,
} from '../types/importFieldAlias.types';

export type { ImportFieldAliasDocType };

const BASE = '/api/v1/system/import-field-aliases';

export async function listImportFieldAliases(
  docType: ImportFieldAliasDocType,
): Promise<ImportFieldAliasGroup[]> {
  const res = await apiFetch(`${BASE}?doc_type=${docType}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load import column mappings'));
  return res.json();
}

export async function listImportFieldAliasFields(
  docType: ImportFieldAliasDocType,
): Promise<ImportFieldAliasFieldOption[]> {
  const res = await apiFetch(`${BASE}/fields?doc_type=${docType}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the field list'));
  return res.json();
}

export async function createImportFieldAlias(data: {
  doc_type: ImportFieldAliasDocType;
  field: string;
  alias: string;
  locale?: string | null;
}): Promise<ImportFieldAliasGroup> {
  const res = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    // The STATUS travels with the message: a caller writing the same alias for two
    // document types at once (the combined-file chip) has to tell "one of them already
    // had it" (409) apart from a real refusal.
    const error = new Error(await extractApiError(res, 'Failed to add that mapping')) as Error & {
      status?: number;
    };
    error.status = res.status;
    throw error;
  }
  return res.json();
}

export async function deleteImportFieldAlias(id: string): Promise<void> {
  const res = await apiFetch(`${BASE}/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to remove that mapping'));
}
