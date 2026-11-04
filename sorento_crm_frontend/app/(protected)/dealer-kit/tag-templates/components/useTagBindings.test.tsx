/**
 * A product that 404s under this request's company (a cross-company line -
 * see `457_ptag_line_xco_repair`) used to toast once per resolution attempt:
 * every line switch remounts `TagCanvasEditor`, and with it a fresh
 * `useTagBindings` instance whose own hook state cannot remember an earlier
 * failure. The dedupe has to survive that remount, so it lives at module
 * scope rather than in the hook.
 */
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('../../services/tagDataService', () => ({
  getProductTagData: vi.fn(),
  getProductSetTagData: vi.fn(),
  listSpecKeys: vi.fn(),
}));
vi.mock('../../services/assetService', () => ({
  listAssets: vi.fn(async () => []),
  listFontAssets: vi.fn(async () => []),
  fontAssetUrl: (id: string) => `/api/v1/public/dealer-kit/fonts/${id}`,
}));

import { toast } from '@/lib/toast';
import {
  getProductTagData,
  getProductSetTagData,
  listSpecKeys,
} from '../../services/tagDataService';
import { listAssets, listFontAssets } from '../../services/assetService';
import {
  invalidateKitLibrary,
  kitLibraryClient,
  KIT_LIBRARY_STALE_MS,
} from '@/lib/dealer-kit/kit-library-cache';
import {
  resetTagBindingsToastDedupeForTests,
  resetKitLibraryCache,
  useKitLibrary,
  useTagBindings,
} from './useTagBindings';
import type { ProductTagData } from '@/lib/dealer-kit/tag-template-types';

const mockGetProduct = vi.mocked(getProductTagData);
const mockGetSet = vi.mocked(getProductSetTagData);
const mockToastError = vi.mocked(toast.error);

function product(overrides: Partial<ProductTagData> = {}): ProductTagData {
  return {
    id: 'prod-1',
    code: 'SRT-1',
    name: 'Kitchen Sink',
    dimensions: '',
    spec_lines: [],
    specs: [],
    images: [],
    list_price: 100,
    offer_price: null,
    promotion_id: null,
    barcode: null,
    ...overrides,
  } as ProductTagData;
}

beforeEach(() => {
  vi.clearAllMocks();
  resetTagBindingsToastDedupeForTests();
});

describe('a product that keeps failing to resolve', () => {
  it('toasts once for five failed resolution attempts on the same product', async () => {
    mockGetProduct.mockRejectedValue(new Error('Product not found.'));
    const { result } = renderHook(() => useTagBindings());

    for (let i = 0; i < 5; i += 1) {
      await act(async () => {
        await result.current.loadProduct('prod-x');
      });
    }

    expect(mockGetProduct).toHaveBeenCalledTimes(5);
    expect(mockToastError).toHaveBeenCalledTimes(1);
    expect(mockToastError).toHaveBeenCalledWith('Product not found.');
  });

  it('toasts once per remount - a fresh hook instance does not toast again', async () => {
    mockGetProduct.mockRejectedValue(new Error('Product not found.'));
    const first = renderHook(() => useTagBindings());
    await act(async () => {
      await first.result.current.loadProduct('prod-x');
    });
    first.unmount();

    const second = renderHook(() => useTagBindings());
    await act(async () => {
      await second.result.current.loadProduct('prod-x');
    });

    expect(mockToastError).toHaveBeenCalledTimes(1);
  });

  it('a DIFFERENT product still gets its own toast', async () => {
    mockGetProduct.mockRejectedValue(new Error('Product not found.'));
    const { result } = renderHook(() => useTagBindings());

    await act(async () => {
      await result.current.loadProduct('prod-x');
    });
    await act(async () => {
      await result.current.loadProduct('prod-y');
    });

    expect(mockToastError).toHaveBeenCalledTimes(2);
  });

  it('a set that keeps failing is deduped the same way', async () => {
    mockGetSet.mockRejectedValue(new Error('Product set not found.'));
    const { result } = renderHook(() => useTagBindings());

    await act(async () => {
      await result.current.loadSet('set-x');
    });
    await act(async () => {
      await result.current.loadSet('set-x');
    });

    expect(mockToastError).toHaveBeenCalledTimes(1);
  });

  it('a later successful resolve clears the dedupe, so a fresh failure toasts again', async () => {
    mockGetProduct.mockRejectedValueOnce(new Error('Product not found.'));
    const { result } = renderHook(() => useTagBindings());

    await act(async () => {
      await result.current.loadProduct('prod-x');
    });
    expect(mockToastError).toHaveBeenCalledTimes(1);

    mockGetProduct.mockResolvedValueOnce(product());
    await act(async () => {
      await result.current.loadProduct('prod-x');
    });

    mockGetProduct.mockRejectedValueOnce(new Error('Product not found.'));
    await act(async () => {
      await result.current.loadProduct('prod-x');
    });

    expect(mockToastError).toHaveBeenCalledTimes(2);
  });
});

