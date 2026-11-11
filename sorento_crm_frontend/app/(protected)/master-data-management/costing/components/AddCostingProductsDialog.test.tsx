/**
 * The Costing "Add products" dialog (fix round 2, S6 and D5): it reads the party's product ids from
 * the cheap id list (not 500 costed rows), marks them "Already added", and states its own cap.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;

const products = vi.hoisted(() => ({ getProducts: vi.fn() }));
vi.mock('../../products/services/productService', () => products);
vi.mock('../../shared/hooks/use-product-category-select-query', () => ({
  useProductCategorySelectQuery: () => ({ data: [], error: null, refetch: vi.fn() }),
}));
vi.mock('../../shared/hooks/use-brand-select-query', () => ({
  useBrandSelectQuery: () => ({ data: [], error: null, refetch: vi.fn() }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const service = vi.hoisted(() => ({
  getPartyProductIds: vi.fn(),
  getCostingRows: vi.fn(),
  addPartyProducts: vi.fn(),
}));
vi.mock('../services/costingService', () => service);

import AddCostingProductsDialog from './AddCostingProductsDialog';

const row = (id: string, code: string) => ({
  id, product_code: code, product_name: `ZZT ${code}`, category_name: 'Bathtub', brand_name: 'B', is_active: true,
});

beforeEach(() => {
  vi.clearAllMocks();
  products.getProducts.mockResolvedValue({
    data: [row('p1', 'ZZT-1'), row('p2', 'ZZT-2')], pagination: { total: 2, page: 1, limit: 25 },
  });
  service.getPartyProductIds.mockResolvedValue({ data: ['p1'] });
  service.addPartyProducts.mockResolvedValue({ added: 1, already: 0 });
});

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AddCostingProductsDialog open onOpenChange={vi.fn()} customerId="cust-1" partyName="Bath Plus" />
    </QueryClientProvider>,
  );
}

describe('Add products dialog', () => {
  it('marks a product already on the party from the id list and never reads costed rows', async () => {
    mount();
    await screen.findByText('ZZT-2');
    await waitFor(() => expect(screen.getAllByText('Already added')).toHaveLength(1));
    expect(service.getPartyProductIds).toHaveBeenCalledWith('cust-1');
    expect(service.getCostingRows).not.toHaveBeenCalled();
  });

  it('states its own cap, not the copy dialogs', async () => {
    mount();
    await screen.findByText('ZZT-2');
    expect(screen.getByText('At most 500 products per add.')).toBeTruthy();
    expect(screen.queryByText(/One copy takes/)).toBeNull();
  });

  it('adds only the ticked products', async () => {
    mount();
    await screen.findByText('ZZT-2');
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select ZZT-2' }));
    fireEvent.click(await screen.findByRole('button', { name: /^Add 1$/ }));
    await waitFor(() => expect(service.addPartyProducts).toHaveBeenCalledWith('cust-1', ['p2']));
  });
});
