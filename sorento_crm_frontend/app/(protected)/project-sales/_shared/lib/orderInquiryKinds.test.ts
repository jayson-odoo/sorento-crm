/**
 * Purchasing's three-kind vocabulary (section 3.I2, AC-I11 to AC-I14): Use SPO, Use PO,
 * Buy - and the arithmetic that keeps the strip, the bar and the "Linked to" column
 * unable to disagree, because every one of them is built off `links[]` here.
 */
import { describe, expect, it } from 'vitest';
import {
  KIND_ORDER,
  facetSegments,
  fullyLinked,
  kindText,
  kindTotals,
  rowCarriesKind,
  segmentsOfRow,
  segmentsOfRows,
} from './orderInquiryKinds';
import type { OrderInquiryKindRow } from './orderInquiryKinds';
import type { OrderInquiryLink } from '../types/orderInquiry.types';

function link(over: Partial<OrderInquiryLink> = {}): OrderInquiryLink {
  return {
    id: 'link-1',
    kind: 'po',
    document: '202601-S0044',
    qty: '5',
    ...over,
  };
}

function row(over: Partial<OrderInquiryKindRow> = {}): OrderInquiryKindRow {
  return { qty: '10', links: [], state: 'raised', ...over };
}

describe('segmentsOfRow', () => {
  it('is one solid rose segment for a wholly unlinked row', () => {
    const segments = segmentsOfRow(row({ qty: '85', links: [] }));

    expect(segments).toEqual([{ kind: 'buy', qty: '85' }]);
  });

  it('is one solid segment for a row wholly linked to a purchase order', () => {
    const segments = segmentsOfRow(
      row({ qty: '35', links: [link({ kind: 'po', qty: '35' })] }),
    );

    expect(segments).toEqual([{ kind: 'po', qty: '35' }]);
  });

  it('is one solid violet segment for a row wholly linked to an SPO allocation', () => {
    const segments = segmentsOfRow(
      row({ qty: '10', links: [link({ kind: 'spo', qty: '10' })] }),
    );

    expect(segments).toEqual([{ kind: 'spo', qty: '10' }]);
  });

  it('splits a partly linked row: PO 5 off a quantity of 8 leaves a Buy of 3', () => {
    const segments = segmentsOfRow(
      row({ qty: '8', links: [link({ kind: 'po', qty: '5' })] }),
    );

    expect(segments).toEqual([
      { kind: 'po', qty: '5' },
      { kind: 'buy', qty: '3' },
    ]);
  });

  it('carries both a spo and a po segment when an ORDER BACK row sits on both', () => {
    const segments = segmentsOfRow(
      row({
        qty: '10',
        links: [link({ kind: 'spo', qty: '4' }), link({ kind: 'po', qty: '6' })],
      }),
    );

    expect(segments).toEqual([
      { kind: 'spo', qty: '4' },
      { kind: 'po', qty: '6' },
    ]);
  });
});

describe('kindTotals', () => {
  it('sums every kind across a mixed set of rows, always all three, in reading order', () => {
    const totals = kindTotals([
      row({ qty: '8', links: [link({ kind: 'po', qty: '5' })] }), // po 5, buy 3
      row({ qty: '10', links: [link({ kind: 'spo', qty: '10' })] }), // spo 10
      row({ qty: '20', links: [] }), // buy 20
    ]);

    expect(totals.map((segment) => segment.kind)).toEqual(KIND_ORDER);
    expect(totals).toEqual([
      { kind: 'spo', qty: '10' },
      { kind: 'po', qty: '5' },
      { kind: 'buy', qty: '23' },
    ]);
  });

  it('carries all three kinds even when every one of them is zero', () => {
    expect(kindTotals([]).map((segment) => segment.kind)).toEqual(['spo', 'po', 'buy']);
    expect(kindTotals([]).every((segment) => segment.qty === '0')).toBe(true);
  });

  it('a cancelled row contributes nothing at all, however large its own quantity', () => {
    const totals = kindTotals([
      row({ qty: '20', links: [], state: 'raised' }),
      row({ qty: '999', links: [link({ kind: 'po', qty: '999' })], state: 'cancelled' }),
    ]);

    expect(totals).toEqual([
      { kind: 'spo', qty: '0' },
      { kind: 'po', qty: '0' },
      { kind: 'buy', qty: '20' },
    ]);
  });

  it('never goes negative when a row is linked beyond its own quantity', () => {
    const totals = kindTotals([row({ qty: '5', links: [link({ kind: 'po', qty: '9' })] })]);

    expect(totals.find((segment) => segment.kind === 'buy')?.qty).toBe('0');
  });
});

describe('rowCarriesKind', () => {
  it('answers true for BOTH kinds a split row carries', () => {
    const split = row({ qty: '8', links: [link({ kind: 'po', qty: '5' })] });

    expect(rowCarriesKind(split, 'po')).toBe(true);
    expect(rowCarriesKind(split, 'buy')).toBe(true);
    expect(rowCarriesKind(split, 'spo')).toBe(false);
  });

  it('answers false for every kind on a cancelled row', () => {
    const cancelled = row({
      qty: '8',
      links: [link({ kind: 'po', qty: '5' })],
      state: 'cancelled',
    });

    expect(rowCarriesKind(cancelled, 'po')).toBe(false);
    expect(rowCarriesKind(cancelled, 'buy')).toBe(false);
  });
});

describe('kindText', () => {
  it('names one kind alone as "Buy 85"', () => {
    expect(kindText(segmentsOfRow(row({ qty: '85', links: [] })))).toBe('Buy 85');
  });

  it('names a split row as "PO 5 · Buy 3"', () => {
    const text = kindText(
      segmentsOfRow(row({ qty: '8', links: [link({ kind: 'po', qty: '5' })] })),
    );

    expect(text).toBe('PO 5 · Buy 3');
  });

  it('is empty when there is nothing to say', () => {
    expect(kindText([])).toBe('');
  });
});

describe('fullyLinked', () => {
  it('is true when every row is wholly on a document', () => {
    expect(
      fullyLinked([
        row({ qty: '5', links: [link({ kind: 'po', qty: '5' })] }),
        row({ qty: '3', links: [link({ kind: 'spo', qty: '3' })] }),
      ]),
    ).toBe(true);
  });

  it('is false while any row still carries a Buy remainder', () => {
    expect(
      fullyLinked([row({ qty: '8', links: [link({ kind: 'po', qty: '5' })] })]),
    ).toBe(false);
  });

  it('is true for an empty selection - there is no unlinked remainder to find', () => {
    expect(fullyLinked([])).toBe(true);
  });
});

describe('facetSegments', () => {
  it('reads three zeros when the summary has not answered yet', () => {
    expect(facetSegments(undefined)).toEqual([
      { kind: 'spo', qty: '0' },
      { kind: 'po', qty: '0' },
      { kind: 'buy', qty: '0' },
    ]);
    expect(facetSegments(null)).toEqual([
      { kind: 'spo', qty: '0' },
      { kind: 'po', qty: '0' },
      { kind: 'buy', qty: '0' },
    ]);
  });

  it('reads the server facet in the same fixed order the cards render', () => {
    expect(facetSegments({ spo: '10', po: '95', buy: '116' })).toEqual([
      { kind: 'spo', qty: '10' },
      { kind: 'po', qty: '95' },
      { kind: 'buy', qty: '116' },
    ]);
  });
});
