/**
 * AFTER-SALES-P2 red test (UAC F2): the Warranty filter travels in the list URL and in the cache key,
 * so Back restores it and two filters never share a cached page.
 * Module extended: `./listQuery`.
 */
import { describe, it, expect } from 'vitest';
import { serviceJobsListParamsFromUrl, serviceJobsListQueryKey } from './listQuery';

describe('listQuery warranty_summary', () => {
  it('reads warranty_summary from the URL filters', () => {
    const params = serviceJobsListParamsFromUrl({
      pageIndex: 0, pageSize: 50, sorting: [], searchQuery: '',
      filters: { warranty_summary: 'covered,unknown' },
    } as never);
    expect((params as { warranty_summary?: string[] }).warranty_summary).toEqual(['covered', 'unknown']);
  });

  it('puts it in the query key', () => {
    const base = { pageIndex: 0, pageSize: 50, sorting: [], searchQuery: '' };
    const a = serviceJobsListQueryKey({ ...base, warranty_summary: ['covered'] } as never);
    const b = serviceJobsListQueryKey({ ...base } as never);
    expect(JSON.stringify(a)).not.toBe(JSON.stringify(b));
    expect(JSON.stringify(a)).toContain('covered');
  });
});
