/**
 * SCM M8 — CashResultsGrid (slice C + drills). The one-table/two-section plan grid
 * with click-to-explain drills, inline edit + decisions, and row-click detail.
 *   M8-A2/A3 DaysCover drill RECONCILIATION: finite frozen rate → net/rate=days;
 *            days_cover=null deficit → undefined copy, NO "/ 0"; rate<=0 → no-demand;
 *            CV unavailable → dash; header spells "Coefficient of variation" not "CV".
 *   M8-A1 Net drill lists committed SOs · M8-C5 inline edit reason-gates-save + live cash
 *   M8-C6 Accept / Fund / Reject inline · M8-C10 row-click detail vs control click targets
 *   M8-C11 Warehouse column
 *
 * The lazy drills (useDrills) + SearchableSelect are mocked so the popovers are
 * deterministic in jsdom.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReorderRecommendation, SupplierChoice } from '../types/reorder.types';
import { recToPlanRow, type M8PlanRow } from '../lib/planRow';

// ── jsdom polyfills Radix Popover needs ──────────────────────────────────────
class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);
Element.prototype.setPointerCapture = Element.prototype.setPointerCapture ?? (() => {});
Element.prototype.releasePointerCapture = Element.prototype.releasePointerCapture ?? (() => {});
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

// Native-select stand-in for the supplier swap (real one is a Radix + cmdk combobox).
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value, onChange, options, placeholder,
  }: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; placeholder?: string }) => (
    <select aria-label={placeholder ?? 'Supplier'} value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => (<option key={o.value} value={o.value}>{o.label}</option>))}
    </select>
  ),
}));

// Lazy drills — return controlled data so the drill popovers render deterministically.
const useExplainNet = vi.fn();
const useExplainDemand = vi.fn();
vi.mock('../hooks/useDrills', () => ({
  useExplainNet: (...a: unknown[]) => useExplainNet(...a),
  useExplainDemand: (...a: unknown[]) => useExplainDemand(...a),
}));

import { CashResultsGrid } from './CashResultsGrid';

const beta: SupplierChoice = {
  supplier_code: 'SUP-BETA', supplier_name: 'Beta Supplies', unit_cost: 80,
  lead_time_days: 21, composite_score: 80, is_primary: false,
};

function rec(over: Partial<ReorderRecommendation> = {}): ReorderRecommendation {
  return {
    id: 'rec-1', type: 'buy', sku: 'CW-BASIN-450', product_name: 'Ceramic Wash Basin 450mm',
    abc_class: 'A', xyz_class: 'X', warehouse_code: 'WH-KL', warehouse_name: 'Kuala Lumpur DC',
    product_id: 'prod-1', warehouse_id: 'wh-1', is_network: false, allocation: null,
    order_qty: 100, recommended_qty: 100, reorder_point: 60, min_qty: null, max_qty: null,
    order_up_to: 200, net_position: 80, days_of_cover: 20, reason: 'reorder_point',
    reason_label: 'net ≤ ROP', confidence: 'high', sample_size: 40,
    supplier: { supplier_code: 'SUP-ACME', supplier_name: 'Acme Sanitary', unit_cost: 100, lead_time_days: 14, composite_score: 88, is_primary: true },
    alternatives: [beta], is_exception: false, disposition_action: null, transfer_flag: null,
    forecast_daily_demand: 4, lead_time_days: 14, lead_time_source: 'measured', safety_stock: 20,
    safety_stock_method: 'fixed_days', safety_stock_fallback: null, service_level: 0.95, safety_days: 7,
    review_days: 30, moq: 10, order_multiple: 5, policy_type: 'reorder_point', supplier_selection: 'primary',
    unit_cost: 100, cash_impact: 10000, rank: 1, rank_score: 0.9, funding_status: null,
    days_to_stockout: 20, rank_factors: [],
    ...over,
  };
}

function renderGrid(row: M8PlanRow, over: Partial<React.ComponentProps<typeof CashResultsGrid>> = {}) {
  const onFund = vi.fn();
  const onReject = vi.fn();
  const onEdit = vi.fn();
  const onOpenDetail = vi.fn();
  render(
    <CashResultsGrid
      within={[row]}
      over={[]}
      decisions={{ [row.id]: null }}
      editedIds={new Set()}
      budgetHeader={<div>budget-header</div>}
      handlers={{ onFund, onReject, onEdit }}
      onOpenDetail={onOpenDetail}
      {...over}
    />,
  );
  return { onFund, onReject, onEdit, onOpenDetail };
}

const NET_OK = {
  data: { on_hand: 100, on_order: 40, committed: 60, net: 80, committed_sos: [{ so_number: 'SO-2026-0007', qty: 60, customer_name: 'Bina Jaya', order_date: '2026-07-10' }] },
  isLoading: false, isError: false,
};
const demand = (cv: number | null) => ({
  data: { product_id: 'prod-1', warehouse_id: 'wh-1', avg_daily_demand: 99, demand_cv: cv, method: 'moving_average', demand_dos: [{ order_id: 'ord-1', do_number: 'DO-2026-0100', order_date: '2026-07-01', qty_out: 25 }], buckets: [] },
  isLoading: false, isError: false,
});

beforeEach(() => {
  useExplainNet.mockReset().mockReturnValue(NET_OK);
  useExplainDemand.mockReset().mockReturnValue(demand(0.34));
});

/** Normalised full-document text (collapses the JSX whitespace between spans). */
const docText = () => (document.body.textContent ?? '').replace(/\s+/g, ' ');

