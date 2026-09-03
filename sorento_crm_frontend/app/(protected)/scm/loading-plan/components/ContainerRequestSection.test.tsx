/**
 * Stage 1 of Ms Tee's journey (PLAN-scm-loading-plan-demand-first.md): what to ask a supplier
 * for before any container is chosen. The states that matter: a supplier whose products carry
 * no open demand says so plainly, a typed quantity reaches the record that owns it, and a
 * cancelled plan renders the same grid without letting anybody type into it.
 *
 * Send, the gear and the two downloads left this component in part 4 (R5) - they live on the
 * record's toolbar now, and `LoadingPlanView.test.tsx` owns them. What turns the grid's
 * quantities into lines that go out is `requestLinesFrom`, covered in
 * `containerRequestSummary.test.ts`. The "Requests sent to X" card left in S2 for its own
 * Sent tab - `SentRequestsPanel.test.tsx` owns everything about it now.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type {
  ContainerRequestHistoryProduct,
  ContainerRequestRow,
  ContainerRequestSoLine,
  ContainerRequestSources,
} from '../../services/fulfilmentService';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  });
}
if (!window.ResizeObserver) {
  (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

// The gear menu, flattened: Radix opens on pointerdown through a portal, and what this suite
// asks of it is which items it offers, not how it animates. Same stub LoadingPlanView.test.tsx
// uses on the toolbar's own gear.
/* eslint-disable @typescript-eslint/no-explicit-any */
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: any) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: any) => <>{children}</>,
  DropdownMenuContent: ({ children }: any) => <div data-testid="menu-content">{children}</div>,
  DropdownMenuItem: ({ children, onSelect, disabled, ...rest }: any) => (
    <button type="button" onClick={onSelect} disabled={disabled} {...rest}>
      {children}
    </button>
  ),
}));
/* eslint-enable @typescript-eslint/no-explicit-any */

// jsdom answers nothing for the personalization fetch DataGrid drives on mount, which would
// otherwise leave every row under a skeleton (see the memory note on DataGridTable + jsdom).
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

// The lightbox's own data hooks (S2 R7): every drill is one query per open dialog, so a test
// about WHICH dialog a figure opens states what came back rather than waiting on react-query.
const useContainerRequestDrill = vi.fn();
vi.mock('../../hooks/useContainerRequestDrill', () => ({
  useContainerRequestDrill: (...a: unknown[]) => useContainerRequestDrill(...a),
}));

const useLocationStock = vi.fn();
vi.mock('../../reorder/hooks/useReorderRun', () => ({
  useLocationStock: (...a: unknown[]) => useLocationStock(...a),
}));

vi.mock('../../../project-sales/fulfilment-planning/components/StockDocumentsPanel', () => ({
  StockDocumentsPanel: ({ locationCode }: { locationCode: string }) => (
    <div data-testid="stock-documents">{`documents for ${locationCode}`}</div>
  ),
}));

// Partial: `DataGrid` itself reads `usePathname` for its listing key, so replacing the whole
// module would blank the grid this suite is about.
const routerPush = vi.fn();
vi.mock('next/navigation', async (importOriginal) => ({
  ...(await importOriginal<typeof import('next/navigation')>()),
  useRouter: () => ({ push: routerPush }),
}));

// Amended contract (PLAN-scm-loading-plan-demand-first.md section 4, 20 Aug): `not_on_stock_list`
// is gone (the row scope now covers the whole stock list, `has_demand` per row instead), and a
// `sources` block carries the per-document freshness stamp the section's own strip reads.
// SF-7 (reviewer): without the type annotation every field infers as the literal `null`, which
// fails tsc anywhere a non-null override (`{ ...EMPTY_SOURCES, so_book_as_of: fresh }`) is spread
// into it - `ContainerRequestSources` is the real backend contract, string | null per field.
const EMPTY_SOURCES: ContainerRequestSources = {
  so_book_as_of: null,
  po_book_as_of: null,
  spo_as_of: null,
  stock_list_as_of: null,
  proforma_as_of: null,
  proforma_pi_number: null,
};

const state = {
  build: {
    isLoading: false,
    isError: false,
    error: null as Error | null,
    data: undefined as
      | {
          stock_list_as_of: string | null;
          rows: ContainerRequestRow[];
          sources: typeof EMPTY_SOURCES;
          lines?: ContainerRequestSoLine[];
        }
      | undefined,
    isFetching: false,
    refetch: vi.fn(),
  },
  send: {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null as Error | null,
  },
  history: { data: undefined, isFetching: false } as {
    data: { products: ContainerRequestHistoryProduct[] } | undefined;
    isFetching: boolean;
  },
  download: vi.fn(),
};

