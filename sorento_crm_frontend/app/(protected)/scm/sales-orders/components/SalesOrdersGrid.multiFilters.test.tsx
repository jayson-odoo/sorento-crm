/**
 * FILTER-MULTISELECT PR3: the Sales orders grid's Status, Priority, Source, Type, Customer and Agent
 * filters take several values (OR within a filter, AND across), comma-joined to the data hook and
 * into the remembered view. An older saved view holding single values still reads back as a
 * one-value filter, so no filtersVersion bump. Harness mirrors SalesOrdersGrid.viewMemory.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

const push = vi.fn();
// Mutable per test: `useListStateFromUrl` reads this to restore pagination/search from a
// Back-to-list query string (S3-01). Empty by default - a fresh sidebar-click open.
const nav = vi.hoisted(() => ({ search: '' }));
vi.mock('next/navigation', async (importOriginal) => ({
  ...(await importOriginal<typeof import('next/navigation')>()),
  useRouter: () => ({ push }),
  usePathname: () => '/scm/sales-orders',
  useSearchParams: () => new URLSearchParams(nav.search),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const service = vi.hoisted(() => ({
  getUserListColumnConfig: vi.fn(),
  upsertUserListColumnConfig: vi.fn(),
}));
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: (...a: unknown[]) => service.getUserListColumnConfig(...a),
  upsertUserListColumnConfig: (...a: unknown[]) => service.upsertUserListColumnConfig(...a),
  resetUserListColumnConfig: vi.fn(async () => undefined),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

const EMPTY = { data: [], isLoading: false };
// Mutable per test: the customer master is a multi-thousand-row list that resolves later
// than the grid's own first paint, so a test needs to simulate "not resolved yet".
const customerOptionsResult = vi.hoisted(() => ({
  data: [{ value: 'C001', label: 'Acme Kitchens' }] as { value: string; label: string }[],
  isLoading: false,
}));
vi.mock('../../hooks/useScmOptions', () => ({
  useCustomerOptions: () => customerOptionsResult,
  useOrderTypeOptions: () => EMPTY,
  useProductOptions: () => EMPTY,
  useSupplierOptions: () => EMPTY,
  useCategoryOptions: () => EMPTY,
  useWarehouseOptions: () => EMPTY,
}));

vi.mock('../hooks/useSalesAgentOptions', () => ({
  useSalesAgentOptions: () => ({
    options: [{ value: 'AG1', label: 'SEAN I' }],
    isLoading: false,
  }),
}));

// The standard SearchableSelect, stood in for as a native <select> - the same pattern
// `SalesOrdersGrid.test.tsx` uses - so a filter change is one `fireEvent.change` rather than
// driving a cmdk popover. What is under test here is the remembered-view wiring, not the
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


vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, placeholder }: Props) => (
    <select multiple aria-label={placeholder ?? 'multi'} value={value}
      onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
      {(options ?? []).map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

const hooks = vi.hoisted(() => ({ useSalesOrders: vi.fn() }));
vi.mock('../../hooks/useSalesOrders', () => ({
  useSalesOrders: (...a: unknown[]) => hooks.useSalesOrders(...a),
  useSalesOrderAgents: () => ({ data: [], isLoading: false }),
  useCreateSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useResetSalesOrderPlanning: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCreateDoFromSalesOrder: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import SalesOrdersGrid from './SalesOrdersGrid';
import type { SalesOrder } from '../../types/scm.types';

const LISTING_KEY = '/scm/sales-orders';

type ListParams = Record<string, unknown> & { enabled: boolean };

function storedConfig(config: Record<string, unknown> | null) {
  service.getUserListColumnConfig.mockResolvedValue({ listing_key: LISTING_KEY, config });
  service.upsertUserListColumnConfig.mockImplementation(async (listingKey: string, payload: unknown) => ({
    listing_key: listingKey,
    config: payload,
  }));
}

function order(): SalesOrder {
  return {
    id: 'so-1', so_number: 'SO900001', order_type: 'project', order_type_label: 'Project', customer_code: 'C001',
    customer_name: 'Acme Kitchens', market_segment: null, priority: 'normal', status: 'open', order_date: '2026-07-01',
    requested_delivery_date: '2026-09-01', total_qty: 12, committed_qty: 12, lines: [], source: 'upload',
    stock_locations: [], linked_purchase_orders: [], awaiting_purchase_orders: 0, order_inquiries: [],
    created_at: '2026-07-01T00:00:00',
  } as SalesOrder;
}

function mockList() {
  hooks.useSalesOrders.mockImplementation((params: ListParams) => ({
    data: params?.enabled
      ? { data: [order()], pagination: { total: 1, page: 1, limit: 25 }, empty: false }
      : undefined,
    isLoading: false, isFetching: false, refetch: vi.fn(),
  }));
}

function renderGrid() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SalesOrdersGrid />
    </QueryClientProvider>,
  );
}

const lastParams = () => {
  const calls = hooks.useSalesOrders.mock.calls.map((c) => c[0] as ListParams).filter((p) => p.enabled);
  return calls[calls.length - 1];
};

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  nav.search = '';
  customerOptionsResult.data = [
    { value: 'C001', label: 'Acme Kitchens' },
    { value: 'C002', label: 'Beta Baths' },
  ];
  customerOptionsResult.isLoading = false;
  mockList();
});

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  renderGrid();
  await screen.findByText('SO900001');
  await user.click(screen.getByRole('button', { name: /^filters/i }));
}
/** The multi control that offers this option text. */
const boxWith = async (option: string) => {
  const boxes = await screen.findAllByRole('listbox');
  const found = boxes.find((b) => within(b).queryByText(option));
  if (!found) throw new Error(`no multi control offers ${option}`);
  return found as HTMLSelectElement;
};

