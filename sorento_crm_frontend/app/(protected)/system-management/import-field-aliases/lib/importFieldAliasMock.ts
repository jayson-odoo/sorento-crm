/**
 * Phase 1 mock store for import column mappings (S5).
 *
 * A deterministic, in-memory prototype - the same shape `companies/lib/companyMock.ts`
 * uses for the same reason: it lets the settings page and the upload dialog's "Map to..."
 * chip be built and browser-verified before the Phase 2 backend (`AliasResolver`, the
 * `import_field_alias` table) exists. Removed whole once `USE_IMPORT_FIELD_ALIAS_MOCKS`
 * flips to false.
 */
import type {
  ImportFieldAlias,
  ImportFieldAliasDocType,
  ImportFieldAliasFieldOption,
  ImportFieldAliasGroup,
} from '../types/importFieldAlias.types';

/** The canonical field set per reader (AC-E1) - in Phase 2 this is built from each
 *  reader's own declared field set, never hand-typed; the Phase 1 mock hand-types the
 *  same list so the page and the upload dialog have something real to show. */
const FIELDS: Record<ImportFieldAliasDocType, ImportFieldAliasFieldOption[]> = {
  proforma_invoice: [
    { field: 'item_code', label: 'Item code' },
    { field: 'description', label: 'Description' },
    { field: 'qty', label: 'Quantity' },
    { field: 'uom', label: 'UOM' },
    { field: 'unit_price', label: 'Unit price' },
    { field: 'cartons', label: 'Cartons' },
    { field: 'cbm_per_unit', label: 'CBM per unit' },
    { field: 'net_weight', label: 'Net weight' },
    { field: 'gross_weight', label: 'Gross weight' },
    { field: 'po_ref', label: 'PO reference' },
    { field: 'remark', label: 'Remark' },
  ],
  packing_list: [
    { field: 'item_code', label: 'Item code' },
    { field: 'supplier_code', label: 'Supplier code' },
    { field: 'description', label: 'Description' },
    { field: 'qty', label: 'Quantity' },
    { field: 'cartons', label: 'Cartons' },
    { field: 'pcs_per_carton', label: 'Pcs per carton' },
    { field: 'carton_length_cm', label: 'Carton length (cm)' },
    { field: 'carton_width_cm', label: 'Carton width (cm)' },
    { field: 'carton_height_cm', label: 'Carton height (cm)' },
    { field: 'cbm_per_carton', label: 'CBM per carton' },
    { field: 'net_weight', label: 'Net weight' },
    { field: 'gross_weight', label: 'Gross weight' },
    { field: 'material', label: 'Material' },
    { field: 'container_no', label: 'Container number' },
    { field: 'remark', label: 'Remark' },
  ],
};

interface MockRow {
  id: string;
  doc_type: ImportFieldAliasDocType;
  field: string;
  alias: string;
  locale: string | null;
  created_at: string;
}

let seq = 0;
function nextId(): string {
  seq += 1;
  return `mock-alias-${seq}`;
}

function seedRow(doc_type: ImportFieldAliasDocType, field: string, alias: string, locale: string | null): MockRow {
  return { id: nextId(), doc_type, field, alias, locale, created_at: '2026-08-01T00:00:00Z' };
}

/** A representative slice of the dev DB's real count (113 proforma_invoice aliases, 44
 *  packing_list) - enough to demonstrate every state the settings page and the upload
 *  dialog's chip need, not a full re-seed. */
let rows: MockRow[] = [
  seedRow('proforma_invoice', 'item_code', '型号', 'zh'),
  seedRow('proforma_invoice', 'item_code', 'ITEM NO.', 'en'),
  seedRow('proforma_invoice', 'description', '品名', 'zh'),
  seedRow('proforma_invoice', 'qty', '数量', 'zh'),
  seedRow('proforma_invoice', 'qty', 'QTY', 'en'),
  seedRow('proforma_invoice', 'unit_price', '单价(元)', 'zh'),
  seedRow('proforma_invoice', 'unit_price', 'UNIT PRICE', 'en'),
  seedRow('proforma_invoice', 'cartons', '箱数', 'zh'),
  seedRow('proforma_invoice', 'net_weight', '净重', 'zh'),
  seedRow('proforma_invoice', 'gross_weight', '毛重', 'zh'),
  seedRow('packing_list', 'item_code', '型号', 'zh'),
  seedRow('packing_list', 'supplier_code', '货号', 'zh'),
  seedRow('packing_list', 'cartons', '箱数', 'zh'),
  seedRow('packing_list', 'pcs_per_carton', '每箱数量', 'zh'),
  seedRow('packing_list', 'carton_length_cm', '长(CM)', 'zh'),
  seedRow('packing_list', 'carton_width_cm', '宽(CM)', 'zh'),
  seedRow('packing_list', 'carton_height_cm', '高(CM)', 'zh'),
  seedRow('packing_list', 'net_weight', '净重', 'zh'),
  seedRow('packing_list', 'gross_weight', '毛重', 'zh'),
  seedRow('packing_list', 'container_no', '柜号', 'zh'),
];

export function mockFieldsFor(docType: ImportFieldAliasDocType): ImportFieldAliasFieldOption[] {
  return FIELDS[docType];
}

function labelFor(docType: ImportFieldAliasDocType, field: string): string {
  return FIELDS[docType].find((f) => f.field === field)?.label ?? field;
}

export function mockListImportFieldAliases(docType: ImportFieldAliasDocType): ImportFieldAliasGroup[] {
  const byField = new Map<string, ImportFieldAlias[]>();
  for (const row of rows) {
    if (row.doc_type !== docType) continue;
    const list = byField.get(row.field) ?? [];
    list.push({ id: row.id, alias: row.alias, locale: row.locale, created_at: row.created_at });
    byField.set(row.field, list);
  }
  // Every field of the doc type, even one with no alias yet - the grid's own empty state
  // per row is "no header maps here yet", not "this field does not exist".
  return FIELDS[docType].map((f) => ({
    field: f.field,
    label: f.label,
    aliases: byField.get(f.field) ?? [],
  }));
}

export function mockCreateImportFieldAlias(input: {
  doc_type: ImportFieldAliasDocType;
  field: string;
  alias: string;
  locale?: string | null;
}): ImportFieldAliasGroup {
  const exists = rows.some(
    (r) => r.doc_type === input.doc_type && r.field === input.field && r.alias === input.alias,
  );
  if (exists) {
    const err = new Error(`"${input.alias}" already maps to ${labelFor(input.doc_type, input.field)}.`);
    (err as Error & { status?: number }).status = 409;
    throw err;
  }
  rows.push(seedRow(input.doc_type, input.field, input.alias, input.locale ?? null));
  return mockListImportFieldAliases(input.doc_type).find((g) => g.field === input.field)!;
}

export function mockDeleteImportFieldAlias(id: string): void {
  rows = rows.filter((r) => r.id !== id);
}
