/**
 * ============================================================================
 * Import column mapper (S4/S5) - feature service
 * ============================================================================
 * Layering: ImportColumnMapper / PlanContainerDialog / SupplierDocumentsUploadDialog ->
 * THIS service -> lib/api-client -> backend.
 *
 * ── BACKEND CONTRACT (app/api/v1/scm/import_mapping.py) ─────────────────────────────────
 * `probeImportMapping`:
 *   POST /api/v1/scm/import-mapping/probe  (multipart file, supplier_id, doc_types[],
 *   optional header_row) -> {header_row, columns:[{position, header, samples, field,
 *   source, required}], required_fields, missing_required, fields:[{field,label}]}  (B4)
 *
 * `saveImportMapping`:
 *   POST /api/v1/scm/import-mapping/save  {supplier_id, doc_types:[...], mappings:[{header,
 *   field}]} - upserts SUPPLIER-scoped rows, replacing this supplier's earlier choice for
 *   the same header rather than accumulating (AC-M6). `field: "ignore"` is a saved choice
 *   (G2/AC-M7), never omitted.                                                     (B5)
 *
 * A combined file (one sheet read as BOTH a proforma invoice and a packing list, grill G4
 * / AC-M13) probes and saves against an ARRAY of doc types rather than one - the backend
 * merges their field lists and required fields into the ONE section the dialog shows, and
 * `save` writes the same rows under both `import_field_alias.doc_type`s.
 *
 * Permission: `require_any_permission(["scm.proforma_invoice.upload", "scm.reorder.run"])`
 * - the union of the two real preview endpoints' own guards (proforma invoice / packing
 * list, and the stock list), since a caller who reached either dialog already holds one.
 *
 * Phase 1's mock (the field lists, `NEW_YANGGANG_HEADERS`, `buildMockProbe`,
 * `__resetImportMappingMockForTests`) is retired (review round 1, reviewer M5): both real
 * endpoints have served every dialog since Phase 2 landed, nothing in the tree imports the
 * mock exports any more (checked - neither dialog spec nor `ImportColumnMapper.test.tsx`
 * reaches for them), and dead code answering a question nobody asks any more is a liability
 * a fix-round removes rather than carries forward "just in case".
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export type ImportMappingDocType =
  | 'proforma_invoice'
  | 'packing_list'
  | 'supplier_inventory';

export const IMPORT_MAPPING_DOC_TYPE_LABELS: Record<
  ImportMappingDocType,
  string
> = {
  proforma_invoice: 'proforma invoice',
  packing_list: 'packing list',
  supplier_inventory: 'stock list',
};

/** Re-exported so a caller only ever imports the mapper's own shapes from ONE place
 *  (the component) and this service's REQUEST/RESPONSE shapes from another. */
export type {
  ImportMappingColumn,
  ImportMappingField,
  ImportMappingProbe,
  ImportMappingSelection,
} from '@/components/common/ImportColumnMapper';
import type {
  ImportMappingField,
  ImportMappingProbe,
  ImportMappingSelection,
} from '@/components/common/ImportColumnMapper';

export interface ProbeImportMappingRequest {
  file: File;
  supplierId: string;
  /** One entry normally; two for a combined file (G4/AC-M13) - `proforma_invoice` and
   *  `packing_list` for the same sheet, same header, same meaning. */
  docTypes: ImportMappingDocType[];
  /** The stepper's current pick (AC-M3); omitted on the first probe of a file. */
  headerRow?: number | null;
}

export interface ProbeImportMappingResult {
  probe: ImportMappingProbe;
  fields: ImportMappingField[];
}

export async function probeImportMapping({
  file,
  supplierId,
  docTypes,
  headerRow,
}: ProbeImportMappingRequest): Promise<ProbeImportMappingResult> {
  const body = new FormData();
  body.append('file', file);
  body.append('supplier_id', supplierId);
  docTypes.forEach((docType) => body.append('doc_types', docType));
  if (headerRow != null) body.append('header_row', String(headerRow));
  const res = await apiFetch('/api/v1/scm/import-mapping/probe', { method: 'POST', body });
  if (!res.ok) throw new Error(await extractApiError(res, "Failed to read the file's columns"));
  const data = await res.json();
  return {
    probe: {
      header_row: data.header_row,
      columns: data.columns,
      required_fields: data.required_fields,
      missing_required: data.missing_required,
      row_count: data.row_count,
    },
    fields: data.fields,
  };
}

export interface SaveImportMappingRequest {
  supplierId: string;
  docTypes: ImportMappingDocType[];
  mappings: ImportMappingSelection[];
}

export async function saveImportMapping({
  supplierId,
  docTypes,
  mappings,
}: SaveImportMappingRequest): Promise<void> {
  const res = await apiFetch('/api/v1/scm/import-mapping/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ supplier_id: supplierId, doc_types: docTypes, mappings }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to save the column mapping'));
}
