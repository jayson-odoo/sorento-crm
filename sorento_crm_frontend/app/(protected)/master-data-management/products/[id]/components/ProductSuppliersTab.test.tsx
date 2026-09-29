/**
 * ProductSuppliersTab (#1305 reviewer pass, Lane A FE rows; round 9 grids).
 *
 * S1: a query failure (e.g. the caller lacks `procurement.product_suppliers.view`) must
 * render an error state, never the "No suppliers configured" empty state - the two are
 * different facts.
 *
 * Round 9 (owner hand test of round 8, 28 Sep 2026): the tab is a list of suppliers in the
 * system grid, a row click opens that supplier's cost prices as a second grid, the cost reads
 * "CNY 40.60", an open-ended price has an empty end date, and no upload code (CPC-nnnn) or
 * "Always" wording shows anywhere on the tab. AC-CL-11 to AC-CL-15.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), prefetch: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/master-data-management/products/prod-1',
  useSearchParams: () => new URLSearchParams(),
}));

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
import { formatPlainDate } from '../../../../procurement-management/cost-price-uploads/lib/formatPlainDate';

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProductSuppliersTab productId="prod-1" />
    </QueryClientProvider>,
  );
}

const LINKS = [
  {
    id: 'ps-1',
    product_id: 'prod-1',
    supplier_id: 'sup-1',
    is_primary_supplier: true,
    standard_lead_time_days: 30,
    unit_cost: 40.6,
    currency: 'CNY',
    moq: 100,
    order_multiple: 10,
    supplier_item_code: 'CB2548',
    supplier: { id: 'sup-1', supplier_code: '400-0002', supplier_name: 'Taiyang Hardware' },
    costs: [
      {
        id: 'c-1',
        packaging_method: '吊卡',
        unit_cost: 40.6,
        currency: 'CNY',
        start_date: '2026-09-01',
        end_date: null,
        status: 'in_force',
        source: { change_set_id: 'set-1', code: 'CPC-0004' },
        created_at: '2026-09-01',
      },
      {
        id: 'c-2',
        packaging_method: '彩盒',
        unit_cost: 42,
        currency: 'CNY',
        start_date: '2026-09-01',
        end_date: '2026-12-31',
        status: 'always',
        source: { change_set_id: 'set-1', code: 'CPC-0004' },
        created_at: '2026-09-01',
      },
    ],
  },
  {
    id: 'ps-2',
    product_id: 'prod-1',
    supplier_id: 'sup-2',
    is_primary_supplier: false,
    standard_lead_time_days: null,
    unit_cost: null,
    currency: null,
    supplier: { id: 'sup-2', supplier_code: '400-0009', supplier_name: 'Beta Supplier' },
    costs: [],
  },
];

const headerTexts = (root: HTMLElement) =>
  within(root)
    .getAllByRole('columnheader')
    .map((th) => th.textContent?.trim())
    .filter(Boolean);

describe('S1: a query error renders an error state, not the empty state', () => {
  it('shows the extracted error message and not "No suppliers configured"', async () => {
    getProductSuppliersByProductId.mockRejectedValue(new Error('You do not have permission to view suppliers'));
    renderTab();

    expect(await screen.findByText('You do not have permission to view suppliers')).toBeInTheDocument();
    expect(screen.queryByText('No suppliers configured for this product.')).not.toBeInTheDocument();
  });
});

describe('Round 9: suppliers and cost prices as data grids', () => {
  beforeEach(() => {
    getProductSuppliersByProductId.mockResolvedValue(LINKS);
  });

  it('AC-CL-11: lists suppliers in the system grid with the buyer columns', async () => {
    renderTab();
    await screen.findByText('Taiyang Hardware');

    const grid = screen.getByTestId('product-suppliers-grid');
    expect(grid.querySelector('[data-slot="data-grid-scroller"]')).not.toBeNull();
    expect(headerTexts(grid)).toEqual([
      'Supplier code',
      'Supplier name',
      'Primary',
      'Lead time (days)',
      'Unit cost',
      'Currency',
      'Minimum order',
      'Order multiple',
      'Their code',
    ]);
    const row = screen.getByText('Taiyang Hardware').closest('tr') as HTMLElement;
    expect(within(row).getByText('400-0002')).toBeInTheDocument();
    expect(within(row).getByText('Yes')).toBeInTheDocument();
    expect(within(row).getByText('40.60')).toBeInTheDocument();
    expect(within(row).getByText('CB2548')).toBeInTheDocument();
  });

  it('AC-CL-11: the search box filters the supplier rows', async () => {
    renderTab();
    await screen.findByText('Taiyang Hardware');

    fireEvent.change(screen.getByPlaceholderText('Search supplier'), { target: { value: 'beta' } });

    expect(screen.getByText('Beta Supplier')).toBeInTheDocument();
    expect(screen.queryByText('Taiyang Hardware')).not.toBeInTheDocument();
  });

  it('AC-CL-12: clicking a supplier row opens its cost prices as a second grid', async () => {
    renderTab();
    await screen.findByText('Taiyang Hardware');
    expect(screen.queryByTestId('supplier-cost-prices-grid')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('Taiyang Hardware'));

    const costs = await screen.findByTestId('supplier-cost-prices-grid');
    expect(headerTexts(costs)).toEqual(['Packaging method', 'Cost', 'Date start', 'Date end']);
    expect(within(costs).getByText('吊卡')).toBeInTheDocument();
    expect(within(costs).getByText('彩盒')).toBeInTheDocument();

    // A second click closes it again.
    fireEvent.click(screen.getByText('Taiyang Hardware'));
    expect(screen.queryByTestId('supplier-cost-prices-grid')).not.toBeInTheDocument();
  });

  it('AC-CL-13: the cost reads currency first with two decimals', async () => {
    renderTab();
    fireEvent.click(await screen.findByText('Taiyang Hardware'));
    const costs = await screen.findByTestId('supplier-cost-prices-grid');

    expect(within(costs).getByText('CNY 40.60')).toBeInTheDocument();
    expect(within(costs).getByText('CNY 42.00')).toBeInTheDocument();
    expect(within(costs).queryByText(/40\.60 CNY/)).not.toBeInTheDocument();
  });

  it('AC-CL-14: an open-ended price shows its start and a dash for the end, never "Always"', async () => {
    renderTab();
    fireEvent.click(await screen.findByText('Taiyang Hardware'));
    const costs = await screen.findByTestId('supplier-cost-prices-grid');

    const openRow = within(costs).getByText('吊卡').closest('tr') as HTMLElement;
    const cells = within(openRow).getAllByRole('cell').map((td) => td.textContent?.trim());
    // The month spelling is the runtime's ICU ("Sep" or "Sept"), so read it off the formatter.
    expect(cells).toEqual(['吊卡', 'CNY 40.60', formatPlainDate('2026-09-01'), '-']);

    const closedRow = within(costs).getByText('彩盒').closest('tr') as HTMLElement;
    expect(within(closedRow).getByText(formatPlainDate('2026-12-31') as string)).toBeInTheDocument();

    expect(screen.queryByText(/always/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/no end/i)).not.toBeInTheDocument();
  });

  it('AC-CL-15: no upload code (CPC-nnnn) anywhere on the tab', async () => {
    const { container } = renderTab();
    fireEvent.click(await screen.findByText('Taiyang Hardware'));
    await screen.findByTestId('supplier-cost-prices-grid');

    expect(container.textContent).not.toMatch(/CPC-\d+/);
    expect(screen.queryByText('Edited by hand')).not.toBeInTheDocument();
  });

  it('AC-CL-12: a supplier with no cost prices shows the grid empty state in one line', async () => {
    renderTab();
    fireEvent.click(await screen.findByText('Beta Supplier'));

    expect(await screen.findByText('No cost prices for this supplier.')).toBeInTheDocument();
  });
});
