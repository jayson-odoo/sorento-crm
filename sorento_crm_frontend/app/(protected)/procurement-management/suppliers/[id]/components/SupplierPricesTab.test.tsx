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
  it('shows the extracted error message and not "No costs recorded"', async () => {
    getSupplierCostLists.mockRejectedValue(new Error('You do not have permission to view this supplier’s prices'));
    renderTab();

    expect(await screen.findByText('You do not have permission to view this supplier’s prices')).toBeInTheDocument();
    expect(screen.queryByText('No costs recorded for this supplier yet')).not.toBeInTheDocument();
  });
});

describe('Round 6 R5: cost, never price', () => {
  it('the empty state says cost and links to the cost list upload', async () => {
    getSupplierCostLists.mockResolvedValue({ data: [], today: '2026-09-28' });
    renderTab();

    expect(await screen.findByText('No costs recorded for this supplier yet')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Upload cost list' })).toBeInTheDocument();
    expect(screen.queryByText(/price/i)).not.toBeInTheDocument();
  });
});

describe('Round 6 R6: the cost list says which row of the upload it came from', () => {
  it('shows the set code and the row in the Source cell', async () => {
    getSupplierCostLists.mockResolvedValue({
      today: '2026-09-28',
      data: [
        {
          product_supplier_id: 'ps-1',
          product: { id: 'p-1', product_code: 'OUR-001', description: 'A product' },
          supplier_code: 'CB2500SS-DIY',
          unit_cost: 8.8,
          currency: 'CNY',
          costs: [
            {
              id: 'c-1', unit_cost: 8.8, currency: 'CNY', start_date: null, end_date: null, status: 'in_force',
              source: { change_set_id: 'set-1', code: 'CPC-0002', sheet: '25 series', row_no: 34 },
              created_at: '2026-09-28T00:00:00',
            },
          ],
        },
      ],
    });
    renderTab();

    const link = await screen.findByRole('link', { name: /CPC-0002/ });
    expect(link).toHaveTextContent('CPC-0002 row 34');
    expect(link).toHaveAttribute('title', 'CPC-0002, 25 series row 34');
  });
});
