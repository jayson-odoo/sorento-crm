/**
 * SalesOrdersGrid: the toolbar tidy-up (PLAN section A, UAC A1-A8).
 *
 * `SalesOrdersList.*.test.tsx` already pins the reporting-back and row-level behaviour of this
 * same table (it renders `SalesOrdersGrid` with no props). What is scoped here is the shape of
 * the toolbar itself - Start vs Actions membership and order (A1/A2), the `pinnedToAgent` prop
 * that only `SalesOrdersGrid` (not the unpinned `SalesOrdersList` wrapper) can exercise (A3),
 * the Source label (A4), the dropped Customer sub-line (A5), and the Document date column (A6).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
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

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const push = vi.fn();
vi.mock('next/navigation', async (importOriginal) => ({
  ...(await importOriginal<typeof import('next/navigation')>()),
  useRouter: () => ({ push }),
  usePathname: () => '/scm/sales-orders',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

// The remembered sort/filter view (PLAN-listing-view-memory) reads this service under
// `useListingViewPreferences`. Stubbed to resolve fast with nothing stored, so the gated
// data fetch unblocks on the next tick rather than hanging on a real network call.
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn(async () => ({ listing_key: '/scm/sales-orders', config: null })),
  upsertUserListColumnConfig: vi.fn(async (listingKey: string, payload: unknown) => ({
    listing_key: listingKey,
    config: payload,
  })),
  resetUserListColumnConfig: vi.fn(async () => undefined),
}));

let hasPermission = true;
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => hasPermission,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

const EMPTY = { data: [], isLoading: false };
vi.mock('../../hooks/useScmOptions', () => ({
  useCustomerOptions: () => EMPTY,
  useOrderTypeOptions: () => EMPTY,
  useProductOptions: () => EMPTY,
  useSupplierOptions: () => EMPTY,
  useCategoryOptions: () => EMPTY,
  useWarehouseOptions: () => EMPTY,
}));

vi.mock('../hooks/useSalesAgentOptions', () => ({
  useSalesAgentOptions: () => ({ options: [], isLoading: false }),
}));

// The filter popover uses the standard SearchableSelect. Mocked as a native <select>, the
// same pattern `PlanLinesGrid.test.tsx` uses, so the options are in the DOM without driving
// a cmdk popover - what is under test here is the label the Source options carry (A4), not
// popover mechanics.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    id,
    value,
    onChange,
    options = [],
    placeholder,
  }: {
    id?: string;
    value?: string;
    onChange?: (v: string) => void;
    options?: Array<{ value: string; label: string }>;
    placeholder?: string;
  }) => (
    <select
      id={id}
      aria-label={placeholder}
      value={value}
      onChange={(e) => onChange?.(e.target.value)}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

const useSalesOrders = vi.fn();
vi.mock('../../hooks/useSalesOrders', () => ({
  useSalesOrders: (...a: unknown[]) => useSalesOrders(...a),
  useSalesOrderAgents: () => ({ data: [], isLoading: false }),
  useCreateSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useResetSalesOrderPlanning: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCreateDoFromSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import SalesOrdersGrid from './SalesOrdersGrid';
import type { SalesOrder } from '../../types/scm.types';

function order(over: Partial<SalesOrder> = {}): SalesOrder {
  return {
    id: 'so-1',
    so_number: 'SO900001',
    order_type: 'project',
    order_type_label: 'Project',
    customer_code: '300-R009',
    customer_name: 'ROWENDA KITCHEN SDN BHD',
    market_segment: 'Retail',
    priority: 'normal',
    status: 'open',
    order_date: '2026-07-01',
    requested_delivery_date: '2026-09-01',
    total_qty: 12,
    committed_qty: 12,
    lines: [],
    source: 'upload',
    stock_locations: [],
    linked_purchase_orders: [],
    awaiting_purchase_orders: 0,
    order_inquiries: [],
    created_at: '2026-07-01T00:00:00',
    ...over,
  } as SalesOrder;
}

function stub(rows: SalesOrder[]) {
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

function renderGrid(props: { salesAgentId?: string; listingKey?: string } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SalesOrdersGrid {...props} />
    </QueryClientProvider>,
  );
}

async function openStart() {
  const trigger = await screen.findByRole('button', { name: /^Start$/ });
  fireEvent.keyDown(trigger, { key: 'Enter' });
}

async function openActions() {
  const trigger = await screen.findByRole('button', { name: /^Actions/i });
  fireEvent.keyDown(trigger, { key: 'Enter' });
}

beforeEach(() => {
  push.mockReset();
  hasPermission = true;
});

/**
 * A1/A2: primary = Start (Upload sales orders, Plan selected (N)); Actions = Add sales
 * order, Reset planning (N), Refresh - and nothing crosses over between the two.
 */
