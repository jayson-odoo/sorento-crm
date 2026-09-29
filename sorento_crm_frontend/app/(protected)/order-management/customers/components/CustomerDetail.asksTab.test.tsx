/**
 * Chatbot stock ask v2 S5, AC-SA508: CustomerDetail carries line tabs "Details" (the two
 * existing cards, unchanged) and "Asks".
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render as rtlRender, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
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
vi.mock('./CustomerAsksTab', () => ({
  CustomerAsksTab: ({ customerId }: { customerId: string }) => <div>asks of {customerId}</div>,
}));

import CustomerDetail from './CustomerDetail';

function render(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('CustomerDetail - tabs', () => {
  it('opens on Details with the two cards, and Asks shows the asks tab', async () => {
    render(<CustomerDetail customerId="cust-1" />);
    await waitFor(() => expect(screen.getByRole('tab', { name: /Details/ })).toBeInTheDocument());
    expect(screen.getByText('Contact Information')).toBeInTheDocument();
    expect(screen.getByText('Additional Information')).toBeInTheDocument();
    const asks = screen.getByRole('tab', { name: /Asks/ });
    fireEvent.mouseDown(asks);
    fireEvent.click(asks);
    await waitFor(() => expect(screen.getByText('asks of cust-1')).toBeInTheDocument());
  });
});
