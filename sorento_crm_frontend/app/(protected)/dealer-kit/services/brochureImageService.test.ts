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

import { apiFetch } from '@/lib/api';
import { getPromotions } from '@/app/(protected)/marketing-management/promotions/services/promotionService';
import * as brochureImageService from './brochureImageService';
import {
  PROMOTION_PAGE_SIZE,
  listBrochureImagePromotionOptions,
  listBrochureImages,
} from './brochureImageService';

const mockGetPromotions = vi.mocked(getPromotions);
const mockApiFetch = vi.mocked(apiFetch);

function jsonResponse(body: unknown) {
  return { ok: true, json: async () => body } as never;
}

/** The query string the mocked apiFetch was actually called with. */
function calledSearchParams() {
  const [url] = mockApiFetch.mock.calls[0] as [string];
  return new URL(url, 'http://test').searchParams;
}

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

/**
 * The listing query string now goes through `buildDataGridParams` (audit rule
 * 3) instead of a hand-rolled `URLSearchParams`. These pin the contract that
 * matters: 1-based `page`, `limit`, `only_unset` always present, `query` and
 * `promotion_id` only when set - so a future refactor cannot silently regress
 * to `pageIndex`/`pageSize` or start sending an empty `query=`.
 */
describe('listBrochureImages query string', () => {
  beforeEach(() => {
    mockApiFetch.mockResolvedValue(
      jsonResponse({ items: [], total: 0, remaining: 0, shown: 0, choosable: 0 }),
    );
  });

  it('sends a 1-based page and the limit, with only_unset always present', async () => {
    await listBrochureImages({ page: 2, limit: 10 });

    const params = calledSearchParams();
    expect(params.get('page')).toBe('2');
    expect(params.get('limit')).toBe('10');
    expect(params.get('only_unset')).toBe('true');
  });

  it('omits query entirely when blank', async () => {
    await listBrochureImages({ query: '   ' });

    expect(calledSearchParams().has('query')).toBe(false);
  });

  it('sends the trimmed query when set', async () => {
    await listBrochureImages({ query: '  basin  ' });

    expect(calledSearchParams().get('query')).toBe('basin');
  });

  it('omits promotion_id when unset, sends it when chosen', async () => {
    await listBrochureImages({});
    expect(calledSearchParams().has('promotion_id')).toBe(false);

    mockApiFetch.mockClear();
    await listBrochureImages({ promotionId: 'promo-1' });
    expect(calledSearchParams().get('promotion_id')).toBe('promo-1');
  });

  it('defaults to page 1 and the standard page size', async () => {
    await listBrochureImages({});

    const params = calledSearchParams();
    expect(params.get('page')).toBe('1');
    expect(params.get('limit')).toBe(String(brochureImageService.BROCHURE_IMAGE_PAGE_SIZE));
  });
});
