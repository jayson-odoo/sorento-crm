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
 * ── PHASE 1 → PHASE 2 ────────────────────────────────────────────────────────────────────
 * Phase 1 built every screen against a MOCK of the two endpoints above (in-memory supplier
 * memory standing in for the real `import_field_alias` table). Phase 2 (B4/B5 landed) swaps
 * the two functions' bodies for real `apiFetch` calls below; every OTHER export here (the
 * shapes, the field lists, the header list, `buildMockProbe`) is unchanged - `buildMockProbe`
 * / `__resetImportMappingMockForTests` stay as TEST-ONLY fixtures (not used by either
 * dialog), the same real header list and field lists a spec can still reach for directly.
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
  ImportMappingColumn,
  ImportMappingField,
  ImportMappingProbe,
  ImportMappingSelection,
} from '@/components/common/ImportColumnMapper';

/** Every field the proforma invoice reader asks for (`ProformaLine` + `ProformaDocument`,
 *  `app/services/scm/proforma_invoice_reader.py`), read off the dataclasses directly -
 *  `row_number`/`index`/`header_row`/`lines` excluded (B7's deny set). Required: item_code,
 *  qty, unit_price. */
const PROFORMA_INVOICE_FIELDS: ImportMappingField[] = [
  { field: 'item_code', label: 'Item code' },
  { field: 'qty', label: 'Quantity' },
  { field: 'description', label: 'Description' },
  { field: 'uom', label: 'UOM' },
  { field: 'unit_price', label: 'Unit price' },
  { field: 'amount', label: 'Amount' },
  { field: 'po_ref', label: 'PO reference' },
  { field: 'remark', label: 'Remark' },
  { field: 'brand', label: 'Brand' },
  { field: 'cartons', label: 'Cartons' },
  { field: 'spec', label: 'Spec' },
  { field: 'cbm_per_unit', label: 'CBM per unit' },
  { field: 'cbm_total', label: 'CBM total' },
  { field: 'net_weight', label: 'Net weight' },
  { field: 'gross_weight', label: 'Gross weight' },
  { field: 'material', label: 'Material' },
  { field: 'pi_number', label: 'PI number' },
  { field: 'invoice_date', label: 'Invoice date' },
  { field: 'container_no', label: 'Container no' },
  { field: 'bl_no', label: 'BL no' },
  { field: 'seal_no', label: 'Seal no' },
  { field: 'consignee', label: 'Consignee' },
  { field: 'currency_hint', label: 'Currency' },
  { field: 'stated_total', label: 'Stated total' },
];

/** `PackingLine` + `PackingBlock`, same rule (`app/services/scm/packing_list_reader.py`).
 *  Required: item_code, qty. */
const PACKING_LIST_FIELDS: ImportMappingField[] = [
  { field: 'item_code', label: 'Item code' },
  { field: 'qty', label: 'Quantity' },
  { field: 'product_name', label: 'Product name' },
  { field: 'spec', label: 'Spec' },
  { field: 'cartons', label: 'Cartons' },
  { field: 'net_weight', label: 'Net weight' },
  { field: 'gross_weight', label: 'Gross weight' },
  { field: 'cbm_per_unit', label: 'CBM per unit' },
  { field: 'cbm_total', label: 'CBM total' },
  { field: 'unit_price', label: 'Unit price' },
  { field: 'amount', label: 'Amount' },
  { field: 'brand', label: 'Brand' },
  { field: 'remark', label: 'Remark' },
  { field: 'supplier_code', label: "Supplier's model number" },
  { field: 'container_no', label: 'Container no' },
  { field: 'material', label: 'Material' },
  { field: 'pcs_per_carton', label: 'Pieces per carton' },
  { field: 'carton_length_cm', label: 'Carton length (cm)' },
  { field: 'carton_width_cm', label: 'Carton width (cm)' },
  { field: 'carton_height_cm', label: 'Carton height (cm)' },
  { field: 'cbm_per_carton', label: 'CBM per carton' },
  { field: 'bl_no', label: 'BL no' },
  { field: 'seal_no', label: 'Seal no' },
  { field: 'consignee', label: 'Consignee' },
  { field: 'pi_number', label: 'PI number' },
  { field: 'invoice_date', label: 'Invoice date' },
];

/** `InventoryRow` (`app/services/scm/supplier_inventory_reader.py`) - the doc type
 *  `canonical_fields()` returns `[]` for TODAY (measured 24 Sep); B7 is what serves this
 *  list for real. Required: item_code, qty_packed. */
const SUPPLIER_INVENTORY_FIELDS: ImportMappingField[] = [
  { field: 'item_code', label: 'Item code' },
  { field: 'qty_packed', label: 'Packed quantity' },
  { field: 'qty_unfinished', label: 'Unfinished quantity' },
  { field: 'cbm_per_unit', label: 'CBM per unit' },
  { field: 'product_name', label: 'Product name' },
  { field: 'brand', label: 'Brand' },
  { field: 'spec', label: 'Spec' },
  { field: 'remark', label: 'Remark' },
  { field: 'model_no', label: "Supplier's model number" },
];