// ---------------------------------------------------------------------------
// The kit library: rename and delete update the dropdown without a reload
// (PLAN-brand-font-manage.md)
// ---------------------------------------------------------------------------

describe('useKitLibrary forget/rename', () => {
  const mockListFontAssets = vi.mocked(listFontAssets);

  beforeEach(() => {
    // The library is read once per session; each test starts from an unread one.
    resetKitLibraryCache();
    vi.mocked(listSpecKeys).mockResolvedValue([]);
  });

  function font(overrides: { id: string; name: string }) {
    return {
      id: overrides.id,
      name: overrides.name,
      kind: 'font',
      tags: [],
      url: null,
      mime_type: null,
    };
  }

  it('forget drops the font from the list and the dropdown', async () => {
    mockListFontAssets.mockResolvedValue([
      font({ id: 'f-1', name: 'Sorento Display' }),
      font({ id: 'f-2', name: 'Sorento Body' }),
    ]);
    const { result } = renderHook(() => useKitLibrary());

    await waitForFonts(result, 2);

    // The shared library cache notifies its subscribers on the next tick.
    await act(async () => {
      result.current.forget('f-1');
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(result.current.fonts.map((f) => f.id)).toEqual(['f-2']);
    expect(
      result.current.fontOptions.some((o) => o.value === 'Sorento Display'),
    ).toBe(false);
  });

  it('rename swaps the label without dropping the option', async () => {
    mockListFontAssets.mockResolvedValue([
      font({ id: 'f-1', name: 'Sorento Display' }),
    ]);
    const { result } = renderHook(() => useKitLibrary());

    await waitForFonts(result, 1);

    await act(async () => {
      result.current.rename('f-1', 'Sorento Display Renamed');
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(result.current.fonts[0].name).toBe('Sorento Display Renamed');
    expect(
      result.current.fontOptions.some(
        (o) => o.value === 'Sorento Display Renamed',
      ),
    ).toBe(true);
    expect(
      result.current.fontOptions.some((o) => o.value === 'Sorento Display'),
    ).toBe(false);
  });
});

describe('useKitLibrary across a company switch and signed URL expiry', () => {
  const mockListAssets = vi.mocked(listAssets);

  beforeEach(() => {
    resetKitLibraryCache();
    mockListAssets.mockReset();
    vi.mocked(listSpecKeys).mockResolvedValue([]);
  });

  function asset(id: string) {
    return { id, name: id, kind: 'image', tags: [], url: `https://cdn/${id}`, mime_type: 'image/png' };
  }

  async function settle() {
    for (let i = 0; i < 10; i += 1) {
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 0));
      });
    }
  }

  it('an open editor reads the new company library after the switch invalidates the cache', async () => {
    mockListAssets.mockResolvedValueOnce([asset('company-a')] as never);
    mockListAssets.mockResolvedValue([asset('company-b')] as never);
    const { result } = renderHook(() => useKitLibrary());
    await settle();
    expect(Object.keys(result.current.assetUrls)).toEqual(['company-a']);

    await act(async () => {
      await invalidateKitLibrary();
    });
    await settle();

    expect(mockListAssets).toHaveBeenCalledTimes(2);
    expect(Object.keys(result.current.assetUrls)).toEqual(['company-b']);
  });

  it('a closed editor reads again on its next open after a switch', async () => {
    mockListAssets.mockResolvedValue([asset('a')] as never);
    const first = renderHook(() => useKitLibrary());
    await settle();
    first.unmount();
    await act(async () => {
      await invalidateKitLibrary();
    });
    renderHook(() => useKitLibrary());
    await settle();
    expect(mockListAssets).toHaveBeenCalledTimes(2);
  });

  it('goes stale before the signed URLs expire (3600 s), so a later open signs fresh links', async () => {
    expect(KIT_LIBRARY_STALE_MS).toBeLessThan(3600 * 1000);
    mockListAssets.mockResolvedValue([asset('a')] as never);
    const first = renderHook(() => useKitLibrary());
    await settle();
    first.unmount();
    // Pretend the read happened just past the stale window.
    const query = kitLibraryClient
      .getQueryCache()
      .find({ queryKey: ['dealer-kit', 'library', 'assets'] });
    query?.setState({ dataUpdatedAt: Date.now() - KIT_LIBRARY_STALE_MS - 1000 });
    renderHook(() => useKitLibrary());
    await settle();
    expect(mockListAssets).toHaveBeenCalledTimes(2);
  });
});

/** Waits for the initial `reload()` effect to land `count` fonts. */
async function waitForFonts(
  result: { current: ReturnType<typeof useKitLibrary> },
  count: number,
): Promise<void> {
  for (let i = 0; i < 20 && result.current.fonts.length < count; i += 1) {
    await act(async () => {
      await Promise.resolve();
    });
  }
}
