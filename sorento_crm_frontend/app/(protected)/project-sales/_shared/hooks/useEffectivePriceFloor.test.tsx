/**
 * The effective-floor read is keyed UNDER the floors key on purpose.
 *
 * Setting a floor on a CATEGORY changes what every product beneath it inherits, and the
 * product editor has no way to know that happened. Sharing the invalidation prefix is
 * what makes the two surfaces agree without either importing the other; if the key ever
 * moves out from under that prefix, a product would keep showing the floor it inherited
 * before the category was changed, and nothing else would fail.
 */
import React, { type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const getEffectivePriceFloor = vi.fn();
const upsertPriceFloor = vi.fn();

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() },
}));

vi.mock('../services/projectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/projectService')>();
  return {
    ...actual,
    getEffectivePriceFloor: (...args: unknown[]) => getEffectivePriceFloor(...args),
    upsertPriceFloor: (...args: unknown[]) => upsertPriceFloor(...args),
  };
});

import { useEffectivePriceFloor, usePriceFloorMutations } from './useProjects';

function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'QueryWrapper';
  return Wrapper;
}

beforeEach(() => {
  getEffectivePriceFloor.mockReset();
  upsertPriceFloor.mockReset();
});

describe('useEffectivePriceFloor', () => {
  it('asks nothing until there is a target to ask about', () => {
    renderHook(() => useEffectivePriceFloor(null), { wrapper: wrapper() });

    expect(getEffectivePriceFloor).not.toHaveBeenCalled();
  });

  it('passes the target through as-is', async () => {
    getEffectivePriceFloor.mockResolvedValue({ target_level: 'product' });

    renderHook(() => useEffectivePriceFloor({ level: 'product', id: 'p-1' }), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(getEffectivePriceFloor).toHaveBeenCalledTimes(1));
    expect(getEffectivePriceFloor).toHaveBeenCalledWith({ level: 'product', id: 'p-1' });
  });

  it('keeps a product and a category apart in the cache', async () => {
    getEffectivePriceFloor.mockResolvedValue({ target_level: 'product' });
    const Wrapper = wrapper();

    renderHook(() => useEffectivePriceFloor({ level: 'product', id: 'x' }), {
      wrapper: Wrapper,
    });
    renderHook(() => useEffectivePriceFloor({ level: 'category', id: 'x' }), {
      wrapper: Wrapper,
    });

    // Same id, different level: two reads, not one answer served to both.
    await waitFor(() => expect(getEffectivePriceFloor).toHaveBeenCalledTimes(2));
  });

  it('re-reads after any floor is written, so a category change reaches the product', async () => {
    getEffectivePriceFloor.mockResolvedValue({ target_level: 'product' });
    upsertPriceFloor.mockResolvedValue({ id: 'r-1' });
    const Wrapper = wrapper();

    const { result } = renderHook(
      () => ({
        floor: useEffectivePriceFloor({ level: 'product', id: 'p-1' }),
        mutations: usePriceFloorMutations(),
      }),
      { wrapper: Wrapper },
    );

    await waitFor(() => expect(getEffectivePriceFloor).toHaveBeenCalledTimes(1));

    await result.current.mutations.upsert.mutateAsync({
      mode: 'percent',
      value: '80',
      category_id: 'c-1',
    });

    await waitFor(() => expect(getEffectivePriceFloor).toHaveBeenCalledTimes(2));
  });
});
