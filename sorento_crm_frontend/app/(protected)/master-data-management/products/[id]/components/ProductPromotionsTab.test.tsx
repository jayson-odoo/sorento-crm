/**
 * M5-06 - the product's Promotions tab renders on DataGrid instead of a raw
 * `<Table>`.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/master-data-management/products/p1',
}));

const LINES = [
  {
    id: 'pp-1',
    promotion_id: 'promo-1',
    product_id: 'p1',
    promotion_price: 90,
    display_order: 1,
    discount_percent: 10,
    promotion: { description: 'Raya Sale', is_active: true },
  },
  {
    id: 'pp-2',
    promotion_id: 'promo-2',
    product_id: 'p1',
    promotion_price: 80,
    display_order: 2,
    discount_percent: null,
    promotion: { description: 'Clearance', is_active: false },
  },
];

vi.mock(
  '@/app/(protected)/marketing-management/promotions/services/promotionService',
  () => ({
    getPromotionsByProductId: vi.fn(async () => LINES),
  }),
);

import ProductPromotionsTab from './ProductPromotionsTab';

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProductPromotionsTab productId="p1" listPrice={100} />
    </QueryClientProvider>,
  );
}

describe('ProductPromotionsTab - DataGrid', () => {
  it('renders the column headers and a real cell value for each promotion line', async () => {
    renderTab();

    expect(await screen.findByText('Promotion Code')).toBeInTheDocument();
    expect(screen.getByText('Description')).toBeInTheDocument();
    expect(screen.getByText('Selling Price')).toBeInTheDocument();

    expect(screen.getAllByText('Raya Sale').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Clearance').length).toBeGreaterThan(0);
    expect(screen.getByText('Inactive')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /View/i })).toHaveLength(2);
  });
});
