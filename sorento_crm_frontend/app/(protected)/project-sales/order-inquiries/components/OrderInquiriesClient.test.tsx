/**
 * Purchasing's cross-project order inquiry (the screen).
 *
 * What is worth pinning is the part a person would notice going wrong: every response
 * shape renders explicitly, the month strip is a real filter that reaches the service and
 * survives being used, the search box gets there too, the export asks for the same
 * filtered set the grid is showing, and each row links to the right document - the CORE
 * sales order for an adopted row, the project document for an authored one, and nothing
 * at all for a row that can reach neither.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  MOCK_WORKLIST_ROWS,
  MOCK_WORKLIST_SUMMARY,
} from '../../_shared/__mocks__/orderInquiryWorklist';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/order-inquiries',
  useSearchParams: () => new URLSearchParams(''),
}));

// Under jsdom nothing answers the preferences fetch, so the grid renders skeletons for
// ever and no row is assertable.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const listOrderInquiryWorklist = vi.fn();
const getOrderInquiryWorklistSummary = vi.fn();
const downloadOrderInquiryWorklistXlsx = vi.fn();

vi.mock('../../_shared/services/orderInquiryService', () => ({
  listOrderInquiryWorklist: (...args: unknown[]) => listOrderInquiryWorklist(...args),
  getOrderInquiryWorklistSummary: (...args: unknown[]) =>
    getOrderInquiryWorklistSummary(...args),
  downloadOrderInquiryWorklistXlsx: (...args: unknown[]) =>
    downloadOrderInquiryWorklistXlsx(...args),
}));

const saveBlobAs = vi.fn();
vi.mock('../../_shared/services/fileDownload', () => ({
  saveBlobAs: (...args: unknown[]) => saveBlobAs(...args),
  filenameFromContentDisposition: vi.fn(),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

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

import { OrderInquiriesClient } from './OrderInquiriesClient';

function envelope(rows: OrderInquiryWorklistRow[]) {
  return { data: rows, total: rows.length, page: 1, limit: 25 };
}

function renderClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <OrderInquiriesClient />
    </QueryClientProvider>,
  );
}

/** Radix opens its dropdown menus on pointerdown, which fireEvent.click does not send. */
function openFilters() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /filters/i }), {
    button: 0,
    ctrlKey: false,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  listOrderInquiryWorklist.mockResolvedValue(envelope(MOCK_WORKLIST_ROWS));
  getOrderInquiryWorklistSummary.mockResolvedValue(MOCK_WORKLIST_SUMMARY);
  downloadOrderInquiryWorklistXlsx.mockResolvedValue(new Blob(['x']));
});

