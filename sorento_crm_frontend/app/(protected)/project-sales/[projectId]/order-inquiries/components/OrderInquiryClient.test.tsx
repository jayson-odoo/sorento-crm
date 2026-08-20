/**
 * The order inquiry screen (P10, AC-I1 to AC-I7).
 *
 * What is pinned here is what the client and the AC each asked for: ONE toolbar row
 * carrying search, filters, columns and the export action, a pinned listing key, the
 * verb in purchasing's own spelling, the coverage naming what covers a row, an EMPTY
 * stock location when no allocation is confirmed, and no UUID anywhere on screen.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { OrderInquiryRow } from '../../../_shared/types/orderInquiry.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const listOrderInquiryRows = vi.fn();
const getOrderInquirySummary = vi.fn();
const markOrderInquiryRows = vi.fn();
const downloadOrderInquiryXlsx = vi.fn();
const getProject = vi.fn();
const listingKeys: (string | null | undefined)[] = [];

vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/p1/order-inquiries',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: ({ listingKey }: { listingKey?: string | null }) => {
    listingKeys.push(listingKey);
    return { resetToDefaults: async () => {}, isLoading: false };
  },
}));

vi.mock('../../../_shared/services/orderInquiryService', () => ({
  listOrderInquiryRows: (...args: unknown[]) => listOrderInquiryRows(...args),
  getOrderInquirySummary: (...args: unknown[]) => getOrderInquirySummary(...args),
  markOrderInquiryRows: (...args: unknown[]) => markOrderInquiryRows(...args),
  getSalesOrderInquiry: vi.fn(),
  downloadOrderInquiryXlsx: (...args: unknown[]) => downloadOrderInquiryXlsx(...args),
}));

vi.mock('../../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../../_shared/services/projectService')
  >();
  return { ...actual, getProject: (...args: unknown[]) => getProject(...args) };
});

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() },
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
      aria-label={placeholder ?? 'select'}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

import { OrderInquiryClient } from './OrderInquiryClient';

function row(overrides: Partial<OrderInquiryRow> = {}): OrderInquiryRow {
  return {
    id: 'row-1',
    order_inquiry_id: 'inq-1',
    sales_order_ref: 'SO397450',
    project_customer: 'BUIMACO / TUJU RESIDENCE',
    item_code: 'CB6633',
    qty: '600',
    delivery_date: '2027-01-07',
    stock_location: 'BRW-BB',
    verb: 'ORDER',
    remark: 'ORDER',
    state: 'raised',
    ...overrides,
  };
}

function envelope(rows: OrderInquiryRow[]) {
  return { data: rows, total: rows.length, page: 1, limit: 25 };
}

function renderClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <OrderInquiryClient projectId="p1" />
    </QueryClientProvider>,
  );
}

/** Radix opens its popovers on pointerdown, which fireEvent.click does not send. */
function openFilters() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /filters/i }), {
    button: 0,
    ctrlKey: false,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  listingKeys.length = 0;
  listOrderInquiryRows.mockResolvedValue(envelope([]));
  getOrderInquirySummary.mockResolvedValue({
    total: 0,
    raised: 0,
    actioned: 0,
    cancelled: 0,
  });
  getProject.mockResolvedValue({
    id: 'p1',
    project_code: 'PRJ-0001',
    title: 'Tuju Residence',
  });
  markOrderInquiryRows.mockResolvedValue([]);
});

