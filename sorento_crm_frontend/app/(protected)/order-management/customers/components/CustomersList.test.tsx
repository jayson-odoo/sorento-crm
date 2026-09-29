/**
 * CustomersList - the "Sales Agent" column (#1170 slice 1, PR #1177 review).
 *
 * The review's kill test found this column had no coverage at all: rendering the raw
 * `sales_agent_id` UUID in the cell left the full vitest suite green (mutation F8). Pinned
 * here: the cell shows `code - name`, never the id, and has an explicit dash when unset.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Customer } from '../types/customer.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => '/order-management/customers',
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

vi.mock('@/components/upload-activity', () => ({
  useImportJobDrawer: () => ({ notifyImportQueued: vi.fn() }),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => false,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

vi.mock('../services/customerImportService', () => ({
  importCustomers: vi.fn(),
  validateCustomerImport: vi.fn(),
}));

const ROWS: Customer[] = [
  {
    id: 'cust-with-agent',
    customer_code: 'C-001',
    customer_name: 'Alpha Trading',
    email: null,
    phone_number: null,
    is_active: true,
    created_at: new Date('2026-01-01T00:00:00Z'),
    sales_agent_id: 'agent-1',
    sales_agent_code: 'SEAN I',
    sales_agent_name: 'Sean Tan',
  },
  {
    id: 'cust-without-agent',
    customer_code: 'C-002',
    customer_name: 'Beta Supplies',
    email: null,
    phone_number: null,
    is_active: true,
    created_at: new Date('2026-01-02T00:00:00Z'),
    sales_agent_id: null,
    sales_agent_code: null,
    sales_agent_name: null,
  },
];

vi.mock('../hooks/useCustomers', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../hooks/useCustomers')>()),
  useCustomers: () => ({
    data: { data: ROWS, pagination: { page: 1, limit: 50, total: ROWS.length } },
    isLoading: false,
    isPlaceholderData: false,
    isFetching: false,
    refetch: vi.fn(),
  }),
}));

import CustomersList from './CustomersList';

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <CustomersList />
    </QueryClientProvider>,
  );
}

function rowFor(code: string): HTMLElement {
  return screen.getByText(code).closest('tr') as HTMLElement;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('CustomersList - Sales Agent column', () => {
  it('has a Sales Agent column header', () => {
    renderList();
    expect(screen.getAllByText('Sales Agent').length).toBeGreaterThan(0);
  });

  it('renders code - name, never the raw agent id', () => {
    renderList();
    const row = rowFor('C-001');
    expect(row.textContent).toContain('SEAN I - Sean Tan');
    expect(row.textContent).not.toContain('agent-1');
  });

  it('shows a dash for a customer with no agent assigned', () => {
    renderList();
    const row = rowFor('C-002');
    expect(row.textContent).toContain('-');
    expect(row.textContent).not.toContain('SEAN I');
  });
});
