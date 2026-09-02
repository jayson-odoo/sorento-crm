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

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('../../services/tagDataService', () => ({
  getProductTagData: vi.fn(),
  getProductSetTagData: vi.fn(),
  listSpecKeys: vi.fn(),
}));
vi.mock('../../services/assetService', () => ({
  listAssets: vi.fn(async () => []),
  listFontAssets: vi.fn(async () => []),
}));

import { toast } from 'sonner';
import { getProductTagData, getProductSetTagData } from '../../services/tagDataService';
import {
  resetTagBindingsToastDedupeForTests,
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
