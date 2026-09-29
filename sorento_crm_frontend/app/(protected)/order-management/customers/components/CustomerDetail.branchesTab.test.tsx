/**
 * #1356: the Customer detail page carries a read-only Branches tab between Details and Asks,
 * shown only with `order_management.branches.view`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render as rtlRender, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

let granted = true;

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/order-management/customers/cust-1',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => slug === 'order_management.branches.view' && granted,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));
vi.mock('../services/customerService', () => ({
  getCustomer: vi.fn().mockResolvedValue({
    id: 'cust-1',
    customer_code: 'C-001',
    customer_name: 'Alpha Trading',
    email: null,
    phone_number: '03-1111111',
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
  }),
  getCustomers: vi.fn(),
}));
vi.mock('./CustomerBranchesTab', () => ({
  CustomerBranchesTab: ({ customerId }: { customerId: string }) => <div>branches of {customerId}</div>,
}));
vi.mock('./CustomerAsksTab', () => ({
  CustomerAsksTab: () => <div>asks</div>,
}));

import CustomerDetail from './CustomerDetail';

function render(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  granted = true;
});

describe('CustomerDetail - Branches tab', () => {
  it('sits between Details and Asks and opens this customer\'s branches', async () => {
    render(<CustomerDetail customerId="cust-1" />);
    await waitFor(() => expect(screen.getByRole('tab', { name: /Branches/ })).toBeInTheDocument());
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(['Details', 'Branches', 'Asks']);
    const tab = screen.getByRole('tab', { name: /Branches/ });
    fireEvent.mouseDown(tab);
    fireEvent.click(tab);
    await waitFor(() => expect(screen.getByText('branches of cust-1')).toBeInTheDocument());
  });

  it('is hidden without order_management.branches.view', async () => {
    granted = false;
    render(<CustomerDetail customerId="cust-1" />);
    await waitFor(() => expect(screen.getByRole('tab', { name: /Details/ })).toBeInTheDocument());
    expect(screen.queryByRole('tab', { name: /Branches/ })).toBeNull();
  });
});
