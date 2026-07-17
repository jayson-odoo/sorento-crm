/**
 * ============================================================================
 * SCM M4 Slice B — DECISION + PO-FLOW DETERMINISTIC MOCK STORE  (Phase 1 only)
 * ============================================================================
 * A single store shared by the reorder decision layer (Accept / Adjust / Reject)
 * and the Purchase Orders list. It exists ONLY so the Phase-1 prototype can
 * demonstrate the full loop — accept a recommendation → a consolidated draft PO
 * appears in the PO list → bulk Confirm flips it to active (now on-order) →
 * create a GR from the active PO — WITHOUT any backend.
 *
 * Phase 2 deletes this file and flips `USE_SLICE_B_MOCKS` to false in the two
 * services (`reorder/services/decisionService.ts`,
 * `services/purchaseOrderService.ts`); the same operations then hit the real
 * endpoints documented at the top of those files.
 *
 * State is persisted in `sessionStorage` (client only) so an accept on the
 * reorder page is visible on the PO list even across a full page reload; a fresh
 * browser session starts from the seed. Deterministic by construction: no
 * `Math.random`, no `Date.now` — PO / GR numbers come from monotonic counters.
 * ============================================================================
 */
import type { PurchaseOrder } from '../types/scm.types';
import type {
  AcceptResult,
  BulkAcceptResult,
  RecDecision,
} from '../reorder/types/decisions.types';
import type { ReorderRecommendation } from '../reorder/types/reorder.types';

/** Phase-1 flag — mirrors `USE_M4_MOCKS` (Slice A). Both flip to false in Phase 2. */
export const USE_SLICE_B_MOCKS = false;

// v2: v1 persisted state predates `poSeq`, so a stale session left `poSeq` undefined
// → `undefined + 1 = NaN` → "PO-2026-0NaN". Bumping the key abandons that state; load()
// also now merges over freshState() defaults so any missing field is backfilled.
const STORAGE_KEY = 'scm_copilot_mock_v2';
/** Fixed "today" — keeps order/expected dates deterministic (no `new Date`). */
const TODAY = '2026-07-16';

/** Statuses that count as incoming supply (mirror of `scm.on_order_v`). */
const ON_ORDER_STATUSES = new Set(['active', 'confirmed', 'partially_received', 'received']);

function computeOnOrder(status: PurchaseOrder['status']): boolean {
  return ON_ORDER_STATUSES.has(status);
}

interface StoreState {
  pos: PurchaseOrder[];
  decisions: Record<string, RecDecision>;
  draftSeq: number;
  grSeq: number;
  lineSeq: number;
  /** Running canonical PO sequence for THIS year — seed max is 0148. On Confirm a
   *  draft is renumbered to `PO-2026-####` from here (M4-D6, numbering rule). */
  poSeq: number;
}

// ── Seed: a couple of pre-existing POs so the list is never empty on first load.
function seedPos(): PurchaseOrder[] {
  return [
    {
      id: 'po-seed-1',
      po_number: 'PO-2026-0148',
      supplier_code: 'SUP-APX',
      supplier_name: 'Apex Auto Parts',
      warehouse_code: 'WH-KL',
      warehouse_name: 'Kuala Lumpur DC',
      status: 'active',
      order_date: '2026-07-02',
      expected_date: '2026-07-19',
      total_qty: 220,
      line_count: 2,
      lines: [
        { id: 'l1', sku: 'BRK-620', product_name: 'Brake Pad Set 620', qty_ordered: 160, qty_received: 0, uom: 'unit' },
        { id: 'l2', sku: 'FLT-120', product_name: 'Oil Filter 120', qty_ordered: 60, qty_received: 0, uom: 'unit' },
      ],
      created_at: '2026-07-02T02:00:00',
      is_on_order: true,
      source: 'manual',
      gr_reference: null,
    },
    {
      id: 'po-seed-2',
      po_number: 'PO-2026-0141',
      supplier_code: 'SUP-VLT',
      supplier_name: 'Volt Electricals',
      warehouse_code: 'WH-KL',
      warehouse_name: 'Kuala Lumpur DC',
      status: 'partially_received',
      order_date: '2026-06-25',
      expected_date: '2026-07-12',
      total_qty: 90,
      line_count: 1,
      lines: [
        { id: 'l3', sku: 'BAT-770', product_name: 'Battery 77Ah', qty_ordered: 90, qty_received: 40, uom: 'unit' },
      ],
      created_at: '2026-06-25T02:00:00',
      is_on_order: true,
      source: 'manual',
      gr_reference: null,
    },
  ];
}

/** Canonical PO number for the current year from the running sequence. */
const PO_YEAR = 2026;
function nextPoNumber(): string {
  // Guard against a corrupted/missing seq (stale persisted state) → never "0NaN".
  if (!Number.isFinite(state.poSeq)) state.poSeq = 148;
  state.poSeq += 1;
  return `PO-${PO_YEAR}-${String(state.poSeq).padStart(4, '0')}`;
}

