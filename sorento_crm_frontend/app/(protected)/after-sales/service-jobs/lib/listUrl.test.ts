/** AFTER-SALES-P1 fix round 2 (R2-4): the list writes ALL its state into its own address, so browser Back restores it. */
import { describe, it, expect } from 'vitest';
import { listUrlSearch } from './listUrl';

const base = { pageIndex: 2, pageSize: 50, sorting: [{ id: 'city', desc: true }], searchQuery: 'ipoh' };

describe('listUrlSearch', () => {
  it('writes page, sort, search and every filter', () => {
    const p = new URLSearchParams(
      listUrlSearch('', { ...base, filters: { status: 'proposed,confirmed', technician_id: 't-1', date_from: '2026-11-01' } }),
    );
    expect(Object.fromEntries(p)).toMatchObject({
      page: '3', limit: '50', sort: 'city', dir: 'desc', query: 'ipoh',
      status: 'proposed,confirmed', technician_id: 't-1', date_from: '2026-11-01',
    });
  });

  it('drops a cleared filter, keeps unrelated params (from, tab)', () => {
    const p = new URLSearchParams(
      listUrlSearch('status=proposed&from=j-1&tab=x', { ...base, filters: { status: undefined } }),
    );
    expect(p.has('status')).toBe(false);
    expect(p.get('from')).toBe('j-1');
    expect(p.get('tab')).toBe('x');
  });
});
