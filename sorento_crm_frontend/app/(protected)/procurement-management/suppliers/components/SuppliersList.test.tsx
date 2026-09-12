/**
 * SuppliersList - the Country column (S2, `PLAN-local-supplier-oi-routing.md`, AC-1.11):
 * shows the country NAME, never the id.
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
  usePathname: () => '/procurement-management/suppliers',
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const useSuppliers = vi.fn();
vi.mock('../hooks/useSuppliers', () => ({
  useSuppliers: (...args: unknown[]) => useSuppliers(...args),
}));

import SuppliersList from './SuppliersList';

const SUPPLIERS = [
  {
    id: 'sup-1',
    supplier_code: 'ZZTMY1',
    supplier_name: 'Mocha Sdn Bhd',
    country_id: 'aaaaaaaa-0000-4000-8000-000000000001',
    country_code: 'MY',
    country_name: 'Malaysia',
    is_active: true,
    created_at: '',
  },
  {
    id: 'sup-2',
    supplier_code: 'ZZTCN1',
    supplier_name: 'Guangdong Factory',
    country_id: null,
    country_code: null,
    country_name: null,
    is_active: true,
    created_at: '',
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  useSuppliers.mockReturnValue({
    data: { data: SUPPLIERS, pagination: { total: SUPPLIERS.length, page: 1 }, empty: false },
    isLoading: false,
    isPlaceholderData: false,
    isFetching: false,
    isError: false,
    error: null,
  });
});

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SuppliersList />
    </QueryClientProvider>,
  );
}

describe('SuppliersList: Country column', () => {
  it('shows the country name for a supplier with one', () => {
    renderList();

    expect(screen.getByText('Malaysia')).toBeInTheDocument();
  });

  it('never renders the country id anywhere on the list', () => {
    const { container } = renderList();

    expect(container.textContent).not.toMatch(/aaaaaaaa-0000-4000-8000-000000000001/);
  });
});
