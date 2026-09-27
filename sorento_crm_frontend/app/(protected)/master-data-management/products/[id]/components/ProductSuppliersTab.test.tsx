/**
 * ProductSuppliersTab (#1305 reviewer pass, Lane A FE rows).
 *
 * S1: a query failure (e.g. the caller lacks `procurement.product_suppliers.view`) must
 * render an error state, never the "No suppliers configured" empty state - the two are
 * different facts and today the component conflates them (`productSuppliers || []`
 * degrades a 403 to an empty list).
 *
 * S4 / AC-CL-08: search must also match a cost row's `source.code` (the cost-price-change
 * set code, e.g. "CPC-0004"), not only the supplier name/code/item code.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

const getProductSuppliersByProductId = vi.fn();
vi.mock('../../../../procurement-management/product-suppliers/services/productSupplierService', () => ({
  getProductSuppliersByProductId: (...args: unknown[]) => getProductSuppliersByProductId(...args),
}));

vi.mock('./ProductSuppliedWithSection', () => ({
  ProductSuppliedWithSection: () => <div data-testid="supplied-with-stub" />,
}));
vi.mock('./ProductShipsWithSection', () => ({
  ProductShipsWithSection: () => <div data-testid="ships-with-stub" />,
}));

import ProductSuppliersTab from './ProductSuppliersTab';

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProductSuppliersTab productId="prod-1" />
    </QueryClientProvider>,
  );
}

describe('S1: a query error renders an error state, not the empty state', () => {
  it('shows the extracted error message and not "No suppliers configured"', async () => {
    getProductSuppliersByProductId.mockRejectedValue(new Error('You do not have permission to view suppliers'));
    renderTab();

    expect(await screen.findByText('You do not have permission to view suppliers')).toBeInTheDocument();
    expect(screen.queryByText('No suppliers configured for this product.')).not.toBeInTheDocument();
  });
});

describe('S4 / AC-CL-08: search also matches a cost row source code', () => {
  it('finds the link whose cost row source.code matches "CPC-0004"', async () => {
    getProductSuppliersByProductId.mockResolvedValue([
      {
        id: 'ps-1',
        product_id: 'prod-1',
        supplier_id: 'sup-1',
        standard_lead_time_days: 7,
        supplier: { id: 'sup-1', supplier_code: 'ZZT-S1', supplier_name: 'Alpha Supplier' },
        costs: [{ id: 'c-1', unit_cost: 10, currency: 'CNY', start_date: null, end_date: null, status: 'in_force', source: { change_set_id: 'set-1', code: 'CPC-0004' }, created_at: '2026-01-01' }],
      },
      {
        id: 'ps-2',
        product_id: 'prod-1',
        supplier_id: 'sup-2',
        standard_lead_time_days: 7,
        supplier: { id: 'sup-2', supplier_code: 'ZZT-S2', supplier_name: 'Beta Supplier' },
        costs: [],
      },
    ]);
    renderTab();
    await screen.findByText('Alpha Supplier');

    fireEvent.change(screen.getByPlaceholderText('Search supplier or upload code'), {
      target: { value: 'CPC-0004' },
    });

    expect(screen.getByText('Alpha Supplier')).toBeInTheDocument();
    expect(screen.queryByText('Beta Supplier')).not.toBeInTheDocument();
  });
});
