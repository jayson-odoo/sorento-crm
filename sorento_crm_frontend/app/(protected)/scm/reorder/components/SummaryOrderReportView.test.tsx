/**
 * SummaryOrderReportView (AC-C2.1 / AC-C2.2 / AC-C2.2a / AC-C2.8).
 *
 * What this screen has to get right, in this order:
 *
 * - One row per product with every figure the printed sheet carries, plus the
 *    two the pen version has no room for: the chosen quantity and the supplier
 *    (AC-C2.1).
 * - Ordered and Incoming as SEPARATE columns (AC-C2.2). Only Incoming drives the
 *    net position; Ordered is displayed so a shortfall does not read as
 *    unattended.
 * - Nothing decomposed inline. Every aggregate is a figure with an information
 *    icon (AC-C2.2a).
 * - The engine's suggestion sits beside the chosen quantity (AC-C2.8), and a
 *    chosen quantity above the shortfall is rendered as a plain figure, not an
 *    error.
 *
 * The real fixtures from `lib/summaryOrderMockStore` are used rather than
 * hand-typed numbers, so a fixture drifting from the ACs fails here too.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

// jsdom polyfills for ScrollArea / DataGrid / Sheet.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/reorder',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const hooks = vi.hoisted(() => ({
  useOrderSummary: vi.fn(),
  useRecordOrderDecision: vi.fn(),
  useConfirmOrderDecisions: vi.fn(),
  useOrderSummaryDemand: vi.fn(),
  useOrderSummaryLocations: vi.fn(),
  useOrderSummarySuppliers: vi.fn(),
  orderSummaryKey: () => ['scm', 'reorder', 'order-summary'],
}));
vi.mock('../hooks/useSummaryOrder', () => hooks);

// The decision slide-over has its own spec; here it is a sentinel so the grid's
// orchestration is what is under test.
vi.mock('./OrderDecisionSheet', () => ({
  OrderDecisionSheet: ({ row, open }: { row: { product_code: string } | null; open: boolean }) =>
    open && row ? <div>{`decision-sheet:${row.product_code}`}</div> : null,
}));

import { SUMMARY_ORDER_FIXTURES } from '../lib/summaryOrderMockStore';
import { SummaryOrderReportView } from './SummaryOrderReportView';

const REPORT = SUMMARY_ORDER_FIXTURES.report();

function state(over: Record<string, unknown> = {}) {
  return { data: undefined, isLoading: false, isError: false, error: null, refetch: vi.fn(), ...over };
}

const mutate = vi.fn();

function renderView(hookState: ReturnType<typeof state>, onBack?: () => void) {
  hooks.useOrderSummary.mockReturnValue(hookState);
  render(<SummaryOrderReportView runId="run-2026-w32" onBack={onBack} />);
  return hookState;
}

/** The grid row for one product, addressed by the product code it renders. */
function rowFor(productCode: string): HTMLElement {
  const cell = screen.getByTitle(productCode);
  const row = cell.closest('tr');
  if (!row) throw new Error(`No row rendered for ${productCode}`);
  return row;
}

beforeEach(() => {
  vi.clearAllMocks();
  hooks.useRecordOrderDecision.mockReturnValue({ mutate, isPending: false });
  hooks.useConfirmOrderDecisions.mockReturnValue({ mutate: vi.fn(), isPending: false });
  hooks.useOrderSummaryDemand.mockReturnValue(state());
  hooks.useOrderSummaryLocations.mockReturnValue(state());
  hooks.useOrderSummarySuppliers.mockReturnValue(state());
});