describe('CashResultsGrid — layout (M8-C11)', () => {
  it('renders the Warehouse column header + the row’s human warehouse label', () => {
    renderGrid(recToPlanRow(rec()));
    expect(screen.getByText('Warehouse')).toBeInTheDocument();
    expect(screen.getByText('Kuala Lumpur DC')).toBeInTheDocument();
  });
});

describe('CashResultsGrid — Days cover drill reconciliation (M8-A2/A3)', () => {
  it('finite frozen rate → arithmetic net/rate=days reconciles; CV spelled in full', () => {
    // net 80, frozen rate 4/day, days_cover 20 → "80 / 4.0 = 20 days".
    renderGrid(recToPlanRow(rec({ net_position: 80, forecast_daily_demand: 4, days_of_cover: 20 })));
    fireEvent.click(screen.getByLabelText('Explain days cover'));
    expect(screen.getByText('Days cover = 20')).toBeInTheDocument();
    // arithmetic uses the FROZEN rate (4), not the live explain/demand window (99)
    expect(docText()).toContain('80 / 4.0 = 20 days');
    expect(docText()).not.toContain('99');
    // full metric name, never the ambiguous "CV"
    expect(screen.getByText('Coefficient of variation')).toBeInTheDocument();
    // navigable DO list (M8-A2) — the demand basis is DOs, not raw buckets
    expect(screen.getByText('DO-2026-0100')).toBeInTheDocument();
  });

  it('days_cover=null on a DEFICIT net → undefined copy, never divides by zero (M8-A3)', () => {
    renderGrid(recToPlanRow(rec({ net_position: -30, days_of_cover: null, forecast_daily_demand: 4 })));
    fireEvent.click(screen.getByLabelText('Explain days cover'));
    expect(screen.getByText(/Days cover = undefined/i)).toBeInTheDocument();
    expect(screen.getByText(/Net is a deficit/i)).toBeInTheDocument();
    // the arithmetic line is suppressed — no "/ 0" ever printed
    expect(docText()).not.toContain('/ 0');
  });

  it('rate<=0 (no measurable demand) → no-demand copy, no division (M8-A3)', () => {
    renderGrid(recToPlanRow(rec({ net_position: 80, days_of_cover: null, forecast_daily_demand: 0 })));
    fireEvent.click(screen.getByLabelText('Explain days cover'));
    expect(screen.getByText(/No measurable daily demand/i)).toBeInTheDocument();
    expect(docText()).not.toContain('/ 0');
  });

  it('CV unavailable → renders a dash, not a fabricated 0', () => {
    useExplainDemand.mockReturnValue(demand(null));
    renderGrid(recToPlanRow(rec()));
    fireEvent.click(screen.getByLabelText('Explain days cover'));
    expect(screen.getByText('Coefficient of variation')).toBeInTheDocument();
    // the CV value cell is an em dash (—), never 0.00
    expect(docText()).not.toContain('0.00');
  });
});

