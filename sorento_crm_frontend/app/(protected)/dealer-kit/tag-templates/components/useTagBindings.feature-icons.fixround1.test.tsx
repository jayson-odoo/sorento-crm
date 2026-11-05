/**
 * Feature icons (N4, then owner ruling 5 Nov 20:35): the canvas reads the icons each spec value
 * carries from `GET /dealer-kit/feature-icons` (the same list the print page gets), with their
 * signed URLs, so no icon the print shows can be missing on the canvas.
 */
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../services/tagDataService', () => ({
  getProductTagData: vi.fn(),
  getProductSetTagData: vi.fn(),
  listSpecKeys: vi.fn(async () => []),
  listFeatureIcons: vi.fn(async () => [
    { id: 'cold', name: 'Cold', spec_key: 'water_supply', values: ['cold_only'], url: 'https://cdn/cold.png' },
    { id: 'hot', name: 'Hot', spec_key: 'water_supply', values: ['mixer'], url: 'https://cdn/hot.png' },
    { id: 'cold', name: 'Cold', spec_key: 'water_supply', values: ['mixer'], url: 'https://cdn/cold.png' },
  ]),
}));
vi.mock('../../services/assetService', () => ({
  // The general library holds no icon at all; the feature icon list is its own read.
  listAssets: vi.fn(async () => []),
  listFontAssets: vi.fn(async () => []),
  fontAssetUrl: (id: string) => `/api/v1/public/dealer-kit/fonts/${id}`,
}));

import { listFeatureIcons } from '../../services/tagDataService';
import { resetKitLibraryCache, useKitLibrary } from './useTagBindings';

beforeEach(() => {
  resetKitLibraryCache();
});

describe('useKitLibrary feature icons', () => {
  it('reads the spec-value icon list, in its order, and signs its URLs', async () => {
    const { result } = renderHook(() => useKitLibrary());
    await waitFor(() =>
      expect(result.current.featureIcons).toEqual([
        { id: 'cold', name: 'Cold', spec_key: 'water_supply', values: ['cold_only'] },
        { id: 'hot', name: 'Hot', spec_key: 'water_supply', values: ['mixer'] },
        { id: 'cold', name: 'Cold', spec_key: 'water_supply', values: ['mixer'] },
      ]),
    );
    expect(vi.mocked(listFeatureIcons)).toHaveBeenCalled();
    expect(result.current.assetUrls.hot).toBe('https://cdn/hot.png');
    expect(result.current.assetUrls.cold).toBe('https://cdn/cold.png');
  });
});
