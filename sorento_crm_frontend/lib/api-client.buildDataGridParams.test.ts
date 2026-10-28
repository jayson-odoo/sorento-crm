/** FILTER-MULTISELECT PR4: `buildDataGridParams` sends an array extra as REPEATED params, items whole, so a text
 * value containing a comma is never split; a plain string extra is encoded exactly as before. */
import { describe, expect, it } from 'vitest';
import { buildDataGridParams } from './api-client';

const base = { pageIndex: 0, pageSize: 25, sorting: [], searchQuery: '' };

describe('buildDataGridParams - list extras', () => {
  it('an array extra with a comma-containing item becomes repeated params, the item whole', () => {
    const sp = buildDataGridParams(base, { class_label: ['Sink, Undermount', 'Tap'] });
    expect(sp.getAll('class_label')).toEqual(['Sink, Undermount', 'Tap']);
    expect(sp.toString()).toContain('class_label=Sink%2C+Undermount&class_label=Tap');
  });

  it('a plain string extra is encoded exactly as before', () => {
    const sp = buildDataGridParams(base, { status: 'draft,submitted', n: 3, flag: false });
    expect(sp.get('status')).toBe('draft,submitted');
    expect(sp.get('n')).toBe('3');
    expect(sp.get('flag')).toBe('false');
    expect(sp.toString()).toBe('page=1&limit=25&status=draft%2Csubmitted&n=3&flag=false');
  });

  it('empty, null, undefined and an empty array add nothing', () => {
    const sp = buildDataGridParams(base, { a: '', b: null, c: undefined, d: [] });
    expect(sp.toString()).toBe('page=1&limit=25');
  });
});
