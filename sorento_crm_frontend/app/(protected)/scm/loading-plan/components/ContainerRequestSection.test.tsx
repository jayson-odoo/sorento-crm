/**
 * Stage 1 of Ms Tee's journey (PLAN-scm-loading-plan-demand-first.md): what to ask a supplier
 * for before any container is chosen. The states that matter: a supplier with no stock list
 * gets a CTA to upload one (not a bare empty table), a supplier whose products carry no open
 * demand says so plainly, editing a quantity to 0 removes it from what gets sent without
 * removing the row, and the Send button cannot fire when nothing would go out.
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
  return {
    product_id: 'p1',
    item_code: 'ITEM-1',
    product_name: 'Widget',
    open_so_need: 10,
    suggested_qty: 10,
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
}

function renderSection(onUploadStockList = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    onUploadStockList,
    ...render(
      <QueryClientProvider client={qc}>
        <ContainerRequestSection
          supplierId="sup-1"
          supplierName="Foshan Ceramics"
          onUploadStockList={onUploadStockList}
        />
      </QueryClientProvider>,
    ),
  };
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

  it('says there is nothing to ask for, and still offers the stock-list upload', () => {
    // AC-A1: a missing stock list is no longer an empty state. The plan builds from what we
    // buy from them and what customers are owed, so the ONLY empty state left is "there is
    // genuinely nothing to ask for" - and the upload is a next step, not a prerequisite.
    state.build.data = { stock_list_as_of: null, rows: [], sources: EMPTY_SOURCES };
    const { onUploadStockList } = renderSection();

    expect(screen.getByText(/nothing to ask foshan ceramics for right now/i)).toBeInTheDocument();
    expect(screen.queryByText(/no stock list for foshan ceramics yet/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /upload stock list/i }));
    expect(onUploadStockList).toHaveBeenCalledTimes(1);
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
    // Twice: once in the freshness strip, once on the row - both name the stand-in.
    expect(screen.getAllByText(/PI 31\/07\/2026/)).toHaveLength(2);
    // Not "0 packed": a proforma states one quantity per line and there is no unfinished
    // half of it to report, so reporting zeroes would be inventing the supplier's words.
    expect(screen.queryByText(/0 packed/)).not.toBeInTheDocument();
    expect(screen.queryByText(/unfinished/)).not.toBeInTheDocument();
    // The freshness strip names the document the holdings actually came from.
    expect(screen.queryByText(/Stock list/)).not.toBeInTheDocument();
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

  it('the suggested qty is editable, and edits are what Send sends', async () => {
    renderSection();

    const qtyInput = screen.getByDisplayValue('10');
    fireEvent.change(qtyInput, { target: { value: '25' } });

    fireEvent.click(screen.getByRole('button', { name: /send to supplier/i }));
    fireEvent.click(await screen.findByRole('button', { name: /^send$/i }));

    await waitFor(() => expect(state.send.mutate).toHaveBeenCalledTimes(1));
    const [payload] = state.send.mutate.mock.calls[0];
    expect(payload.lines).toEqual([{ product_id: 'p1', qty: 25 }]);
  });

  it('a quantity edited to 0 is dropped from what gets sent, without leaving the grid', async () => {
    state.build.data = {
      stock_list_as_of: '2026-08-18T00:00:00',
      rows: [row({ product_id: 'p1', item_code: 'ITEM-1' }), row({ product_id: 'p2', item_code: 'ITEM-2', suggested_qty: 5 })],
      sources: EMPTY_SOURCES,
    };
    renderSection();

    fireEvent.change(screen.getByDisplayValue('10'), { target: { value: '0' } });
    // The row stays visible even at 0.
    expect(screen.getByText('ITEM-1')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /send to supplier/i }));
    fireEvent.click(await screen.findByRole('button', { name: /^send$/i }));

    await waitFor(() => expect(state.send.mutate).toHaveBeenCalledTimes(1));
    const [payload] = state.send.mutate.mock.calls[0];
    expect(payload.lines).toEqual([{ product_id: 'p2', qty: 5 }]);
  });

  it('Send is disabled once every row has been edited to 0', () => {
    renderSection();

    fireEvent.change(screen.getByDisplayValue('10'), { target: { value: '0' } });

    expect(screen.getByRole('button', { name: /send to supplier/i })).toBeDisabled();
  });

  it('the confirm dialog states the supplier, line count and channel before anything is sent', async () => {
    renderSection();

    fireEvent.click(screen.getByRole('button', { name: /send to supplier/i }));

    expect(
      await screen.findByText(/send this request to foshan ceramics\?/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/1 product, 10 units in total/i)).toBeInTheDocument();
    expect(state.send.mutate).not.toHaveBeenCalled();
  });
});

describe('ContainerRequestSection - the freshness strip (source staleness)', () => {
  // "plan with trusted data": a source older than a week reads amber, not a hard block.
  it('a source fetched moments ago reads in the ordinary tone, no warning title', () => {
    const fresh = new Date().toISOString();
    state.build.data = {
      stock_list_as_of: '2026-08-18',
      rows: [row()],
      sources: { ...EMPTY_SOURCES, so_book_as_of: fresh },
    };
    renderSection();

    const stamp = screen.getByText(/SO book/).closest('span') as HTMLElement;
    expect(stamp.className).not.toContain('text-amber-600');
    expect(stamp).not.toHaveAttribute('title');
  });

  it('a source over 7 days old reads amber, with a re-upload hint', () => {
    const stale = new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString();
    state.build.data = {
      stock_list_as_of: '2026-08-18',
      rows: [row()],
      sources: { ...EMPTY_SOURCES, so_book_as_of: stale },
    };
    renderSection();

    const stamp = screen.getByText(/SO book/).closest('span') as HTMLElement;
    expect(stamp.className).toContain('text-amber-600');
    expect(stamp).toHaveAttribute('title', 'Consider re-uploading');
  });

  it('a source with no ingest yet renders the em dash, never a fabricated date', () => {
    state.build.data = {
      stock_list_as_of: '2026-08-18',
      rows: [row()],
      sources: EMPTY_SOURCES,
    };
    renderSection();

    expect(screen.getByText(/PO book -/)).toBeInTheDocument();
  });

  // SF-3 (reviewer): the timestamp half must go through `formatDateTimeInMalaysia` (parses
  // naive-UTC, renders MYT) rather than a bare `new Date(iso)`, which reads the naive string as
  // local time and lands the displayed clock 8h early.
  it('a naive-UTC timestamp source renders its time 8h ahead, in Malaysia time', () => {
    state.build.data = {
      stock_list_as_of: '2026-08-18',
      rows: [row()],
      sources: { ...EMPTY_SOURCES, so_book_as_of: '2026-08-18T00:00:00' },
    };
    renderSection();

    const stamp = screen.getByText(/SO book/).closest('span') as HTMLElement;
    expect(stamp.textContent).toContain('8:00 am');
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

describe('ContainerRequestSection - the gear on the header (R23)', () => {
  it('keeps Send as the only button, everything else behind the gear', () => {
    renderSection();

    expect(screen.getByRole('button', { name: /send to supplier/i })).toBeInTheDocument();
    expect(screen.getByLabelText('Plan actions')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /refresh suggestion/i })).toBeInTheDocument();
  });

  it('Refresh suggestion re-runs the build', () => {
    renderSection();

    fireEvent.click(screen.getByRole('button', { name: /refresh suggestion/i }));

    expect(state.build.refetch).toHaveBeenCalledTimes(1);
  });

  it('Copy link is disabled, and says why, until something has been sent', () => {
    renderSection();

    const item = screen.getByRole('button', { name: /copy link/i });
    expect(item).toBeDisabled();
    expect(item).toHaveAttribute('title', 'No link sent yet');
  });

  it('Copy link copies the supplier s current live link', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    state.notices = [
      {
        id: 'n-5', supplier_id: 'sup-1', supplier_name: 'Foshan Ceramics',
        loading_plan_id: null, notice_type: 'container_request', channel: 'email',
        recipient: null, status: 'sent', status_reason: null,
        sent_at: '2026-08-18T02:00:00', attempt_count: 1, last_error: null,
        document_filename: 'container-request.pdf', has_document: true,
        xlsx_filename: null, has_xlsx: false,
        public_url: 'https://crm.test/c/SRT/supplier-request/tok-live',
        link_retired: false,
        container_type: null, container_count: null, planned_cbm: null,
        line_count: 1, production_line_count: 0, created_at: '2026-08-18T02:00:00',
        created_by: 'Ms Tee',
      },
    ];
    renderSection();

    fireEvent.click(
      within(screen.getByTestId('menu-content')).getByRole('button', { name: /copy link/i }),
    );

    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith('https://crm.test/c/SRT/supplier-request/tok-live'),
    );
  });

  it('downloads the sheet for the quantities on screen, without sending anything', () => {
    renderSection();

    fireEvent.change(screen.getByDisplayValue('10'), { target: { value: '25' } });
    fireEvent.click(screen.getByRole('button', { name: /download xlsx/i }));

    expect(state.download).toHaveBeenCalledWith({
      lines: [{ product_id: 'p1', qty: 25 }],
      format: 'xlsx',
    });
    expect(state.send.mutate).not.toHaveBeenCalled();
  });

  it('downloads the PDF off the same lines', () => {
    renderSection();

    fireEvent.click(screen.getByRole('button', { name: /download pdf/i }));

    expect(state.download).toHaveBeenCalledWith({
      lines: [{ product_id: 'p1', qty: 10 }],
      format: 'pdf',
    });
  });

  it('has nothing to download once every quantity is 0', () => {
    renderSection();

    fireEvent.change(screen.getByDisplayValue('10'), { target: { value: '0' } });

    expect(screen.getByRole('button', { name: /download xlsx/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /download pdf/i })).toBeDisabled();
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
