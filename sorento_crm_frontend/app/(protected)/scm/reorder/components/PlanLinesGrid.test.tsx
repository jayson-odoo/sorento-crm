/**
 * The plan grid after the revamp (plan 4.3/4.4/4.6, UAC C3-C6, D1-D9, F1).
 *
 * The collapsed row states facts and nothing else: eleven columns, a status pill, and six
 * numbers that open the documents behind them. Deciding happens in the expanded row, into a
 * DRAFT the page holds - nothing here writes to the backend, which is the whole difference
 * from the screen this replaces.
 */
import React, { useState } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReorderRecommendation } from '../types/reorder.types';
import { recToPlanLine, type PlanLine } from '../lib/planLine';
import type { PlanDecisionMap } from '../lib/planDecisions';
import type { PlanRowEdit, PlanRowEditMap } from '../lib/planEdits';
import { PlanLinesGrid } from './PlanLinesGrid';
import { coverForLine, NO_COVER, type CoverSource } from '../lib/coverPlan';
import type { PoReceipt } from '../lib/poCover';
import type { LevelSuggestion } from '../lib/levelSuggestion';
import type { ProductEconomics } from '../lib/productHealth';

class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {},
  });
}

// The two lightbox reads that hit the network. Stubbed so a dialog's own body is
// deterministic - what is asserted here is that the NUMBER opens it, not what the server
// would have said.
vi.mock('../hooks/useReorderRun', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useReorderRun')>();
  return {
    ...actual,
    useLocationStock: () => ({
      isLoading: false,
      data: {
        product_id: 'p1',
        as_of: '2026-08-27T06:05:00',
        locations: [
          {
            warehouse_id: 'w1', warehouse_code: 'BRW', on_hand: 5431, reserved: 0,
            held_by_decisions: 0, free: 5431, so_qty: 9, spo_qty: 0, available: 5422,
            is_pool: true, po_qty: 63,
          },
        ],
      },
    }),
    useRecommendationDemand: () => ({ isLoading: false, data: { lines: [], history_lines: [] } }),
  };
});

// The saved column layout is a server read. Stubbed so it cannot fetch, and so the key it
// was asked for is visible to the test below.
const listingKeys: (string | null | undefined)[] = [];
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: ({ listingKey }: { listingKey?: string | null }) => {
    listingKeys.push(listingKey);
    return { resetToDefaults: vi.fn(), isLoading: false };
  },
}));

// The filter popover uses the standard SearchableSelect. A native <select> keeps the
// options in the DOM without driving a cmdk popover.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options = [],
    placeholder,
  }: {
    value?: string;
    onChange?: (v: string) => void;
    options?: Array<{ value: string; label: string }>;
    placeholder?: string;
  }) => (
    <select aria-label={placeholder} value={value} onChange={(e) => onChange?.(e.target.value)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  ),
}));

function rec(over: Partial<ReorderRecommendation> = {}): ReorderRecommendation {
  return {
    id: 'r1', type: 'buy', sku: 'SKU-1', product_name: 'Product one',
    abc_class: null, xyz_class: null, warehouse_code: 'BRW', warehouse_name: 'Butterworth',
    product_id: 'p1', warehouse_id: 'w1', is_network: false, allocation: null,
    order_qty: 23, recommended_qty: 23, reorder_point: 0, min_qty: null, max_qty: null,
    order_up_to: 0, net_position: -23, days_of_cover: null, reason: 'reorder_point',
    reason_label: '', confidence: 'low', sample_size: 0,
    supplier: { supplier_code: 'S1', supplier_name: 'Acme', unit_cost: 10,
                lead_time_days: 30, composite_score: 0, is_primary: true },
    alternatives: [], is_exception: false, disposition_action: null, transfer_flag: null,
    forecast_daily_demand: 0, lead_time_days: 30, lead_time_source: 'default',
    safety_stock: 0, safety_stock_method: null, safety_stock_fallback: null,
    service_level: null, safety_days: 0, review_days: 0,
    moq: null, master_moq: null, moq_is_override: false,
    order_multiple: null, policy_type: 'reorder_point', supplier_selection: 'primary',
    unit_cost: 10, cash_impact: 230, rank: 1, rank_score: 0, funding_status: null,
    days_to_stockout: null, rank_factors: [],
    on_hand: 1, incoming_spo: 0, outstanding_po: 0, outstanding_sales: 24,
    project_need: 0, retail_need: 0,
    reorder_level: null, master_reorder_level: null, master_reorder_quantity: null,
    ...over,
  } as ReorderRecommendation;
}

