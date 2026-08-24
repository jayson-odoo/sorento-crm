/**
 * Stage 1 of Ms Tee's journey (PLAN-scm-loading-plan-demand-first.md): what to ask a supplier
 * for before any container is chosen. The states that matter: a supplier with no stock list
 * gets a CTA to upload one (not a bare empty table), a supplier whose products carry no open
 * demand says so plainly, editing a quantity to 0 removes it from what gets sent without
 * removing the row, and the Send button cannot fire when nothing would go out.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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
  // What the supplier holds unfinished, per the feed the ranked table's "They hold" column
  // now folds in (captain follow-up, 20 Aug). Empty by default - only the "unmatched" tests
  // below populate it.
  unfinished: [] as { item_code: string; product_name: string | null; qty_unfinished: number; qty_packed: number; as_of: string | null }[],
};

vi.mock('../../hooks/useFulfilment', () => ({
  useContainerRequestBuild: () => state.build,
  useSendContainerRequest: () => state.send,
  useSupplierNotices: () => ({ data: state.notices }),
  useUnfinishedStock: () => ({ data: state.unfinished }),
}));

import { ContainerRequestSection } from './ContainerRequestSection';

function row(over: Partial<ContainerRequestRow> = {}): ContainerRequestRow {
  return {
    product_id: 'p1',
    item_code: 'ITEM-1',
    product_name: 'Widget',
    open_so_need: 10,
    suggested_qty: 10,
    on_hand: 0,
    incoming_spo: 0,
    outstanding_po: 0,
    project_qty: 6,
    retail_qty: 4,
    unclassified_qty: 0,
    earliest_required_date: '2026-09-01',
    so_count: 2,
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
  state.unfinished = [];
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

  it('offers a CTA to upload a stock list when this supplier has none yet, not a bare table', () => {
    state.build.data = { stock_list_as_of: null, rows: [], sources: EMPTY_SOURCES };
    const { onUploadStockList } = renderSection();

    expect(screen.getByText(/no stock list for foshan ceramics yet/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /upload stock list/i }));
    expect(onUploadStockList).toHaveBeenCalledTimes(1);
  });

  it('says plainly when the supplier\'s products carry no open demand', () => {
    state.build.data = { stock_list_as_of: '2026-08-18T00:00:00', rows: [], sources: EMPTY_SOURCES };
    renderSection();

    expect(
      screen.getByText(/no open customer demand for what foshan ceramics supplies/i),
    ).toBeInTheDocument();
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
    expect(screen.getByText('2')).toBeInTheDocument(); // so_count
  });

  it('the Unclassified column only appears when a row actually carries one', () => {
    renderSection();
    expect(screen.queryByText('Unclassified')).not.toBeInTheDocument();
  });

  it('the Unclassified column appears once a row carries a nonzero unclassified qty', () => {
    state.build.data = {
      stock_list_as_of: '2026-08-18T00:00:00',
      rows: [row({ unclassified_qty: 3 })],
      sources: EMPTY_SOURCES,
    };
    renderSection();
    expect(screen.getByText('Unclassified')).toBeInTheDocument();
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

  it('clicking Document calls getNoticeDocumentUrl for that notice and opens the returned url', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    state.notices = [
      {
        id: 'n-3', supplier_id: 'sup-1', supplier_name: 'Foshan Ceramics',
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

    fireEvent.click(screen.getByRole('button', { name: /document/i }));

    await waitFor(() => expect(getNoticeDocumentUrlMock).toHaveBeenCalledWith('n-3'));
    await waitFor(() =>
      expect(openSpy).toHaveBeenCalledWith('https://cdn.test/doc.pdf', '_blank', 'noopener'),
    );
    openSpy.mockRestore();
  });
});

describe('ContainerRequestSection - SF-4 (reviewer): the sent-requests card survives every early return', () => {
  it('renders on the no-stock-list branch', () => {
    state.build.data = { stock_list_as_of: null, rows: [], sources: EMPTY_SOURCES };
    renderSection();

    expect(screen.getByText(/no stock list for foshan ceramics yet/i)).toBeInTheDocument();
    expect(screen.getByText('Requests sent to Foshan Ceramics')).toBeInTheDocument();
    expect(screen.getByText('Nothing sent to this supplier yet.')).toBeInTheDocument();
  });

  it('renders on the zero-rows (no open demand) branch', () => {
    state.build.data = { stock_list_as_of: '2026-08-18T00:00:00', rows: [], sources: EMPTY_SOURCES };
    renderSection();

    expect(
      screen.getByText(/no open customer demand for what foshan ceramics supplies/i),
    ).toBeInTheDocument();
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

describe('ContainerRequestSection - the sort arrow sorts (BL-027 / AC-G01)', () => {
  /** The item code of every rendered row, top to bottom. */
  function codeOrder(): string[] {
    return Array.from(document.querySelectorAll('tbody tr')).map(
      (tr) => tr.querySelectorAll('td')[1]?.querySelector('span')?.textContent?.trim() ?? '',
    );
  }

  function threeHoldings() {
    state.build.data = {
      stock_list_as_of: '2026-08-18T00:00:00',
      rows: [
        row({ product_id: 'p1', item_code: 'AAA-9', rank: 1, qty_unfinished: 9 }),
        row({ product_id: 'p2', item_code: 'BBB-10', rank: 2, qty_unfinished: 10 }),
        row({ product_id: 'p3', item_code: 'CCC-2', rank: 3, qty_unfinished: 2 }),
      ],
      sources: EMPTY_SOURCES,
    };
    renderSection();
  }

  it('reorders on what the supplier holds numerically (9 before 10)', () => {
    threeHoldings();
    // Untouched, the table is in the engine's rank order.
    expect(codeOrder()).toEqual(['AAA-9', 'BBB-10', 'CCC-2']);

    // The shared header always opens a column ascending, so 2 leads, not 10.
    fireEvent.click(screen.getByRole('button', { name: 'They hold' }));

    expect(codeOrder()).toEqual(['CCC-2', 'AAA-9', 'BBB-10']);
  });

  it('reverses on the second click', () => {
    threeHoldings();

    fireEvent.click(screen.getByRole('button', { name: 'They hold' }));
    fireEvent.click(screen.getByRole('button', { name: 'They hold' }));

    expect(codeOrder()).toEqual(['BBB-10', 'AAA-9', 'CCC-2']);
  });
});