function freshState(): StoreState {
  return { pos: seedPos(), decisions: {}, draftSeq: 0, grSeq: 8140, lineSeq: 0, poSeq: 148 };
}

function load(): StoreState {
  if (typeof window === 'undefined') return freshState();
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    // Merge over defaults so any field absent from an older persisted shape is backfilled
    // (JSON serializes NaN as null, so also coerce a null/undefined poSeq back to the default).
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<StoreState>;
      const merged = { ...freshState(), ...parsed };
      if (!Number.isFinite(merged.poSeq)) merged.poSeq = 148;
      return merged;
    }
  } catch {
    /* fall through to fresh */
  }
  return freshState();
}

let state: StoreState = load();

function persist() {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* sessionStorage unavailable — in-memory state still works for the session */
  }
}

function nextDraftNumber(): string {
  state.draftSeq += 1;
  return `PO-DRAFT-${String(state.draftSeq).padStart(4, '0')}`;
}

function recomputeTotals(po: PurchaseOrder) {
  po.line_count = po.lines.length;
  po.total_qty = po.lines.reduce((sum, l) => sum + l.qty_ordered, 0);
}

/** Find (or create) the open draft PO for a supplier — consolidation (M4-D4). */
function draftForSupplier(rec: ReorderRecommendation, supplierCode: string, supplierName: string): PurchaseOrder {
  let po = state.pos.find((p) => p.status === 'draft_recommendation' && p.supplier_code === supplierCode);
  if (!po) {
    po = {
      id: `po-draft-${state.draftSeq + 1}`,
      po_number: nextDraftNumber(),
      supplier_code: supplierCode,
      supplier_name: supplierName,
      warehouse_code: rec.warehouse_code,
      warehouse_name: rec.warehouse_name,
      status: 'draft_recommendation',
      order_date: TODAY,
      expected_date: null,
      total_qty: 0,
      line_count: 0,
      lines: [],
      created_at: `${TODAY}T03:00:00`,
      is_on_order: false,
      source: 'recommendation',
      gr_reference: null,
    };
    state.pos = [po, ...state.pos];
  }
  return po;
}

/** Add / replace the line for a recommendation's SKU inside a draft PO. */
function upsertLine(po: PurchaseOrder, sku: string, productName: string, qty: number) {
  const existing = po.lines.find((l) => l.sku === sku);
  if (existing) {
    existing.qty_ordered = qty;
    existing.product_name = productName;
  } else {
    state.lineSeq += 1;
    po.lines.push({
      id: `dl-${state.lineSeq}`,
      sku,
      product_name: productName,
      qty_ordered: qty,
      qty_received: 0,
      uom: 'unit',
    });
  }
  recomputeTotals(po);
}

/** Remove a recommendation's line from its draft PO (used when a prior
 *  accept/adjust is later rejected). Drops the draft entirely if it empties. */
function removeLineForRec(rec: ReorderRecommendation) {
  const prev = state.decisions[rec.id];
  if (!prev?.draft_po_id) return;
  const po = state.pos.find((p) => p.id === prev.draft_po_id);
  if (!po || po.status !== 'draft_recommendation') return;
  po.lines = po.lines.filter((l) => l.sku !== rec.sku);
  if (po.lines.length === 0) {
    state.pos = state.pos.filter((p) => p.po_number !== po.po_number);
  } else {
    recomputeTotals(po);
  }
}

function cloneDecisions(): RecDecision[] {
  return Object.values(state.decisions).map((d) => ({ ...d }));
}

function clonePos(): PurchaseOrder[] {
  return state.pos.map((p) => ({ ...p, lines: p.lines.map((l) => ({ ...l })) }));
}

// ── Decision operations ──────────────────────────────────────────────────────

export function mockListDecisions(): RecDecision[] {
  return cloneDecisions();
}

export function mockAcceptRecommendation(rec: ReorderRecommendation): AcceptResult {
  removeLineForRec(rec);
  const supplier = rec.supplier;
  const supplierCode = supplier?.supplier_code ?? 'SUP-UNKNOWN';
  const supplierName = supplier?.supplier_name ?? 'Unassigned supplier';
  const po = draftForSupplier(rec, supplierCode, supplierName);
  upsertLine(po, rec.sku, rec.product_name, rec.order_qty ?? 0);
  state.decisions[rec.id] = {
    recommendation_id: rec.id,
    status: 'accepted',
    override_qty: null,
    override_supplier_code: null,
    override_supplier_name: null,
    reason_text: null,
    draft_po_number: po.po_number,
    draft_po_id: po.id,
  };
  persist();
  return { draft_po_number: po.po_number, draft_po_id: po.id, supplier_name: supplierName };
}

