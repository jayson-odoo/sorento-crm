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
  assignSalesAgentCustomer: vi.fn(),
}));
vi.mock('../../services/salesAgentService', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  ...services,
}));

vi.mock('@/app/(protected)/order-management/customers/services/customerService', () => ({
  searchCustomersSelect: vi.fn(async () => []),
  CUSTOMER_SELECT_PAGE_SIZE: 50,
}));

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

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
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

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: { onChange: (v: string) => void; 'aria-label'?: string }) => (
    <button type="button" onClick={() => props.onChange('99999999-8888-4777-8666-555555555555')}>
      pick:{props['aria-label']}
    </button>
  ),
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

function page(rows: typeof ROWS) {
  return { data: rows, pagination: { total: rows.length, page: 1, limit: 50 }, empty: rows.length === 0 };
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
  services.assignSalesAgentCustomer.mockResolvedValue(ROWS[0]);
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

    await screen.findByText('C-100');
    const hrefs = Array.from(document.querySelectorAll('a')).map((a) => a.getAttribute('href'));
    expect(hrefs).toContain(`/order-management/customers/${ROWS[0].id}`);
  });

  it('AC-8: an agent with no customers shows the empty state', async () => {
    services.getSalesAgentCustomers.mockResolvedValue(page([]));
    renderTab();

    expect(await screen.findByText('No customers assigned')).toBeInTheDocument();
    expect(screen.getByText('Assign the customers this agent handles')).toBeInTheDocument();
  });

  it('AC-9: picking a customer calls assign with the agent and that customer id, no refusal', async () => {
    services.getSalesAgentCustomers.mockResolvedValue(page(ROWS));
    renderTab();

    fireEvent.click(await screen.findByRole('button', { name: /pick:Assign customer/ }));

    await waitFor(() => expect(services.assignSalesAgentCustomer).toHaveBeenCalledTimes(1));
    expect(services.assignSalesAgentCustomer).toHaveBeenCalledWith(
      'agent-1',
      '99999999-8888-4777-8666-555555555555',
    );
  });

  it('AC-12: with sales_agents.edit each row has Unassign and the assign select shows', async () => {
    services.getSalesAgentCustomers.mockResolvedValue(page(ROWS));
    renderTab();

    await screen.findByText('C-100');
    expect(screen.getAllByRole('button', { name: /unassign/i })).toHaveLength(2);
    expect(screen.getByRole('button', { name: /pick:Assign customer/ })).toBeInTheDocument();
  });

  it('AC-12: without sales_agents.edit the tab is read-only (no select, no Unassign)', async () => {
    permissionState.granted = new Set();
    services.getSalesAgentCustomers.mockResolvedValue(page(ROWS));
    renderTab();

    expect(await screen.findByText('C-100')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /pick:Assign customer/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /unassign/i })).toBeNull();
  });
});