const line = (over: Partial<ReorderRecommendation> = {}): PlanLine => recToPlanLine(rec(over));

/** The grid, with the draft map wired the way the section wires it. */
function renderGrid(
  lines: PlanLine[],
  opts: {
    decisions?: PlanDecisionMap;
    edits?: PlanRowEditMap;
    free?: CoverSource[];
    poFor?: (l: PlanLine) => PoReceipt[];
    levelFor?: (l: PlanLine) => LevelSuggestion | undefined;
    economicsFor?: (l: PlanLine) => ProductEconomics | undefined;
    decisionsReadOnly?: boolean;
    readOnlyReason?: string | null;
    toolbarPrimary?: React.ReactNode;
    live?: boolean;
  } = {},
) {
  const onRowEdit = vi.fn();
  const onResetRow = vi.fn();
  const coverFor = (l: PlanLine) =>
    l.purchasable ? coverForLine(l, opts.free ?? []) : NO_COVER;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  /** A live draft map, so an edit made in the panel is visible on the pill next to it. */
  function Harness() {
    const [edits, setEdits] = useState<PlanRowEditMap>(opts.edits ?? {});
    return (
      <PlanLinesGrid
        runId="run-1"
        lines={lines}
        decisions={opts.decisions ?? {}}
        edits={opts.live ? edits : (opts.edits ?? {})}
        onRowEdit={(l: PlanLine, patch: PlanRowEdit) => {
          onRowEdit(l, patch);
          setEdits((prev) => ({ ...prev, [l.id]: { ...prev[l.id], ...patch } }));
        }}
        onResetRow={(l: PlanLine) => {
          onResetRow(l);
          setEdits((prev) => {
            const next = { ...prev };
            delete next[l.id];
            return next;
          });
        }}
        toolbarPrimary={opts.toolbarPrimary}
        coverFor={coverFor}
        poFor={opts.poFor}
        levelFor={opts.levelFor}
        economicsFor={opts.economicsFor}
        decisionsReadOnly={opts.decisionsReadOnly}
        readOnlyReason={opts.readOnlyReason ?? null}
      />
    );
  }

  render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>,
  );
  return { onRowEdit, onResetRow };
}

const headerNames = () =>
  Array.from(document.querySelectorAll('thead th')).map((th) => th.textContent?.trim() ?? '');

beforeEach(() => vi.clearAllMocks());

describe('PlanLinesGrid - the collapsed row (C4)', () => {
  it('shows exactly the eleven columns the plan names, in order', () => {
    renderGrid([line()]);
    expect(headerNames()).toEqual([
      '#', 'Product', 'Location', 'Suggested qty', 'Reorder level', 'Reorder qty',
      'Project', 'Retail', 'On hand', 'SPO', 'PO', 'Decision',
    ]);
  });

  it('keeps the Project column on a run whose every row is retail (28 Aug: "where is my project quantity column")', () => {
    renderGrid([line({ segment: 'dealer' }), line({ id: 'r2', segment: 'dealer' })]);
    const names = headerNames();
    expect(names).toContain('Project');
    expect(names).toContain('Retail');
    expect(names.indexOf('Project')).toBeLessThan(names.indexOf('Retail'));
  });

  it('has no MOQ, price, supplier, level or health column - they moved into the panel', () => {
    renderGrid([line()]);
    const names = headerNames();
    expect(names).not.toContain('MOQ');
    expect(names).not.toContain('Suggested price');
    expect(names).not.toContain('Suggested supplier');
    expect(names).not.toContain('AutoCount level + qty');
    expect(names).not.toContain('Product health');
  });

  it('defines Total cost but hides it by default - the panel states the line cost', () => {
    renderGrid([line()]);
    expect(headerNames()).not.toContain('Total cost');
    // Still reachable: the Columns menu lists every hideable column by its own title.
    expect(screen.getByRole('button', { name: /Columns/i })).toBeInTheDocument();
  });

  it('renames PO outstanding to PO (R13)', () => {
    renderGrid([line()]);
    expect(headerNames()).toContain('PO');
    expect(headerNames()).not.toContain('PO outstanding');
  });
});