export function mockAdjustRecommendation(
  rec: ReorderRecommendation,
  payload: { override_qty: number; override_supplier_code: string | null; reason_text: string },
): AcceptResult {
  removeLineForRec(rec);
  const chosen =
    (payload.override_supplier_code
      ? rec.alternatives.find((s) => s.supplier_code === payload.override_supplier_code)
      : null) ?? rec.supplier;
  const supplierCode = chosen?.supplier_code ?? 'SUP-UNKNOWN';
  const supplierName = chosen?.supplier_name ?? 'Unassigned supplier';
  const po = draftForSupplier(rec, supplierCode, supplierName);
  upsertLine(po, rec.sku, rec.product_name, payload.override_qty);
  state.decisions[rec.id] = {
    recommendation_id: rec.id,
    status: 'adjusted',
    override_qty: payload.override_qty,
    override_supplier_code: payload.override_supplier_code,
    override_supplier_name: supplierName,
    reason_text: payload.reason_text,
    draft_po_number: po.po_number,
    draft_po_id: po.id,
  };
  persist();
  return { draft_po_number: po.po_number, draft_po_id: po.id, supplier_name: supplierName };
}

export function mockRejectRecommendation(rec: ReorderRecommendation, reasonText: string): void {
  removeLineForRec(rec);
  state.decisions[rec.id] = {
    recommendation_id: rec.id,
    status: 'dismissed',
    override_qty: null,
    override_supplier_code: null,
    override_supplier_name: null,
    reason_text: reasonText,
    draft_po_number: null,
    draft_po_id: null,
  };
  persist();
}

/** Bulk Accept over a set of recommendations (funded, M4-D9). Consolidates per
 *  supplier and reports how many distinct draft POs were touched. */
export function mockBulkAccept(recs: ReorderRecommendation[]): BulkAcceptResult {
  const touched = new Set<string>();
  for (const rec of recs) {
    const res = mockAcceptRecommendation(rec);
    if (res.draft_po_number) touched.add(res.draft_po_number);
  }
  return { accepted_count: recs.length, po_count: touched.size };
}

/** Bulk Reject over a set of recommendations with one shared reason (M4-D9). */
export function mockBulkReject(recs: ReorderRecommendation[], reasonText: string): number {
  for (const rec of recs) mockRejectRecommendation(rec, reasonText);
  return recs.length;
}

// ── PO operations ────────────────────────────────────────────────────────────

export function mockListPurchaseOrders(): PurchaseOrder[] {
  return clonePos();
}

/** Single PO by stable id (drives the detail page). Returns a deep clone. */
export function mockGetPurchaseOrder(id: string): PurchaseOrder | null {
  const po = state.pos.find((p) => p.id === id);
  return po ? { ...po, lines: po.lines.map((l) => ({ ...l })) } : null;
}

/** Confirm draft POs → active (M4-D6). Only `draft_recommendation` rows flip and
 *  each is RENUMBERED from its provisional `PO-DRAFT-####` to the canonical
 *  `PO-YYYY-####` running sequence (the backend assigns this at confirm time via
 *  the PO numbering rule — see alembic 274). Any decision referencing the PO is
 *  re-pointed to the new number so the results hyperlink stays correct. Returns
 *  how many were confirmed. */
export function mockConfirmPurchaseOrders(ids: string[]): number {
  let confirmed = 0;
  for (const id of ids) {
    const po = state.pos.find((p) => p.id === id);
    if (po && po.status === 'draft_recommendation') {
      po.status = 'active';
      po.po_number = nextPoNumber();
      po.is_on_order = computeOnOrder('active');
      po.expected_date = po.expected_date ?? '2026-07-30';
      // Keep any recommendation decision's displayed PO number in sync.
      for (const d of Object.values(state.decisions)) {
        if (d.draft_po_id === po.id) d.draft_po_number = po.po_number;
      }
      confirmed += 1;
    }
  }
  persist();
  return confirmed;
}

/** Create a goods receipt from an active PO (M4-D6): stamp received = ordered on
 *  every line, flip to received, and return the GR reference. */
export function mockCreateGr(id: string): { gr_reference: string } | null {
  const po = state.pos.find((p) => p.id === id);
  if (!po || po.status === 'draft_recommendation' || po.status === 'cancelled') return null;
  state.grSeq += 1;
  const grRef = `GR-${state.grSeq}`;
  po.lines.forEach((l) => {
    l.qty_received = l.qty_ordered;
  });
  po.status = 'received';
  po.is_on_order = computeOnOrder('received');
  po.gr_reference = grRef;
  persist();
  return { gr_reference: grRef };
}

/** TEST/DEV ONLY — reset the store to its seed. */
export function __resetCopilotMockStore() {
  state = freshState();
  persist();
}
