/** SEARCH-CHIPS slice 1 (UAC S2, contract): `parseDetailSearch` keeps `searchQuery` (the first
 * `query`) and adds `searchQueries` (every `query`), so Back and prev/next carry every chip. */
import { describe, expect, it } from 'vitest';
import { buildDetailSearch, parseDetailSearch } from './listNavQuery';

describe('parseDetailSearch - repeated query', () => {
  it('returns every query value as searchQueries, searchQuery stays the first', () => {
    const out = parseDetailSearch(
      new URLSearchParams('page=2&limit=25&query=SO371334&query=Acme%2C+Trading&status=open'),
    );
    expect(out.searchQueries).toEqual(['SO371334', 'Acme, Trading']);
    expect(out.searchQuery).toBe('SO371334');
    expect(out.filters).toEqual({ status: 'open' });
    expect(out.pageIndex).toBe(1);
  });

  it('a single query gives a one-item searchQueries', () => {
    const out = parseDetailSearch(new URLSearchParams('query=SO1'));
    expect(out.searchQueries).toEqual(['SO1']);
    expect(out.searchQuery).toBe('SO1');
  });

  it('no query gives an empty searchQueries and an empty searchQuery', () => {
    const out = parseDetailSearch(new URLSearchParams('page=1'));
    expect(out.searchQueries).toEqual([]);
    expect(out.searchQuery).toBe('');
  });

  it('blank query values are dropped from searchQueries', () => {
    const out = parseDetailSearch(new URLSearchParams('query=&query=SO2'));
    expect(out.searchQueries).toEqual(['SO2']);
  });

  it('round-trips with buildDetailSearch given an array searchQuery', () => {
    const search = buildDetailSearch({
      pageIndex: 0,
      pageSize: 50,
      searchQuery: ['SO1', 'Acme Trading'] as unknown as string,
    });
    expect(parseDetailSearch(new URLSearchParams(search)).searchQueries).toEqual([
      'SO1',
      'Acme Trading',
    ]);
  });
});
