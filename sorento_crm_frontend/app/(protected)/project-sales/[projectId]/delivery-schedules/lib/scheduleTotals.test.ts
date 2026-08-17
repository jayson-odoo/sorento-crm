/**
 * P6 - the arithmetic the whole screen rests on.
 *
 * These are not incidental helpers: the feature IS the comparison of three numbers, so a
 * totalling bug shows up as a column that reads "reconciled" while the document disagrees.
 * The float-precision cases are pinned deliberately, because `Number('0.1') + Number('0.2')`
 * would pass a lax assertion and fail an exact one.
 */
import { describe, expect, it } from 'vitest';
import {
  buildColumnStates,
  compareQty,
  groupPhasesByArea,
  isQty,
  normaliseQty,
  phaseRowLabel,
  signedQty,
  subtractQty,
  sumQty,
} from './scheduleTotals';

const product = (over: Partial<Parameters<typeof buildColumnStates>[0][number]> = {}) => ({
  product_id: 'p1',
  product_code: 'SRTWC8613-RL',
  product_name: 'One-Piece WC',
  customer_code_raw: 'BUI-HB-SRTWC8613-RL',
  resolution_source: 'code' as const,
  reported_total: '927',
  po_qty: '927',
  ...over,
});

const phases = [
  { id: 'ph1', area_group: 'TOWER', sequence: 1, label: 'Level 2 & 7' },
  { id: 'ph2', area_group: 'TOWER', sequence: 2, label: 'Level 8 & 10' },
];

describe('quantity arithmetic', () => {
  it('sums exactly where floats would not', () => {
    expect(sumQty(['0.1', '0.2'])).toBe('0.3');
    expect(sumQty(['1.005', '2.005'])).toBe('3.01');
  });

  it('treats a blank as an absence, not a zero', () => {
    expect(sumQty(['72', '', null, undefined, '72'])).toBe('144');
    expect(sumQty([])).toBe('0');
  });

  it('sums a real column off the schedule', () => {
    const tower = ['135', ...Array.from({ length: 11 }, () => '72')];
    expect(sumQty(tower)).toBe('927');
  });

  it('compares across differing scales', () => {
    expect(compareQty('927', '927.00')).toBe(0);
    expect(compareQty('927', '894')).toBe(1);
    expect(compareQty('8', '16')).toBe(-1);
    expect(compareQty('8', 'not a number')).toBeNull();
  });

  it('normalises transcribed separators and trailing zeros', () => {
    expect(normaliseQty('1,826')).toBe('1826');
    expect(normaliseQty(' 72.00 ')).toBe('72');
    expect(normaliseQty('.5')).toBe('0.5');
    expect(normaliseQty('')).toBeNull();
    expect(isQty('16 sets')).toBe(false);
  });

  it('reports a shortfall as a signed difference', () => {
    expect(subtractQty('8', '16')).toBe('-8');
    expect(signedQty('-8')).toBe('-8');
    expect(signedQty('8')).toBe('+8');
  });
});

describe('buildColumnStates', () => {
  it('reconciles a column whose three numbers agree', () => {
    const [column] = buildColumnStates(
      [product()],
      phases,
      [
        { phase_id: 'ph1', product_id: 'p1', qty: '855' },
        { phase_id: 'ph2', product_id: 'p1', qty: '72' },
      ],
    );

    expect(column.ourTotal).toBe('927');
    expect(column.reportedTotal).toBe('927');
    expect(column.poQty).toBe('927');
    expect(column.reconciled).toBe(true);
    expect(column.blockers).toHaveLength(0);
  });

  it('names both disagreements with their numbers', () => {
    const [column] = buildColumnStates(
      [product({ reported_total: '16', po_qty: '16' })],
      phases,
      [{ phase_id: 'ph1', product_id: 'p1', qty: '8' }],
    );

    expect(column.reconciled).toBe(false);
    expect(column.blockers.map((blocker) => blocker.code)).toEqual([
      'po_mismatch',
      'reported_mismatch',
    ]);
    // The numbers, the size of the gap in words rather than as a sign to decode, and what
    // to do about it.
    expect(column.blockers[0].detail).toBe(
      'The schedule asks for 8 and the PO orders 16, 8 short. ' +
        'Correct a phase quantity, or amend the PO.',
    );
    expect(column.blockers[1].detail).toBe(
      "The phases add up to 8 but the schedule's own TOTAL QTY row says 16. " +
        'One of the two was misread, so check the cells against the paper.',
    );
  });

  it('flips to reconciled on an edit, without waiting for the server', () => {
    const drafts = new Map([['ph1|p1', '16']]);
    const [column] = buildColumnStates(
      [product({ reported_total: '16', po_qty: '16' })],
      phases,
      [{ phase_id: 'ph1', product_id: 'p1', qty: '8' }],
      drafts,
    );

    expect(column.ourTotal).toBe('16');
    expect(column.reconciled).toBe(true);
  });

  it('blocks a column with no product, and one the PO never ordered', () => {
    const [column] = buildColumnStates(
      [
        product({
          product_id: null,
          product_code: null,
          po_qty: null,
          reported_total: '927',
          customer_code_raw: 'BUI-HB-SRTWB7055',
        }),
      ],
      phases,
      [{ phase_id: 'ph1', product_id: null, product_index: 0, qty: '927' }],
    );

    expect(column.key).toBe('#0');
    expect(column.ourTotal).toBe('927');
    expect(column.blockers.map((blocker) => blocker.code)).toEqual([
      'needs_product',
      'not_on_po',
    ]);
    // Both sentences end in the thing to do next, which is what a reviewer seeing this
    // screen for the first time asked for out loud.
    expect(column.blockers[0].detail).toBe(
      'BUI-HB-SRTWB7055 is not matched to a product. Pick the product this column means.',
    );
    expect(column.blockers[1].detail).toBe(
      'The PO version does not order this item, but the schedule asks for 927. ' +
        'Check the column is the right product, or amend the PO.',
    );
  });

  it('marks a column a remembered customer code resolved by itself', () => {
    const [column] = buildColumnStates(
      [product({ resolution_source: 'map' })],
      phases,
      [{ phase_id: 'ph1', product_id: 'p1', qty: '927' }],
    );
    expect(column.fromRememberedMap).toBe(true);
  });
});

describe('phase grouping', () => {
  it('keeps areas in document order and orders rows by sequence', () => {
    const groups = groupPhasesByArea([
      { area_group: 'TOWER', sequence: 2, label: 'Level 8 & 10' },
      { area_group: 'COMMON AREA', sequence: 1, label: null },
      { area_group: 'TOWER', sequence: 1, label: 'Level 2 & 7' },
    ]);

    expect(groups.map((group) => group.area)).toEqual(['TOWER', 'COMMON AREA']);
    expect(groups[0].phases.map((phase) => phase.sequence)).toEqual([1, 2]);
  });

  it('names an unlabeled row by its sequence, because COMMON AREA rows have no label', () => {
    expect(phaseRowLabel({ label: null, sequence: 3 })).toBe('Phase 3');
    expect(phaseRowLabel({ label: '  ', sequence: 3 })).toBe('Phase 3');
    expect(phaseRowLabel({ label: 'Level 2 & 7', sequence: 1 })).toBe('Level 2 & 7');
  });
});
