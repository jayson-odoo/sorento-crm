/**
 * Lane BULK-ACCESS-PREVIEW, UAC P5: a change shown as before -> after, one item per line,
 * added items marked; unchanged facets named once.
 */
import { describe, it, expect } from 'vitest';
import {
  allExactConfirmed,
  changeLines,
  confirmAllExact,
  hasConfirmableExact,
  initialSelection,
  orderedChanges,
  resultCsv,
  unchangedFacets,
} from './accessSheet';
import type { AccessSheetResult } from '@/services/contactAccessSheetService';

describe('changeLines', () => {
  it('lists every item of a list facet and marks only the added ones', () => {
    const lines = changeLines({
      facet: 'access_types',
      before: ['end_user'],
      after: ['cabana_dealer', 'dealer', 'end_user'],
    });
    expect(lines.before).toEqual([{ text: 'end_user', added: false }]);
    expect(lines.after).toEqual([
      { text: 'cabana_dealer', added: true },
      { text: 'dealer', added: true },
      { text: 'end_user', added: false },
    ]);
  });

  it('a text before (every brand) is one line and every after item is added', () => {
    const lines = changeLines({
      facet: 'brands',
      before: 'every brand',
      after: ['CABANA', 'SORENTO'],
    });
    expect(lines.before).toEqual([{ text: 'every brand', added: false }]);
    expect(lines.after.map((i) => i.added)).toEqual([true, true]);
  });

  it('null before is no line; a switch shows on / off with no + (only list items are added)', () => {
    expect(
      changeLines({ facet: 'stock_locations', before: null, after: ['BRW'] })
        .before,
    ).toEqual([]);
    const sw = changeLines({
      facet: 'packing_list_allowed',
      before: true,
      after: false,
    });
    expect(sw.before).toEqual([{ text: 'on', added: false }]);
    expect(sw.after).toEqual([{ text: 'off', added: false }]);
    expect(
      changeLines({
        facet: 'stock_check_mode',
        before: null,
        after: 'availability',
      }).after,
    ).toEqual([{ text: 'availability', added: false }]);
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

describe('confirmAllExact (crew ruling 27 Oct: Rows disagree cards are confirmed too)', () => {
  const block = (key: string, warnings: string[] = []) => ({
    key,
    dealer: key,
    alt_dealers: [],
    companies: ['SRT'],
    status: 'exact',
    warnings,
    accounts: [],
    contacts: [],
  });
  const preview = {
    blocks: [block('a'), block('b', ['rows_disagree'])],
  } as unknown as AccessSheetResult;

  it('confirms a Rows disagree card like any exact card', () => {
    const sel = confirmAllExact(preview, initialSelection(preview));
    expect(sel.confirmed).toEqual({ a: true, b: true });
  });

  it('reads as all confirmed once every exact card is', () => {
    expect(
      allExactConfirmed(
        preview,
        confirmAllExact(preview, initialSelection(preview)),
      ),
    ).toBe(true);
  });
});

describe('resultCsv (BULK-ACCESS-PREVIEW)', () => {
  it('carries holds-more items and links outside the row, as the preview showed them', () => {
    const csv = resultCsv({
      dry_run: false,
      counts: {},
      errors: [],
      blocks: [
        {
          key: 'a',
          dealer: 'A',
          alt_dealers: [],
          companies: ['SRT'],
          status: 'exact',
          warnings: [],
          accounts: [],
          contacts: [
            {
              line: 2,
              name: 'Ann',
              phone: '+60100000001',
              in_crm: true,
              contact_id: 'x',
              role: 'owner',
              companies: ['SRT'],
              template: 'SRT owner',
              status: 'applied',
              skip_reason: null,
              changes: [],
              warnings: ['holds_more'],
              not_applied: [],
              holds_more_items: [{ facet: 'brands', items: ['BRAVAT'] }],
              outside_links: ['300-Y055 YOO A (MCH)'],
            },
          ],
        },
      ],
    } as unknown as AccessSheetResult);
    const [header, row] = csv.split('\n');
    expect(header).toContain('Holds more');
    expect(header).toContain('Linked outside row');
    expect(row).toContain('brands: BRAVAT');
    expect(row).toContain('300-Y055 YOO A (MCH)');
  });
});

describe('orderedChanges', () => {
  it('lists the changes in the template order the No change line uses', () => {
    const out = orderedChanges([
      { facet: 'packing_list_allowed', before: true, after: false },
      { facet: 'customers', before: [], after: ['300-A'] },
      { facet: 'access_types', before: [], after: ['end_user'] },
      { facet: 'companies', before: [], after: ['SRT'] },
    ]);
    expect(out.map((c) => c.facet)).toEqual([
      'companies',
      'access_types',
      'customers',
      'packing_list_allowed',
    ]);
  });
});

describe('hasConfirmableExact', () => {
  it('is true for an exact card whose rows disagree, false when no card is exact', () => {
    const block = (warnings: string[], status = 'exact') => ({
      key: 'b',
      dealer: 'b',
      alt_dealers: [],
      companies: ['SRT'],
      status,
      warnings,
      accounts: [],
      contacts: [],
    });
    expect(
      hasConfirmableExact({
        blocks: [block(['rows_disagree'])],
      } as unknown as AccessSheetResult),
    ).toBe(true);
    expect(
      hasConfirmableExact({
        blocks: [block([], 'pick')],
      } as unknown as AccessSheetResult),
    ).toBe(false);
  });
});
