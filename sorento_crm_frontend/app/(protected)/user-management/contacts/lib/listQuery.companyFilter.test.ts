/**
 * FILTER-MULTISELECT PR 1: the contacts list's Company filter rides the URL as one comma-joined
 * `company` value (the API reads it as any-of). An old link with one id still reads.
 */
import { describe, it, expect } from 'vitest';
import { contactCompanyFilterFromUrl, contactsListFilters } from './listQuery';
import { popoverFilterChips, popoverFilterCount } from './contactFilterSummary';

const A = '11111111-1111-4111-8111-111111111111';
const B = '22222222-2222-4222-8222-222222222222';

describe('contacts Company filter in the URL', () => {
  it('writes the chosen companies as one comma-joined param', () => {
    expect(contactsListFilters({ chatbotMemoryLevel: null, companyIds: [A, B] })).toEqual({
      company: `${A},${B}`,
    });
  });
  it('is absent when none is chosen', () => {
    expect(contactsListFilters({ chatbotMemoryLevel: null, companyIds: [] })).toEqual({});
  });
  it('reads several back', () => {
    expect(contactCompanyFilterFromUrl({ company: `${A},${B}` })).toEqual([A, B]);
  });
  it('reads a single id from an older link', () => {
    expect(contactCompanyFilterFromUrl({ company: A })).toEqual([A]);
  });
  it('reads nothing as no filter', () => {
    expect(contactCompanyFilterFromUrl({})).toEqual([]);
  });
});

describe('contacts Company filter chip', () => {
  it('counts once however many companies are chosen', () => {
    expect(popoverFilterCount({ company: `${A},${B}` })).toBe(1);
  });
  it('names the companies, never an id', () => {
    const chips = popoverFilterChips({ company: `${A},${B}` }, { company: 'Mocha, Sorento' }, () => {});
    expect(chips.map((c) => c.label)).toEqual(['Company: Mocha, Sorento']);
  });
  it('clearing the chip drops the whole filter', () => {
    let next: Record<string, string> | null = null;
    const [chip] = popoverFilterChips({ company: A, region: 'west' }, { company: 'Mocha' }, (n) => {
      next = n;
    });
    chip.onClear();
    expect(next).toEqual({ region: 'west' });
  });
});