describe('OrderInquiryClient', () => {
  it('puts search, filters, columns and the export action on ONE toolbar row', async () => {
    renderClient();

    const toolbar = (await screen.findByPlaceholderText(/Search item code/i)).closest(
      '[data-slot="card-header"]',
    ) as HTMLElement;
    expect(within(toolbar).getByRole('button', { name: /filters/i })).toBeInTheDocument();
    expect(within(toolbar).getByRole('button', { name: /columns/i })).toBeInTheDocument();
    expect(within(toolbar).getByRole('button', { name: /export excel/i })).toBeInTheDocument();
    expect(within(toolbar).getByRole('button', { name: 'Refresh list' })).toBeInTheDocument();
  });

  it('pins its own listing key rather than falling back to the pathname', async () => {
    renderClient();

    await waitFor(() => expect(listingKeys.length).toBeGreaterThan(0));
    expect(listingKeys).toContain('projects.projects.view::project-order-inquiry');
    expect(listingKeys).not.toContain('/project-sales/p1/order-inquiries');
  });

  it('renders a row with the number, the code and the instruction, and no UUID', async () => {
    listOrderInquiryRows.mockResolvedValue(envelope([row()]));

    renderClient();

    expect(await screen.findByText('SO397450')).toBeInTheDocument();
    expect(screen.getByText('CB6633')).toBeInTheDocument();
    // The Qty column only: the Instruction cell drops its own copy of the figure (it duplicated
    // the Qty column rather than adding to it) and shows the verb pill and info icon alone.
    expect(screen.getByText('600')).toBeInTheDocument();
    expect(screen.getByText('BRW-BB')).toBeInTheDocument();
    expect(screen.getByText('ORDER')).toBeInTheDocument();
    expect(screen.getByText('Raised')).toBeInTheDocument();
    expect(screen.queryByText('row-1')).not.toBeInTheDocument();
    expect(screen.queryByText('inq-1')).not.toBeInTheDocument();
  });

  it('spells a covered row the way purchasing writes it and says what covers it', async () => {
    listOrderInquiryRows.mockResolvedValue(
      envelope([
        row({
          id: 'row-covered',
          verb: 'PRE_ORDERED_DO_NOT_ORDER',
          covered_by: 'Pre-order SO383057',
          remark: 'PRE-ORDERED, DO NOT ORDER',
        }),
      ]),
    );

    renderClient();

    expect(await screen.findByText('PRE-ORDERED, DO NOT ORDER')).toBeInTheDocument();
    expect(screen.getByText('Pre-order SO383057')).toBeInTheDocument();
  });

  it('spells RESERVE & ORDER with the ampersand, not the stored constant', async () => {
    listOrderInquiryRows.mockResolvedValue(
      envelope([row({ verb: 'RESERVE_AND_ORDER', remark: 'RESERVE & ORDER' })]),
    );

    renderClient();

    expect(await screen.findByText('RESERVE & ORDER')).toBeInTheDocument();
    expect(screen.queryByText('RESERVE_AND_ORDER')).not.toBeInTheDocument();
  });

  it('shows the SPO reference on a row already on the water', async () => {
    listOrderInquiryRows.mockResolvedValue(
      envelope([
        row({
          verb: 'ALREADY_INBOUND',
          spo_ref: '202511-S0022',
          covered_by: 'Inbound SPO 202511-S0022',
          remark: '202511-S0022',
        }),
      ]),
    );

    renderClient();

    expect(await screen.findByText('Inbound SPO 202511-S0022')).toBeInTheDocument();
  });

  it('says a buying row is covered by nothing rather than leaving the cell blank', async () => {
    listOrderInquiryRows.mockResolvedValue(envelope([row({ covered_by: null })]));

    renderClient();

    expect(await screen.findByText('Nothing covers this')).toBeInTheDocument();
  });

  it('leaves the stock location empty when no allocation is confirmed', async () => {
    listOrderInquiryRows.mockResolvedValue(envelope([row({ stock_location: null })]));

    renderClient();

    expect(await screen.findByText('Not allocated yet')).toBeInTheDocument();
    expect(screen.queryByText('BRW-BB')).not.toBeInTheDocument();
  });

  it('carries the previous date on a DELAY, because the verb alone is not actionable', async () => {
    listOrderInquiryRows.mockResolvedValue(
      envelope([row({ verb: 'DELAY', remark: 'DELAY', note: 'Was 2026-07-01' })]),
    );

    renderClient();

    expect(await screen.findByText('DELAY')).toBeInTheDocument();
    // Behind the info icon now, not inline under the pill (A3).
    expect(screen.queryByText('Was 2026-07-01')).not.toBeInTheDocument();
    fireEvent.focus(screen.getByRole('button', { name: 'Why this instruction' }));
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Was 2026-07-01');
  });

  it('shows who actioned a row and when', async () => {
    listOrderInquiryRows.mockResolvedValue(
      envelope([
        row({
          state: 'actioned',
          actioned_by_name: 'Eling',
          actioned_at: '2026-08-03T02:00:00',
        }),
      ]),
    );

    renderClient();

    // The row first: "Actioned" is also a column heading, so waiting on it alone
    // resolves before the data has landed.
    expect(await screen.findByText('SO397450')).toBeInTheDocument();
    expect(screen.getByText(/Eling on /)).toBeInTheDocument();
  });

  it('renders an empty state that points at where the rows come from', async () => {
    renderClient();

    expect(await screen.findByText('Nothing has been raised yet')).toBeInTheDocument();
    // Stage 1C: a row is raised by the CONFIRMATION, not by publishing the sales order.
    expect(
      screen.getByText(
        /Confirming a Project SO in Fulfilment Planning raises the rows purchasing acts on/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /open fulfilment planning/i }),
    ).toHaveAttribute('href', '/project-sales/fulfilment-planning');
  });

  it('says the filters emptied the list rather than that nothing exists', async () => {
    listOrderInquiryRows.mockResolvedValue(envelope([]));

    renderClient();
    await screen.findByText('Nothing has been raised yet');

    openFilters();
    fireEvent.change(await screen.findByLabelText('Every instruction'), {
      target: { value: 'DELAY' },
    });

    expect(await screen.findByText('No rows match')).toBeInTheDocument();
  });

  it('filters by verb through the service rather than in the browser', async () => {
    renderClient();
    await screen.findByPlaceholderText(/Search item code/i);

    openFilters();
    fireEvent.change(await screen.findByLabelText('Every instruction'), {
      target: { value: 'DELAY' },
    });

    await waitFor(() =>
      expect(listOrderInquiryRows).toHaveBeenLastCalledWith(
        'p1',
        expect.objectContaining({ verb: 'DELAY' }),
      ),
    );
  });

  it('shows the error state rather than an empty grid when the load fails', async () => {
    listOrderInquiryRows.mockRejectedValue(new Error('Backend unavailable'));

    renderClient();

    expect(await screen.findByText('The order inquiry could not be loaded')).toBeInTheDocument();
    expect(screen.getByText('Backend unavailable')).toBeInTheDocument();
  });

  it('exports the filtered set with the same filters the list is showing', async () => {
    downloadOrderInquiryXlsx.mockResolvedValue(new Blob(['x']));
    const createObjectURL = vi.fn(() => 'blob:x');
    const revokeObjectURL = vi.fn();
    Object.assign(URL, { createObjectURL, revokeObjectURL });
    listOrderInquiryRows.mockResolvedValue(envelope([row()]));

    renderClient();
    await screen.findByText('SO397450');

    openFilters();
    fireEvent.change(await screen.findByLabelText('Every state'), {
      target: { value: 'raised' },
    });
    // The filter popover is modal, so everything behind it is out of the
    // accessibility tree until it closes.
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' });
    const exportButton = await screen.findByRole('button', { name: /export excel/i });
    fireEvent.click(exportButton);

    await waitFor(() =>
      expect(downloadOrderInquiryXlsx).toHaveBeenCalledWith(
        'p1',
        expect.objectContaining({ state: 'raised' }),
      ),
    );
  });

  it('marks the selected rows actioned through the service', async () => {
    listOrderInquiryRows.mockResolvedValue(
      envelope([row(), row({ id: 'row-2', sales_order_ref: 'SO397460' })]),
    );

    renderClient();
    await screen.findByText('SO397450');

    fireEvent.click(screen.getAllByLabelText('Select row')[0]);
    fireEvent.click(await screen.findByRole('button', { name: /mark actioned/i }));

    await waitFor(() =>
      expect(markOrderInquiryRows).toHaveBeenCalledWith(['row-1'], 'actioned'),
    );
  });

  // ------------------------------------------------- AC-D06: the trace to the decision
  it('traces a Buy row to the Project SO, its line number and the decision revision', async () => {
    listOrderInquiryRows.mockResolvedValue(
      envelope([
        row({
          project_so_ref: 'PSO-000123',
          line_no: 4,
          decision_revision: 2,
        }),
      ]),
    );

    renderClient();

    expect(await screen.findByText('PSO-000123')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    // The item code and the required date are the other two halves of the same trace.
    expect(screen.getByText('CB6633')).toBeInTheDocument();
  });

  it('states an amendment row as belonging to no project decision, rather than blank', async () => {
    listOrderInquiryRows.mockResolvedValue(
      envelope([
        row({ project_so_ref: null, line_no: null, decision_revision: null }),
      ]),
    );

    renderClient();

    expect(await screen.findByText('No line')).toBeInTheDocument();
    expect(screen.getByText('Not from a project')).toBeInTheDocument();
    expect(screen.getByText('Not from a decision')).toBeInTheDocument();
  });

  it('renders no UUID-looking id on the trace columns, only the human identifiers', async () => {
    listOrderInquiryRows.mockResolvedValue(
      envelope([
        row({
          id: 'f1e2d3c4-5678-4a90-b123-456789abcdef',
          order_inquiry_id: 'a1b2c3d4-5678-4a90-b123-456789abcdef',
          so_line_id: 'b2c3d4e5-5678-4a90-b123-456789abcdef',
          project_sales_order_id: 'c3d4e5f6-5678-4a90-b123-456789abcdef',
          project_so_ref: 'PSO-000123',
          line_no: 4,
          decision_revision: 2,
        }),
      ]),
    );

    const { container } = renderClient();

    await screen.findByText('PSO-000123');
    expect(container.textContent).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i);
  });

  it('offers no way to author a row, because instructions are derived', async () => {
    listOrderInquiryRows.mockResolvedValue(envelope([row()]));

    renderClient();
    await screen.findByText('SO397450');

    expect(screen.queryByRole('button', { name: /^add/i })).not.toBeInTheDocument();
  });
});
