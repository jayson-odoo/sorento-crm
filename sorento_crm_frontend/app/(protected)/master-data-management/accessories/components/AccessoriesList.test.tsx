import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const rows = vi.hoisted(() => [
  {
    id: 'a1',
    name: 'Tap',
    spec: 'Chrome finish',
    image: null,
    product_count: 3,
    combo_count: 1,
  },
  { id: 'a2', name: 'Waste', spec: null, image: null, product_count: 0, combo_count: 2 },
]);
vi.mock('../hooks/useAccessories', () => ({
  useAccessories: () => ({
    data: { data: rows, pagination: { total: 2, page: 1 } },
    isLoading: false,
    isPlaceholderData: false,
    error: null,
    refetch: vi.fn(),
  }),
}));
const deletionRun = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run: deletionRun, targetId: null, isPending: false, countdown: null }),
  useRowPending: () => () => false,
}));
vi.mock('./AccessoryFormDialog', () => ({ default: () => null }));

import AccessoriesList from './AccessoriesList';

describe('AccessoriesList', () => {
  it('renders a row per accessory with its Used on text and the Add button', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <AccessoriesList />
      </QueryClientProvider>,
    );
    expect(screen.getByText('Tap')).toBeInTheDocument();
    expect(screen.getByText('Chrome finish')).toBeInTheDocument();
    expect(screen.getByText('3 products, 1 combo')).toBeInTheDocument();
    expect(screen.getByText('0 products, 2 combos')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Add accessory/ })).toBeInTheDocument();
  });

  it('Delete parks a deferred action on the row instead of deleting at once', async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <AccessoriesList />
      </QueryClientProvider>,
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /accessory Tap actions/i }));
    await user.click(await screen.findByText('Delete accessory'));
    expect(deletionRun).toHaveBeenCalledWith({ id: 'a1', subject: 'Tap' });
  });
});
