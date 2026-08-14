/**
 * The dealer kit's half of the brochure-image contract: listing the work and
 * the promotion filter above it. Writing the flag is product master data and
 * lives in `products/services/productBrochureImageService`, so a second copy
 * appearing here is a regression these tests catch rather than a convenience.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));
vi.mock('@/app/(protected)/marketing-management/promotions/services/promotionService', () => ({
  getPromotions: vi.fn(),
}));

import { getPromotions } from '@/app/(protected)/marketing-management/promotions/services/promotionService';
import * as brochureImageService from './brochureImageService';
import { PROMOTION_PAGE_SIZE, listBrochureImagePromotionOptions } from './brochureImageService';

const mockGetPromotions = vi.mocked(getPromotions);

function promotionsPage(data: unknown[]) {
  return {
    data,
    empty: data.length === 0,
    pagination: { total: data.length, page: 1 },
  } as never;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetPromotions.mockResolvedValue(promotionsPage([]));
});

describe('dealer kit brochure image service', () => {
  it('leaves writing the flag to the product master data service', () => {
    // Two copies of these drifted in URL spelling and failure message without
    // anything failing, because both spellings resolve through the api rewrite.
    expect('setBrochureImage' in brochureImageService).toBe(false);
    expect('clearBrochureImage' in brochureImageService).toBe(false);
  });

  it('asks the promotions service for the filter options', async () => {
    mockGetPromotions.mockResolvedValue(
      promotionsPage([{ id: 'promo-1', description: 'A3 Flyer 2026', products_count: 2 }]),
    );

    const options = await listBrochureImagePromotionOptions('flyer', 1);

    expect(mockGetPromotions).toHaveBeenCalledWith(
      expect.objectContaining({
        pageIndex: 1,
        pageSize: PROMOTION_PAGE_SIZE,
        searchQuery: 'flyer',
      }),
    );
    expect(options).toEqual([
      { value: 'promo-1', label: 'A3 Flyer 2026', description: '2 products' },
    ]);
  });

  it('never labels a promotion with its id', async () => {
    mockGetPromotions.mockResolvedValue(
      promotionsPage([{ id: '0f0e1d2c-3b4a-5968-8776-a5b4c3d2e1f0', description: null }]),
    );

    const options = await listBrochureImagePromotionOptions();

    expect(options[0].label).toBe('Untitled promotion');
    expect(options[0].description).toBeUndefined();
  });
});
