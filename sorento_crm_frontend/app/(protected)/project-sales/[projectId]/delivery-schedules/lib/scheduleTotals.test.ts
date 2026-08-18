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

  it('blocks on the sheet disagreeing with itself, and names the numbers', () => {
    const [column] = buildColumnStates(
      [product({ reported_total: '16', po_qty: '16' })],
      phases,
      [{ phase_id: 'ph1', product_id: 'p1', qty: '8' }],
    );

    expect(column.reconciled).toBe(false);
    // ONE blocker: the phases not adding up to the sheet's own TOTAL QTY. Asking for 8 of
    // the 16 ordered is a partial schedule, which the server treats as a warning, so the
    // screen must not report it as a second thing to fix.
    expect(column.blockers.map((blocker) => blocker.code)).toEqual([
      'reported_mismatch',
    ]);
    expect(column.blockers[0].detail).toBe(
      "The phases add up to 8 but the schedule's own TOTAL QTY row says 16. " +
        'One of the two was misread, so check the cells against the paper.',
    );
  });

  /**
   * A partial schedule is the normal state of a live project.
   *
   * The customer schedules part of what they ordered now and the rest on a later document,
   * and the server says so too (`_verdict`: a shortfall is `(reconciled, None, warning)`).
   * Blocking on it demanded a correction to something that was never wrong, and disagreed
   * with the backend, which confirms the same schedule happily.
   */
  it('reads a shortfall against the PO as a warning, not a blocker', () => {
    const [column] = buildColumnStates(
      [product({ reported_total: null, po_qty: '927' })],
      phases,
      [{ phase_id: 'ph1', product_id: 'p1', qty: '855' }],
    );

    expect(column.reconciled).toBe(true);
    expect(column.blockers).toHaveLength(0);
    expect(column.warning).toBe(
      'The schedule asks for 855 of the 927 on the purchase order; the remaining 72 is ' +
        'expected on a later schedule.',
    );
  });

  it('still blocks a column asking for MORE than the PO ordered', () => {
    const [column] = buildColumnStates(
      [product({ reported_total: null, po_qty: '900' })],
      phases,
      [{ phase_id: 'ph1', product_id: 'p1', qty: '927' }],
    );

    expect(column.reconciled).toBe(false);
    expect(column.blockers.map((blocker) => blocker.code)).toEqual(['po_mismatch']);
    expect(column.blockers[0].detail).toBe(
      'The schedule asks for 927 and the PO orders 900, 27 over. ' +
        'Correct a phase quantity, or amend the PO.',
    );
    expect(column.warning).toBeNull();
  });

  it("prefers the server's own warning on a column nobody has edited", () => {
    const [column] = buildColumnStates(
      [
        product({
          reported_total: null,
          po_qty: '927',
          warning: 'Matched by description, not by code.',
        }),
      ],
      phases,
      [{ phase_id: 'ph1', product_id: 'p1', qty: '927' }],
    );

    expect(column.reconciled).toBe(true);
    expect(column.warning).toBe('Matched by description, not by code.');
  });

  it('drops a stale server warning as soon as the column is being typed into', () => {
    const [column] = buildColumnStates(
      [
        product({
          reported_total: null,
          po_qty: '927',
          warning: 'The schedule asks for 855 of the 927 on the purchase order.',
        }),
      ],
      phases,
      [{ phase_id: 'ph1', product_id: 'p1', qty: '855' }],
      new Map([['ph1|p1', '927']]),
    );

    // The sentence describes the SAVED numbers; on screen the column now adds to 927.
    expect(column.ourTotal).toBe('927');
    expect(column.warning).toBeNull();
  });

  /**
   * Measured on the live stack: every one of HQ/26/01/121's 21 blocked columns came back
   * carrying a refusal written before a shortfall became a warning, because verdicts are
   * STORED with the version. Trusting it put the blocker straight back.
   */
  it('ignores a stored server refusal that is only the shortfall it already explains', () => {
    const [column] = buildColumnStates(
      [
        product({
          reported_total: null,
          po_qty: '1777',
          reconciled: false,
          reason: 'the column adds up to 53, the purchase order says 1777',
        }),
      ],
      phases,
      [{ phase_id: 'ph1', product_id: 'p1', qty: '53' }],
    );

    expect(column.blockers).toHaveLength(0);
    expect(column.reconciled).toBe(true);
    expect(column.warning).toContain('the remaining 1724 is expected on a later schedule');
  });

  it("carries a server refusal this file cannot derive, rather than reading as clean", () => {
    const [column] = buildColumnStates(
      [
        product({
          reported_total: null,
          po_qty: '927',
          reconciled: false,
          reason: 'the PO line was cancelled after this schedule was drawn',
        }),
      ],
      phases,
      [{ phase_id: 'ph1', product_id: 'p1', qty: '927' }],
    );

    // Being laxer than the server is the bad direction: the screen would invite a confirm
    // the server then rejects.
    expect(column.reconciled).toBe(false);
    expect(column.blockers.map((blocker) => blocker.code)).toEqual(['server']);
    expect(column.blockers[0].detail).toBe(
      'the PO line was cancelled after this schedule was drawn',
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
