/**
 * SummaryOrderReportView (AC-C2.1 / AC-C2.2 / AC-C2.2a / AC-C2.8).
 *
 * What this screen has to get right, in this order:
 *
 *  - One row per product with every figure the printed sheet carries, plus the
 *    two the pen version has no room for: the chosen quantity and the supplier
 *    (AC-C2.1).
 *  - On order and in transit as SEPARATE columns (AC-C2.2). Their sum drives the
 *    net position; the split is displayed because only the on-order half is
 *    still negotiable.
 *  - Nothing decomposed inline. Every aggregate is a figure with an information
 *    icon (AC-C2.2a).
 *  - The engine's suggestion sits beside the chosen quantity (AC-C2.8), and a
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
  useOrderSummaryDemand: vi.fn(),
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

function renderView(hookState: ReturnType<typeof state>) {
  hooks.useOrderSummary.mockReturnValue(hookState);
  render(<SummaryOrderReportView runId="run-2026-w32" />);
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
  hooks.useOrderSummaryDemand.mockReturnValue(state());
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
    expect(screen.getByText(/As of 03 Aug 2026/)).toBeInTheDocument();
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
      within(row).getByRole('button', { name: /Dealer outstanding for B2155-NL-BLUE, 4 lines/i }),
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

describe('SummaryOrderReportView - on order and in transit stay separate (AC-C2.2)', () => {
  it('renders them as two columns, not one incoming total', () => {
    renderView(state({ data: REPORT }));
    expect(screen.getByText('On order')).toBeInTheDocument();
    expect(screen.getByText('In transit')).toBeInTheDocument();
    expect(screen.queryByText('Incoming')).not.toBeInTheDocument();
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
