/**
 * SCM M8 - CashResultsGrid (slice C + drills). The one-table/two-section plan grid
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
import { EM_DASH as EM_DASH_TEXT } from '../../lib/format';

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

// Lazy drills - return controlled data so the drill popovers render deterministically.
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

describe('CashResultsGrid - layout (M8-C11)', () => {
  it('renders the Warehouse column header + the row’s human warehouse label', () => {
    renderGrid(recToPlanRow(rec()));
    expect(screen.getByText('Warehouse')).toBeInTheDocument();
    expect(screen.getByText('Kuala Lumpur DC')).toBeInTheDocument();
  });
});

describe('CashResultsGrid - Days cover drill reconciliation (M8-A2/A3)', () => {
  it('finite frozen rate → arithmetic net/rate=days reconciles; CV spelled in full', () => {
    // net 80, frozen rate 4/day, days_cover 20 → "80 / 4.0 = 20 days".
    renderGrid(recToPlanRow(rec({ net_position: 80, forecast_daily_demand: 4, days_of_cover: 20 })));
    fireEvent.click(screen.getByLabelText('Explain runway'));
    expect(screen.getByText('Runway = 20 days')).toBeInTheDocument();
    // arithmetic uses the FROZEN rate (4), not the live explain/demand window (99)
    expect(docText()).toContain('80 / 4.0 = 20 days');
    expect(docText()).not.toContain('99');
    // full metric name, never the ambiguous "CV"
    expect(screen.getByText('Coefficient of variation')).toBeInTheDocument();
    // navigable DO list (M8-A2) - the demand basis is DOs, not raw buckets
    expect(screen.getByText('DO-2026-0100')).toBeInTheDocument();
  });

  it('days_cover=null on a DEFICIT net → undefined copy, never divides by zero (M8-A3)', () => {
    renderGrid(recToPlanRow(rec({ net_position: -30, days_of_cover: null, forecast_daily_demand: 4 })));
    fireEvent.click(screen.getByLabelText('Explain runway'));
    expect(screen.getByText(/Runway = undefined/i)).toBeInTheDocument();
    expect(screen.getByText(/Net is a deficit/i)).toBeInTheDocument();
    // the arithmetic line is suppressed - no "/ 0" ever printed
    expect(docText()).not.toContain('/ 0');
  });

  it('rate<=0 (no measurable demand) → no-demand copy, no division (M8-A3)', () => {
    renderGrid(recToPlanRow(rec({ net_position: 80, days_of_cover: null, forecast_daily_demand: 0 })));
    fireEvent.click(screen.getByLabelText('Explain runway'));
    expect(screen.getByText(/No measurable daily demand/i)).toBeInTheDocument();
    expect(docText()).not.toContain('/ 0');
  });

  it('CV unavailable → renders a dash, not a fabricated 0', () => {
    useExplainDemand.mockReturnValue(demand(null));
    renderGrid(recToPlanRow(rec()));
    fireEvent.click(screen.getByLabelText('Explain runway'));
    const label = screen.getByText('Coefficient of variation');
    // Asserted on the CV cell itself, not the whole document: prices elsewhere on the row
    // legitimately carry cents ("RM 100.00"), and a document-wide check for "0.00" fails
    // on those without the CV cell being wrong at all.
    // The shared placeholder, whatever it is - asserting the character itself makes a
    // change of dash look like a broken CV cell.
    expect(label.nextElementSibling?.textContent).toBe(EM_DASH_TEXT);
  });
});

describe('CashResultsGrid - Net drill lists committed SOs (M8-A1)', () => {
  it('shows on-hand/on-order/committed + the open SO behind committed', () => {
    renderGrid(recToPlanRow(rec()));
    fireEvent.click(screen.getByLabelText('Explain net'));
    expect(screen.getByText('SO-2026-0007')).toBeInTheDocument();
    expect(screen.getByText('Bina Jaya')).toBeInTheDocument();
    expect(screen.getByText('Open sales orders')).toBeInTheDocument();
  });
});

describe('CashResultsGrid - inline edit (M8-C5)', () => {
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

describe('CashResultsGrid - inline decisions (M8-C6)', () => {
  it('Accept funds a within-budget row', () => {
    const { onFund } = renderGrid(recToPlanRow(rec()));
    fireEvent.click(screen.getByRole('button', { name: 'Accept' }));
    expect(onFund).toHaveBeenCalledWith(expect.objectContaining({ id: 'rec-1' }));
  });

  it('an Over-budget row has NO call-to-action - no Accept / Reject / Fund (M8-F13)', () => {
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

describe('CashResultsGrid - reject keeps the row IN PLACE (M8-F1 REVISED)', () => {
  it('a rejected WITHIN row stays in the Within section with a "Rejected" chip + Accept (undo)', () => {
    const row = recToPlanRow(rec());
    // The rejected row is passed in the WITHIN section (reject no longer moves it to Over).
    const { onFund } = renderGrid(row, {
      within: [row],
      over: [],
      decisions: { [row.id]: 'rejected' },
    });
    // the row is NOT removed - its product name still renders
    expect(screen.getByText('Ceramic Wash Basin 450mm')).toBeInTheDocument();
    // a "Rejected" chip marks the state (parity with "Accepted")
    expect(screen.getByText('Rejected')).toBeInTheDocument();
    // the restore control is now "Accept" (undo) - the old "Fund" button is gone
    expect(screen.queryByRole('button', { name: 'Fund' })).toBeNull();
    const accept = screen.getByRole('button', { name: 'Accept' });
    fireEvent.click(accept);
    expect(onFund).toHaveBeenCalledWith(expect.objectContaining({ id: 'rec-1' }));
  });
});

describe('CashResultsGrid - confirmed line shows a PO link (M8-F8 / M8-F9)', () => {
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

describe('CashResultsGrid - supplier cell never overlaps Decision (M8-F3)', () => {
  it('renders the supplier name truncated inside an overflow-hidden cell', () => {
    renderGrid(recToPlanRow(rec()));
    const supplierName = screen.getByText('Acme Sanitary');
    // truncation stops the supplier text bleeding into the Decision column
    expect(supplierName.className).toContain('truncate');
    // the cell itself clips overflow so the fixed grid columns can never collide
    expect(supplierName.closest('.overflow-hidden')).not.toBeNull();
  });
});

describe('CashResultsGrid - order-qty drill shows the ROP formula (M8-A4 / M8-F5)', () => {
  it('renders "ROP = safety stock + demand rate x lead time" with the frozen inputs', () => {
    // safety_stock 20, forecast_daily_demand 4, supplier lead 14, reorder_point 60.
    renderGrid(recToPlanRow(rec()));
    fireEvent.click(screen.getByLabelText('Explain order qty'));
    expect(screen.getByText('ROP = safety stock + demand rate x lead time')).toBeInTheDocument();
    // the frozen inputs behind the formula are spelled out (SS + demand/day x lead days)
    const text = docText();
    // One decimal: a whole-number safety stock made the printed sum disagree with the
    // reorder point beside it by a unit, which reads as a broken calculation.
    expect(text).toContain('20.0 +');
    expect(text).toContain('4.0/day x 14d lead');
  });
});

describe('CashResultsGrid - product search + column sort (additive)', () => {
  const supplier = (name: string, cost: number): SupplierChoice => ({
    supplier_code: `SUP-${name.slice(0, 3).toUpperCase()}`, supplier_name: name,
    unit_cost: cost, lead_time_days: 14, composite_score: 80, is_primary: true,
  });
  const rowA = recToPlanRow(rec({ id: 'rec-a', rank: 1, sku: 'AAA-1', product_name: 'Alpha Widget', warehouse_name: 'Penang DC', order_qty: 300, unit_cost: 10, days_of_cover: 5, supplier: supplier('Zeta Traders', 10) }));
  const rowB = recToPlanRow(rec({ id: 'rec-b', rank: 2, sku: 'BBB-2', product_name: 'Bravo Gadget', warehouse_name: 'Johor DC', order_qty: 100, unit_cost: 50, days_of_cover: 30, supplier: supplier('Alpha Supplies', 50) }));
  const rowC = recToPlanRow(rec({ id: 'rec-c', rank: 3, sku: 'CCC-3', product_name: 'Charlie Thing', warehouse_name: 'KL DC', order_qty: 200, unit_cost: 1, days_of_cover: 15, supplier: supplier('Mid Supply', 1) }));

  function renderMulti(rows: M8PlanRow[] = [rowA, rowB, rowC]) {
    const handlers = { onFund: vi.fn(), onReject: vi.fn(), onEdit: vi.fn() };
    render(
      <CashResultsGrid
        within={rows}
        over={[]}
        decisions={Object.fromEntries(rows.map((r) => [r.id, null]))}
        editedIds={new Set()}
        budgetHeader={<div>budget-header</div>}
        handlers={handlers}
      />,
    );
  }

  /** true when node `a` precedes node `b` in DOM order. */
  const before = (a: string, b: string) =>
    !!(screen.getByText(a).compareDocumentPosition(screen.getByText(b)) & Node.DOCUMENT_POSITION_FOLLOWING);

  it('filters both-section rows by SKU / product / supplier (case-insensitive) with a live count', () => {
    renderMulti();
    // all three visible initially
    expect(screen.getByText('Alpha Widget')).toBeInTheDocument();
    expect(screen.getByText('Bravo Gadget')).toBeInTheDocument();
    // supplier-name match: "alpha" hits Bravo's supplier "Alpha Supplies" AND "Alpha Widget"
    fireEvent.change(screen.getByLabelText('Search buy recommendations'), { target: { value: 'alpha' } });
    expect(screen.getByText('Alpha Widget')).toBeInTheDocument();
    expect(screen.getByText('Bravo Gadget')).toBeInTheDocument();
    expect(screen.queryByText('Charlie Thing')).toBeNull();
    // section badge reflects the filtered count as "X of Y"
    expect(screen.getByText('2 of 3')).toBeInTheDocument();
  });

  it('narrows to a single SKU and shows a no-match empty state when nothing matches', () => {
    renderMulti();
    fireEvent.change(screen.getByLabelText('Search buy recommendations'), { target: { value: 'bravo' } });
    expect(screen.getByText('Bravo Gadget')).toBeInTheDocument();
    expect(screen.queryByText('Alpha Widget')).toBeNull();
    // clear restores everything
    fireEvent.click(screen.getByLabelText('Clear search'));
    expect(screen.getByText('Alpha Widget')).toBeInTheDocument();
    // an unmatched query renders the section no-match copy
    fireEvent.change(screen.getByLabelText('Search buy recommendations'), { target: { value: 'zzzz' } });
    expect(screen.getByText(/No buys in this section match your search/i)).toBeInTheDocument();
  });

  it('sorts by Order qty asc → desc → back to default rank order on repeated header clicks', () => {
    renderMulti();
    // default = engine array order A, B, C
    expect(before('Alpha Widget', 'Bravo Gadget')).toBe(true);
    const orderQtyHeader = screen.getByRole('button', { name: 'Sort by Order qty' });
    // asc: B(100) < C(200) < A(300)
    fireEvent.click(orderQtyHeader);
    expect(before('Bravo Gadget', 'Charlie Thing')).toBe(true);
    expect(before('Charlie Thing', 'Alpha Widget')).toBe(true);
    // desc: A(300) > C(200) > B(100)
    fireEvent.click(orderQtyHeader);
    expect(before('Alpha Widget', 'Charlie Thing')).toBe(true);
    expect(before('Charlie Thing', 'Bravo Gadget')).toBe(true);
    // third click restores the default rank order (A, B, C)
    fireEvent.click(orderQtyHeader);
    expect(before('Alpha Widget', 'Bravo Gadget')).toBe(true);
    expect(before('Bravo Gadget', 'Charlie Thing')).toBe(true);
  });

  it('disables the drag handles when a sort is active and when a search is active; enabled in default view', () => {
    renderMulti();
    // default view: every row has a live drag handle
    expect(screen.getByLabelText('Drag AAA-1 between sections')).toBeInTheDocument();
    // sorting freezes the order → handles removed
    fireEvent.click(screen.getByRole('button', { name: 'Sort by Order qty' }));
    expect(screen.queryByLabelText('Drag AAA-1 between sections')).toBeNull();
    // reset sort back to default → handles return
    fireEvent.click(screen.getByRole('button', { name: 'Sort by Order qty' })); // desc
    fireEvent.click(screen.getByRole('button', { name: 'Sort by Order qty' })); // back to rank
    expect(screen.getByLabelText('Drag AAA-1 between sections')).toBeInTheDocument();
    // an active search also disables drag
    fireEvent.change(screen.getByLabelText('Search buy recommendations'), { target: { value: 'a' } });
    expect(screen.queryByLabelText('Drag AAA-1 between sections')).toBeNull();
  });
});

