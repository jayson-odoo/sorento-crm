/**
 * SupplierDetail (#1305 reviewer pass, Lane A FE rows, S1): a role holding
 * `procurement.suppliers.view` but not `procurement.product_suppliers.view` must not see
 * the Prices tab - today it always renders and the tab's own query 403s, which the tab
 * then degrades to "No prices recorded for this supplier yet".
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

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

const grantedPerms = vi.hoisted(() => ({ granted: new Set<string>() }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => grantedPerms.granted.has(slug),
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

function renderDetail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SupplierDetail supplierId="sup-1" />
    </QueryClientProvider>,
  );
}

describe('S1: the Costs tab (Prices before round 6 R5) is gated on procurement.product_suppliers.view', () => {
  it('renders no Costs tab for a caller without the permission', () => {
    grantedPerms.granted.clear();
    useSupplier.mockReturnValue({ data: SUPPLIER, isLoading: false });
    renderDetail();

    expect(screen.queryByRole('tab', { name: 'Costs' })).not.toBeInTheDocument();
  });

  it('renders the Costs tab for a caller with the permission', () => {
    grantedPerms.granted = new Set(['procurement.product_suppliers.view']);
    useSupplier.mockReturnValue({ data: SUPPLIER, isLoading: false });
    renderDetail();

    expect(screen.getByRole('tab', { name: 'Costs' })).toBeInTheDocument();
  });
});