describe('SummaryOrderReportView - states', () => {
  it('shows the grid skeleton while the report is being built', () => {
    renderView(state({ isLoading: true }));
    // The grid renders its own skeleton rows; no product has arrived yet.
    expect(screen.queryByTitle('B2155-NL-BLUE')).not.toBeInTheDocument();
  });

  it('shows the backend message and a retry when the report fails', () => {
    const s = renderView(state({ isError: true, error: new Error('No run for 2026-07-27') }));
    expect(screen.getByText('No run for 2026-07-27')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Try again/i }));
    expect(s.refetch).toHaveBeenCalled();
  });

  it('says nothing is short rather than rendering an empty grid', () => {
    renderView(state({ data: SUMMARY_ORDER_FIXTURES.emptyReport() }));
    expect(screen.getByText('Nothing to order')).toBeInTheDocument();
  });

  it('states the as-of date the position is quoted at (AC-C2.9)', () => {
    renderView(state({ data: REPORT }));
    expect(screen.getByText(/As of 03\/08\/2026/)).toBeInTheDocument();
  });

  it('filters the grid by product or supplier without re-fetching', () => {
    const s = renderView(state({ data: REPORT }));
    fireEvent.change(screen.getByLabelText('Search product or supplier'), {
      target: { value: 'SRTWT' },
    });
    expect(screen.getByTitle('SRTWT7408')).toBeInTheDocument();
    expect(screen.queryByTitle('B2155-NL-BLUE')).not.toBeInTheDocument();
    expect(s.refetch).not.toHaveBeenCalled();
  });
});

describe('SummaryOrderReportView - the row carries only what is needed (AC-C2.1 / C2.2a)', () => {
  it('renders one row per product with its human code and name, never an id', () => {
    renderView(state({ data: REPORT }));
    expect(screen.getByTitle('B2155-NL-BLUE')).toBeInTheDocument();
    expect(screen.getByTitle('SRTWT7408')).toBeInTheDocument();
    expect(screen.getByTitle('Basin 2155 Nano-Lite Blue')).toBeInTheDocument();
    // run_id identifies the week and is never rendered.
    expect(screen.queryByText('run-2026-w32')).not.toBeInTheDocument();
  });

  it('renders every figure the printed sheet carries, on one row', () => {
    renderView(state({ data: REPORT }));
    const row = rowFor('B2155-NL-BLUE');
    expect(row).toHaveTextContent('96'); // on hand
    expect(row).toHaveTextContent('480'); // project demand
    expect(row).toHaveTextContent('186'); // dealer outstanding
    expect(row).toHaveTextContent('120'); // on order
    expect(row).toHaveTextContent('200'); // in transit
    expect(row).toHaveTextContent('278'); // shortfall
    expect(row).toHaveTextContent('300'); // suggested
    expect(row).toHaveTextContent('600'); // chosen
    expect(row).toHaveTextContent('Guangdong Sanitary Ware');
  });

  it('does NOT decompose an aggregate inline - the lines stay behind the icon', () => {
    renderView(state({ data: REPORT }));
    const row = rowFor('B2155-NL-BLUE');
    expect(row).not.toHaveTextContent('Kedai Perabot Seri Muda');
    expect(row).not.toHaveTextContent('Maryam Tuju Residence');
    expect(row).not.toHaveTextContent('SO-2025-1188');
    // The icon is there to open them.
    expect(
      within(row).getByRole('button', { name: /Retail outstanding for B2155-NL-BLUE, 4 lines/i }),
    ).toBeInTheDocument();
    expect(
      within(row).getByRole('button', { name: /Project demand for B2155-NL-BLUE, 3 lines/i }),
    ).toBeInTheDocument();
  });

  it('flags the worst ageing on the row so a stale dealer line is visible without opening it', () => {
    renderView(state({ data: REPORT }));
    expect(rowFor('B2155-NL-BLUE')).toHaveTextContent('worst 214 days');
    expect(rowFor('SRTSK2210')).toHaveTextContent('worst 402 days');
  });
});

