/**
 * The line-save warning speaks the same words as the pill under the price (owner meeting,
 * 29 Oct): "minimum price", with the amount in ringgit, never "floor".
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from '@/lib/toast';

const createQuotationLine = vi.fn();
const updateQuotationLine = vi.fn();

vi.mock('../services/projectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/projectService')>();
  return {
    ...actual,
    createQuotationLine: (...args: unknown[]) => createQuotationLine(...args),
    updateQuotationLine: (...args: unknown[]) => updateQuotationLine(...args),
  };
});

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

import { useQuotationLineMutations } from './useProjects';

function Harness({ onReady }: { onReady: (api: ReturnType<typeof useQuotationLineMutations>) => void }) {
  const api = useQuotationLineMutations('p1', 'v1');
  React.useEffect(() => {
    onReady(api);
  }, [api, onReady]);
  return null;
}

function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  let api: ReturnType<typeof useQuotationLineMutations> | null = null;
  render(
    <QueryClientProvider client={client}>
      <Harness onReady={(value) => (api = value)} />
    </QueryClientProvider>,
  );
  return () => api!;
}

const BELOW = { id: 'l1', is_below_floor: true, floor_value_applied: '700.00' };

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useQuotationLineMutations warning wording', () => {
  it('warns about the minimum price when a new line saves below it', async () => {
    createQuotationLine.mockResolvedValue(BELOW);
    const api = mount();

    await act(async () => {
      await api().create.mutateAsync({ description_snapshot: 'Wall-hung WC' } as never);
    });

    expect(toast.warning).toHaveBeenCalledWith(
      'Below the minimum price of RM 700.00. Management has been notified.',
    );
  });

  it('warns about the minimum price when an edited line saves below it', async () => {
    updateQuotationLine.mockResolvedValue(BELOW);
    const api = mount();

    await act(async () => {
      await api().update.mutateAsync({ id: 'l1', body: { unit_price: '400.00' } });
    });

    expect(toast.warning).toHaveBeenCalledWith('Below the minimum price of RM 700.00.');
  });
});
