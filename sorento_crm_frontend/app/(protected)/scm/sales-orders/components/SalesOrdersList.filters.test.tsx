/**
 * Getting to one order out of 11,626, and opening it.
 *
 * > "the filter, needs to be dynamic, like i will want to search by date range, customer,
 * > any outstanding all these things, and btw the whole row should be clickble"
 *
 * Status, priority and source were the only filters, and none of them answers the questions
 * this screen is actually asked. What is asserted here is that each control reaches the query
 * - the filtering itself is the backend's, pinned in
 * `tests/scm/test_sales_order_list_filters.py` - and that a click anywhere on a row opens the
 * order without breaking the SO-number anchor.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

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
Element.prototype.scrollIntoView = vi.fn();

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

// The real `DateRangePicker` is a Popover + react-day-picker Calendar - its own behaviour
// (enforcing from <= to by construction) is not this list's concern and has no repo pattern
// for driving a Calendar grid under jsdom. Stood in for here with a single button that fires
// `onChange` with both ends at once - the ONE-FACT contract the real widget guarantees - so
// what this suite asserts is that the list wires the range into both query params, not that
// the calendar itself works.
vi.mock('@/components/ui/date-range-picker', () => ({
  DateRangePicker: (props: {
    id?: string;
    from?: string | null;
    to?: string | null;
    onChange: (next: { from: string | null; to: string | null }) => void;
    placeholder?: string;
  }) => (
    <button
      type="button"
      id={props.id}
      onClick={() => props.onChange({ from: '2026-03-01', to: '2026-03-31' })}
    >
      {props.from && props.to ? `${props.from} - ${props.to}` : (props.placeholder ?? 'Pick a date range')}
    </button>
  ),
}));

const push = vi.fn();
// PARTIAL. The grid and its toolbar reach for other exports of this module, and replacing it
// wholesale left them undefined - which showed up as a grid stuck on its loading skeleton
// rather than as an error.
vi.mock('next/navigation', async (importOriginal) => ({
  ...(await importOriginal<typeof import('next/navigation')>()),
  useRouter: () => ({ push }),
  usePathname: () => '/scm/sales-orders',
  useSearchParams: () => new URLSearchParams(),
}));

const EMPTY = { data: [], isLoading: false };
vi.mock('../../hooks/useScmOptions', () => ({
  useCustomerOptions: () => ({
    data: [{ value: '300-R009', label: 'Rowenda Kitchen Sdn Bhd' }],
    isLoading: false,
  }),
  // The Add-sales-order modal renders alongside the list and reaches for these.
  useOrderTypeOptions: () => EMPTY,
  useProductOptions: () => EMPTY,
  useSupplierOptions: () => EMPTY,
  useCategoryOptions: () => EMPTY,
  useWarehouseOptions: () => EMPTY,
}));

// The grid asks for the user's saved column order via this hook, which reads the route to
// build its listing key. With `next/navigation` mocked the hook goes down its fetching path
// and the grid sits on its loading skeleton, so it is stubbed the same way the detail suite
// stubs it.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const useSalesOrders = vi.fn();
vi.mock('../../hooks/useSalesOrders', () => ({
  useSalesOrders: (...a: unknown[]) => useSalesOrders(...a),
  useSalesOrderAgents: () => ({ data: [], isLoading: false }),
  useCreateSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCreateDoFromSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import SalesOrdersList from './SalesOrdersList';
import type { SalesOrder } from '../../types/scm.types';

function order(over: Partial<SalesOrder> = {}): SalesOrder {
  return {
    id: 'so-1',
    so_number: 'SO900001',
    order_type: 'project',
    order_type_label: 'Project',
    customer_code: '300-R009',
    customer_name: 'Rowenda Kitchen Sdn Bhd',
    market_segment: null,
    priority: 'normal',
    status: 'open',
    order_date: '2026-07-01',
    requested_delivery_date: '2026-09-01',
    total_qty: 12,
    committed_qty: 12,
    lines: [],
    source: 'inquiry',
    internal_note: null,
    stock_locations: [],
    linked_purchase_orders: [],
    created_at: '2026-07-01T00:00:00',
    ...over,
  } as SalesOrder;
}

function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SalesOrdersList />
    </QueryClientProvider>,
  );
}

function stub(rows: SalesOrder[] = [order()]) {
  useSalesOrders.mockReturnValue({
    data: {
      data: rows,
      pagination: { total: rows.length, page: 1, limit: 25 },
      empty: !rows.length,
    },
    isLoading: false,
    isFetching: false,
    refetch: vi.fn(),
  });
}

/** The arguments of the most recent list query. */
function lastQuery(): Record<string, unknown> {
  return useSalesOrders.mock.calls[useSalesOrders.mock.calls.length - 1][0] as Record<
    string,
    unknown
  >;
}