describe('PlanLinesGrid - the Decision cell is a pill (C6)', () => {
  const pill = (state: string) => screen.getByTestId(`decision-pill-${state}`);

  it('reads Suggested with the engine mixture when nobody has touched the row', () => {
    renderGrid([line({ order_qty: 31 })]);
    expect(pill('suggested')).toHaveTextContent('Suggested');
    expect(pill('suggested')).toHaveTextContent('Buy 31');
  });

  it('reads Saved once a decision is persisted', () => {
    renderGrid([line()], { decisions: { r1: { buy: 20 } } });
    expect(pill('saved')).toHaveTextContent('Saved');
    expect(pill('saved')).toHaveTextContent('Buy 20');
  });

  it('reads Confirmed once the decision carries a draft purchase order', () => {
    renderGrid([line()], { decisions: { r1: { buy: 20, confirmed: true } } });
    expect(pill('confirmed')).toHaveTextContent('Confirmed');
  });

  it('reads Skipped, and says it once rather than twice', () => {
    renderGrid([line()], { decisions: { r1: { skip: true } } });
    expect(pill('skipped').textContent).toBe('Skipped');
  });

  it('reads Unsaved the moment a draft edit exists on the row', () => {
    renderGrid([line()], { edits: { r1: { decision: { buy: 200 } } } });
    expect(pill('unsaved')).toHaveTextContent('Unsaved');
    expect(pill('unsaved')).toHaveTextContent('Buy 200');
  });

  it('carries no buttons - deciding happens in the expanded row', () => {
    renderGrid([line()]);
    const cell = pill('suggested').closest('td') as HTMLElement;
    expect(within(cell).queryByRole('button')).not.toBeInTheDocument();
  });

  it('a legacy run says so instead, and never shows a pill', () => {
    renderGrid([line()], {
      decisionsReadOnly: true,
      readOnlyReason: 'Legacy run - read only. Create a new plan to decide.',
    });
    expect(screen.getByTestId('decision-read-only-r1')).toHaveTextContent('Legacy run');
    expect(screen.queryByTestId('decision-pill-suggested')).not.toBeInTheDocument();
  });
});

