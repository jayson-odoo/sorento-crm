/** #1356: the Customer detail Branches tab lists that customer's branches, read only. */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => '/order-management/customers/cust-1',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const getBranches = vi.fn();
vi.mock('../../branches/services/branchService', () => ({
  getBranches: (...args: unknown[]) => getBranches(...args),
  getBranchBooks: () => Promise.resolve([]),
}));

import { CustomerBranchesTab } from './CustomerBranchesTab';

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <CustomerBranchesTab customerId="cust-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => getBranches.mockReset());

describe('CustomerBranchesTab', () => {
  it("asks for this customer's branches and lists them", async () => {
    getBranches.mockResolvedValue({
      data: [
        {
          id: 'b1', source_book: 'SRT', acc_no: 'C-001', branch_code: 'KL01',
          branch_name: 'Kepong Showroom', last_synced_at: '2026-09-29T06:00:00',
          customer_id: 'cust-1', customer_name: 'Alpha Trading',
        },
      ],
      pagination: { page: 1, limit: 20, total: 1 },
    });
    renderTab();
    await waitFor(() => expect(screen.getByText('Kepong Showroom')).toBeInTheDocument());
    expect(screen.getByText('KL01')).toBeInTheDocument();
    expect(screen.getByText('SRT')).toBeInTheDocument();
    expect(getBranches.mock.calls[0][0].customerId).toBe('cust-1');
    expect(screen.queryByRole('button', { name: /add|edit|delete/i })).toBeNull();
  });

  it('shows the empty state for a customer with no branches', async () => {
    getBranches.mockResolvedValue({ data: [], pagination: { page: 1, limit: 20, total: 0 } });
    renderTab();
    await waitFor(() => expect(screen.getByText('No branches')).toBeInTheDocument());
  });
});