vi.mock('../../hooks/useFulfilment', () => ({
  useContainerRequestBuild: () => state.build,
  // The sales-history sidecar (F3) is its own query, off by default here: this suite is about
  // the request table, and `ContainerRequestHistory.test.tsx` owns the series itself. The two
  // peak columns need it, so a test that opens one states its own series.
  useContainerRequestHistory: () => state.history,
  useSendContainerRequest: () => state.send,
  useDownloadContainerRequestDocument: () => ({
    mutate: state.download,
    isPending: false,
  }),
}));

import { ContainerRequestSection, holdingSortValue } from './ContainerRequestSection';

function row(over: Partial<ContainerRequestRow> = {}): ContainerRequestRow {
  const merged: ContainerRequestRow = {
    // F12: an ordinary product row. A set row sets `row_kind`, `product_set_id` and the
    // driver fields; `row_key` follows `product_id` unless a test names its own.
    row_key: 'p1',
    row_kind: 'product' as const,
    product_set_id: null,
    set_code: null,
    set_name: null,
    driver_product_id: null,
    driver_item_code: null,
    driver_product_name: null,
    product_id: 'p1',
    item_code: 'ITEM-1',
    product_name: 'Widget',
    open_so_need: 10,
    suggested_qty: 10,
    engine_qty: 10,
    on_hand: 0,
    on_hand_group: 0,
    incoming_spo: 0,
    incoming_spo_group: 0,
    incoming_pl: 0,
    incoming_pl_shipments: [],
    outstanding_po: 0,
    outstanding_po_lines: [],
    sites: [],
    group_locations: { count: 0, on_hand: 0, incoming_spo: 0, warehouse_codes: [] },
    project_qty: 6,
    retail_qty: 4,
    unclassified_qty: 0,
    earliest_required_date: '2026-09-01',
    so_count: 2,
    holding_source: 'stock_list' as const,
    holding_qty: 3,
    holding_as_of: null,
    holding_blocks: 0,
    blocks: [],
    qty_packed: 3,
    qty_unfinished: 1,
    cbm_per_unit: null,
    row_as_of: null,
    rank: 1,
    rank_score: 0.8,
    rank_factors: [],
    has_demand: true,
    ...over,
  };
  // Keyed off whatever `product_id` ended up being, so two rows in one test never collide
  // on the grid's row id just because only one of them named a key. `engine_qty` follows
  // `suggested_qty` unless a test states its own: an unedited row is the engine's answer.
  return {
    ...merged,
    row_key: over.row_key ?? merged.product_id,
    engine_qty: over.engine_qty ?? merged.suggested_qty,
  };
}

/**
 * The section is CONTROLLED since part 4 (R5): the record page owns the typed quantities,
 * because Save and Send act on them from its own toolbar. This harness plays that record -
 * it holds the map and reports every change, so a test can assert both what reached the
 * parent and what the grid shows afterwards.
 */
const onQtyChange = vi.fn();

function Harness({ readOnly }: { readOnly?: boolean }) {
  const [edits, setEdits] = React.useState<Record<string, number>>({});
  return (
    <ContainerRequestSection
      planId="plan-1"
      supplierId="sup-1"
      supplierName="Foshan Ceramics"
      readOnly={readOnly}
      qtyFor={(r) => edits[r.row_key] ?? r.suggested_qty}
      onQtyChange={(rowKey, qty) => {
        onQtyChange(rowKey, qty);
        setEdits((prev) => ({ ...prev, [rowKey]: qty }));
      }}
    />
  );
}

function renderSection(readOnly = false) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Harness readOnly={readOnly} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  state.build = {
    isLoading: false,
    isError: false,
    error: null,
    data: { stock_list_as_of: '2026-08-18T00:00:00', rows: [row()], sources: EMPTY_SOURCES },
    isFetching: false,
    refetch: vi.fn(),
  };
  state.send = { mutate: vi.fn(), isPending: false, isError: false, error: null };
  state.history = { data: undefined, isFetching: false };
  useContainerRequestDrill.mockReset();
  useContainerRequestDrill.mockReturnValue({
    data: { rows: [], total: 0, history: [] },
    isLoading: false,
  });
  useLocationStock.mockReset();
  useLocationStock.mockReturnValue({ data: undefined, isLoading: false });
  routerPush.mockReset();
  state.download = vi.fn();
  onQtyChange.mockReset();
});