const FIELDS_BY_DOC_TYPE: Record<ImportMappingDocType, ImportMappingField[]> = {
  proforma_invoice: PROFORMA_INVOICE_FIELDS,
  packing_list: PACKING_LIST_FIELDS,
  supplier_inventory: SUPPLIER_INVENTORY_FIELDS,
};

const REQUIRED_BY_DOC_TYPE: Record<ImportMappingDocType, string[]> = {
  proforma_invoice: ['item_code', 'qty', 'unit_price'],
  packing_list: ['item_code', 'qty'],
  supplier_inventory: ['item_code', 'qty_packed'],
};

function mergedFields(docTypes: ImportMappingDocType[]): ImportMappingField[] {
  const seen = new Set<string>();
  const out: ImportMappingField[] = [];
  docTypes.forEach((dt) => {
    FIELDS_BY_DOC_TYPE[dt].forEach((f) => {
      if (!seen.has(f.field)) {
        seen.add(f.field);
        out.push(f);
      }
    });
  });
  return out;
}

function mergedRequired(docTypes: ImportMappingDocType[]): string[] {
  const seen = new Set<string>();
  docTypes.forEach((dt) =>
    REQUIRED_BY_DOC_TYPE[dt].forEach((f) => seen.add(f)),
  );
  return [...seen];
}

/** The NEW YANGGANG proforma invoice's own header row (measured 24 Sep, header row 15) -
 *  the ONE real header list this mock has. Sample values are placeholders (see file
 *  header comment); header TEXT is exactly what the plan's B2 measured, including the
 *  two-line headers and the merged carton-dimension columns already split into `[2]`/`[3]`
 *  the way B2's probe will synthesise them. */
const NEW_YANGGANG_HEADER_ROW = 15;
const NEW_YANGGANG_HEADERS: { header: string; samples: string[] }[] = [
  { header: '序号', samples: ['1', '2'] },
  { header: '工厂型号', samples: ['YG-2201', 'YG-2202'] },
  { header: '品名', samples: ['陶瓷洗手盆', '陶瓷坐便器'] },
  { header: '唛头', samples: ['N/M', 'N/M'] },
  { header: '客户型号', samples: ['SRT-1001', 'SRT-1002'] },
  { header: '规格尺寸', samples: ['500x400x850', '600x450x900'] },
  { header: '外箱/木托尺寸', samples: ['58', '62'] },
  { header: '外箱/木托尺寸 [2]', samples: ['45', '48'] },
  { header: '外箱/木托尺寸 [3]', samples: ['40', '42'] },
  { header: '单箱数量\n（个）', samples: ['1', '2'] },
  { header: '件数\n（件）', samples: ['120', '95'] },
  { header: '总数量\n（个）', samples: ['120', '190'] },
  { header: '单价\n（元）', samples: ['185.00', '210.00'] },
  { header: '金额\n（元）', samples: ['22200.00', '19950.00'] },
  { header: '方数', samples: ['0.104', '0.126'] },
  { header: '单个产品重量（ＫＧ)', samples: ['18.5', '21.0'] },
  { header: '货物净重', samples: ['2220.0', '1995.0'] },
  { header: '单箱/单板重量（KG)', samples: ['19.8', '22.4'] },
  { header: '总重量（KG）', samples: ['2376.0', '2128.0'] },
  { header: '备注', samples: ['含配件', '无'] },
];

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

/** Direct access to the two (three, counting the derived one) probe shapes, with no
 *  supplier memory and no delay - for a spec that wants a state without driving the flow
 *  that produces it (see file header comment). Not used by either dialog. */
export function buildMockProbe(
  state: 'fresh' | 'known' | 'oneNewColumn',
  docTypes: ImportMappingDocType[] = ['proforma_invoice'],
): ProbeImportMappingResult {
  const columns: ImportMappingColumn[] = NEW_YANGGANG_HEADERS.map((h, i) => {
    const known =
      state !== 'fresh' &&
      !(state === 'oneNewColumn' && i === NEW_YANGGANG_HEADERS.length - 1);
    return {
      position: i,
      header: h.header,
      samples: h.samples,
      field: known ? 'ignore' : null,
      source: known ? 'supplier' : 'none',
    };
  });
  return {
    probe: {
      header_row: NEW_YANGGANG_HEADER_ROW,
      columns,
      required_fields: mergedRequired(docTypes),
    },
    fields: mergedFields(docTypes),
  };
}

/** Test-only. A no-op now that `probeImportMapping`/`saveImportMapping` call the real
 *  API (Phase 2, B4/B5) - there is no in-memory supplier layout left to clear. Kept
 *  exported so a spec written against the Phase 1 mock's contract does not need editing
 *  to drop the call; real state lives on the server and is whatever the test's own
 *  fixture (a rolled-back savepoint) leaves it. */
export function __resetImportMappingMockForTests(): void {
  // Nothing to reset - see the doc comment above.
}