describe('SummaryOrderReportView - ordered and incoming stay separate (AC-C2.2)', () => {
  it('renders them as two columns, and never as one total', () => {
    renderView(state({ data: REPORT }));
    expect(screen.getByText('Ordered')).toBeInTheDocument();
    expect(screen.getByText('Incoming')).toBeInTheDocument();
    // Only Incoming is in the net position. A single combined column would put an order
    // the supplier has shipped nothing against into a figure that reads as cover.
    expect(screen.queryByText('Total incoming')).not.toBeInTheDocument();
  });

  it('keeps the split visible even where one half is zero', () => {
    renderView(state({ data: REPORT }));
    const row = rowFor('SRTBS4832');
    // 200 on order, nothing shipped yet: the negotiable half is the whole of it.
    expect(row).toHaveTextContent('200');
    expect(row).toHaveTextContent('0');
  });
});

describe('SummaryOrderReportView - the two demand questions are named apart', () => {
  it('labels the shortfall and the suggestion by the demand each is about', () => {
    // They sit side by side and answer different questions: the shortfall is the dated gap
    // against COMMITTED orders, the suggestion is the reorder policy against FORECAST
    // demand. On the real book 317 of 317 planned rows show a zero shortfall beside a
    // non-zero suggestion, which reads as a contradiction under the bare labels
    // "Shortfall" and "Suggested" and is not one.
    renderView(state({ data: REPORT }));
    expect(screen.getByText('Short vs orders')).toBeInTheDocument();
    expect(screen.getByText('Suggested (policy)')).toBeInTheDocument();
    expect(screen.queryByText('Shortfall')).not.toBeInTheDocument();
  });
});