describe('CashResultsGrid — Net drill lists committed SOs (M8-A1)', () => {
  it('shows on-hand/on-order/committed + the open SO behind committed', () => {
    renderGrid(recToPlanRow(rec()));
    fireEvent.click(screen.getByLabelText('Explain net'));
    expect(screen.getByText('SO-2026-0007')).toBeInTheDocument();
    expect(screen.getByText('Bina Jaya')).toBeInTheDocument();
    expect(screen.getByText('Open sales orders')).toBeInTheDocument();
  });
});

describe('CashResultsGrid — inline edit (M8-C5)', () => {
  it('reason-gates Save, shows live cash, and emits the supplier CODE on save', () => {
    const { onEdit } = renderGrid(recToPlanRow(rec()));
    // open the qty edit popover
    fireEvent.click(screen.getByTitle('Click to adjust qty / supplier'));
    const save = screen.getByRole('button', { name: 'Save' });
    // Save is blocked until a reason is entered (M8-C5)
    expect(save).toBeDisabled();
    // switch supplier → live cash preview recomputes off the swapped unit cost (80)
    fireEvent.change(screen.getByLabelText('Select supplier'), { target: { value: 'SUP-BETA' } });
    fireEvent.change(screen.getByLabelText(/Reason/i), { target: { value: 'cheaper supplier' } });
    expect(save).toBeEnabled();
    fireEvent.click(save);
    expect(onEdit).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'rec-1' }),
      { order_qty: 100, supplier_code: 'SUP-BETA' },
      'cheaper supplier',
    );
  });
});

describe('CashResultsGrid — inline decisions (M8-C6)', () => {
  it('Accept funds a within-budget row', () => {
    const { onFund } = renderGrid(recToPlanRow(rec()));
    fireEvent.click(screen.getByRole('button', { name: 'Accept' }));
    expect(onFund).toHaveBeenCalledWith(expect.objectContaining({ id: 'rec-1' }));
  });

  it('an Over-budget row has NO call-to-action — no Accept / Reject / Fund (M8-F13)', () => {
    const row = recToPlanRow(rec());
    renderGrid(row, { within: [], over: [row] });
    // M8-F13: over-budget rows show only data + a drag handle; the ONLY way to fund
    // one is to drag it up into Within budget. No decision buttons at all.
    expect(screen.queryByRole('button', { name: 'Fund' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Accept' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull();
    // the only funding affordance in the Decision cell is a drag hint
    expect(screen.getByText('Drag up to fund')).toBeInTheDocument();
  });

  it('Reject requires a reason before the destructive confirm fires', () => {
    const { onReject } = renderGrid(recToPlanRow(rec()));
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }));
    const confirm = screen.getAllByRole('button', { name: 'Reject' }).find((b) => (b as HTMLButtonElement).className.includes('destructive'))!;
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByPlaceholderText(/Reason for rejecting/i), { target: { value: 'overstocked' } });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    expect(onReject).toHaveBeenCalledWith(expect.objectContaining({ id: 'rec-1' }), 'overstocked');
  });
});

