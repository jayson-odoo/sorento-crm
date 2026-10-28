/**
 * FILTER-MULTISELECT PR3 review: the Brochure images Promotion filter keeps the paging the single picker
 * had (`paginated`, `pageSize` = PROMOTION_PAGE_SIZE, a loader that takes a page index), so with more
 * promotions than one page the later pages are reachable with no search typed. The multi control is stood
 * in for so the props it is handed can be read.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('../../services/brochureImageService', () => ({
  BROCHURE_IMAGE_PAGE_SIZE: 25,
  PROMOTION_PAGE_SIZE: 50,
  listBrochureImages: vi.fn(),
  listBrochureImagePromotionOptions: vi.fn(),
  adoptSingleBrochureImages: vi.fn(),
}));
vi.mock('@/app/(protected)/master-data-management/products/services/productBrochureImageService', () => ({
  setBrochureImage: vi.fn(),
  clearBrochureImage: vi.fn(),
}));
const multi = vi.hoisted(() => ({ props: null as null | Record<string, unknown> }));
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  return {
    ...actual,
    SearchableMultiSelect: (props: Record<string, unknown>) => {
      if (props.id === 'dk-bi-promotion') multi.props = props;
      return null;
    },
  };
});

import { listBrochureImages, listBrochureImagePromotionOptions } from '../../services/brochureImageService';
import { BrochureImagePicker } from './BrochureImagePicker';

beforeEach(() => {
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    })) as unknown as typeof window.matchMedia;
  }
  if (!('ResizeObserver' in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
  vi.mocked(listBrochureImages).mockReset();
  vi.mocked(listBrochureImages).mockResolvedValue({
    items: [], total: 0, page: 1, limit: 25, pages: 1, summary: {},
  } as never);
  vi.mocked(listBrochureImagePromotionOptions).mockReset();
  // The service returns the options array itself (brochureImageService.ts listBrochureImagePromotionOptions).
  vi.mocked(listBrochureImagePromotionOptions).mockResolvedValue([
    { value: 'promo-1', label: 'ZZT Flyer One' },
    { value: 'promo-2', label: 'ZZT Flyer Two' },
  ]);
});
afterEach(() => cleanup());

function renderIt() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <BrochureImagePicker />
    </QueryClientProvider>,
  );
}

describe('Brochure images - the Promotion filter pages', () => {
  it('is given the paginated loader with the promotion page size', async () => {
    renderIt();
    await waitFor(() => expect(multi.props).not.toBeNull());
    expect(multi.props!.paginated).toBe(true);
    expect(multi.props!.pageSize).toBe(50);
  });

  it('its loader requests the page it is asked for, so page 2 is reachable', async () => {
    renderIt();
    await waitFor(() => expect(multi.props).not.toBeNull());
    const load = multi.props!.fetchOptions as (q: string, pageIndex: number) => Promise<unknown>;
    await load('', 1);
    expect(vi.mocked(listBrochureImagePromotionOptions)).toHaveBeenCalledWith('', 1);
  });
});

// Browser pass 28 Oct: with two long promotion names picked, the trigger grew to its chips' width and
// pushed the Product box under the "Only products still without an image" switch. The multi control
// sizes its trigger through `triggerClassName`; its `className` styles the popover.
describe('Brochure images - the Promotion trigger keeps its width', () => {
  it('passes the w-full / sm:w-72 width to the trigger, not the popover', async () => {
    renderIt();
    await waitFor(() => expect(multi.props).not.toBeNull());
    expect(String(multi.props!.triggerClassName ?? '')).toContain('sm:w-72');
    expect(String(multi.props!.className ?? '')).not.toContain('sm:w-72');
  });

  it('lets the filter row wrap, so the fixed-width trigger never overlaps the Product box', async () => {
    const { container } = renderIt();
    await waitFor(() => expect(multi.props).not.toBeNull());
    const row = container.querySelector('#dk-bi-search')?.closest('.sm\\:flex-row');
    expect(row).not.toBeNull();
    expect(row!.className).toContain('sm:flex-wrap');
  });
});
