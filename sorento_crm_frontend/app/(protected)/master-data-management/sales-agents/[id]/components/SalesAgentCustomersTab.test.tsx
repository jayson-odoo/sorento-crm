/**
 * Sales agent -> Customers tab (UAC AC-7, AC-8, AC-9, AC-12). Service modules are mocked, never
 * fetch; the real query hooks and the real DataGrid run.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

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
    dispatchEvent: () => false,
  });
}
Element.prototype.scrollIntoView = vi.fn();

const services = vi.hoisted(() => ({
  getSalesAgentCustomers: vi.fn(),
  assignSalesAgentCustomers: vi.fn(),
}));
vi.mock('../../services/salesAgentService', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  ...services,
}));

const customerSvc = vi.hoisted(() => ({
  searchCustomersSelect: vi.fn(),
  CUSTOMER_SELECT_PAGE_SIZE: 50,
}));
vi.mock('@/app/(protected)/order-management/customers/services/customerService', () => customerSvc);

const permissionState = vi.hoisted(() => ({
  granted: new Set<string>(['master_data.sales_agents.edit']),
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => permissionState.granted.has(slug),
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({
    run: vi.fn(),
    targetId: null,
    countdown: null,
    isPending: false,
  }),
  useRowPending: () => () => false,
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const nav = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push }),
  usePathname: () => '/master-data-management/sales-agents/agent-1',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn(async () => ({ listing_key: 'k', config: null })),
  upsertUserListColumnConfig: vi.fn(async (listingKey: string, payload: unknown) => ({
    listing_key: listingKey,
    config: payload,
  })),
  resetUserListColumnConfig: vi.fn(async () => undefined),
}));

// The real multi-select is a Radix popover; this stand-in lists the fetched options as checkboxes.
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: (props: {
    value: string[];
    onChange: (v: string[]) => void;
    fetchOptions?: (q: string) => Promise<
      { value: string; label: string; description?: string; disabled?: boolean }[]
    >;
  }) => {
    const [opts, setOpts] = React.useState<
      { value: string; label: string; description?: string; disabled?: boolean }[]
    >([]);
    // The real control fetches when it opens, not on mount, so options reflect the rows
    // loaded by then (which is what disables "already linked").
    return (
      <div>
        <button type="button" onClick={() => void props.fetchOptions?.('').then(setOpts)}>
          open picker
        </button>
        {opts.map((o) => (
          <label key={o.value}>
            <input
              type="checkbox"
              aria-label={o.label}
              checked={props.value.includes(o.value)}
              disabled={o.disabled}
              onChange={(e) =>
                props.onChange(
                  e.target.checked
                    ? [...props.value, o.value]
                    : props.value.filter((v) => v !== o.value),
                )
              }
            />
          </label>
        ))}
      </div>
    );
  },
}));

import SalesAgentCustomersTab from './SalesAgentCustomersTab';

const ROWS = [
  {
    id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    customer_code: 'C-100',
    customer_name: 'Hanlim Alpha',
    is_active: true,
    region: 'Selangor',
    market_segment_code: 'retail',
    sales_agent_id: 'agent-1',
    sales_agent_code: 'AG-1',
    sales_agent_name: 'Alice',
  },
  {
    id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    customer_code: 'C-200',
    customer_name: 'Hanlim Beta',
    is_active: false,
    region: null,
    market_segment_code: null,
    sales_agent_id: 'agent-1',
    sales_agent_code: 'AG-1',
    sales_agent_name: 'Alice',
  },
];

// `salesAgentId` is what the tab reads to disable "already on this agent".
const OPTIONS = [
  { value: 'own-1', label: 'Option own', description: 'AG-1 - Alice', salesAgentId: 'agent-1' },
  { value: 'other-1', label: 'Option other', description: 'AG-2 - Bob', salesAgentId: 'agent-2' },
  { value: 'free-1', label: 'Option free', description: 'No sales agent', salesAgentId: null },
].map((o) => ({ ...o, disabled: false }));

function page(rows: typeof ROWS) {
  return { data: rows, pagination: { total: rows.length, page: 1, limit: 50 }, empty: rows.length === 0 };
}

async function openPicker() {
  fireEvent.click(await screen.findByRole('button', { name: 'open picker' }));
}

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SalesAgentCustomersTab agentId="agent-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  Object.values(services).forEach((fn) => fn.mockReset());
  permissionState.granted = new Set(['master_data.sales_agents.edit']);
  nav.push.mockReset();
  services.assignSalesAgentCustomers.mockResolvedValue([ROWS[0]]);
  customerSvc.searchCustomersSelect.mockReset();
  customerSvc.searchCustomersSelect.mockResolvedValue(OPTIONS);
});

afterEach(() => cleanup());

describe('SalesAgentCustomersTab', () => {
  it('AC-7: grid rows carry code, name, region, market segment and status', async () => {
    services.getSalesAgentCustomers.mockResolvedValue(page(ROWS));
    renderTab();

    expect(await screen.findByText('C-100')).toBeInTheDocument();
    expect(screen.getByText('Hanlim Alpha')).toBeInTheDocument();
    expect(screen.getByText('Selangor')).toBeInTheDocument();
    expect(screen.getByText('retail')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.getByText('Inactive')).toBeInTheDocument();
    for (const title of ['Code', 'Name', 'Region', 'Market segment', 'Status']) {
      expect(screen.getAllByText(title).length).toBeGreaterThan(0);
    }
    expect(services.getSalesAgentCustomers.mock.calls[0][0]).toBe('agent-1');
  });

  it('AC-7: a row opens the customer detail', async () => {
    services.getSalesAgentCustomers.mockResolvedValue(page(ROWS));
    renderTab();

    fireEvent.click(await screen.findByText('Hanlim Alpha'));

    await waitFor(() => expect(nav.push).toHaveBeenCalled());
    expect(String(nav.push.mock.calls[0][0])).toContain(
      `/order-management/customers/${ROWS[0].id}`,
    );
  });

  it('AC-8: an agent with no customers shows the empty state', async () => {
    services.getSalesAgentCustomers.mockResolvedValue(page([]));
    renderTab();

    expect(await screen.findByText('No customers assigned')).toBeInTheDocument();
    expect(screen.getByText('Assign the customers this agent handles')).toBeInTheDocument();
  });

  it('AC-9 / AC-15: two ticked (one handled by another agent) reads "Assign 2 customers", one call with both ids', async () => {
    services.getSalesAgentCustomers.mockResolvedValue(page(ROWS));
    renderTab();

    await openPicker();
    fireEvent.click(await screen.findByLabelText('Option other'));
    fireEvent.click(screen.getByLabelText('Option free'));

    const button = screen.getByRole('button', { name: 'Assign customers' });
    expect(button).toHaveTextContent('Assign 2 customers');
    fireEvent.click(button);

    await waitFor(() => expect(services.assignSalesAgentCustomers).toHaveBeenCalledTimes(1));
    expect(services.assignSalesAgentCustomers).toHaveBeenCalledWith('agent-1', [
      'other-1',
      'free-1',
    ]);
  });

  it('AC-15: with nothing ticked the Assign button is disabled', async () => {
    services.getSalesAgentCustomers.mockResolvedValue(page(ROWS));
    renderTab();

    await openPicker();
    await screen.findByLabelText('Option free');
    expect(screen.getByRole('button', { name: 'Assign customers' })).toBeDisabled();
    expect(services.assignSalesAgentCustomers).not.toHaveBeenCalled();
  });

  it('AC-9: a customer already on this agent is a disabled option, the others are not', async () => {
    services.getSalesAgentCustomers.mockResolvedValue(page(ROWS));
    renderTab();

    await openPicker();
    expect(await screen.findByLabelText('Option own')).toBeDisabled();
    expect(screen.getByLabelText('Option other')).toBeEnabled();
    expect(screen.getByLabelText('Option free')).toBeEnabled();
  });

  it('AC-12: with sales_agents.edit each row has Unassign and the assign select shows', async () => {
    services.getSalesAgentCustomers.mockResolvedValue(page(ROWS));
    renderTab();

    await screen.findByText('C-100');
    expect(screen.getAllByRole('button', { name: /unassign/i })).toHaveLength(2);
    expect(screen.getByRole('button', { name: 'Assign customers' })).toBeInTheDocument();
  });

  it('AC-12: without sales_agents.edit the tab is read-only (no select, no Unassign)', async () => {
    permissionState.granted = new Set();
    services.getSalesAgentCustomers.mockResolvedValue(page(ROWS));
    renderTab();

    expect(await screen.findByText('C-100')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Assign customers' })).toBeNull();
    expect(screen.queryByLabelText('Option free')).toBeNull();
    expect(screen.queryByRole('button', { name: /unassign/i })).toBeNull();
  });
});