async function openFilters() {
  fireEvent.pointerDown(
    screen.getByRole('button', { name: /^Filters/ }),
    { ctrlKey: false, button: 0 },
  );
  await screen.findByText('Still owed');
}

beforeEach(() => {
  useSalesOrders.mockReset();
  push.mockReset();
});

describe('SalesOrdersList - the whole row opens the order', () => {
  it('navigates when a cell other than the number is clicked', async () => {
    stub();
    renderList();

    fireEvent.click(await screen.findByText('Rowenda Kitchen Sdn Bhd'));

    expect(push).toHaveBeenCalledWith(expect.stringContaining('/scm/sales-orders/so-1'));
  });

  it('carries the list query so the detail pager walks the same set', async () => {
    stub();
    renderList();

    fireEvent.click(await screen.findByText('Rowenda Kitchen Sdn Bhd'));

    expect(push).toHaveBeenCalledWith(expect.stringMatching(/\?.*page=1/));
  });

  it('leaves the SO-number anchor working as a link', async () => {
    // A real anchor, so middle-click and "copy link" still behave. It stops its own click
    // propagating, or the row handler would fire a second navigation on top of the anchor's.
    stub();
    renderList();

    const link = await screen.findByRole('link', { name: 'SO900001' });
    expect(link).toHaveAttribute('href', expect.stringContaining('/scm/sales-orders/so-1'));

    fireEvent.click(link);
    expect(push).not.toHaveBeenCalled();
  });
});

describe('SalesOrdersList - dynamic filters', () => {
  it('sends a date range from the date-range picker, both ends at once', async () => {
    // Two bare fields let "to" land before "from"; the range picker is ONE control that
    // emits both ends together, so this asserts the list forwards that pair as-is.
    stub();
    renderList();
    await openFilters();

    fireEvent.click(screen.getByLabelText('Ordered'));

    await waitFor(() => {
      expect(lastQuery()).toMatchObject({ dateFrom: '2026-03-01', dateTo: '2026-03-31' });
    });
  });

  it('sends the customer the user picked', async () => {
    stub();
    renderList();
    await openFilters();

    // The customer's name is also a cell in the row behind the popover, so the option is
    // taken from inside the listbox rather than from the page.
    fireEvent.click(screen.getByRole('combobox', { name: /customer/i }));
    const option = await screen.findByRole('option', { name: /Rowenda Kitchen Sdn Bhd/ });
    fireEvent.click(option);

    await waitFor(() => {
      expect(lastQuery()).toMatchObject({ customerId: '300-R009' });
    });
  });

  it('sends "still owed" only when it is on', async () => {
    stub();
    renderList();
    await openFilters();

    expect(lastQuery()).toMatchObject({ outstanding: false });

    fireEvent.click(screen.getByRole('switch', { name: /still owed/i }));

    await waitFor(() => {
      expect(lastQuery()).toMatchObject({ outstanding: true });
    });
  });

  it('sends the demand class the user picked as "Type"', async () => {
    stub();
    renderList();
    await openFilters();

    expect(lastQuery()).toMatchObject({ demandClass: null });

    fireEvent.click(screen.getByRole('combobox', { name: /type/i }));
    const option = await screen.findByRole('option', { name: 'Project' });
    fireEvent.click(option);

    await waitFor(() => {
      expect(lastQuery()).toMatchObject({ demandClass: 'project' });
    });
  });

  it('sends "unclassified" for the Type filter, not the whole list', async () => {
    stub();
    renderList();
    await openFilters();

    fireEvent.click(screen.getByRole('combobox', { name: /type/i }));
    const option = await screen.findByRole('option', { name: 'Unclassified' });
    fireEvent.click(option);

    await waitFor(() => {
      expect(lastQuery()).toMatchObject({ demandClass: 'unclassified' });
    });
  });

  it('counts every active filter, so the badge does not undercount', async () => {
    stub();
    renderList();
    await openFilters();

    // The date-range picker sets BOTH ends in one act - two of the eight filters this badge
    // sums - plus the switch, so the count is 3, not 1.
    fireEvent.click(screen.getByLabelText('Ordered'));
    fireEvent.click(screen.getByRole('switch', { name: /still owed/i }));

    expect(await screen.findByText('3')).toBeInTheDocument();
  });

  it('clears the new filters along with the old ones', async () => {
    stub();
    renderList();
    await openFilters();

    fireEvent.click(screen.getByLabelText('Ordered'));
    fireEvent.click(screen.getByRole('switch', { name: /still owed/i }));
    fireEvent.click(screen.getByRole('combobox', { name: /type/i }));
    fireEvent.click(await screen.findByRole('option', { name: 'Project' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Clear filters' }));

    await waitFor(() => {
      expect(lastQuery()).toMatchObject({
        dateFrom: null,
        dateTo: null,
        outstanding: false,
        demandClass: null,
      });
    });
  });
});
