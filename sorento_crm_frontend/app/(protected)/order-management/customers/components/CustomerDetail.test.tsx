/**
 * CustomerDetail - the "Sales Agent" read-only field (#1170 slice 1).
 *
 * Same section and position as the form's field (Contact Information / after Phone), code
 * + name only - no UUID ever reaches the screen - and an explicit empty state when unset.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  usePathname: () => '/order-management/customers/cust-1',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => false,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

const getCustomer = vi.fn();
vi.mock('../services/customerService', () => ({
  getCustomer: (...a: unknown[]) => getCustomer(...a),
  createCustomer: vi.fn(),
  updateCustomer: vi.fn(),
  getCustomers: vi.fn(),
  deleteCustomer: vi.fn(),
  getCustomerSalesAgentsSelect: vi.fn().mockResolvedValue([]),
}));

import CustomerDetail from './CustomerDetail';

const BASE = {
  id: 'cust-1',
  customer_code: 'C-001',
  customer_name: 'Alpha Trading',
  email: null,
  phone_number: '03-1111111',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
};

function render(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('CustomerDetail - Sales Agent', () => {
  it('shows code - name, no id, next to Phone', async () => {
    getCustomer.mockResolvedValue({
      ...BASE,
      sales_agent_id: 'agent-1',
      sales_agent_code: 'SEAN I',
      sales_agent_name: 'Sean Tan',
    });
    render(<CustomerDetail customerId="cust-1" />);

    await waitFor(() => expect(screen.getByText('SEAN I - Sean Tan')).toBeInTheDocument());
    expect(screen.queryByText('agent-1')).not.toBeInTheDocument();

    // Same card as Phone (Contact Information section).
    const phoneLabel = screen.getByText('Phone');
    const agentLabel = screen.getByText('Sales Agent');
    expect(phoneLabel.closest('[data-slot="card"]')).toBe(agentLabel.closest('[data-slot="card"]'));
  });

  it('shows an explicit empty state when no agent is assigned', async () => {
    getCustomer.mockResolvedValue({ ...BASE, sales_agent_id: null, sales_agent_code: null, sales_agent_name: null });
    render(<CustomerDetail customerId="cust-1" />);

    await waitFor(() =>
      expect(screen.getByText('No sales agent assigned')).toBeInTheDocument(),
    );
  });
});
