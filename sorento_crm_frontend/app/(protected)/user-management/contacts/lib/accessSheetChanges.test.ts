/**
 * Lane BULK-ACCESS-PREVIEW, UAC P5: a change shown as before -> after, one item per line,
 * added items marked; unchanged facets named once.
 */
import { describe, it, expect } from 'vitest';
import { changeLines, unchangedFacets } from './accessSheet';

describe('changeLines', () => {
  it('lists every item of a list facet and marks only the added ones', () => {
    const lines = changeLines({ facet: 'access_types', before: ['end_user'], after: ['cabana_dealer', 'dealer', 'end_user'] });
    expect(lines.before).toEqual([{ text: 'end_user', added: false }]);
    expect(lines.after).toEqual([
      { text: 'cabana_dealer', added: true },
      { text: 'dealer', added: true },
      { text: 'end_user', added: false },
    ]);
  });

  it('a text before (every brand) is one line and every after item is added', () => {
    const lines = changeLines({ facet: 'brands', before: 'every brand', after: ['CABANA', 'SORENTO'] });
    expect(lines.before).toEqual([{ text: 'every brand', added: false }]);
    expect(lines.after.map((i) => i.added)).toEqual([true, true]);
  });

  it('null before is no line; a switch shows on / off', () => {
    expect(changeLines({ facet: 'stock_locations', before: null, after: ['BRW'] }).before).toEqual([]);
    const sw = changeLines({ facet: 'packing_list_allowed', before: true, after: false });
    expect(sw.before).toEqual([{ text: 'on', added: false }]);
    expect(sw.after).toEqual([{ text: 'off', added: true }]);
  });
});

describe('unchangedFacets', () => {
  it('names every template facet that is neither changed nor not applied', () => {
    const out = unchangedFacets({
      changes: [{ facet: 'companies', before: [], after: ['SRT'] }],
      not_applied: ['agent_access'],
    });
    expect(out).not.toContain('companies');
    expect(out).not.toContain('agent_access');
    expect(out).toContain('market_segments');
    expect(out).toContain('packing_list_allowed');
  });
});
