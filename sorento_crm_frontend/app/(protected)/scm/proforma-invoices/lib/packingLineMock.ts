/**
 * Phase 1 mock store for supplier packing rows on the invoice (S2).
 *
 * A deterministic, in-memory prototype - the same shape `companies/lib/companyMock.ts`
 * uses - seeded from the invoice's OWN (real) lines, so the Packing tab, the Packed
 * column and the convert dialog all demonstrate every state (empty, fully matched,
 * mismatched, unmatched, dismissed) against real invoices already on file, with no
 * backend change. Removed whole once `USE_PACKING_LINE_MOCKS` in
 * `proformaInvoicePackingService.ts` flips to false.
 */
import type { ProformaInvoiceDetail, ProformaInvoiceLine } from '../../services/proformaInvoiceService';
import type {
  PackingLineMatchState,
  ProformaInvoicePackingFile,
  ProformaInvoicePackingLine,
} from '../types/packingLine.types';

interface MockInvoiceState {
  rows: ProformaInvoicePackingLine[];
  file: ProformaInvoicePackingFile | null;
}

const stateByInvoice = new Map<string, MockInvoiceState>();
let seq = 0;
function nextId(): string {
  seq += 1;
  return `mock-packing-row-${seq}`;
}

/** Which of the three demo scenarios an invoice gets - a stable hash of its id, so the
 *  SAME invoice always reads the same way across a session and a reload. */
function scenarioFor(invoiceId: string): 0 | 1 | 2 {
  let hash = 0;
  for (const ch of invoiceId) hash = (hash * 31 + ch.charCodeAt(0)) % 3;
  return hash as 0 | 1 | 2;
}

function packingRowFromLine(
  line: ProformaInvoiceLine,
  rowNo: number,
  overrides: Partial<ProformaInvoicePackingLine> = {},
): ProformaInvoicePackingLine {
  const cartons = line.cartons ?? null;
  const cbmTotal = line.cbm_total ?? null;
  return {
    id: nextId(),
    proforma_invoice_line_id: line.id,
    row_no: rowNo,
    item_code: line.item_code,
    supplier_code: line.item_code,
    description: line.description,
    product_id: line.product_id,
    product_set_id: line.product_set_id,
    qty: line.qty ?? 0,
    cartons,
    pcs_per_carton: cartons && line.qty ? Math.round((line.qty / cartons) * 100) / 100 : null,
    carton_length_cm: null,
    carton_width_cm: null,
    carton_height_cm: null,
    cbm_per_carton: cartons && cbmTotal ? cbmTotal / cartons : null,
    cbm_total: cbmTotal,
    net_weight: line.net_weight,
    gross_weight: line.gross_weight,
    total_net_weight: line.net_weight != null && line.qty != null ? line.net_weight * line.qty : null,
    total_gross_weight:
      line.gross_weight != null && line.qty != null ? line.gross_weight * line.qty : null,
    material: null,
    container_no: null,
    remark: null,
    match_state: 'matched',
    unmatched_reason: null,
    ...overrides,
  };
}

/** Roll-up (AC-B8): each line's cartons/cbm_total/net/gross = sums over its MATCHED rows. */
export function rollupForLine(
  lineId: string,
  rows: ProformaInvoicePackingLine[],
): { cartons: number | null; cbm_total: number | null; net_weight: number | null; gross_weight: number | null } {
  const forLine = rows.filter(
    (r) => r.proforma_invoice_line_id === lineId && r.match_state === 'matched',
  );
  if (!forLine.length) return { cartons: null, cbm_total: null, net_weight: null, gross_weight: null };
  const sum = (pick: (r: ProformaInvoicePackingLine) => number | null) => {
    const values = forLine.map(pick).filter((v): v is number => v != null);
    return values.length ? values.reduce((a, b) => a + b, 0) : null;
  };
  return {
    cartons: sum((r) => r.cartons),
    cbm_total: sum((r) => r.cbm_total),
    net_weight: sum((r) => r.total_net_weight),
    gross_weight: sum((r) => r.total_gross_weight),
  };
}

