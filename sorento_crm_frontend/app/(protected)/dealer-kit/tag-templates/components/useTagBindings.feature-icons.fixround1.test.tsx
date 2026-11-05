/**
 * Feature icons review fix round 1 (N4): the canvas's icon library is its own read by kind,
 * so an icon the print page shows cannot fall outside the general library's first page.
 */
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../services/tagDataService', () => ({
  getProductTagData: vi.fn(),
  getProductSetTagData: vi.fn(),
  listSpecKeys: vi.fn(async () => []),
}));
vi.mock('../../services/assetService', () => ({
  // The general library's first page holds no icon at all; the icon read is separate.
  listAssets: vi.fn(async () => []),
  listIconAssets: vi.fn(async () => [
          {
            id: 'ruled',
            name: 'Hot',
            kind: 'icon',
            tags: [],
            url: 'https://cdn/hot.png',
            mime_type: 'image/png',
            show_when_spec_key: 'water_supply',
            show_when_values: ['mixer'],
          },
  ]),
  listFontAssets: vi.fn(async () => []),
  fontAssetUrl: (id: string) => `/api/v1/public/dealer-kit/fonts/${id}`,
}));

import { listIconAssets } from '../../services/assetService';
import { resetKitLibraryCache, useKitLibrary } from './useTagBindings';

beforeEach(() => {
  resetKitLibraryCache();
});

describe('useKitLibrary feature icons', () => {
  it('reads the icon library by kind and signs its URLs', async () => {
    const { result } = renderHook(() => useKitLibrary());
    await waitFor(() =>
      expect(result.current.featureIcons).toEqual([
        { id: 'ruled', name: 'Hot', spec_key: 'water_supply', values: ['mixer'] },
      ]),
    );
    expect(vi.mocked(listIconAssets)).toHaveBeenCalled();
    expect(result.current.assetUrls.ruled).toBe('https://cdn/hot.png');
  });
});
