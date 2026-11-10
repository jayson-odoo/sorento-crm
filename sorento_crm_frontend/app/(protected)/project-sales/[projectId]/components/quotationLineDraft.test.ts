/**
 * SET-QUOTE-LINE (A2b, A7, F2): the draft carries the SET a line names, and the Complete set text
 * the screen pre-fills is built the same way the server builds it, so a line saved from the grid
 * and a line saved without it read alike.
 */
import { describe, expect, it } from 'vitest';
import type { QuotationLine, StagedQuotationLine } from '../../_shared/types/project.types';
import {
  completeSetText,
  emptyDraft,
  isSectionDraft,
  lineErrors,
  sectionDraft,
  serverToDraft,
  splitCarriedHeadings,
  toBody,
  totalFromDrafts,
} from './quotationLineDraft';

function line(overrides: Partial<QuotationLine> = {}): QuotationLine {
  return {
    id: 'l1',
    version_id: 'v1',
    product_id: null,
    product_set_id: null,
    set_parts: [],
    unit_price: '900.00',
    quantity: '10.00',
    ...overrides,
  } as QuotationLine;
}

describe('completeSetText', () => {
  it('joins the part codes with " + " in the order given', () => {
    expect(
      completeSetText([
        { product_code: 'CWCX1009-RL', quantity: '1' },
        { product_code: 'CWCY1009', quantity: '1' },
        { product_code: 'CWC1009-SC', quantity: '1' },
      ]),
    ).toBe('CWCX1009-RL + CWCY1009 + CWC1009-SC');
  });

  it('reads a part with a quantity other than one as "2 x CODE"', () => {
    expect(
      completeSetText([
        { product_code: 'CWCX1009-RL', quantity: '1' },
        { product_code: 'CWC1009-SC', quantity: '2' },
      ]),
    ).toBe('CWCX1009-RL + 2 x CWC1009-SC');
    expect(completeSetText([{ product_code: 'AB', quantity: 3 }])).toBe('3 x AB');
  });

  it('treats the server decimal strings "1.0000" and "2.0000" as the numbers 1 and 2', () => {
    expect(
      completeSetText([
        { product_code: 'AB', quantity: '1.0000' },
        { product_code: 'CD', quantity: '2.0000' },
      ]),
    ).toBe('AB + 2 x CD');
  });

  it('is cut at the 100 characters the column holds', () => {
    const parts = Array.from({ length: 6 }, (_, index) => ({
      product_code: `LONG-PART-CODE-NUMBER-${index}-XXXXXXXX`,
      quantity: '1',
    }));
    const full = parts.map((part) => part.product_code).join(' + ');
    expect(full.length).toBeGreaterThan(100);
    const text = completeSetText(parts);
    expect(text).toHaveLength(100);
    expect(text).toBe(full.slice(0, 100));
  });

  it('is empty for a set with no parts', () => {
    expect(completeSetText([])).toBe('');
  });
});

describe('the draft of a set line', () => {
  it('starts a new row with no set', () => {
    expect(emptyDraft().product_set_id).toBe('');
  });

  it('maps the stored product_set_id into the draft, and a product line to empty', () => {
    expect(serverToDraft(line({ product_set_id: 'set-1' })).product_set_id).toBe('set-1');
    expect(serverToDraft(line({ product_id: 'p1' })).product_set_id).toBe('');
  });

  it('sends product_set_id as the string it holds, and null when there is none', () => {
    const setBody = toBody(
      { ...emptyDraft(), product_set_id: 'set-1', unit_price: '900', quantity: '10' },
      null,
    );
    expect(setBody.product_set_id).toBe('set-1');
    expect(setBody.product_id).toBeNull();

    const productBody = toBody({ ...emptyDraft(), product_id: 'p1' }, null);
    expect(productBody.product_set_id).toBeNull();
    expect(productBody.product_id).toBe('p1');
  });

  it('does not ask a set line for a description (the set name is the description)', () => {
    expect(lineErrors({ ...emptyDraft(), product_set_id: 'set-1' })).toEqual({});
  });
});

