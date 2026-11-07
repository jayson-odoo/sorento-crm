/**
 * Spec-value feature icons, review fix round: a saved spec refreshes the price tag designer's
 * feature icon list (it caches it in the kit library client), and an Icon order outside 1..999
 * or not a whole number is caught before anything is sent.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const updateSpecKey = vi.fn();
vi.mock('../services/productSpecService', () => ({
  updateSpecKey: (...a: unknown[]) => updateSpecKey(...a),
  createSpecKey: vi.fn(),
  rereadCatalogue: vi.fn(),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

import { kitLibraryClient } from '@/lib/dealer-kit/kit-library-cache';
import { FEATURE_ICONS_KEY } from '@/app/(protected)/dealer-kit/tag-templates/components/useTagBindings';
import { useSpecKeyRecord } from './useSpecKeyRecord';
import type { SpecRegistryKey } from '../types/productSpec.types';

function waterSupply(): SpecRegistryKey {
  return {
    id: 'k1',
    spec_key: 'water_supply',
    label: 'Water supply',
    data_type: 'enum',
    unit: null,
    allowed_values: ['mixer'],
    synonyms: { mixer: ['mixer'] },
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
    parser_hint: null,
    label_owned: false,
    icon_order: 2,
    value_icons: {},
  } as SpecRegistryKey;
}

let client: QueryClient;
function wrapper({ children }: { children: React.ReactNode }) {
  return React.createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  updateSpecKey.mockReset();
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

describe('useSpecKeyRecord feature icons', () => {
  it("a save refreshes the designer's feature icon list", async () => {
    const row = waterSupply();
    updateSpecKey.mockResolvedValue({ ...row, products_updated: 0 });
    const spy = vi.spyOn(kitLibraryClient, 'invalidateQueries');
    const { result } = renderHook(() => useSpecKeyRecord(row), { wrapper });
    act(() => result.current.edit());
    act(() => result.current.setDraft((d) => ({ ...d, iconOrder: '1' })));
    await act(async () => {
      expect(await result.current.save()).toBe(true);
    });
    expect(spy).toHaveBeenCalledWith({ queryKey: FEATURE_ICONS_KEY });
    spy.mockRestore();
  });

  it.each(['0', '1000', '1.5'])('refuses Icon order %s before sending anything', async (bad) => {
    const row = waterSupply();
    const { result } = renderHook(() => useSpecKeyRecord(row), { wrapper });
    act(() => result.current.edit());
    act(() => result.current.setDraft((d) => ({ ...d, iconOrder: bad })));
    await act(async () => {
      expect(await result.current.save()).toBe(false);
    });
    expect(updateSpecKey).not.toHaveBeenCalled();
    expect(result.current.draft?.iconOrderError).toMatch(/whole number between 1 and 999/);
  });
});
