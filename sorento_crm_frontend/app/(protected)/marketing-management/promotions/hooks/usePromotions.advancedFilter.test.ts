/**
 * FILTER-MULTISELECT PR3, a known bug pinned red: with an advanced filter set, the Promotions list posts
 * to the list-query search and drops `attachment_state` (and, once several values are allowed, the whole
 * Access level set). Both the quick filters must reach the request together with the advanced filter.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const postListQuerySearch = vi.fn();
vi.mock('@/lib/list-query/listQueryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/list-query/listQueryService')>();
  return { ...actual, postListQuerySearch: (...a: unknown[]) => postListQuerySearch(...a) };
});
const getPromotions = vi.fn();
vi.mock('../services/promotionService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/promotionService')>();
  return { ...actual, getPromotions: (...a: unknown[]) => getPromotions(...a) };
});

import { fetchPromotionsPage } from './usePromotions';

const ADVANCED = { combinator: 'and', rules: [{ field: 'description', operator: 'contains', value: 'sale' }] };

beforeEach(() => {
  postListQuerySearch.mockReset();
  postListQuerySearch.mockResolvedValue({ data: [], pagination: { total: 0 } });
  getPromotions.mockReset();
  getPromotions.mockResolvedValue({ data: [], pagination: { total: 0 } });
});

const base = { pageIndex: 0, pageSize: 25, sorting: [], searchQuery: '' };

describe('fetchPromotionsPage with an advanced filter', () => {
  it('carries the attachment state into the request beside the advanced filter', async () => {
    await fetchPromotionsPage({
      ...base,
      status: 'all',
      attachment_state: 'unlinked_or_trashed',
      advancedFilter: ADVANCED,
    } as never);
    expect(postListQuerySearch).toHaveBeenCalledTimes(1);
    expect(JSON.stringify(postListQuerySearch.mock.calls[0][0])).toContain('unlinked_or_trashed');
  });

  it('carries several access levels and several attachment states together', async () => {
    await fetchPromotionsPage({
      ...base,
      status: 'all',
      user_type: 'dealer,end_user',
      attachment_state: 'unlinked,linked_to_trashed',
      advancedFilter: ADVANCED,
    } as never);
    const sent = JSON.stringify(postListQuerySearch.mock.calls[0][0]);
    expect(sent).toContain('dealer,end_user');
    expect(sent).toContain('unlinked,linked_to_trashed');
  });

  it('without an advanced filter the plain list still gets both (guard)', async () => {
    await fetchPromotionsPage({ ...base, status: 'all', user_type: 'dealer', attachment_state: 'unlinked' } as never);
    expect(getPromotions).toHaveBeenCalledWith(
      expect.objectContaining({ user_type: 'dealer', attachment_state: 'unlinked' }),
    );
  });
});