describe('lineErrors: every line names a catalogue product or set (QUOTE-NO-FREE-TEXT AC-9, AC-10)', () => {
  const MESSAGE = 'Pick a catalogue product or set';

  it('refuses a line with a description but no product and no set', () => {
    const errors = lineErrors({ ...emptyDraft(), description: 'Bespoke stone counter' });
    expect(Object.values(errors)).toEqual([MESSAGE]);
  });

  it('refuses an untouched line with nothing at all, with the same message', () => {
    expect(Object.values(lineErrors(emptyDraft()))).toEqual([MESSAGE]);
  });

  it('has no error once a product is set, with or without a description', () => {
    expect(lineErrors({ ...emptyDraft(), product_id: 'p1' })).toEqual({});
    expect(
      lineErrors({ ...emptyDraft(), product_id: 'p1', description: 'Reworded for the customer' }),
    ).toEqual({});
  });

  it('has no error once a set is set', () => {
    expect(lineErrors({ ...emptyDraft(), product_set_id: 'set-1' })).toEqual({});
  });

  it('shows the error again when the product of a described line is cleared', () => {
    const cleared = { ...emptyDraft(), product_id: '', description: 'Wall-hung basin' };
    expect(Object.values(lineErrors(cleared))).toEqual([MESSAGE]);
  });
});

/**
 * PROPOSAL-FORM-COLLAPSE (owner, 10 Nov): "a heading shouldnt be tied to line". A heading is its
 * own row (`is_section`): its body is the heading alone, it needs no product, adds nothing, and a
 * product line that still carries a heading from before is shown as a heading row above it.
 */
describe('heading rows', () => {
  const heading = sectionDraft('BILL NO 3 PAGE 15/4');

  it('is a heading draft, with nothing to fix and nothing to add up', () => {
    expect(isSectionDraft(heading)).toBe(true);
    expect(isSectionDraft(emptyDraft())).toBe(false);
    expect(lineErrors(heading)).toEqual({});
    const priced = { ...emptyDraft(), product_id: 'p1', quantity: '2', unit_price: '10.00' };
    expect(totalFromDrafts([priced, heading])).toBe(totalFromDrafts([priced]));
  });

  it('sends the heading alone', () => {
    expect(toBody(heading, null)).toEqual({ is_section: true, band_label: 'BILL NO 3 PAGE 15/4' });
  });

  it('reads a stored heading row back as a heading draft', () => {
    const stored = {
      id: 's1',
      version_id: 'v1',
      is_section: true,
      band_label: 'OPTION',
      quantity: '0.00',
      unit_price: '0.00',
      line_total: '0.00',
    } as unknown as QuotationLine;
    const draft = serverToDraft(stored);
    expect(isSectionDraft(draft)).toBe(true);
    expect(draft.band_label).toBe('OPTION');
  });

  it('splits a heading carried by a product line into a heading row above it', () => {
    const carried: StagedQuotationLine = {
      id: 'l1',
      key: 'l1',
      line: null,
      draft: { ...emptyDraft(), product_id: 'p1', band_label: 'PAGE 1' },
      removed: false,
    };
    const plain: StagedQuotationLine = {
      id: 'l2',
      key: 'l2',
      line: null,
      draft: { ...emptyDraft(), product_id: 'p2' },
      removed: false,
    };
    const split = splitCarriedHeadings([carried, plain]);
    expect(split.map((row) => row.key)).toEqual(['heading:l1', 'l1', 'l2']);
    expect(split[0]).toMatchObject({ id: null, line: null, removed: false });
    expect(isSectionDraft(split[0].draft)).toBe(true);
    expect(split[0].draft.band_label).toBe('PAGE 1');
    expect(split[1].draft.band_label).toBe('');
    expect(split[2]).toBe(plain);
    // Idempotent: a set already split is returned as it is.
    expect(splitCarriedHeadings(split).map((row) => row.key)).toEqual(['heading:l1', 'l1', 'l2']);
  });
});
