/**
 * The same floor dialog, opened from somewhere that already knows the target.
 *
 * The point of the locked mode is that it removes a decision rather than adding a
 * screen: the person editing BASIN-001 has already said which product they mean, so the
 * level radios and the product picker are replaced by its name. The rest of the dialog
 * (percent versus fixed, the over-100% refusal, the copy about issuing) is deliberately
 * the same component, so it cannot drift between the two places a floor gets set.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const upsertPriceFloor = vi.fn();

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() },
}));

vi.mock('../services/projectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/projectService')>();
  return {
    ...actual,
    upsertPriceFloor: (...args: unknown[]) => upsertPriceFloor(...args),
  };
});

vi.mock(
  '@/app/(protected)/master-data-management/shared/hooks/use-product-category-select-query',
  () => ({ useProductCategorySelectQuery: () => ({ data: [] }) }),
);

vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProductsForVariantSelect: vi.fn(async () => []),
}));

import { PriceFloorDialog } from './PriceFloorDialog';

function renderDialog(node: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

beforeEach(() => {
  upsertPriceFloor.mockReset();
  upsertPriceFloor.mockResolvedValue({ id: 'r-1' });
});

describe('PriceFloorDialog with a locked target', () => {
  it('names the target instead of asking which one, and drops the level choice', () => {
    renderDialog(
      <PriceFloorDialog
        rule={null}
        lockedTarget={{ level: 'product', id: 'p-1', label: 'BASIN-001' }}
        onDone={() => {}}
      />,
    );

    expect(screen.getByText('Set the floor for BASIN-001')).toBeTruthy();
    expect(screen.getByText('BASIN-001')).toBeTruthy();
    // The three-way level choice belongs to the pricing policy screen only.
    expect(screen.queryByText('Company default')).toBeNull();
    expect(screen.queryByLabelText(/Product \*/)).toBeNull();
  });

  it('writes the floor against the target the caller pinned', async () => {
    renderDialog(
      <PriceFloorDialog
        rule={null}
        lockedTarget={{ level: 'product', id: 'p-1', label: 'BASIN-001' }}
        onDone={() => {}}
      />,
    );

    fireEvent.change(screen.getByLabelText(/Minimum percent of list/), {
      target: { value: '80' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add floor' }));

    await waitFor(() => expect(upsertPriceFloor).toHaveBeenCalledTimes(1));
    expect(upsertPriceFloor).toHaveBeenCalledWith(
      expect.objectContaining({ mode: 'percent', value: '80', product_id: 'p-1', category_id: null }),
    );
  });

  it('writes a category floor against the category, never the product key', async () => {
    renderDialog(
      <PriceFloorDialog
        rule={null}
        lockedTarget={{ level: 'category', id: 'c-1', label: 'Basins' }}
        onDone={() => {}}
      />,
    );

    fireEvent.change(screen.getByLabelText(/Minimum percent of list/), {
      target: { value: '75' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add floor' }));

    await waitFor(() => expect(upsertPriceFloor).toHaveBeenCalledTimes(1));
    expect(upsertPriceFloor).toHaveBeenCalledWith(
      expect.objectContaining({ product_id: null, category_id: 'c-1' }),
    );
  });

  it('still refuses a percentage above list, wherever it was opened from', async () => {
    renderDialog(
      <PriceFloorDialog
        rule={null}
        lockedTarget={{ level: 'product', id: 'p-1', label: 'BASIN-001' }}
        onDone={() => {}}
      />,
    );

    fireEvent.change(screen.getByLabelText(/Minimum percent of list/), {
      target: { value: '950' },
    });

    expect(
      screen.getByText('A floor above 100% of list would flag every sale at list price.'),
    ).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Add floor' }).getAttribute('disabled')).not.toBeNull();
  });

  it('prefills the existing rule when the target already has one', () => {
    renderDialog(
      <PriceFloorDialog
        rule={{
          id: 'r-own',
          product_id: 'p-1',
          product_code: 'BASIN-001',
          mode: 'absolute',
          value: '950.00',
          is_active: true,
          level: 'product',
        }}
        lockedTarget={{ level: 'product', id: 'p-1', label: 'BASIN-001' }}
        onDone={() => {}}
      />,
    );

    expect(screen.getByText('Change the floor for BASIN-001')).toBeTruthy();
    expect(
      (screen.getByLabelText(/Minimum price/) as HTMLInputElement).value,
    ).toBe('950.00');
  });
});