describe('PlanLinesGrid - expanding (C3, D1)', () => {
  it('clicking a row opens its decision panel', () => {
    renderGrid([line()]);
    expect(screen.queryByText('Cover')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('SKU-1'));
    expect(screen.getByText('Cover')).toBeInTheDocument();
    expect(screen.getByText('Price and supplier')).toBeInTheDocument();
    expect(screen.getByText('AutoCount level + qty')).toBeInTheDocument();
    expect(screen.getByText('Product health')).toBeInTheDocument();
  });

  it('several rows can be open at once', () => {
    renderGrid([line({ id: 'r1', sku: 'SKU-1' }), line({ id: 'r2', sku: 'SKU-2', rank: 2 })]);
    fireEvent.click(screen.getByText('SKU-1'));
    fireEvent.click(screen.getByText('SKU-2'));
    expect(screen.getAllByText('Cover')).toHaveLength(2);
  });

  it('Expand all opens every row on the page, Collapse all closes them', () => {
    renderGrid([line({ id: 'r1', sku: 'SKU-1' }), line({ id: 'r2', sku: 'SKU-2', rank: 2 })]);
    fireEvent.click(screen.getByRole('button', { name: 'Expand all' }));
    expect(screen.getAllByText('Cover')).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: 'Collapse all' }));
    expect(screen.queryByText('Cover')).not.toBeInTheDocument();
  });

  it('each button is disabled when it has nothing to do', () => {
    renderGrid([line()]);
    expect(screen.getByRole('button', { name: 'Expand all' })).not.toBeDisabled();
    expect(screen.getByRole('button', { name: 'Collapse all' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Expand all' }));
    expect(screen.getByRole('button', { name: 'Expand all' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Collapse all' })).not.toBeDisabled();
  });
});

describe('PlanLinesGrid - the six lightboxes (F1)', () => {
  const openNumber = (name: RegExp) => fireEvent.click(screen.getByRole('button', { name }));

  it('Suggested qty opens the ledger', () => {
    renderGrid([line({ order_qty: 31 })]);
    openNumber(/^Suggested qty - open how we got it$/);
    expect(screen.getByRole('dialog')).toHaveTextContent('Suggested qty - SKU-1');
  });

  it('Project opens the project orders', () => {
    renderGrid([line({ project_need: 4 })]);
    openNumber(/^Project demand - open the orders behind it$/);
    expect(screen.getByRole('dialog')).toHaveTextContent('Project demand - SKU-1');
  });

  it('Retail opens the retail orders', () => {
    renderGrid([line({ retail_need: 19 })]);
    openNumber(/^Retail demand - open the orders behind it$/);
    expect(screen.getByRole('dialog')).toHaveTextContent('Retail demand - SKU-1');
  });

  it('On hand opens the site pool stock, with the documents under each location', () => {
    renderGrid([line({ on_hand: 5431 })]);
    openNumber(/^On hand - open the stock by location$/);
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveTextContent('On hand - SKU-1');
    expect(within(dialog).getByText('BRW')).toBeInTheDocument();
    expect(within(dialog).getByText(/Stock as of/)).toBeInTheDocument();
  });

  it('SPO opens the shipments, named to the pool location (R15)', () => {
    renderGrid([line({ incoming_spo: 500 })]);
    openNumber(/^SPO - open the shipments arriving$/);
    expect(screen.getByRole('dialog')).toHaveTextContent('SPO - SKU-1 - to BRW');
  });

  it('PO opens what is already ordered, named to the pool location (R15)', () => {
    renderGrid([line({ outstanding_po: 63 })]);
    openNumber(/^PO - open what is already ordered$/);
    expect(screen.getByRole('dialog')).toHaveTextContent('PO - SKU-1 - to BRW');
  });

  it('leaves no explain icon on those six cells', () => {
    renderGrid([line()]);
    expect(screen.queryByRole('button', { name: /Explain order qty/i })).not.toBeInTheDocument();
  });
});

describe('PlanLinesGrid - the panel edits a draft, never the backend (D2-D9)', () => {
  it('Buy re-rounds to the MOQ and multiple on blur (D3)', () => {
    const { onRowEdit } = renderGrid([line({ order_qty: 23, moq: 100, order_multiple: 50 })]);
    fireEvent.click(screen.getByText('SKU-1'));
    const buy = screen.getByLabelText('Units to buy');
    fireEvent.change(buy, { target: { value: '120' } });
    fireEvent.blur(buy);
    expect(onRowEdit).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'r1' }),
      { decision: expect.objectContaining({ buy: 150 }) },
    );
  });

  it('turns the pill Unsaved as soon as an input moves (D7)', () => {
    renderGrid([line({ order_qty: 23 })], { live: true });
    fireEvent.click(screen.getByText('SKU-1'));
    fireEvent.change(screen.getByLabelText('MOQ'), { target: { value: '100' } });
    expect(screen.getByTestId('decision-pill-unsaved')).toBeInTheDocument();
  });

  it('states the caps beside the two capped inputs (D2)', () => {
    renderGrid([line()], { poFor: () => [{ po_number: 'PO-1', status: 'open', expected_date: null, remaining: 40 }] });
    fireEvent.click(screen.getByText('SKU-1'));
    expect(screen.getByText(/pool available/)).toBeInTheDocument();
    expect(screen.getByText(/open 40/)).toBeInTheDocument();
  });

  it('SPO arriving is a read-only fact, never an input (R2, D2)', () => {
    renderGrid([line({ incoming_spo: 12 })]);
    fireEvent.click(screen.getByText('SKU-1'));
    expect(screen.getByText(/SPO arriving/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/SPO arriving/)).not.toBeInTheDocument();
  });

  it('hints only when the mixture differs from the suggestion (D2)', () => {
    renderGrid([line({ order_qty: 23 })]);
    fireEvent.click(screen.getByText('SKU-1'));
    expect(screen.queryByText(/over suggested|short of suggested/)).not.toBeInTheDocument();
  });

  it('Use suggestion drops the row draft', () => {
    const { onResetRow } = renderGrid([line()], { edits: { r1: { decision: { buy: 9 } } } });
    fireEvent.click(screen.getByText('SKU-1'));
    fireEvent.click(screen.getByRole('button', { name: 'Use suggestion' }));
    expect(onResetRow).toHaveBeenCalledWith(expect.objectContaining({ id: 'r1' }));
  });

  it('Skip records a skip on the draft', () => {
    const { onRowEdit } = renderGrid([line()]);
    fireEvent.click(screen.getByText('SKU-1'));
    fireEvent.click(screen.getByRole('button', { name: 'Skip' }));
    expect(onRowEdit).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'r1' }),
      { decision: { skip: true } },
    );
  });

  it('has no location table and no "Live stock as of" line (D9, R12)', () => {
    renderGrid([line()]);
    fireEvent.click(screen.getByText('SKU-1'));
    expect(screen.queryByText(/Live stock as of/)).not.toBeInTheDocument();
    expect(screen.queryByText('Available')).not.toBeInTheDocument();
  });

  it('a legacy run renders the panel with every input dead (D8)', () => {
    renderGrid([line()], {
      decisionsReadOnly: true,
      readOnlyReason: 'Legacy run - read only. Create a new plan to decide.',
    });
    fireEvent.click(screen.getByText('SKU-1'));
    expect(screen.getByLabelText('Units to buy')).toBeDisabled();
    expect(screen.getByLabelText('MOQ')).toBeDisabled();
    expect(screen.getByLabelText('AutoCount level')).toBeDisabled();
    expect(screen.getByLabelText('AutoCount reorder qty')).toBeDisabled();
  });
});