describe('CashResultsGrid — reject keeps the row IN PLACE (M8-F1 REVISED)', () => {
  it('a rejected WITHIN row stays in the Within section with a "Rejected" chip + Accept (undo)', () => {
    const row = recToPlanRow(rec());
    // The rejected row is passed in the WITHIN section (reject no longer moves it to Over).
    const { onFund } = renderGrid(row, {
      within: [row],
      over: [],
      decisions: { [row.id]: 'rejected' },
    });
    // the row is NOT removed — its product name still renders
    expect(screen.getByText('Ceramic Wash Basin 450mm')).toBeInTheDocument();
    // a "Rejected" chip marks the state (parity with "Accepted")
    expect(screen.getByText('Rejected')).toBeInTheDocument();
    // the restore control is now "Accept" (undo) — the old "Fund" button is gone
    expect(screen.queryByRole('button', { name: 'Fund' })).toBeNull();
    const accept = screen.getByRole('button', { name: 'Accept' });
    fireEvent.click(accept);
    expect(onFund).toHaveBeenCalledWith(expect.objectContaining({ id: 'rec-1' }));
  });
});

describe('CashResultsGrid — confirmed line shows a PO link (M8-F8 / M8-F9)', () => {
  it('a line with a draft PO shows "PO created" + a link to the PO, no Accept/Reject', () => {
    const row = recToPlanRow(rec());
    renderGrid(row, {
      within: [row],
      over: [],
      decisions: { [row.id]: 'accepted' },
      poByRow: { [row.id]: { po_number: 'PO-2026-0007', po_id: 'po-abc' } },
    });
    // the confirmed state replaces the Accept/Reject controls
    expect(screen.getByText('PO created')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Accept' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull();
    // and links to the PO detail page by its human number (never a raw UUID)
    const link = screen.getByRole('link', { name: 'PO-2026-0007' });
    expect(link).toHaveAttribute('href', '/scm/purchase-orders/po-abc');
  });
});

describe('CashResultsGrid — supplier cell never overlaps Decision (M8-F3)', () => {
  it('renders the supplier name truncated inside an overflow-hidden cell', () => {
    renderGrid(recToPlanRow(rec()));
    const supplierName = screen.getByText('Acme Sanitary');
    // truncation stops the supplier text bleeding into the Decision column
    expect(supplierName.className).toContain('truncate');
    // the cell itself clips overflow so the fixed grid columns can never collide
    expect(supplierName.closest('.overflow-hidden')).not.toBeNull();
  });
});

describe('CashResultsGrid — order-qty drill shows the ROP formula (M8-A4 / M8-F5)', () => {
  it('renders "ROP = safety stock + demand rate x lead time" with the frozen inputs', () => {
    // safety_stock 20, forecast_daily_demand 4, supplier lead 14, reorder_point 60.
    renderGrid(recToPlanRow(rec()));
    fireEvent.click(screen.getByLabelText('Explain order qty'));
    expect(screen.getByText('ROP = safety stock + demand rate x lead time')).toBeInTheDocument();
    // the frozen inputs behind the formula are spelled out (SS + demand/day x lead days)
    const text = docText();
    expect(text).toContain('20 +');
    expect(text).toContain('4.0/day x 14d lead');
  });
});

describe('CashResultsGrid — row-click detail vs control targets (M8-C10)', () => {
  it('clicking the bare row opens the detail view', () => {
    const { onOpenDetail } = renderGrid(recToPlanRow(rec()));
    fireEvent.click(screen.getByText('Ceramic Wash Basin 450mm'));
    expect(onOpenDetail).toHaveBeenCalledWith(expect.objectContaining({ id: 'rec-1' }));
  });

  it('clicking an inline control (Accept) does NOT open the detail view', () => {
    const { onOpenDetail } = renderGrid(recToPlanRow(rec()));
    fireEvent.click(screen.getByRole('button', { name: 'Accept' }));
    expect(onOpenDetail).not.toHaveBeenCalled();
  });
});
