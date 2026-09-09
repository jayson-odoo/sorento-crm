/**
 * ============================================================================
 * Import column mappings (S5) - feature service
 * ============================================================================
 * Layering: ImportFieldAliasesList / ImportFieldAliasFormDialog / the upload dialogs'
 * "Map to..." chip -> THIS service -> lib/api-client -> backend.
 *
 * ── PHASE-1 / PHASE-2 SWAP ──────────────────────────────────────────────────
 * `USE_IMPORT_FIELD_ALIAS_MOCKS` is the single flag toggling this feature between the
 * deterministic prototype store (`lib/importFieldAliasMock.ts`) and the live backend, the
 * same shape `companies/services/companyService.ts` uses for the same reason. Phase 1 =
 * true (no backend). Phase 2 flips it to false; every mock branch below already has its
 * real `apiFetch` counterpart wired to the contract, so the swap is one line + deleting
 * the mock import.
 *
 * ── PHASE-2 BACKEND CONTRACT (app/api/v1/system/import_field_aliases.py) ───────────────
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
import {
  mockCreateImportFieldAlias,
  mockDeleteImportFieldAlias,
  mockFieldsFor,
  mockListImportFieldAliases,
} from '../lib/importFieldAliasMock';

export type { ImportFieldAliasDocType };

/** Phase-1 flag - true = deterministic mock store, false = live backend. */
export const USE_IMPORT_FIELD_ALIAS_MOCKS = true;

const BASE = '/api/v1/system/import-field-aliases';

export async function listImportFieldAliases(
  docType: ImportFieldAliasDocType,
): Promise<ImportFieldAliasGroup[]> {
  if (USE_IMPORT_FIELD_ALIAS_MOCKS) return mockListImportFieldAliases(docType);
  const res = await apiFetch(`${BASE}?doc_type=${docType}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load import column mappings'));
  return res.json();
}

export async function listImportFieldAliasFields(
  docType: ImportFieldAliasDocType,
): Promise<ImportFieldAliasFieldOption[]> {
  if (USE_IMPORT_FIELD_ALIAS_MOCKS) return mockFieldsFor(docType);
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
  if (USE_IMPORT_FIELD_ALIAS_MOCKS) return mockCreateImportFieldAlias(data);
  const res = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to add that mapping'));
  return res.json();
}

export async function deleteImportFieldAlias(id: string): Promise<void> {
  if (USE_IMPORT_FIELD_ALIAS_MOCKS) {
    mockDeleteImportFieldAlias(id);
    return;
  }
  const res = await apiFetch(`${BASE}/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to remove that mapping'));
}