describe('Sales orders - multi Status, Priority, Source, Type, Customer and Agent filters', () => {
  it('are six multi controls', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    expect(boxes).toHaveLength(6);
    for (const box of boxes) expect(box.hasAttribute('multiple')).toBe(true);
  });

  it('each filter reaches the data hook comma-joined, never with an All placeholder', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await boxWith('Urgent'), ['urgent', 'high']);
    await user.selectOptions(await boxWith('Order inquiry'), ['autocount', 'manual']);
    await user.selectOptions(await boxWith('Retail'), ['project', 'unclassified']);
    await user.selectOptions(await boxWith('Beta Baths'), ['C001', 'C002']);
    await user.selectOptions(await boxWith('SEAN I'), ['AG1']);
    await waitFor(() =>
      expect(lastParams()).toMatchObject({
        priority: 'urgent,high', source: 'autocount,manual', demandClass: 'project,unclassified',
        customerCode: 'C001,C002', salesAgentId: 'AG1',
      }),
    );
  });

  it('two statuses reach the hook comma-joined and write comma-joined into the remembered view', async () => {
    storedConfig(null);
    const user = userEvent.setup();
    await openFilters(user);
    const box = (await screen.findAllByRole('listbox')).find((b) => within(b).queryByText('Completed')) as HTMLSelectElement;
    await user.selectOptions(box, ['open', 'closed']);
    await waitFor(() => expect(lastParams().status).toBe('open,closed'));
    await waitFor(
      () => {
        const [, payload] = service.upsertUserListColumnConfig.mock.calls.at(-1)!;
        expect(payload).toMatchObject({ filters: { status: 'open,closed' } });
      },
      { timeout: 3000 },
    );
  });

  it('an older saved view holding single values reads back as one-value filters (no version bump)', async () => {
    storedConfig({
      version: 1,
      sorting: [{ id: 'order_date', desc: true }],
      filters: { status: 'open', priority: 'high', source: 'upload', demand_class: 'retail', customer_code: 'C001', sales_agent_id: 'AG1' },
      filtersVersion: 2,
    });
    renderGrid();
    await screen.findByText('SO900001');
    expect(lastParams()).toMatchObject({
      status: 'open', priority: 'high', source: 'upload', demandClass: 'retail', customerCode: 'C001', salesAgentId: 'AG1',
    });
  });

  it('a saved view holding comma-joined values reads back as the same several-value filters', async () => {
    storedConfig({
      version: 1,
      sorting: [{ id: 'order_date', desc: true }],
      filters: { status: 'open,closed', priority: 'high,low', source: 'upload,manual' },
      filtersVersion: 2,
    });
    renderGrid();
    await screen.findByText('SO900001');
    expect(lastParams()).toMatchObject({ status: 'open,closed', priority: 'high,low', source: 'upload,manual' });
  });

  it('the chip names several values once per filter and clearing it drops them all', async () => {
    storedConfig({
      version: 1,
      sorting: [{ id: 'order_date', desc: true }],
      filters: { status: 'open,closed', customer_code: 'C001,C002' },
      filtersVersion: 2,
    });
    const user = userEvent.setup();
    renderGrid();
    await screen.findByText('SO900001');
    expect(await screen.findByText(/Acme Kitchens, Beta Baths/)).toBeInTheDocument();
    expect(screen.queryByText(/C001/)).toBeNull();
    await user.click(screen.getByRole('button', { name: /^clear filter/i }));
    await waitFor(() => expect(lastParams().status).toBeNull());
    expect(lastParams().customerCode).toBeNull();
  });
});