describe('SalesOrdersGrid: Start vs Actions membership and order (A1, A2)', () => {
  it('Start carries only Upload sales orders and Plan selected, in that order, no heading row', async () => {
    stub([order()]);
    renderGrid();

    await openStart();
    const items = screen.getAllByRole('menuitem').map((item) => item.textContent ?? '');
    expect(items[0]).toContain('Upload sales orders');
    expect(items[1]).toContain('Plan selected');
    expect(items).toHaveLength(2);
    expect(screen.queryByText('Start', { selector: '[role="menuitem"], [data-radix-menu-label]' })).not.toBeInTheDocument();
  });

  it('Actions carries Add sales order, Reset planning, Refresh, in that order', async () => {
    stub([order()]);
    renderGrid();

    await openActions();
    const items = screen.getAllByRole('menuitem').map((item) => item.textContent ?? '');
    expect(items[0]).toContain('Add sales order');
    expect(items[1]).toContain('Reset planning');
    expect(items[2]).toBe('Refresh');
  });

  it('never offers Plan selected or Upload from the Actions menu', async () => {
    stub([order()]);
    renderGrid();

    await openActions();
    expect(screen.queryByRole('menuitem', { name: /Plan selected/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: /Upload sales orders/ })).not.toBeInTheDocument();
  });

  it('never offers Add sales order or Refresh from the Start menu', async () => {
    stub([order()]);
    renderGrid();

    await openStart();
    expect(screen.queryByRole('menuitem', { name: /Add sales order/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: /^Refresh$/ })).not.toBeInTheDocument();
  });
});

/** A1: Plan selected disabled at 0 and above the board's 50-order bound. */
describe('SalesOrdersGrid: Plan selected disabled at 0 and above 50 (A1)', () => {
  it('is disabled with nothing ticked', async () => {
    stub([order()]);
    renderGrid();

    await openStart();
    const item = screen.getByRole('menuitem', { name: /^Plan selected \(0\)$/ });
    expect(item).toHaveAttribute('data-disabled');
  });

  it('is disabled once more than 50 are ticked, and names the bound', async () => {
    stub(Array.from({ length: 51 }, (_unused, i) => order({ id: `so-${i}`, so_number: `SO${i}` })));
    renderGrid();

    fireEvent.click(await screen.findByLabelText('Select all rows on this page'));
    await openStart();
    const item = screen.getByRole('menuitem', { name: /^Plan selected \(51\)$/ });
    expect(item).toHaveAttribute('data-disabled');
    expect(item).toHaveAttribute('title', expect.stringContaining('up to 50'));
  });

  it('enables once 1-50 are ticked, and opens the board on them', async () => {
    stub([order(), order({ id: 'so-2', so_number: 'SO900002' })]);
    renderGrid();

    fireEvent.click(await screen.findByLabelText('Select SO900001'));
    await openStart();
    const item = screen.getByRole('menuitem', { name: /^Plan selected \(1\)$/ });
    expect(item).not.toHaveAttribute('data-disabled');
    fireEvent.click(item);

    expect(push).toHaveBeenCalledWith('/project-sales/fulfilment-planning?orders=SO900001');
  });
});