describe('ContainerRequestSection - loading / empty / error states', () => {
  it('shows a loading skeleton while the build is in flight', () => {
    state.build.isLoading = true;
    state.build.data = undefined;
    renderSection();
    expect(screen.queryByText('What to ask Foshan Ceramics for')).not.toBeInTheDocument();
  });

  it('says there is nothing to ask for, and points at the list rather than an Upload of its own', () => {
    // AC-A1: a missing stock list is no longer an empty state. AC-A3: the ONE Upload lives on
    // the plans list, so this state says where to go rather than growing a second button.
    state.build.data = { stock_list_as_of: null, rows: [], sources: EMPTY_SOURCES };
    renderSection();

    expect(screen.getByText(/nothing to ask foshan ceramics for right now/i)).toBeInTheDocument();
    expect(screen.getByText(/Start a new plan from the loading plans list/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /upload/i })).not.toBeInTheDocument();
  });

  it('renders the table with no stock list at all, on demand alone', () => {
    // The regression AC-A1 exists to prevent: a supplier who has never sent a stock list used
    // to get a CTA instead of a plan.
    state.build.data = {
      stock_list_as_of: null,
      rows: [row({ holding_source: 'none', holding_qty: null, qty_packed: 0, qty_unfinished: 0 })],
      sources: EMPTY_SOURCES,
    };
    renderSection();

    expect(screen.getByText('ITEM-1')).toBeInTheDocument();
    expect(screen.queryByText(/nothing to ask foshan ceramics for/i)).not.toBeInTheDocument();
  });

  it('shows the error and lets her try again', () => {
    state.build.isError = true;
    state.build.error = new Error('The build blew up');
    renderSection();

    expect(screen.getByText('The build blew up')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(state.build.refetch).toHaveBeenCalledTimes(1);
  });
});