describe('CashResultsGrid - row-click detail vs control targets (M8-C10)', () => {
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

describe('CashResultsGrid - master-data reorder settings on the row', () => {
  it('shows the reorder level and quantity held on the product record', () => {
    const row = recToPlanRow(
      rec({ master_reorder_level: 120, master_reorder_quantity: 400 } as Partial<ReorderRecommendation>),
    );
    renderGrid(row);
    expect(screen.getByText('120')).toBeInTheDocument();
    expect(screen.getByText('400')).toBeInTheDocument();
  });

  it('names both columns after the product-record fields they come from', () => {
    renderGrid(recToPlanRow(rec()));
    expect(screen.getByText('Reorder level')).toBeInTheDocument();
    expect(screen.getByText('Reorder qty')).toBeInTheDocument();
  });

  it('an unset setting reads as a dash, never as zero', () => {
    const row = recToPlanRow(
      rec({ master_reorder_level: null, master_reorder_quantity: null } as Partial<ReorderRecommendation>),
    );
    renderGrid(row);
    // A product with no reorder level is not a product whose level is 0 - the second
    // would read as "let it run to nothing", which nobody decided.
    expect(screen.queryByText('Reorder level')).toBeInTheDocument();
    expect(screen.getAllByText(EM_DASH_TEXT).length).toBeGreaterThan(0);
  });
});

describe('CashResultsGrid - a search that matches an uncosted buy says so', () => {
  it('names the item instead of returning silence', () => {
    const priced = recToPlanRow(rec({ id: 'rec-priced', sku: 'AAA-1' }));
    const uncosted = recToPlanRow(
      rec({ id: 'rec-nocost', sku: 'CWCX1009-RL', unit_cost: null, cash_impact: null,
            warehouse_code: 'BRW-IB' } as Partial<ReorderRecommendation>),
    );
    renderGrid(priced, { within: [priced], over: [], needsCost: [uncosted] });
    fireEvent.change(screen.getByPlaceholderText(/search sku/i), {
      target: { value: 'CWCX1009-RL' },
    });
    // Without this the grid answers "No buys match", which reads as "not short" when the
    // truth is the opposite: it IS short, we just cannot price it.
    expect(screen.getByText(/not in the plan below/i)).toBeInTheDocument();
    expect(screen.getByText(/no supplier cost/i)).toBeInTheDocument();
    expect(screen.getByText(/CWCX1009-RL \(BRW-IB\)/)).toBeInTheDocument();
  });

  it('stays quiet when the search matches something that IS priced', () => {
    const priced = recToPlanRow(rec({ sku: 'AAA-1' }));
    const uncosted = recToPlanRow(
      rec({ id: 'rec-nocost', sku: 'ZZZ-9', unit_cost: null } as Partial<ReorderRecommendation>),
    );
    renderGrid(priced, { within: [priced], over: [], needsCost: [uncosted] });
    fireEvent.change(screen.getByPlaceholderText(/search sku/i), { target: { value: 'AAA-1' } });
    expect(screen.queryByText(/not in the plan below/i)).toBeNull();
  });
});