/** Packed quantity for a line (AC-B11): sum of MATCHED rows' qty, or null with no rows at
 *  all (the Lines tab shows "-" rather than 0, which would read as "packed nothing"). */
export function packedQtyForLine(lineId: string, rows: ProformaInvoicePackingLine[]): number | null {
  const forLine = rows.filter(
    (r) => r.proforma_invoice_line_id === lineId && r.match_state !== 'dismissed',
  );
  if (!forLine.length) return null;
  return forLine.reduce((sum, r) => sum + (r.qty ?? 0), 0);
}

function seed(invoice: ProformaInvoiceDetail): MockInvoiceState {
  const scenario = scenarioFor(invoice.id);
  if (scenario === 0 || invoice.lines.length === 0) {
    return { rows: [], file: null };
  }
  const file: ProformaInvoicePackingFile = {
    name: `${invoice.supplier_code ?? invoice.supplier_name ?? 'supplier'}-packing-list.xlsx`,
    uploaded_at: invoice.created_at ?? new Date().toISOString(),
  };
  const rows: ProformaInvoicePackingLine[] = [];
  // Every row names the invoice's own header container (S4, AC-D2c) - a real packing
  // list's rows agree with each other far more often than not, which is what lets the
  // convert dialog carry the container/seal/BL over rather than leaving them blank.
  const containerNo = invoice.container_no ?? null;
  invoice.lines.forEach((line, i) => {
    if (scenario === 1) {
      // Every line packed exactly as invoiced.
      rows.push(packingRowFromLine(line, i + 1, { container_no: containerNo }));
      return;
    }
    // scenario 2: mixed - the first line ships short (Packed < Qty, D8 mismatch badge),
    // the rest agree, one extra dismissed row and one extra unmatched row round it out.
    if (i === 0 && line.qty) {
      rows.push(
        packingRowFromLine(line, i + 1, { qty: Math.max(0, line.qty - 5), container_no: containerNo }),
      );
    } else {
      rows.push(packingRowFromLine(line, i + 1, { container_no: containerNo }));
    }
  });
  if (scenario === 2) {
    rows.push(
      packingRowFromLine(
        { ...invoice.lines[0], id: '', item_code: 'SPARE-01', description: '备用配件', qty: 2, cartons: 1 },
        rows.length + 1,
        {
          proforma_invoice_line_id: null,
          product_id: null,
          product_set_id: null,
          match_state: 'unmatched',
          unmatched_reason: 'not_on_invoice',
        },
      ),
    );
    rows.push(
      packingRowFromLine(
        { ...invoice.lines[0], id: '', item_code: 'OLD-CODE-1', description: '旧编码', qty: 1, cartons: 1 },
        rows.length + 1,
        {
          proforma_invoice_line_id: null,
          product_id: null,
          product_set_id: null,
          match_state: 'dismissed',
        },
      ),
    );
  }
  return { rows, file };
}

export function getMockPackingState(invoice: ProformaInvoiceDetail): MockInvoiceState {
  let state = stateByInvoice.get(invoice.id);
  if (!state) {
    state = seed(invoice);
    stateByInvoice.set(invoice.id, state);
  }
  return state;
}

export function mockSetMatchState(invoiceId: string, rowId: string, matchState: PackingLineMatchState): void {
  const state = stateByInvoice.get(invoiceId);
  if (!state) return;
  state.rows = state.rows.map((r) => (r.id === rowId ? { ...r, match_state: matchState } : r));
}

/** "Attach packing list" from an empty PI (AC-B10) - the Phase 1 mock re-seeds the
 *  invoice as if scenario 1 (fully matched) just arrived, since no real file is parsed
 *  client-side. Phase 2 replaces this with the real apply response. */
export function mockAttachPackingList(invoice: ProformaInvoiceDetail): void {
  const file: ProformaInvoicePackingFile = {
    name: `${invoice.supplier_code ?? invoice.supplier_name ?? 'supplier'}-packing-list.xlsx`,
    uploaded_at: new Date().toISOString(),
  };
  const rows = invoice.lines.map((line, i) =>
    packingRowFromLine(line, i + 1, { container_no: invoice.container_no ?? null }),
  );
  stateByInvoice.set(invoice.id, { rows, file });
}