describe('ContainerRequestSection - the grid', () => {
  it('renders the ranked rows with product, need split and stock-on-hand', () => {
    renderSection();

    expect(screen.getByText('ITEM-1')).toBeInTheDocument();
    expect(screen.getByText('Widget')).toBeInTheDocument();
  });

  // AC-A2 / AC-A3: "Packed" says WHICH document said it.
  it('reads the packed quantity off a stock list, and nothing about unfinished (captain, 27 Aug)', () => {
    state.build.data = {
      stock_list_as_of: '2026-08-18T00:00:00',
      rows: [row({ holding_source: 'stock_list', holding_qty: 3, qty_packed: 3, qty_unfinished: 7 })],
      sources: EMPTY_SOURCES,
    };
    renderSection();

    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.queryByText(/unfinished/)).not.toBeInTheDocument();
  });

  it('reads the stand-in proforma with a PI badge, not as packed stock', () => {
    state.build.data = {
      stock_list_as_of: null,
      rows: [
        row({
          holding_source: 'proforma',
          holding_qty: 300,
          holding_as_of: '2026-07-31',
          qty_packed: 0,
          qty_unfinished: 0,
        }),
      ],
      sources: { ...EMPTY_SOURCES, proforma_as_of: '2026-07-31', proforma_pi_number: 'PI-7' },
    };
    renderSection();

    expect(screen.getByText('300')).toBeInTheDocument();
    // Once, on the row: the freshness strip is gone (captain, 27 Aug).
    expect(screen.getAllByText(/PI 31\/07\/2026/)).toHaveLength(1);
    // Not "0 packed": a proforma states one quantity per line and there is no unfinished
    // half of it to report, so reporting zeroes would be inventing the supplier's words.
    expect(screen.queryByText(/0 packed/)).not.toBeInTheDocument();
    expect(screen.queryByText(/unfinished/)).not.toBeInTheDocument();
  });

  it('opens the per-block split behind a proforma figure (AC-F4)', async () => {
    // One uploaded sheet is five stacked invoices; a sum with no split behind it cannot be
    // checked against the paper the supplier actually sent.
    state.build.data = {
      stock_list_as_of: null,
      rows: [
        row({
          holding_source: 'proforma',
          holding_qty: 100,
          holding_as_of: '2026-07-31',
          holding_blocks: 5,
          blocks: [
            { block_index: 4, pi_number: 'PI-JBC-4', qty: 60 },
            { block_index: 5, pi_number: 'PI-JBC-5', qty: 40 },
          ],
          qty_packed: 0,
          qty_unfinished: 0,
        }),
      ],
      sources: { ...EMPTY_SOURCES, proforma_as_of: '2026-07-31', proforma_pi_number: 'PI-JBC-4' },
    };
    renderSection();

    fireEvent.click(screen.getByRole('button', { name: 'Invoice blocks behind this figure' }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('PI-JBC-4')).toBeInTheDocument();
    expect(within(dialog).getByText('PI-JBC-5')).toBeInTheDocument();
    expect(within(dialog).getByText('60')).toBeInTheDocument();
    expect(within(dialog).getByText('40')).toBeInTheDocument();
  });

  it('foots the Packed column with the sum of the blocks (AC-J2/J3 parity, S10 fix 3)', async () => {
    // S9 converted every other row-figure dialog to the shared DataGrid + footer TOTAL;
    // the Blocks table was still a plain <table> with no total row until this fix.
    state.build.data = {
      stock_list_as_of: null,
      rows: [
        row({
          holding_source: 'proforma',
          holding_qty: 100,
          holding_as_of: '2026-07-31',
          holding_blocks: 5,
          blocks: [
            { block_index: 4, pi_number: 'PI-JBC-4', qty: 60 },
            { block_index: 5, pi_number: 'PI-JBC-5', qty: 40 },
          ],
          qty_packed: 0,
          qty_unfinished: 0,
        }),
      ],
      sources: { ...EMPTY_SOURCES, proforma_as_of: '2026-07-31', proforma_pi_number: 'PI-JBC-4' },
    };
    renderSection();

    fireEvent.click(screen.getByRole('button', { name: 'Invoice blocks behind this figure' }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Total')).toBeInTheDocument();
    // 60 + 40 = 100, the same number the row's own "They hold" cell already reads.
    expect(within(dialog).getByText('100')).toBeInTheDocument();
  });

  it('says so when no invoice on the plan names the product', async () => {
    state.build.data = {
      stock_list_as_of: null,
      rows: [
        row({
          holding_source: 'proforma',
          holding_qty: 0,
          holding_as_of: '2026-07-31',
          holding_blocks: 5,
          blocks: [],
          qty_packed: 0,
          qty_unfinished: 0,
        }),
      ],
      sources: { ...EMPTY_SOURCES, proforma_as_of: '2026-07-31', proforma_pi_number: 'PI-JBC-4' },
    };
    renderSection();

    // Nothing to split, so the figure is plain text rather than a door onto an empty table.
    expect(
      screen.queryByRole('button', { name: 'Invoice blocks behind this figure' }),
    ).toBeNull();
  });

  it('reads a dash when neither document names the product', () => {
    // Not a zero: "they have told us nothing" and "they told us they have none" are
    // different answers, and only one of them lets the plan proceed on their word.
    state.build.data = {
      stock_list_as_of: null,
      rows: [row({ holding_source: 'none', holding_qty: null, qty_packed: 0, qty_unfinished: 0 })],
      sources: EMPTY_SOURCES,
    };
    renderSection();

    expect(screen.queryByText('0 packed')).not.toBeInTheDocument();
  });

  // AC-A2.2: the column is gone for good, unclassified demand or not - it goes with part 2's
  // P4 classification work, and the figure still travels on the row for the breakdown.
  it('has no Unclassified column, even when a row carries an unclassified qty', () => {
    state.build.data = {
      stock_list_as_of: '2026-08-18T00:00:00',
      rows: [row({ unclassified_qty: 3 })],
      sources: EMPTY_SOURCES,
    };
    renderSection();
    expect(screen.queryByText('Unclassified')).not.toBeInTheDocument();
  });

  it('shows the four cards above the grid, decomposing the need (AC-A2.1)', () => {
    state.build.data = {
      stock_list_as_of: '2026-08-18T00:00:00',
      rows: [row({ open_so_need: 100, on_hand: 30, incoming_spo: 20, suggested_qty: 50 })],
      sources: EMPTY_SOURCES,
    };
    renderSection();

    const cards = screen.getByTestId('container-request-stat-cards');
    expect(within(cards).getByTestId('stat-need')).toHaveTextContent('100');
    expect(within(cards).getByTestId('stat-pool')).toHaveTextContent('30');
    expect(within(cards).getByTestId('stat-spo')).toHaveTextContent('20');
    expect(within(cards).getByTestId('stat-ask')).toHaveTextContent('50');
    expect(within(cards).queryByTestId('stat-packed')).not.toBeInTheDocument();
  });

  it('the To ask card follows an edited quantity', async () => {
    state.build.data = {
      stock_list_as_of: '2026-08-18T00:00:00',
      rows: [row({ open_so_need: 100, suggested_qty: 100 })],
      sources: EMPTY_SOURCES,
    };
    renderSection();

    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '7' } });

    await waitFor(() =>
      expect(screen.getByTestId('stat-ask')).toHaveTextContent('7'),
    );
  });

  it('carries an Incoming PL column that is never part of the suggestion (AC-B4/B5)', () => {
    state.build.data = {
      stock_list_as_of: '2026-08-18T00:00:00',
      rows: [row({ open_so_need: 10, incoming_pl: 600, suggested_qty: 10 })],
      sources: EMPTY_SOURCES,
    };
    renderSection();

    expect(screen.getByText('Incoming PL')).toBeInTheDocument();
    expect(screen.getByText('600')).toBeInTheDocument();
    expect(screen.getByDisplayValue('10')).toBeInTheDocument(); // the ask, untouched by it
  });

  it('clicking the product opens the row breakdown (AC-A2.3)', async () => {
    renderSection();

    expect(screen.queryByTestId('container-request-row-dialog')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /ITEM-1/ }));

    await waitFor(() =>
      expect(screen.getByTestId('container-request-row-dialog')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('row-quantity-needed')).toBeInTheDocument();
  });

  it('the suggested qty is editable, and the typed figure reaches the record', async () => {
    renderSection();

    fireEvent.change(screen.getByDisplayValue('10'), { target: { value: '25' } });

    expect(onQtyChange).toHaveBeenCalledWith('p1', 25);
    await waitFor(() => expect(screen.getByDisplayValue('25')).toBeInTheDocument());
  });

  it('a cancelled plan shows the same grid, with nothing typeable (AC-A8)', () => {
    renderSection(true);

    expect(screen.getByDisplayValue('10')).toBeDisabled();
  });

  it('the formula tooltip explains the ENGINE figure, not the typed one', () => {
    state.build.data = {
      stock_list_as_of: '2026-08-18T00:00:00',
      rows: [row({ suggested_qty: 25, engine_qty: 10 })],
      sources: EMPTY_SOURCES,
    };
    renderSection();

    expect(screen.getByDisplayValue('25').getAttribute('title')).toContain('= 10');
  });

  it('a set row wears a Set badge and names the member its figures come from (AC-F12.3)', () => {
    state.build.data = {
      stock_list_as_of: '2026-08-18T00:00:00',
      rows: [
        row({
          row_key: 'set:s-1',
          row_kind: 'set',
          product_id: 'p-driver',
          product_set_id: 's-1',
          set_code: 'CWC605-RL',
          set_name: 'Close-coupled WC',
          item_code: 'CWC605-RL',
          product_name: 'Close-coupled WC',
          driver_product_id: 'p-driver',
          driver_item_code: 'CWCX605-RL',
          driver_product_name: 'Pedestal',
        }),
      ],
      sources: EMPTY_SOURCES,
    };
    renderSection();

    expect(screen.getByTestId('set-badge')).toBeInTheDocument();
    expect(screen.getByText('CWC605-RL')).toBeInTheDocument();
    // The driver's code, not the set's name: whose numbers these are is the question the
    // second line answers.
    expect(screen.getByText('CWCX605-RL')).toBeInTheDocument();
  });

  it('two set rows sharing a driver each keep their own editable quantity', () => {
    state.build.data = {
      stock_list_as_of: '2026-08-18T00:00:00',
      rows: [
        row({
          row_key: 'set:s-1',
          row_kind: 'set',
          product_id: 'p-driver',
          product_set_id: 's-1',
          item_code: 'SET-ONE',
          driver_item_code: 'CWCX605-RL',
          suggested_qty: 11,
        }),
        row({
          row_key: 'set:s-2',
          row_kind: 'set',
          product_id: 'p-driver',
          product_set_id: 's-2',
          item_code: 'SET-TWO',
          driver_item_code: 'CWCX605-RL',
          suggested_qty: 22,
        }),
      ],
      sources: EMPTY_SOURCES,
    };
    renderSection();

    expect(screen.getByDisplayValue('11')).toBeInTheDocument();
    expect(screen.getByDisplayValue('22')).toBeInTheDocument();
  });

  it('a quantity edited to 0 keeps its row on the grid', () => {
    state.build.data = {
      stock_list_as_of: '2026-08-18T00:00:00',
      rows: [row({ product_id: 'p1', item_code: 'ITEM-1' }), row({ product_id: 'p2', item_code: 'ITEM-2', suggested_qty: 5 })],
      sources: EMPTY_SOURCES,
    };
    renderSection();

    fireEvent.change(screen.getByDisplayValue('10'), { target: { value: '0' } });

    // She can still see it and change her mind; it just leaves the request.
    expect(screen.getByText('ITEM-1')).toBeInTheDocument();
    expect(onQtyChange).toHaveBeenCalledWith('p1', 0);
  });

  it('Send, the gear and the downloads are NOT here any more (R5)', () => {
    renderSection();

    expect(screen.queryByRole('button', { name: /send to supplier/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Plan actions' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /download/i })).not.toBeInTheDocument();
  });
});

describe('ContainerRequestSection - the fold (S5, AC-E1/AC-E2/AC-E3)', () => {
  it('splits held-but-no-demand rows out of the ranked grid, into their own fold line', () => {
    state.build.data = {
      stock_list_as_of: '2026-08-18T00:00:00',
      rows: [
        row({ product_id: 'p1', item_code: 'ITEM-1' }),
        row({
          product_id: 'p2',
          item_code: 'ITEM-2',
          has_demand: false,
          rank: null,
          open_so_need: 0,
        }),
      ],
      sources: EMPTY_SOURCES,
    };
    renderSection();

    expect(screen.getByText('ITEM-1')).toBeInTheDocument();
    expect(screen.queryByText('ITEM-2')).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /1 products held with no open demand/i }),
    ).toBeInTheDocument();
  });

  it('is collapsed on load; expanding renders the folded row in its own grid, same columns', () => {
    state.build.data = {
      stock_list_as_of: '2026-08-18T00:00:00',
      rows: [
        row({ product_id: 'p1', item_code: 'ITEM-1' }),
        row({
          product_id: 'p2',
          item_code: 'ITEM-2',
          has_demand: false,
          rank: null,
          open_so_need: 0,
        }),
      ],
      sources: EMPTY_SOURCES,
    };
    renderSection();

    const trigger = screen.getByRole('button', { name: /products held with no open demand/i });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('ITEM-2')).not.toBeInTheDocument();

    fireEvent.click(trigger);

    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('ITEM-2')).toBeInTheDocument();
    // Same column set as the ranked grid: rank reads a dash, Need reads the muted copy.
    expect(screen.getByText('No open demand')).toBeInTheDocument();
  });

  it('the fold line is absent when every row carries open demand', () => {
    renderSection(); // default single row, has_demand: true

    expect(screen.queryByText(/products held with no open demand/i)).not.toBeInTheDocument();
  });

  it('a typed qty on a folded row still reaches the record (AC-E3)', () => {
    state.build.data = {
      stock_list_as_of: '2026-08-18T00:00:00',
      rows: [
        row({
          product_id: 'p2',
          item_code: 'ITEM-2',
          has_demand: false,
          rank: null,
          open_so_need: 0,
          suggested_qty: 0,
        }),
      ],
      sources: EMPTY_SOURCES,
    };
    renderSection();

    fireEvent.click(screen.getByRole('button', { name: /1 products held with no open demand/i }));
    fireEvent.change(screen.getByDisplayValue('0'), { target: { value: '15' } });

    expect(onQtyChange).toHaveBeenCalledWith('p2', 15);
  });
});

