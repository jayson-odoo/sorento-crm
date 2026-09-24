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
 * Permission: PER doc type, not one blanket gate (review round 1, R2) - each requested doc
 * type in `doc_types` is checked against exactly the permission(s) its OWN upload endpoint
 * accepts (`scm.proforma_invoice.upload` or `scm.reorder.run` for proforma_invoice /
 * packing_list, `scm.reorder.run` only for supplier_inventory), so a proforma-invoice-only
 * caller cannot probe or save a stock-list layout through this endpoint even though
 * `/scm/supplier-inventory/*` itself would refuse them directly.
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
  ImportMappingHeaderField,
  ImportMappingProbe,
  ImportMappingSelection,
} from '@/components/common/ImportColumnMapper';
import { IGNORE_FIELD } from '@/components/common/ImportColumnMapper';
import type {
  ImportMappingField,
  ImportMappingHeaderField,
  ImportMappingProbe,
  ImportMappingSelection,
} from '@/components/common/ImportColumnMapper';

/**
 * ── F1 MOCK (Phase 1, frontend-first against mocks - L2-S2/#1211) ──────────────────────
 * `header_probe.probe` does not return `header_fields` yet - Phase 2 wires that for real
 * (PLAN-pi-header-fields-convert-fixes-24sep.md F1). Until then this stands in with
 * DAFUYUAN's own header block (the plan's "Measured" sample) so the mapper's "Header
 * fields" section (F2) has real pairs to map, fold and save against. A real response's
 * `header_fields` always wins the moment Phase 2 lands (`data.header_fields ?? mock...`
 * below) - remove the mock at that point (grep this comment).
 *
 * Only relevant to the doc types that carry a header block at all (proforma_invoice /
 * packing_list) - a pure `supplier_inventory` probe gets no `header_fields`, same as a
 * real one would answer.
 *
 * `mockHeaderFieldMemory` plays the part of the supplier-scoped resolve a real probe
 * would already know on a SECOND file from the same supplier (AC-F3: "the next upload
 * from the same supplier folds the section into the N of N mapped summary") - written by
 * `saveImportMapping` below, read by `probeImportMapping`. In-memory only: it forgets on
 * reload, same as every earlier Phase 1 mock this codebase has carried until its backend
 * landed (see `buildMockProbe`'s retirement note in `components/common/ImportColumnMapper.tsx`
 * git history).
 */
const HEADER_FIELD_RELEVANT_DOC_TYPES = new Set<ImportMappingDocType>([
  'proforma_invoice',
  'packing_list',
]);

const MOCK_HEADER_FIELD_PAIRS: { row: number; label: string; sample: string }[] = [
  { row: 4, label: '提单号', sample: 'OOLU2339207730' },
  { row: 4, label: '柜号', sample: 'FSCU9304169' },
  { row: 4, label: '封条号', sample: 'OOLLGZ7182' },
  { row: 1, label: 'Date:', sample: '22/09/2026' },
  { row: 1, label: 'PI No.:', sample: 'DFY20260922' },
];

const mockHeaderFieldMemory = new Map<string, Record<string, string>>();

function mockHeaderFieldsFor(
  supplierId: string,
  docTypes: ImportMappingDocType[],
): ImportMappingHeaderField[] | undefined {
  if (!docTypes.some((dt) => HEADER_FIELD_RELEVANT_DOC_TYPES.has(dt))) return undefined;
  const known = mockHeaderFieldMemory.get(supplierId) ?? {};
  return MOCK_HEADER_FIELD_PAIRS.map((pair) => {
    const field = known[pair.label] ?? null;
    return {
      row: pair.row,
      label: pair.label,
      sample: pair.sample,
      field,
      source: field ? ('supplier' as const) : ('none' as const),
    };
  });
}

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
      // F1 MOCK (see the block above) - a real `data.header_fields` always wins.
      header_fields: data.header_fields ?? mockHeaderFieldsFor(supplierId, docTypes),
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
  // F1 MOCK (see the block above): a Header fields pick has no real row to write to yet -
  // `header_probe`'s resolver does not exist until Phase 2, and sending one through as a
  // plain column mapping would either 422 (a field the readers' dataclasses do not carry
  // under this exact name, e.g. `currency`) or write a premature `import_field_alias` row
  // for the rest. Kept in the client-side memory instead, so AC-F3's "next upload folds"
  // still holds; column picks are unaffected and go through exactly as before.
  const knownHeaderLabels = new Set(MOCK_HEADER_FIELD_PAIRS.map((p) => p.label));
  const headerPicks = mappings.filter((m) => knownHeaderLabels.has(m.header));
  const columnPicks = mappings.filter((m) => !knownHeaderLabels.has(m.header));
  if (headerPicks.length) {
    const existing = mockHeaderFieldMemory.get(supplierId) ?? {};
    headerPicks.forEach((m) => {
      existing[m.header] = m.field === IGNORE_FIELD ? IGNORE_FIELD : m.field;
    });
    mockHeaderFieldMemory.set(supplierId, existing);
  }
  if (!columnPicks.length) return;
  const res = await apiFetch('/api/v1/scm/import-mapping/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ supplier_id: supplierId, doc_types: docTypes, mappings: columnPicks }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to save the column mapping'));
}