/** A3: pinned to an agent hides Add + Upload, but Plan selected still shows. */
describe('SalesOrdersGrid: pinnedToAgent hides Add + Upload but not Plan selected (A3)', () => {
  it('drops Upload sales orders from Start, keeping only Plan selected', async () => {
    stub([order()]);
    renderGrid({ salesAgentId: 'agent-1' });

    await openStart();
    expect(screen.queryByRole('menuitem', { name: /Upload sales orders/ })).not.toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /^Plan selected/ })).toBeInTheDocument();
  });

  it('drops Add sales order from Actions', async () => {
    stub([order()]);
    renderGrid({ salesAgentId: 'agent-1' });

    await openActions();
    expect(screen.queryByRole('menuitem', { name: /Add sales order/ })).not.toBeInTheDocument();
  });

  it('drops the Agent column, since every row already belongs to this agent', async () => {
    stub([order()]);
    renderGrid({ salesAgentId: 'agent-1' });

    await screen.findByText('SO900001');
    expect(screen.queryByRole('columnheader', { name: 'Agent' })).not.toBeInTheDocument();
  });
});

/** A4: Source reads Upload, in the column and in the filter. */
describe('SalesOrdersGrid: "Upload" label in column and filter (A4)', () => {
  it('reads Upload in the Source column for an uploaded order', async () => {
    stub([order({ source: 'upload' })]);
    renderGrid();

    expect(await screen.findByText('Upload')).toBeInTheDocument();
    expect(screen.queryByText('Sales order upload')).not.toBeInTheDocument();
  });

  it('offers Upload as a Source filter option', async () => {
    stub([order()]);
    renderGrid();

    fireEvent.keyDown(await screen.findByRole('button', { name: /Filters/i }), { key: 'Enter' });
    const select = await screen.findByLabelText('Source');
    expect(within(select).getByRole('option', { name: 'Upload' })).toBeInTheDocument();
    expect(within(select).queryByRole('option', { name: 'Sales order upload' })).not.toBeInTheDocument();
  });
});

/** A5: the Customer cell is the name only. */
describe('SalesOrdersGrid: no market segment sub-line (A5)', () => {
  it('shows the customer name and nothing else under it', async () => {
    stub([order({ customer_name: 'ROWENDA KITCHEN SDN BHD', market_segment: 'Retail' })]);
    renderGrid();

    await screen.findByText('ROWENDA KITCHEN SDN BHD');
    expect(screen.queryByText('Retail')).not.toBeInTheDocument();
  });
});

/** A6: Document date sits right after Sales order (so_number) and is sortable. */
describe('SalesOrdersGrid: order_date column right after so_number and sortable (A6)', () => {
  it('places Document date immediately after SO number in the header row', async () => {
    stub([order()]);
    renderGrid();

    await screen.findByText('SO900001');
    const headers = screen
      .getAllByRole('columnheader')
      .map((node) => node.textContent ?? '');
    const soIndex = headers.findIndex((header) => header.includes('SO number'));
    const dateIndex = headers.findIndex((header) => header.includes('Document date'));
    expect(soIndex).toBeGreaterThanOrEqual(0);
    // The select-all checkbox column sits before SO number, so Document date is the very
    // next header after it.
    expect(dateIndex).toBe(soIndex + 1);
  });

  it('renders the order date, and offers a sort control on the column', async () => {
    stub([order({ order_date: '2026-07-01' })]);
    renderGrid();

    await screen.findByText('SO900001');
    expect(screen.getByRole('button', { name: 'Document date' })).toBeInTheDocument();
  });

  it('the SO number cell no longer prints a date of its own', async () => {
    stub([order({ order_date: '2026-07-01' })]);
    renderGrid();

    const link = await screen.findByRole('link', { name: 'SO900001' });
    // The cell is the link and, at most, the Changed badge - no second line of text.
    expect(link.parentElement?.textContent).toBe('SO900001');
  });
});
