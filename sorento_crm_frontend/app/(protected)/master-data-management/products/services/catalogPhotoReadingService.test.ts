/**
 * The service builds the photo list query through buildDataGridParams (page, limit, sort, dir)
 * plus the active tab, and reads the API's snake_case bodies as they are.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import { attachCatalogPhotos, listCatalogPhotos, patchCatalogPhoto } from './catalogPhotoReadingService';

const mockApiFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;
const ok = (body: unknown) => ({ ok: true, json: async () => body });

beforeEach(() => {
  mockApiFetch.mockReset();
  mockApiFetch.mockResolvedValue(ok({ data: [], empty: true, pagination: { total: 0, page: 1 } }));
});

describe('catalogPhotoReadingService', () => {
  it('sends tab, page, limit, sort and dir for the active tab', async () => {
    await listCatalogPhotos('r1', {
      tab: 'duplicate',
      pageIndex: 1,
      pageSize: 25,
      sort: 'printed_code',
      desc: true,
    });
    const url = new URL(String(mockApiFetch.mock.calls[0][0]), 'http://x');
    expect(url.pathname).toBe('/api/v1/master-data/catalogue-photo-readings/r1/photos');
    expect(Object.fromEntries(url.searchParams)).toEqual({
      tab: 'duplicate',
      page: '2',
      limit: '25',
      sort: 'printed_code',
      dir: 'desc',
    });
  });

  it('omits sort when none is chosen, so the server default (page, then position) applies', async () => {
    await listCatalogPhotos('r1', { tab: 'ready', pageIndex: 0, pageSize: 25 });
    const url = new URL(String(mockApiFetch.mock.calls[0][0]), 'http://x');
    expect(url.searchParams.has('sort')).toBe(false);
    expect(url.searchParams.get('page')).toBe('1');
  });

  it('PATCHes a decision as JSON', async () => {
    mockApiFetch.mockResolvedValue(ok({ id: 'p1' }));
    await patchCatalogPhoto('r1', 'p1', { decision: 'replace' });
    const [url, init] = mockApiFetch.mock.calls[0];
    expect(String(url)).toBe('/api/v1/master-data/catalogue-photo-readings/r1/photos/p1');
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(init.body)).toEqual({ decision: 'replace' });
  });

  it('POSTs attach and returns the counts', async () => {
    mockApiFetch.mockResolvedValue(ok({ attached: 3, replaced: 1, skipped: 2, products: 3 }));
    await expect(attachCatalogPhotos('r1')).resolves.toEqual({
      attached: 3,
      replaced: 1,
      skipped: 2,
      products: 3,
    });
    expect(mockApiFetch.mock.calls[0][1].method).toBe('POST');
  });
});
