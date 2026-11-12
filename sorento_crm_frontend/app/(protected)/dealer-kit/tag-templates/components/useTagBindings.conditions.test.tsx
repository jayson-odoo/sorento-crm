/**
 * SPEC-ICON-COMBINED round 2: the designer's icon list (template designer and request designer
 * both read `useKitLibrary().featureIcons`) must keep each icon's `conditions`, or a P trap at
 * 150 mm previews "S trap 150mm".
 */
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../services/tagDataService', () => ({
  getProductTagData: vi.fn(),
  getProductSetTagData: vi.fn(),
  listSpecKeys: vi.fn(async () => []),
  listFeatureIcons: vi.fn(async () => [
    { id: 's', name: 'S trap', spec_key: 'trap_type', values: ['s_trap'], conditions: [], url: 'https://cdn/s.png' },
    {
      id: 's150',
      name: 'S trap 150mm',
      spec_key: 'trap_length',
      values: ['150'],
      conditions: [{ spec_key: 'trap_type', value: 's_trap' }],
      url: 'https://cdn/s150.png',
    },
  ]),
}));
vi.mock('../../services/assetService', () => ({
  listAssets: vi.fn(async () => []),
  listFontAssets: vi.fn(async () => []),
  fontAssetUrl: (id: string) => `/api/v1/public/dealer-kit/fonts/${id}`,
}));

import { featureIconsFor } from '@/lib/dealer-kit/feature-icons';
import { resetKitLibraryCache, useKitLibrary } from './useTagBindings';

beforeEach(() => {
  resetKitLibraryCache();
});

describe('useKitLibrary feature icon conditions', () => {
  it('a P trap at 150 mm does not get the S trap 150mm icon, an S trap does', async () => {
    const { result } = renderHook(() => useKitLibrary());
    await waitFor(() => expect(result.current.featureIcons.length).toBe(2));
    const ids = (trap: string) =>
      featureIconsFor(
        [
          { key: 'trap_type', raw: trap },
          { key: 'trap_length', raw: '150' },
        ],
        result.current.featureIcons,
      ).map((i) => i.id);
    expect(ids('p_trap')).toEqual([]);
    expect(ids('s_trap')).toEqual(['s', 's150']);
  });
});
