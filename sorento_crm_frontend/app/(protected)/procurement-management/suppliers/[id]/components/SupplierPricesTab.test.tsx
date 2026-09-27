/**
 * SupplierPricesTab (#1305 reviewer pass, Lane A FE rows, S1).
 *
 * A query failure (e.g. the caller lacks `procurement.product_suppliers.view`) must
 * render an error state, never the "No prices recorded" empty state.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => false,
}));

const getSupplierCostLists = vi.fn();
vi.mock('@/app/(protected)/procurement-management/cost-price-uploads/services/costPriceService', () => ({
  getSupplierCostLists: (...args: unknown[]) => getSupplierCostLists(...args),
}));

import { SupplierPricesTab } from './SupplierPricesTab';

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SupplierPricesTab supplierId="sup-1" />
    </QueryClientProvider>,
  );
}

describe('S1: a query error renders an error state, not the empty state', () => {
  it('shows the extracted error message and not "No prices recorded"', async () => {
    getSupplierCostLists.mockRejectedValue(new Error('You do not have permission to view this supplier’s prices'));
    renderTab();

    expect(await screen.findByText('You do not have permission to view this supplier’s prices')).toBeInTheDocument();
    expect(screen.queryByText('No prices recorded for this supplier yet')).not.toBeInTheDocument();
  });
});