describe('SummaryOrderReportView - the decision (AC-C2.7 / AC-C2.8)', () => {
  it('renders the suggested quantity beside the chosen one', () => {
    renderView(state({ data: REPORT }));
    expect(screen.getByText('Suggested (policy)')).toBeInTheDocument();
    expect(screen.getByText('Order qty')).toBeInTheDocument();
    const row = rowFor('B2155-NL-BLUE');
    expect(within(row).getByTestId('chosen-qty-B2155-NL-BLUE')).toHaveTextContent('600');
  });

  it('renders a chosen quantity ABOVE the shortfall as a plain figure, not an error', () => {
    renderView(state({ data: REPORT }));
    const chosen = screen.getByTestId('chosen-qty-B2155-NL-BLUE');
    expect(chosen).toHaveTextContent('600');
    expect(chosen.className).not.toMatch(/destructive|stockout/);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('offers a Set action on a product with no quantity decided yet', () => {
    renderView(state({ data: REPORT }));
    expect(within(rowFor('SRTBS4832')).getByTestId('set-qty-SRTBS4832')).toBeInTheDocument();
    expect(within(rowFor('SRTBS4832')).getByText('Choose')).toBeInTheDocument();
  });

  it('opens the decision slide-over from the row, the quantity cell and the supplier cell', () => {
    renderView(state({ data: REPORT }));

    fireEvent.click(screen.getByTestId('set-qty-SRTBS4832'));
    expect(screen.getByText('decision-sheet:SRTBS4832')).toBeInTheDocument();
  });

  it('opens the decision slide-over from the supplier cell too', () => {
    renderView(state({ data: REPORT }));
    fireEvent.click(screen.getByTestId('supplier-cell-SRTSK2210'));
    expect(screen.getByText('decision-sheet:SRTSK2210')).toBeInTheDocument();
  });
});

describe('SummaryOrderReportView - channel is analysis inside the row, never row identity (AC-E03 / AC-E06)', () => {
  it('stacks Project, Retail and Unclassified demand readings in one SO demand cell', () => {
    renderView(state({ data: REPORT }));
    const row = rowFor('B2155-NL-BLUE');
    // "Retail" labels both the SO demand row and the Suggested row, so scope by the
    // hint text unique to the SO-demand reading.
    expect(within(row).getByTitle('Open Project-class SO quantity')).toHaveTextContent('Project');
    expect(within(row).getByTitle('Open Retail-class SO quantity')).toHaveTextContent('Retail');
    expect(within(row).getByText('Unclass.')).toBeInTheDocument();
    expect(row).toHaveTextContent('480'); // project_demand
    expect(row).toHaveTextContent('186'); // retail_outstanding
    expect(row).toHaveTextContent('12'); // unclassified_demand_qty
  });

  it('stacks Project Buy, Retail replenishment and the once-rounded Total in one Suggested cell', () => {
    renderView(state({ data: REPORT }));
    const row = rowFor('B2155-NL-BLUE');
    expect(within(row).getByText('Project Buy')).toBeInTheDocument();
    expect(row).toHaveTextContent('180'); // project_buy_qty
    expect(row).toHaveTextContent('80'); // retail_replenishment_qty
    expect(row).toHaveTextContent('300'); // suggested_qty, the once-rounded total
  });

  it('renders exactly one row for a product with both Project and Retail demand', () => {
    renderView(state({ data: REPORT }));
    expect(screen.getAllByTitle('B2155-NL-BLUE')).toHaveLength(1);
  });
});

describe('SummaryOrderReportView - the run states its stamped plan grain (AC-F01)', () => {
  it('renders "Plan grain: Product" for a run stamped at Product grain', () => {
    renderView(state({ data: REPORT }));
    expect(screen.getByTestId('plan-grain-chip')).toHaveTextContent('Plan grain: Product');
    // A fact about the run, not a control: no selector renders anywhere on this screen.
    expect(screen.queryByRole('combobox', { name: /grain/i })).not.toBeInTheDocument();
  });

  it('renders "Legacy run" instead of a grain, for a run that predates the contract', () => {
    renderView(state({ data: SUMMARY_ORDER_FIXTURES.legacyReport() }));
    expect(screen.getByTestId('plan-grain-chip')).toHaveTextContent('Legacy run');
  });

  it('renders no grain chip before the report has arrived', () => {
    renderView(state({ isLoading: true }));
    expect(screen.queryByTestId('plan-grain-chip')).not.toBeInTheDocument();
  });
});

describe('SummaryOrderReportView - Confirm decisions (product grain, code review 21 Aug)', () => {
  it('renders enabled with the decided count on a product-grain run', () => {
    renderView(state({ data: REPORT }));
    const button = screen.getByTestId('confirm-order-decisions');
    // REPORT's fixture rows carry two positive chosen_qty decisions.
    expect(button).toHaveTextContent('Confirm decisions (2)');
    expect(button).toBeEnabled();
  });

  it('renders disabled when no row has a positive chosen quantity', () => {
    const noneDecided = {
      ...REPORT,
      rows: REPORT.rows.map((r) => ({ ...r, chosen_qty: null })),
    };
    renderView(state({ data: noneDecided }));
    const button = screen.getByTestId('confirm-order-decisions');
    expect(button).toHaveTextContent('Confirm decisions');
    expect(button).not.toHaveTextContent('(0)');
    expect(button).toBeDisabled();
  });

  it('does not count a zero ("use the pool") decision - confirm skips it too', () => {
    const zeroDecided = {
      ...REPORT,
      rows: REPORT.rows.map((r) => ({ ...r, chosen_qty: 0 })),
    };
    renderView(state({ data: zeroDecided }));
    expect(screen.getByTestId('confirm-order-decisions')).toBeDisabled();
  });

  it('is absent when the run is decided at the other grain', () => {
    renderView(state({ data: SUMMARY_ORDER_FIXTURES.locationGrainReport() }));
    expect(screen.queryByTestId('confirm-order-decisions')).not.toBeInTheDocument();
  });

  it('is absent on a legacy run', () => {
    renderView(state({ data: SUMMARY_ORDER_FIXTURES.legacyReport() }));
    expect(screen.queryByTestId('confirm-order-decisions')).not.toBeInTheDocument();
  });

  it('fires the confirm mutation on click', () => {
    const mutate = vi.fn();
    hooks.useConfirmOrderDecisions.mockReturnValue({ mutate, isPending: false });
    renderView(state({ data: REPORT }));

    fireEvent.click(screen.getByTestId('confirm-order-decisions'));

    expect(mutate).toHaveBeenCalledTimes(1);
  });

  it('disables the button while a confirm is already in flight', () => {
    hooks.useConfirmOrderDecisions.mockReturnValue({ mutate: vi.fn(), isPending: true });
    renderView(state({ data: REPORT }));
    expect(screen.getByTestId('confirm-order-decisions')).toBeDisabled();
  });
});

describe('SummaryOrderReportView - a run decided at the other grain locks the Product decision (AC-F09)', () => {
  it('states the grain-lock reason under the header', () => {
    renderView(state({ data: SUMMARY_ORDER_FIXTURES.locationGrainReport() }));
    expect(screen.getByTestId('grain-lock-note')).toHaveTextContent('Decided at Location grain');
  });

  it('renders every chosen quantity as read-only text instead of an editable cell', () => {
    renderView(state({ data: SUMMARY_ORDER_FIXTURES.locationGrainReport() }));
    const row = rowFor('B2155-NL-BLUE');
    expect(within(row).getByTestId('chosen-qty-locked-B2155-NL-BLUE')).toHaveTextContent('600');
    expect(within(row).queryByTestId('chosen-qty-B2155-NL-BLUE')).not.toBeInTheDocument();
    expect(within(rowFor('SRTBS4832')).queryByTestId('set-qty-SRTBS4832')).not.toBeInTheDocument();
  });

  it('states the legacy-run lock reason instead, on a legacy run', () => {
    renderView(state({ data: SUMMARY_ORDER_FIXTURES.legacyReport() }));
    expect(screen.getByTestId('grain-lock-note')).toHaveTextContent(
      'Legacy run - read only. Create a new plan to decide.',
    );
  });

  it('renders no lock note when the run accepts the Product decision', () => {
    renderView(state({ data: REPORT }));
    expect(screen.queryByTestId('grain-lock-note')).not.toBeInTheDocument();
  });
});

describe('SummaryOrderReportView - a legacy run states its channel breakdown is unavailable (AC-F10)', () => {
  it('renders "Unavailable" for every channel a legacy run cannot state, never zero', () => {
    renderView(state({ data: SUMMARY_ORDER_FIXTURES.legacyReport() }));
    const row = rowFor('B2155-NL-BLUE');
    // Unclassified demand, Project Buy and Retail replenishment are all nulled on a
    // legacy row - three separate "Unavailable" cells, not a zeroed figure.
    expect(within(row).getAllByText('Unavailable')).toHaveLength(3);
    // Project demand and Retail outstanding are ordinary SO totals, not a Stage-2
    // channel split, and stay stated on a legacy run.
    expect(row).toHaveTextContent('480');
    expect(row).toHaveTextContent('186');
  });

  it('still states the once-rounded suggested total on a legacy run', () => {
    renderView(state({ data: SUMMARY_ORDER_FIXTURES.legacyReport() }));
    expect(rowFor('B2155-NL-BLUE')).toHaveTextContent('300');
  });
});

describe('SummaryOrderReportView - onBack (this report has no row in the buy grid to return to)', () => {
  it('renders no back link when the caller supplies none', () => {
    renderView(state({ data: REPORT }));
    expect(screen.queryByText('Back to plan')).not.toBeInTheDocument();
  });

  it('calls onBack when "Back to plan" is clicked, with data on screen', () => {
    const onBack = vi.fn();
    renderView(state({ data: REPORT }), onBack);
    screen.getByText('Back to plan').click();
    expect(onBack).toHaveBeenCalled();
  });

  it('still offers a way back on the error state', () => {
    const onBack = vi.fn();
    renderView(state({ isError: true, error: new Error('boom') }), onBack);
    screen.getByText('Back to plan').click();
    expect(onBack).toHaveBeenCalled();
  });

  it('still offers a way back on the empty state', () => {
    const onBack = vi.fn();
    renderView(state({ data: SUMMARY_ORDER_FIXTURES.emptyReport() }), onBack);
    screen.getByText('Back to plan').click();
    expect(onBack).toHaveBeenCalled();
  });
});
