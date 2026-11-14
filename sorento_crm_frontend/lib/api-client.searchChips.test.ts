/** SEARCH-CHIPS slice 1 (UAC S1, contract): `buildDataGridParams` takes `searchQuery?: string | string[]`;
 * an array becomes one repeated `query` param per value, each value whole. */
import { describe, expect, it } from 'vitest';
import { buildDataGridParams } from './api-client';

const base = { pageIndex: 0, pageSize: 25, sorting: [] };

describe('buildDataGridParams - searchQuery as chips', () => {
  it('an array searchQuery becomes repeated query params, comma values whole', () => {
    const sp = buildDataGridParams({ ...base, searchQuery: ['SO371334', 'Acme, Trading'] });
    expect(sp.getAll('query')).toEqual(['SO371334', 'Acme, Trading']);
    expect(sp.toString()).toBe('page=1&limit=25&query=SO371334&query=Acme%2C+Trading');
  });

  it('a string searchQuery is unchanged', () => {
    const sp = buildDataGridParams({ ...base, searchQuery: 'SO371334' });
    expect(sp.getAll('query')).toEqual(['SO371334']);
    expect(sp.toString()).toBe('page=1&limit=25&query=SO371334');
  });

  it('an empty array (or blank items) sends no query', () => {
    expect(buildDataGridParams({ ...base, searchQuery: [] }).has('query')).toBe(false);
    expect(buildDataGridParams({ ...base, searchQuery: ['', '  '] }).getAll('query')).toEqual([]);
  });

  it('array query keeps its place among sort and extras', () => {
    const sp = buildDataGridParams(
      { ...base, sorting: [{ id: 'so_number', desc: true }], searchQuery: ['A1', 'B2'] },
      { status: 'open' },
    );
    expect(sp.getAll('query')).toEqual(['A1', 'B2']);
    expect(sp.get('sort')).toBe('so_number');
    expect(sp.get('status')).toBe('open');
  });
});
