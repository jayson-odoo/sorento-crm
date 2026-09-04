/**
 * M5-06 - the product's Stock Information tab renders on DataGrid instead of
 * a raw `<Table>`.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/master-data-management/products/p1',
}));

const STOCK_ITEMS = [
  {
    id: 's-1',
    product_id: 'p1',
    warehouse_id: 'w-1',
    warehouse: { warehouse_name: 'Klang Valley DC' },
    quantity_available: 40,
    quantity_reserved: 5,
    quantity_on_hand: 45,
    product: { reorder_level: 20 },
  },
  {
    id: 's-2',
    product_id: 'p1',
    warehouse_id: 'w-2',
    warehouse: { warehouse_name: 'Penang DC' },
    quantity_available: 0,
    quantity_reserved: 0,
    quantity_on_hand: 0,
    product: { reorder_level: 20 },
  },
];

vi.mock('@/app/(protected)/inventory-management/stock/hooks/useStock', () => ({
  useStockBalance: () => ({
    data: { data: STOCK_ITEMS, pagination: { total: 2 } },
    isLoading: false,
  }),
}));

import ProductStockTab from './ProductStockTab';

describe('ProductStockTab - DataGrid', () => {
  it('renders the column headers and a real cell value for each warehouse', () => {
    render(<ProductStockTab productId="p1" />);

    expect(screen.getByText('Warehouse')).toBeInTheDocument();
    expect(screen.getByText('Available')).toBeInTheDocument();
    expect(screen.getByText('Status')).toBeInTheDocument();

    expect(screen.getByText('Klang Valley DC')).toBeInTheDocument();
    expect(screen.getByText('Penang DC')).toBeInTheDocument();
    expect(screen.getByText('Normal')).toBeInTheDocument();
    expect(screen.getByText('Critical')).toBeInTheDocument();
  });
});