describe('PlanLinesGrid - the toolbar (C2)', () => {
  it('renders the caller Save and Confirm buttons at the right end', () => {
    renderGrid([line()], {
      toolbarPrimary: (
        <>
          <button type="button">Save (3)</button>
          <button type="button">Confirm (20)</button>
        </>
      ),
    });
    expect(screen.getByRole('button', { name: 'Save (3)' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm (20)' })).toBeInTheDocument();
  });

  it('keeps the price and level filters so the hidden fields stay findable (R8)', async () => {
    renderGrid([line()]);
    const trigger = screen.getByRole('button', { name: /Filters/i });
    // Radix opens its menu on pointerdown, not on click.
    fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' });
    expect(await screen.findByLabelText('Suggested price')).toBeInTheDocument();
    expect(screen.getByLabelText('AutoCount level')).toBeInTheDocument();
  });
});


describe('PlanLinesGrid - saved column layout belongs to the screen (A1)', () => {
  it('keys the column preferences on the listing, never on the plan id', () => {
    listingKeys.length = 0;
    renderGrid([line()]);
    expect(listingKeys).toContain('scm.dashboard.view::reorder-plan-lines');
    // Defaulted, `DataGrid` keys off the pathname - `/scm/reorder/{run_id}` - so every
    // plan started from the defaults and a buyer's own layout was never seen twice.
    expect(listingKeys).not.toContain('/scm/reorder/run-1');
  });
});
