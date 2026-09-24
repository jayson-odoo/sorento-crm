/**
 * ============================================================================
 * Import column mapper (S4/S5) - feature service
 * ============================================================================
 * Layering: ImportColumnMapper / PlanContainerDialog / SupplierDocumentsUploadDialog ->
 * THIS service -> (Phase 2) lib/api-client -> backend.
 *
 * ── PHASE 1 MOCK (PRINCIPLES.md phase order; PLAN-import-column-mapper-24sep.md B4/B5) ──
 * The two backend endpoints below do not exist yet - this lane's Phase 1 builds every
 * screen against a MOCK of them, per the plan's own slice order ("F1 ... against a mocked
 * probe, F2+F3+F4"). Phase 2 swaps `probeImportMapping`/`saveImportMapping` for real
 * `apiFetch` calls; every OTHER export here (the shapes, the field lists, the header list)
 * is the contract Phase 2 keeps - only the two functions' bodies change.
 *
 * `probeImportMapping` stands in for:
 *   POST /api/v1/scm/import-mapping/probe  (multipart file, supplier_id, doc_type,
 *   optional header_row) -> {header_row, columns:[{position, header, samples, field,
 *   source}], required_fields, fields:[{field,label}]}                            (B4)
 *
 * `saveImportMapping` stands in for:
 *   POST /api/v1/scm/import-mapping/save  {supplier_id, doc_type, mappings:[{header,
 *   field}]} - upserts SUPPLIER-scoped rows, replacing this supplier's earlier choice for
 *   the same header rather than accumulating (AC-M6). `field: "ignore"` is a saved choice
 *   (G2/AC-M7), never omitted.                                                     (B5)
 *
 * A combined file (one sheet read as BOTH a proforma invoice and a packing list, grill G4
 * / AC-M13) probes and saves against an ARRAY of doc types rather than one - the mock
 * merges their field lists and required fields into the ONE section the dialog shows,
 * and records the pick under one shared key. Phase 2's real save still has to write rows
 * under both `import_field_alias.doc_type`s (G4); this mock does not model that split
 * (there is only one doc type table row shape here, not two) - noted so Phase 2 does not
 * assume the split already works.
 *
 * ── WHAT IS REAL, WHAT IS MADE UP ──────────────────────────────────────────────────────
 * The header TEXTS below are measured (PLAN "Measured" section, 24 Sep): the NEW YANGGANG
 * proforma invoice's own header row, header row 15, with the two-line headers
 * (`件数\n（件）`) and the merged `外箱/木托尺寸` columns exactly as the plan's B2 will
 * synthesise them (`外箱/木托尺寸 [2]`, `[3]`). The SAMPLE VALUES under them are made up -
 * nobody has read the real cells yet, only the header row - so they are plausible
 * placeholders, not the supplier's own figures. Nothing downstream should read a sample
 * value as fact.
 *
 * ── THE TWO STATES A CALLER SEES ────────────────────────────────────────────────────────
 * The mock behaves like a real supplier-scoped memory, in-process: the FIRST probe for a
 * (supplier, doc types) pair returns every column unresolved (`field: null,
 * source: 'none'`) - the golden path, AC-M9/AC-E1. Once `saveImportMapping` has been
 * called for that pair, every LATER probe returns whatever was saved (`source: 'supplier'`)
 * - the collapsed path, AC-M11/AC-E2 - and a column never saved (because the operator left
 * it unpicked) keeps reading as unresolved forever after, which is exactly how AC-M12's
 * "one new column" state arises from ordinary use: map 19 of 20 columns, Test, reopen -
 * the 20th is still `source: 'none'` and the mapper expands with it highlighted.
 * `buildMockProbe` below exposes the same two states directly (no supplier memory, no
 * async) for a caller - a vitest spec - that wants one without driving the flow that
 * produces it.
 * ============================================================================
 */

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

function normalizeHeaderKey(header: string): string {
  // A loose stand-in for the backend's own `normalize_header` (NFKC + strip to
  // alphanumeric/CJK) - good enough to treat `件数\n（件）` and `件数（件）` as the same
  // key without importing the real normaliser into the browser bundle.
  return header
    .normalize('NFKC')
    .toLowerCase()
    .replace(/[^0-9a-z㐀-鿿]+/g, '');
}

/** In-memory stand-in for the `import_field_alias` rows a real save would write -
 *  supplier + doc-type-set scoped, exactly like the real table (R1/R2). Module-level on
 *  purpose: the whole point is that it survives closing and reopening a dialog within the
 *  same browser session, the way a real save would. `__resetImportMappingMockForTests`
 *  clears it between vitest specs. */
const savedLayouts = new Map<string, Record<string, string>>();

function layoutKey(
  supplierId: string,
  docTypes: ImportMappingDocType[],
): string {
  return `${supplierId}::${[...docTypes].sort().join('+')}`;
}

async function settle<T>(value: T): Promise<T> {
  // A real request has a round trip; a busy state that resolves synchronously reads as a
  // bug (nothing ever shows the Testing/Reading spinner) the moment somebody removes an
  // `await` upstream expecting one.
  await new Promise((resolve) => setTimeout(resolve, 30));
  return value;
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
  supplierId,
  docTypes,
  headerRow,
}: ProbeImportMappingRequest): Promise<ProbeImportMappingResult> {
  const saved = savedLayouts.get(layoutKey(supplierId, docTypes)) ?? {};
  const columns: ImportMappingColumn[] = NEW_YANGGANG_HEADERS.map((h, i) => {
    const field = saved[normalizeHeaderKey(h.header)] ?? null;
    return {
      position: i,
      header: h.header,
      samples: h.samples,
      field,
      source: field ? 'supplier' : 'none',
    };
  });
  return settle({
    probe: {
      header_row: headerRow ?? NEW_YANGGANG_HEADER_ROW,
      columns,
      required_fields: mergedRequired(docTypes),
    },
    fields: mergedFields(docTypes),
  });
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
  const key = layoutKey(supplierId, docTypes);
  const next = { ...(savedLayouts.get(key) ?? {}) };
  mappings.forEach((m) => {
    next[normalizeHeaderKey(m.header)] = m.field;
  });
  savedLayouts.set(key, next);
  await settle(undefined);
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

/** Test-only: clears the module-level supplier memory between specs. */
export function __resetImportMappingMockForTests(): void {
  savedLayouts.clear();
}
