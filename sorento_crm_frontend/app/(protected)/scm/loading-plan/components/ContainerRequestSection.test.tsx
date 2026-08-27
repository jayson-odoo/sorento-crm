/**
 * Stage 1 of Ms Tee's journey (PLAN-scm-loading-plan-demand-first.md): what to ask a supplier
 * for before any container is chosen. The states that matter: a supplier whose products carry
 * no open demand says so plainly, a typed quantity reaches the record that owns it, and a
 * cancelled plan renders the same grid without letting anybody type into it.
 *
 * Send, the gear and the two downloads left this component in part 4 (R5) - they live on the
 * record's toolbar now, and `LoadingPlanView.test.tsx` owns them. What turns the grid's
 * quantities into lines that go out is `requestLinesFrom`, covered in
 * `containerRequestSummary.test.ts`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ContainerRequestRow, ContainerRequestSources } from '../../services/fulfilmentService';

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

// B3 gap: the Document button on a sent-notice row calls the real service fn, not a bare fetch.
const getNoticeDocumentUrlMock = vi.fn();
vi.mock('../../services/fulfilmentService', async () => {
  const actual = await vi.importActual<typeof import('../../services/fulfilmentService')>(
    '../../services/fulfilmentService',
  );
  return { ...actual, getNoticeDocumentUrl: (...args: [string]) => getNoticeDocumentUrlMock(...args) };
});

// jsdom answers nothing for the personalization fetch DataGrid drives on mount, which would
// otherwise leave every row under a skeleton (see the memory note on DataGridTable + jsdom).
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
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
          lines?: never[];
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
  notices: [] as unknown[],
  download: vi.fn(),
};

vi.mock('../../hooks/useFulfilment', () => ({
  useContainerRequestBuild: () => state.build,
  // The sales-history sidecar (F3) is its own query, off by default here: this suite is about
  // the request table, and `ContainerRequestHistory.test.tsx` owns the series itself.
  useContainerRequestHistory: () => ({ data: undefined, isFetching: false }),
  useSendContainerRequest: () => state.send,
  useSupplierNotices: () => ({ data: state.notices }),
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
  state.notices = [];
  state.download = vi.fn();
  onQtyChange.mockReset();
  getNoticeDocumentUrlMock.mockReset();
  getNoticeDocumentUrlMock.mockResolvedValue({ url: 'https://cdn.test/doc.pdf', filename: 'doc.pdf' });
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

describe('ContainerRequestSection - requests already sent', () => {
  it('lists a previously sent request with its channel and status', () => {
    state.notices = [
      {
        id: 'n-1', supplier_id: 'sup-1', supplier_name: 'Foshan Ceramics',
        loading_plan_id: null, notice_type: 'container_request', channel: 'email',
        recipient: 'sales@foshan.test', status: 'sent', status_reason: null,
        sent_at: '2026-08-18T02:00:00', attempt_count: 1, last_error: null,
        document_filename: 'container-request.pdf', has_document: true,
        container_type: null, container_count: null, planned_cbm: null,
        line_count: 4, production_line_count: 0, created_at: '2026-08-18T02:00:00',
        created_by: 'Ms Tee',
      },
    ];
    renderSection();

    expect(screen.getByText('Requests sent to Foshan Ceramics')).toBeInTheDocument();
    expect(screen.getByText('Email')).toBeInTheDocument();
    expect(screen.getByText('Sent')).toBeInTheDocument();
  });

  it('a loading-notice (not a request) does not appear in the request panel', () => {
    // Invalidated by S4 (reviewer): the section is now ALWAYS rendered, with an explicit empty
    // state - it can no longer disappear as a proxy for "filtered out". The updated assertion
    // is what S4 actually asks for: the heading stays, a `notice_type: 'loading'` row does not
    // populate it, so the empty-state copy is what shows.
    state.notices = [
      {
        id: 'n-2', supplier_id: 'sup-1', supplier_name: 'Foshan Ceramics',
        loading_plan_id: 'plan-1', notice_type: 'loading', channel: 'email',
        recipient: 'sales@foshan.test', status: 'sent', status_reason: null,
        sent_at: '2026-08-18T02:00:00', attempt_count: 1, last_error: null,
        document_filename: 'loading-notice.pdf', has_document: true,
        container_type: '40HQ', container_count: 1, planned_cbm: 60,
        line_count: 4, production_line_count: 0, created_at: '2026-08-18T02:00:00',
        created_by: 'Ms Tee',
      },
    ];
    renderSection();

    expect(screen.getByText('Requests sent to Foshan Ceramics')).toBeInTheDocument();
    expect(screen.getByText('Nothing sent to this supplier yet.')).toBeInTheDocument();
  });

  const sentRequest = () => ({
    id: 'n-3', supplier_id: 'sup-1', supplier_name: 'Foshan Ceramics',
    loading_plan_id: null, notice_type: 'container_request', channel: 'email',
    recipient: 'sales@foshan.test', status: 'sent', status_reason: null,
    sent_at: '2026-08-18T02:00:00', attempt_count: 1, last_error: null,
    document_filename: 'container-request.pdf', has_document: true,
    xlsx_filename: 'container-request.xlsx', has_xlsx: true,
    public_url: 'https://crm.test/c/SRT/supplier-request/tok-1',
    link_retired: false,
    container_type: null, container_count: null, planned_cbm: null,
    line_count: 4, production_line_count: 0, created_at: '2026-08-18T02:00:00',
    created_by: 'Ms Tee',
  });

  it('clicking PDF calls getNoticeDocumentUrl for that notice and opens the returned url', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    state.notices = [sentRequest()];
    renderSection();

    fireEvent.click(
      within(screen.getByTestId('requests-sent')).getByRole('button', { name: /^pdf$/i }),
    );

    await waitFor(() => expect(getNoticeDocumentUrlMock).toHaveBeenCalledWith('n-3', 'pdf'));
    await waitFor(() =>
      expect(openSpy).toHaveBeenCalledWith('https://cdn.test/doc.pdf', '_blank', 'noopener'),
    );
    openSpy.mockRestore();
  });

  // AC-C4: the card offers all three of what the send produced.
  it('clicking XLSX asks for the spreadsheet, not the pdf', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    state.notices = [sentRequest()];
    renderSection();

    fireEvent.click(
      within(screen.getByTestId('requests-sent')).getByRole('button', { name: /xlsx/i }),
    );

    await waitFor(() => expect(getNoticeDocumentUrlMock).toHaveBeenCalledWith('n-3', 'xlsx'));
    openSpy.mockRestore();
  });

  it('a notice sent before the spreadsheet existed offers no XLSX button', () => {
    state.notices = [{ ...sentRequest(), has_xlsx: false, xlsx_filename: null }];
    renderSection();

    expect(
      within(screen.getByTestId('requests-sent')).queryByRole('button', { name: /xlsx/i }),
    ).not.toBeInTheDocument();
  });

  it('Copy link puts the supplier page on the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    state.notices = [sentRequest()];
    renderSection();

    // Scoped to the card: the gear on the header offers the same action for the CURRENT
    // link, and this is about the row's own button.
    fireEvent.click(
      within(screen.getByTestId('requests-sent')).getByRole('button', { name: /copy link/i }),
    );

    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith('https://crm.test/c/SRT/supplier-request/tok-1'),
    );
  });

  it('a retired link says so instead of offering a dead button (AC-C8)', () => {
    // A copied dead link is worse than no button: the supplier opens it, is told it is gone,
    // and has no way to tell that a live one exists. Silence is not right either - the row
    // would read like one that never carried a link at all.
    state.notices = [{ ...sentRequest(), public_url: null, link_retired: true }];
    renderSection();

    const card = within(screen.getByTestId('requests-sent'));
    expect(card.queryByRole('button', { name: /copy link/i })).not.toBeInTheDocument();
    expect(card.getByText('Link retired')).toBeInTheDocument();
  });

  it('a notice that never carried a link says nothing about one', () => {
    state.notices = [{ ...sentRequest(), public_url: null, link_retired: false }];
    renderSection();

    const card = within(screen.getByTestId('requests-sent'));
    expect(card.queryByRole('button', { name: /copy link/i })).not.toBeInTheDocument();
    expect(card.queryByText('Link retired')).not.toBeInTheDocument();
  });

  it('offers Copy link on BOTH rows of one send (AC-C8)', () => {
    // R23: one credential, delivered two ways. The chat row is the one Ms Tee copies from
    // for WeChat, so a link on the email row alone is a link she cannot reach where she
    // looks for it.
    state.notices = [
      sentRequest(),
      { ...sentRequest(), id: 'n-4', channel: 'chat', status: 'skipped' },
    ];
    renderSection();

    expect(
      within(screen.getByTestId('requests-sent')).getAllByRole('button', { name: /copy link/i }),
    ).toHaveLength(2);
  });
});

describe('ContainerRequestSection - SF-4 (reviewer): the sent-requests card survives every early return', () => {
  it('renders on the nothing-to-ask-for branch', () => {
    state.build.data = { stock_list_as_of: null, rows: [], sources: EMPTY_SOURCES };
    renderSection();

    expect(screen.getByText(/nothing to ask foshan ceramics for right now/i)).toBeInTheDocument();
    expect(screen.getByText('Requests sent to Foshan Ceramics')).toBeInTheDocument();
    expect(screen.getByText('Nothing sent to this supplier yet.')).toBeInTheDocument();
  });

  it('renders on the loading branch', () => {
    state.build.isLoading = true;
    state.build.data = undefined;
    renderSection();

    expect(screen.getByText('Requests sent to Foshan Ceramics')).toBeInTheDocument();
  });

  it('renders on the error branch', () => {
    state.build.isError = true;
    state.build.error = new Error('The build blew up');
    renderSection();

    expect(screen.getByText('Requests sent to Foshan Ceramics')).toBeInTheDocument();
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