describe('OrderInquiriesClient', () => {
  it('shows the rows purchasing has been told to buy', async () => {
    renderClient();

    expect(await screen.findByText('SO385126')).toBeInTheDocument();
    expect(screen.getByText('SRTWC8605-SC-RL')).toBeInTheDocument();
    expect(screen.getByText('Wall hung basin 5400')).toBeInTheDocument();
    expect(screen.getByText('DAFUYUAN')).toBeInTheDocument();
    expect(screen.getByText('202601-S0015')).toBeInTheDocument();
  });

  it('renders the columns in the order their own spreadsheet has them', async () => {
    renderClient();
    await screen.findByText('SO385126');

    const headers = screen
      .getAllByRole('columnheader')
      .map((cell) => cell.textContent ?? '');
    const order = [
      'SO date',
      'S/O no',
      'Item code',
      'Qty',
      'Delivery date',
      'Project / customer',
      'Location',
      'Supplier',
      'PO no',
      'Instruction',
      'State',
    ];
    let cursor = -1;
    for (const title of order) {
      const at = headers.findIndex(
        (text, index) => index > cursor && text.includes(title),
      );
      expect(at, `${title} out of order`).toBeGreaterThan(cursor);
      cursor = at;
    }
  });

  it('names the verb on every row, so a borrow shortfall is not mistaken for an order', async () => {
    listOrderInquiryWorklist.mockResolvedValue(
      envelope([
        MOCK_WORKLIST_ROWS[0],
        {
          ...MOCK_WORKLIST_ROWS[1],
          id: 'oi-borrow',
          so_number: 'SO390001',
          verb: 'BORROW_SHORTFALL',
          note: 'BRW-BB is short by 12',
        },
      ]),
    );

    renderClient();

    const shortfall = (await screen.findByText('SO390001')).closest('tr') as HTMLElement;
    expect(within(shortfall).getByText('BORROW SHORTFALL')).toBeInTheDocument();
    // The server's note is behind the info icon now, not inline under the pill (A3).
    expect(within(shortfall).queryByText('BRW-BB is short by 12')).not.toBeInTheDocument();
    fireEvent.focus(within(shortfall).getByRole('button', { name: 'Why this instruction' }));
    expect(await screen.findByRole('tooltip')).toHaveTextContent('BRW-BB is short by 12');
    const order = screen.getByText('SO385126').closest('tr') as HTMLElement;
    expect(within(order).getByText('ORDER')).toBeInTheDocument();
    expect(within(order).queryByText('BORROW SHORTFALL')).not.toBeInTheDocument();
  });

  it('says nothing has been raised yet, and offers the screen that raises it', async () => {
    listOrderInquiryWorklist.mockResolvedValue(envelope([]));
    getOrderInquiryWorklistSummary.mockResolvedValue({
      ...MOCK_WORKLIST_SUMMARY,
      total_rows: 0,
      by_month: [],
    });
    renderClient();

    expect(await screen.findByText('Nothing has been raised yet')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /open fulfilment planning/i }),
    ).toHaveAttribute('href', '/project-sales/fulfilment-planning');
    expect(screen.getByText('No delivery months yet')).toBeInTheDocument();
  });

  it('says the failure out loud rather than showing an empty table', async () => {
    listOrderInquiryWorklist.mockRejectedValue(new Error('Backend is down'));
    renderClient();

    expect(
      await screen.findByText('The order inquiry could not be loaded'),
    ).toBeInTheDocument();
    expect(screen.getByText('Backend is down')).toBeInTheDocument();
  });

  it('renders a loading state before the first answer arrives', async () => {
    listOrderInquiryWorklist.mockReturnValue(new Promise(() => {}));
    const { container } = renderClient();

    await waitFor(() =>
      expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(
        0,
      ),
    );
  });

  it('a month tab narrows the list and the strip, and the tabs stay', async () => {
    renderClient();
    await screen.findByText('SO385126');

    fireEvent.click(screen.getByRole('button', { name: /JAN 26/ }));

    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
        expect.objectContaining({ delivery_month: '2026-01' }),
      ),
    );
    // The month strip is the control that changes month, so it must survive being used.
    expect(screen.getByRole('button', { name: /MAR 26/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /all months/i })).toBeInTheDocument();
  });

  it('sends the search box to the service', async () => {
    renderClient();
    await screen.findByText('SO385126');

    fireEvent.change(screen.getByLabelText('Search order inquiry rows'), {
      target: { value: 'SRTWT107' },
    });

    await waitFor(
      () =>
        expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
          expect.objectContaining({ query: 'SRTWT107' }),
        ),
      { timeout: 2000 },
    );
  });

  it('sends the state filter to the service', async () => {
    renderClient();
    await screen.findByText('SO385126');

    openFilters();
    fireEvent.change(await screen.findByLabelText('Every state'), {
      target: { value: 'raised' },
    });

    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
        expect.objectContaining({ state: 'raised' }),
      ),
    );
  });

  it('exports the set the screen is showing, not the whole book', async () => {
    renderClient();
    await screen.findByText('SO385126');
    fireEvent.click(screen.getByRole('button', { name: /JAN 26/ }));
    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
        expect.objectContaining({ delivery_month: '2026-01' }),
      ),
    );

    fireEvent.click(screen.getByRole('button', { name: /export excel/i }));

    await waitFor(() =>
      expect(downloadOrderInquiryWorklistXlsx).toHaveBeenCalledWith(
        expect.objectContaining({ delivery_month: '2026-01' }),
      ),
    );
    await waitFor(() => expect(saveBlobAs).toHaveBeenCalled());
    expect(saveBlobAs.mock.calls[0][1]).toBe('order-inquiry-2026-01.xlsx');
  });

  it('links an adopted row to the core sales order and a project row to its own', async () => {
    renderClient();

    expect(await screen.findByRole('link', { name: 'SO385126' })).toHaveAttribute(
      'href',
      '/scm/sales-orders/so-385126',
    );
    expect(screen.getByRole('link', { name: 'SO363150' })).toHaveAttribute(
      'href',
      '/project-sales/proj-9/sales-orders/pso-3',
    );
  });

  it('leaves a row that can reach no document as plain text', async () => {
    listOrderInquiryWorklist.mockResolvedValue(
      envelope([
        {
          ...MOCK_WORKLIST_ROWS[0],
          id: 'row-orphan',
          so_number: 'SO999999',
          core_sales_order_id: null,
          project_id: null,
          project_sales_order_id: null,
        },
      ]),
    );
    renderClient();

    expect(await screen.findByText('SO999999')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'SO999999' })).toBeNull();
  });

  it('prints the location it was stamped with, and nothing when it has none', async () => {
    renderClient();

    const donor = (await screen.findByText('SO385126')).closest('tr') as HTMLElement;
    expect(within(donor).getByText('BRW-BB')).toBeInTheDocument();

    const unlocated = screen.getByText('SO386461').closest('tr') as HTMLElement;
    expect(within(unlocated).queryByText('BRW-BB')).not.toBeInTheDocument();
  });

  it('says "not placed" rather than inventing a supplier', async () => {
    listOrderInquiryWorklist.mockResolvedValue(
      envelope([MOCK_WORKLIST_ROWS[1]]),
    );
    renderClient();

    const row = (await screen.findByText('SRTWC8605-SC-RL')).closest('tr');
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getAllByText('Not placed')).toHaveLength(2);
  });
});