describe('ContainerRequestSection - the eight figures open the shared lightbox (AC-B1-B7)', () => {
  function soLine(over: Partial<ContainerRequestSoLine> = {}): ContainerRequestSoLine {
    return {
      product_id: 'p1',
      item_code: 'ITEM-1',
      so_number: 'SO-1',
      customer_label: 'Acme Sdn Bhd',
      project_title: null,
      agent_label: null,
      unit_price: null,
      demand_class: 'project',
      order_date: '2026-05-01',
      required_date: '2026-08-19',
      qty: 6,
      ...over,
    };
  }

  function series(peakMonth: string | null, peakQty: number) {
    const months = ['2026-06', '2026-07'].map((month) => ({
      month,
      qty: month === peakMonth ? peakQty : 0,
    }));
    return { months, total: peakQty, avg: peakQty / 2, peak_month: peakMonth, peak_qty: peakQty };
  }

  function withHistory() {
    state.history = {
      data: {
        products: [
          {
            product_id: 'p1',
            project: series('2026-06', 1240),
            retail: series('2026-07', 320),
          } as ContainerRequestHistoryProduct,
        ],
      },
      isFetching: false,
    };
  }

  function openFigure(name: RegExp | string) {
    fireEvent.click(screen.getByRole('button', { name }));
    return screen.getByRole('dialog');
  }

  beforeEach(() => {
    state.build.data = {
      stock_list_as_of: '2026-08-18T00:00:00',
      rows: [row({ on_hand: 40, incoming_spo: 117, incoming_pl: 25, outstanding_po: 60 })],
      sources: EMPTY_SOURCES,
      lines: [
        soLine({
          so_number: 'SO-PROJ',
          demand_class: 'project',
          qty: 6,
          project_title: 'Tuju Residence',
          agent_label: 'Wong Mei Ling',
          unit_price: 12.5,
        }),
        soLine({ so_number: 'SO-RET', demand_class: 'retail', qty: 4 }),
      ],
    };
  });

  it('the Project figure opens the project lines, with the seven columns and a footing total', () => {
    renderSection();

    const dialog = openFigure('Open project sales orders');

    expect(dialog).toHaveTextContent('Project · ITEM-1');
    for (const header of ['Sales order', 'Customer', 'Project', 'Agent', 'Price', 'Qty', 'Required']) {
      expect(within(dialog).getByText(header)).toBeInTheDocument();
    }
    expect(within(dialog).getByText('SO-PROJ')).toBeInTheDocument();
    expect(within(dialog).getByText('Tuju Residence')).toBeInTheDocument();
    expect(within(dialog).getByText('Wong Mei Ling')).toBeInTheDocument();
    // AC-B2: the total foots to the cell, which is the row's own project_qty.
    expect(within(dialog).getByText('Total').closest('tr')).toHaveTextContent('6');
    // The retail line is on the other channel's dialog, never on this one.
    expect(within(dialog).queryByText('SO-RET')).not.toBeInTheDocument();
  });

  it('the Retail figure opens the retail lines, and its total is the retail cell', () => {
    renderSection();

    const dialog = openFigure('Open retail sales orders');

    expect(dialog).toHaveTextContent('Retail · ITEM-1');
    expect(within(dialog).getByText('SO-RET')).toBeInTheDocument();
    expect(within(dialog).queryByText('SO-PROJ')).not.toBeInTheDocument();
    expect(within(dialog).getByText('Total').closest('tr')).toHaveTextContent('4');
  });

  it('the Need cell opens a dialog titled "Need · <code>" listing both channels together with a Channel column (S2, AC-B1/AC-B2)', () => {
    renderSection();

    const dialog = openFigure('Open demand, project and retail');

    expect(dialog).toHaveTextContent('Need · ITEM-1');
    expect(within(dialog).getByText('Channel')).toBeInTheDocument();
    expect(within(dialog).getByText('SO-PROJ')).toBeInTheDocument();
    expect(within(dialog).getByText('SO-RET')).toBeInTheDocument();
    // Total = need = project (6) + retail (4).
    expect(within(dialog).getByText('Total').closest('tr')).toHaveTextContent('10');
  });

  it('the On hand figure opens the location table, pools only, footing to the cell (AC-B3)', () => {
    useLocationStock.mockReturnValue({
      data: {
        as_of: '2026-08-27T10:00:00',
        locations: [
          {
            warehouse_id: 'w1',
            warehouse_code: 'BRW',
            is_pool: true,
            on_hand: 40,
            reserved: 5,
            free: 35,
            so_qty: 10,
            spo_qty: 2,
            available: 25,
          },
          {
            warehouse_id: 'w2',
            warehouse_code: 'PROJ-BIN',
            is_pool: false,
            on_hand: 999,
            reserved: 0,
            free: 999,
            so_qty: 0,
            spo_qty: 0,
            available: 999,
          },
        ],
      },
      isLoading: false,
    });
    renderSection();

    const dialog = openFigure('Stock by location');

    expect(dialog).toHaveTextContent('On hand · ITEM-1');
    expect(within(dialog).getByText('BRW')).toBeInTheDocument();
    expect(within(dialog).queryByText('PROJ-BIN')).not.toBeInTheDocument();
    expect(within(dialog).getByText('Site pools').closest('tr')).toHaveTextContent('40');
  });

  it('the SPO figure opens the shipping orders on their way to a pool (AC-B4)', () => {
    useContainerRequestDrill.mockReturnValue({
      data: {
        rows: [
          {
            spo_number: 'SPO-9',
            shipment_id: 's1',
            shipment_number: 'PL-2608-001',
            warehouse_code: 'BRW',
            qty: 117,
            received: 0,
            eta: '2026-09-10',
            status: 'In transit',
          },
        ],
        total: 117,
        history: [],
      },
      isLoading: false,
    });
    renderSection();

    const dialog = openFigure('Shipping orders on their way to a site pool');

    expect(dialog).toHaveTextContent('SPO · ITEM-1');
    expect(within(dialog).getByText('SPO-9')).toBeInTheDocument();
    expect(within(dialog).getByText('Total').closest('tr')).toHaveTextContent('117');
  });

  it('the Incoming PL figure opens the packing lists, and one opens the packing list itself', () => {
    useContainerRequestDrill.mockReturnValue({
      data: {
        rows: [
          {
            shipment_id: 'ship-7',
            shipment_number: 'PL-2608-004',
            container_number: 'FSCU8103365',
            supplier_name: 'Foshan Ceramics',
            qty: 25,
            eta: '2026-09-02',
            status: 'In transit',
          },
        ],
        total: 25,
        history: [],
      },
      isLoading: false,
    });
    renderSection();

    const dialog = openFigure('Packing lists on their way, reference only');

    expect(dialog).toHaveTextContent('Incoming PL · ITEM-1');
    expect(within(dialog).getByText('FSCU8103365')).toBeInTheDocument();
    expect(within(dialog).getByText('Total').closest('tr')).toHaveTextContent('25');

    fireEvent.click(within(dialog).getByRole('button', { name: 'PL-2608-004' }));
    expect(routerPush).toHaveBeenCalledWith('/procurement-management/packing-lists/ship-7');
  });

  it('the PO figure opens the purchase orders still to come', () => {
    useContainerRequestDrill.mockReturnValue({
      data: {
        rows: [
          {
            purchase_order_id: 'po1',
            po_number: 'PO-77',
            supplier_name: 'Foshan Ceramics',
            qty_ordered: 100,
            still_to_come: 60,
            unit_price: null,
            currency: null,
            issued: '2026-06-01',
            eta: '2026-09-20',
            status: 'Open',
          },
        ],
        total: 60,
        history: [],
      },
      isLoading: false,
    });
    renderSection();

    const dialog = openFigure('Purchase orders still to come, reference only');

    expect(dialog).toHaveTextContent('PO · ITEM-1');
    expect(within(dialog).getByText('PO-77')).toBeInTheDocument();
    expect(within(dialog).getByText('Total still to come').closest('tr')).toHaveTextContent('60');
  });

  it('a peak figure opens its channel dialog on the 12-month tab, with both peak cells marked (AC-B6, S1)', () => {
    withHistory();
    renderSection();

    // The cell states the peak and the month it fell in.
    const peak = screen.getByRole('button', { name: 'Project ordered, last 12 months' });
    expect(peak).toHaveTextContent('1,240');
    expect(peak).toHaveTextContent('Jun 26');

    fireEvent.click(peak);
    const dialog = screen.getByRole('dialog');

    expect(dialog).toHaveTextContent('Project · ITEM-1');
    // Landed ON the history tab, not the open one.
    expect(within(dialog).getByRole('tab', { name: '12-month history' })).toHaveAttribute(
      'data-state',
      'active',
    );
    const projectPeak = dialog.querySelector('[data-peak="project"]');
    const retailPeak = dialog.querySelector('[data-peak="retail"]');
    expect(projectPeak?.textContent).toBe('1,240');
    expect(projectPeak?.closest('tr')).toHaveTextContent('Jun 26');
    expect(retailPeak?.textContent).toBe('320');
    expect(retailPeak?.closest('tr')).toHaveTextContent('Jul 26');
  });

  it('the Retail peak opens the retail dialog on the same tab', () => {
    withHistory();
    renderSection();

    fireEvent.click(screen.getByRole('button', { name: 'Retail ordered, last 12 months' }));

    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveTextContent('Retail · ITEM-1');
    expect(within(dialog).getByRole('tab', { name: '12-month history' })).toHaveAttribute(
      'data-state',
      'active',
    );
  });

  it('names no context beside the title any more (S3, AC-C4)', () => {
    renderSection();

    const dialog = openFigure('Open project sales orders');

    // The header used to carry "N open before cut-off ..." beside the title; the tab now
    // states its own sum, so nothing sits beside "Project · ITEM-1" any more.
    expect(within(dialog).queryByText(/open before cut-off/i)).not.toBeInTheDocument();
    expect(within(dialog).queryByText(/still to come/i)).not.toBeInTheDocument();
    expect(within(dialog).queryByText(/at site pools/i)).not.toBeInTheDocument();
  });

  it('Escape closes the lightbox (AC-B1)', async () => {
    renderSection();
    openFigure('Open project sales orders');

    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape', code: 'Escape' });

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('a channel figure with nothing behind it is plain text, not a dead trigger', () => {
    state.build.data = {
      stock_list_as_of: null,
      rows: [row({ project_qty: 0, retail_qty: 0 })],
      sources: EMPTY_SOURCES,
      lines: [],
    };
    renderSection();

    expect(
      screen.queryByRole('button', { name: 'Open project sales orders' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Open retail sales orders' }),
    ).not.toBeInTheDocument();
  });
});

describe('holdingSortValue - what "Packed" sorts by', () => {
  // Captain, 27 Aug: the unfinished half left the grid, so the column sorts on the one
  // figure it shows. (It used to sort on unfinished, the ordering of the old "Waiting on
  // production" list.)
  it('sorts a stock-list row by its packed quantity', () => {
    expect(holdingSortValue(row({ holding_source: 'stock_list', holding_qty: 9, qty_unfinished: 500 })))
      .toBe(9);
  });

  it('sorts a proforma row by the quantity it states', () => {
    expect(
      holdingSortValue(
        row({ holding_source: 'proforma', holding_qty: 400, qty_packed: 0, qty_unfinished: 0 }),
      ),
    ).toBe(400);
  });

  it('sorts a row neither document names below every row that has a figure', () => {
    expect(holdingSortValue(row({ holding_source: 'none', holding_qty: null, qty_unfinished: 0 })))
      .toBeLessThan(0);
  });
});
