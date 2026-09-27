/**
 * S-12 (review round 2) - a save that re-read products leaves the Products tab
 * and the Choices counts stale unless their query is fetched again.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const updateSpecKey = vi.fn();
vi.mock('../services/productSpecService', () => ({
  updateSpecKey: (...a: unknown[]) => updateSpecKey(...a),
  createSpecKey: vi.fn(),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

import { useSpecKeyRecord } from './useSpecKeyRecord';
import type { SpecRegistryKey } from '../types/productSpec.types';

const ROW: SpecRegistryKey = {
  spec_key: 'finish',
  label: 'Finish',
  data_type: 'enum',
  unit: null,
  allowed_values: ['chrome'],
  synonyms: {},
  excluded_values: [],
  user_values: [],
  suppressed_values: [],
  value_weights: {},
  derivation_rules: [],
  effective_rules: [],
  applies_when: {},
  read_from: 'rules',
  rank_weight: 1,
  measured_coverage: null,
  source: 'seed',
  user_synonyms: {},
  suppressed_synonyms: {},
  match_tolerance: 0,
  match_decay: 0,
  is_active: true,
};

let client: QueryClient;
const wrapper = ({ children }: { children: React.ReactNode }) =>
  React.createElement(QueryClientProvider, { client }, children);

const productsKeyCalls = (spy: ReturnType<typeof vi.spyOn>) =>
  spy.mock.calls.filter(([filters]) => {
    const key = (filters as { queryKey?: unknown[] } | undefined)?.queryKey;
    return Array.isArray(key) && key[0] === 'spec-key-products' && key[1] === 'finish';
  });

beforeEach(() => {
  updateSpecKey.mockReset();
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

describe('S-12 - Products and Choices counts refresh after a save that updated products', () => {
  it('invalidates the spec-key-products query when products_updated > 0', async () => {
    updateSpecKey.mockResolvedValue({ ...ROW, products_updated: 3 });
    const spy = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(() => useSpecKeyRecord(ROW), { wrapper });

    act(() => result.current.edit());
    await act(async () => {
      await result.current.save();
    });

    expect(productsKeyCalls(spy)).toHaveLength(1);
  });

  it('leaves it alone when the save updated no product', async () => {
    updateSpecKey.mockResolvedValue({ ...ROW, products_updated: 0 });
    const spy = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(() => useSpecKeyRecord(ROW), { wrapper });

    act(() => result.current.edit());
    await act(async () => {
      await result.current.save();
    });

    expect(productsKeyCalls(spy)).toHaveLength(0);
  });
});
