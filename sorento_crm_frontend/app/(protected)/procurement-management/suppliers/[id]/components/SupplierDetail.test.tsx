/**
 * SupplierDetail - the Country field on the header/detail page (S2, `PLAN-local-supplier-oi-
 * routing.md`, AC-1.11): shows the country NAME, never the id.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { roleName: 'viewer' } }, status: 'authenticated' }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/procurement-management/suppliers/sup-1',
}));

const useSupplier = vi.fn();
vi.mock('../../hooks/useSuppliers', () => ({
  useSupplier: (...args: unknown[]) => useSupplier(...args),
  suppliersPagerQuery: {
    listQueryKey: () => ['suppliers-pager'],
    fetchPage: async () => ({ ids: ['sup-1'], hasNextPage: false }),
  },
}));

vi.mock('../../actions', () => ({
  useSupplierActions: () => ({ actions: [], dialogs: null }),
}));

import SupplierDetail from './SupplierDetail';

const SUPPLIER = {
  id: 'sup-1',
  supplier_code: 'ZZTMY1',
  supplier_name: 'Mocha Sdn Bhd',
  country_id: 'aaaaaaaa-0000-4000-8000-000000000001',
  country_code: 'MY',
  country_name: 'Malaysia',
  address_line1: '1 Jalan Test',
  is_active: true,
  payment_terms_days: 30,
  created_at: '2026-01-01T00:00:00Z',
};

beforeEach(() => {
  vi.clearAllMocks();
  useSupplier.mockReturnValue({ data: SUPPLIER, isLoading: false });
});

function renderDetail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SupplierDetail supplierId="sup-1" />
    </QueryClientProvider>,
  );
}

describe('SupplierDetail: Country', () => {
  it('shows the country name', () => {
    renderDetail();

    expect(screen.getByText(/Malaysia/)).toBeInTheDocument();
  });

  it('never renders the country id', () => {
    const { container } = renderDetail();

    expect(container.textContent).not.toMatch(/aaaaaaaa-0000-4000-8000-000000000001/);
  });
});
