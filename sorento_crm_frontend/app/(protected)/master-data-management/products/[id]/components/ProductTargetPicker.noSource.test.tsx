/**
 * useProductTargetPicker without a source product (lane PRODUCT-COSTING, Phase 2 red tests F4;
 * AC-CG-12): the Costing page's "Add products" dialog reuses the shared picker, there is no product
 * being copied from, and products already on the party are marked and never re-sent.
 *
 * ASSUMED API (read ProductTargetPicker.tsx: it has no existing equivalent, so one is added):
 *   useProductTargetPicker(sourceProductId?: string, options?: { alreadyAddedIds?: string[] })
 *  - `sourceProductId` becomes optional (CONTRACT section 5). Omitted = nothing is excluded as "the source".
 *  - `alreadyAddedIds`: those rows get a disabled tick box (like the source row) with an explanatory
 *    reason, can never end up in `picked`, and are skipped by "Select all N records".
 * The existing one-argument behaviour (CopyAccessoriesDialog / CopyComboDialog) must not change.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const products = vi.hoisted(() => ({ getProducts: vi.fn() }));
vi.mock('../../services/productService', () => products);
vi.mock('../../../shared/hooks/use-product-category-select-query', () => ({
  useProductCategorySelectQuery: () => ({ data: [{ id: 'c1', category_name: 'Bathtub' }], error: null, refetch: vi.fn() }),
}));
vi.mock('../../../shared/hooks/use-brand-select-query', () => ({
  useBrandSelectQuery: () => ({ data: [{ id: 'b1', brand_name: 'ZZT Brand' }], error: null, refetch: vi.fn() }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { useProductTargetPicker } from './ProductTargetPicker';

type PickerArgs = [sourceProductId?: string, options?: { alreadyAddedIds?: string[] }];
// The second argument does not exist yet; the cast keeps this file compiling until the coder adds it.
const usePicker = useProductTargetPicker as unknown as (...args: PickerArgs) => ReturnType<typeof useProductTargetPicker>;

const row = (id: string, code: string) => ({
  id, product_code: code, product_name: `ZZT ${code}`, category_name: 'Bathtub', brand_name: 'ZZT Brand', is_active: true,
});
const PAGE = [row('p1', 'ZZT-TUB-1'), row('p2', 'ZZT-TUB-2'), row('p3', 'ZZT-TUB-3')];

function Harness({ source, added }: { source?: string; added?: string[] }) {
  const picker = usePicker(source, added ? { alreadyAddedIds: added } : undefined);
  return (
    <div>
      {picker.grid}
      <output data-testid="picked">{[...picker.picked].sort().join(',')}</output>
    </div>
  );
}
function mount(props: { source?: string; added?: string[] }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Harness {...props} />
    </QueryClientProvider>,
  );
}
const isDisabled = (el: HTMLElement) => el.hasAttribute('disabled') || el.getAttribute('data-disabled') !== null;

beforeEach(() => {
  vi.clearAllMocks();
  products.getProducts.mockResolvedValue({ data: PAGE, pagination: { total: 3, page: 1, limit: 25 } });
});

describe('without a source product', () => {
  it('lists active products and lets every row be ticked', async () => {
    mount({});
    await screen.findByText('ZZT-TUB-1');
    expect(products.getProducts).toHaveBeenCalledWith(expect.objectContaining({ status: 'active' }));
    for (const code of ['ZZT-TUB-1', 'ZZT-TUB-2', 'ZZT-TUB-3']) {
      expect(isDisabled(screen.getByRole('checkbox', { name: `Select ${code}` }))).toBe(false);
    }
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select ZZT-TUB-1' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select ZZT-TUB-3' }));
    expect(screen.getByTestId('picked').textContent).toBe('p1,p3');
  });
});

describe('alreadyAddedIds', () => {
  it('disables the tick box of a product already on the party and keeps the rest tickable', async () => {
    mount({ added: ['p1'] });
    await screen.findByText('ZZT-TUB-1');
    expect(isDisabled(screen.getByRole('checkbox', { name: 'Select ZZT-TUB-1' }))).toBe(true);
    expect(isDisabled(screen.getByRole('checkbox', { name: 'Select ZZT-TUB-2' }))).toBe(false);
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select ZZT-TUB-2' }));
    expect(screen.getByTestId('picked').textContent).toBe('p2');
  });

  it('the page tick-all never picks an already added product', async () => {
    mount({ added: ['p1'] });
    await screen.findByText('ZZT-TUB-1');
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select all rows on this page' }));
    expect(screen.getByTestId('picked').textContent).toBe('p2,p3');
  });

  it('"Select all N records" skips the already added products', async () => {
    products.getProducts.mockImplementation(async (params: { pageSize: number }) =>
      params.pageSize > 25
        ? { data: [...PAGE, row('p4', 'ZZT-TUB-4')], pagination: { total: 4, page: 1, limit: params.pageSize } }
        : { data: PAGE, pagination: { total: 4, page: 1, limit: 25 } },
    );
    mount({ added: ['p1'] });
    await screen.findByText('ZZT-TUB-1');
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select all rows on this page' }));
    fireEvent.click(await screen.findByRole('button', { name: /select all 4 records/i }));
    await vi.waitFor(() => expect(screen.getByTestId('picked').textContent).toBe('p2,p3,p4'));
  });

  it('an alreadyAddedIds list does not disturb a copy picker that still has a source', async () => {
    mount({ source: 'p2', added: ['p1'] });
    await screen.findByText('ZZT-TUB-1');
    expect(isDisabled(screen.getByRole('checkbox', { name: 'Select ZZT-TUB-1' }))).toBe(true);
    expect(isDisabled(screen.getByRole('checkbox', { name: 'Select ZZT-TUB-2' }))).toBe(true);
    expect(isDisabled(screen.getByRole('checkbox', { name: 'Select ZZT-TUB-3' }))).toBe(false);
  });
});
