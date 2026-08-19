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
  buildCellMetaMap,
  buildColumnStates,
  compareQty,
  dateColumns,
  diffScheduleQuantities,
  groupPhasesByArea,
  isQty,
  normaliseQty,
  phaseRowLabel,
  proposalCadenceLabel,
  schedulePhaseDateMoves,
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

describe('schedulePhaseDateMoves (section 9.1)', () => {
  it('reports a phase whose promoted date differs from this version, with the day delta', () => {
    const moves = schedulePhaseDateMoves([
      {
        id: 'ph1',
        area_group: 'TOWER',
        sequence: 1,
        label: 'Level 2 & 7',
        delivery_date: '2027-01-07',
        promoted_delivery_date: '2026-07-01',
      },
    ]);

    expect(moves).toHaveLength(1);
    expect(moves[0]).toMatchObject({
      phaseId: 'ph1',
      label: 'Level 2 & 7',
      area: 'TOWER',
      from: '2026-07-01',
      to: '2027-01-07',
      deltaDays: 190,
    });
  });

  it('leaves out a phase with no promoted date, or one that did not move', () => {
    const moves = schedulePhaseDateMoves([
      {
        id: 'ph1',
        area_group: 'TOWER',
        sequence: 1,
        label: null,
        delivery_date: '2027-01-07',
        promoted_delivery_date: null,
      },
      {
        id: 'ph2',
        area_group: 'TOWER',
        sequence: 2,
        label: null,
        delivery_date: '2027-01-07',
        promoted_delivery_date: '2027-01-07',
      },
    ]);

    expect(moves).toHaveLength(0);
  });

  it('reads a pulled-in date as a negative delta', () => {
    const moves = schedulePhaseDateMoves([
      {
        id: 'ph1',
        area_group: null,
        sequence: 1,
        label: null,
        delivery_date: '2026-01-01',
        promoted_delivery_date: '2026-01-11',
      },
    ]);

    expect(moves[0].deltaDays).toBe(-10);
  });
});

describe('diffScheduleQuantities (section 9.1)', () => {
  const priorPhases = [{ id: 'prior-ph1', area_group: 'TOWER', sequence: 1, label: 'Level 2 & 7' }];
  const currentPhases = [
    { id: 'cur-ph1', area_group: 'TOWER', sequence: 1, label: 'Level 2 & 7' },
  ];

  it('matches phases by (area_group, sequence) and products by id across two versions', () => {
    const { changes, unchangedCount } = diffScheduleQuantities(
      {
        phases: currentPhases,
        products: [product({ product_id: 'p1' })],
        cells: [{ phase_id: 'cur-ph1', product_id: 'p1', qty: '66' }],
      },
      {
        phases: priorPhases,
        products: [product({ product_id: 'p1' })],
        cells: [{ phase_id: 'prior-ph1', product_id: 'p1', qty: '72' }],
      },
    );

    expect(unchangedCount).toBe(0);
    expect(changes).toEqual([
      {
        phaseId: 'cur-ph1',
        phaseLabel: 'Level 2 & 7',
        area: 'TOWER',
        productLabel: 'SRTWC8613-RL',
        from: '72',
        to: '66',
      },
    ]);
  });

  it('counts a matched cell with the same quantity as unchanged', () => {
    const { changes, unchangedCount } = diffScheduleQuantities(
      {
        phases: currentPhases,
        products: [product({ product_id: 'p1' })],
        cells: [{ phase_id: 'cur-ph1', product_id: 'p1', qty: '72' }],
      },
      {
        phases: priorPhases,
        products: [product({ product_id: 'p1' })],
        cells: [{ phase_id: 'prior-ph1', product_id: 'p1', qty: '72.00' }],
      },
    );

    expect(changes).toHaveLength(0);
    expect(unchangedCount).toBe(1);
  });

  it('falls back to the product code when neither version has resolved the product', () => {
    const { changes } = diffScheduleQuantities(
      {
        phases: currentPhases,
        products: [product({ product_id: null, product_code: 'SRTWB7055' })],
        cells: [{ phase_id: 'cur-ph1', product_id: null, product_index: 0, qty: '20' }],
      },
      {
        phases: priorPhases,
        products: [product({ product_id: null, product_code: 'SRTWB7055' })],
        cells: [{ phase_id: 'prior-ph1', product_id: null, product_index: 0, qty: '10' }],
      },
    );

    expect(changes).toEqual([
      expect.objectContaining({ productLabel: 'SRTWB7055', from: '10', to: '20' }),
    ]);
  });

  it('reports a quantity the prior version had that this one no longer carries', () => {
    const { changes } = diffScheduleQuantities(
      {
        phases: currentPhases,
        products: [product({ product_id: 'p1' })],
        cells: [],
      },
      {
        phases: priorPhases,
        products: [product({ product_id: 'p1' })],
        cells: [{ phase_id: 'prior-ph1', product_id: 'p1', qty: '72' }],
      },
    );

    expect(changes).toEqual([
      expect.objectContaining({ productLabel: 'SRTWC8613-RL', from: '72', to: null }),
    ]);
  });

  it('reports a quantity on a phase+product the prior version never had, as added', () => {
    const { changes } = diffScheduleQuantities(
      {
        phases: currentPhases,
        products: [product({ product_id: 'p1' })],
        cells: [{ phase_id: 'cur-ph1', product_id: 'p1', qty: '72' }],
      },
      {
        phases: [{ id: 'prior-ph9', area_group: 'COMMON AREA', sequence: 9, label: null }],
        products: [product({ product_id: 'p9' })],
        cells: [{ phase_id: 'prior-ph9', product_id: 'p9', qty: '5' }],
      },
    );

    expect(changes).toEqual([
      expect.objectContaining({ productLabel: 'SRTWC8613-RL', from: null, to: '72' }),
    ]);
  });

  it('leaves out a prior quantity whose phase no longer exists on this version at all', () => {
    const { changes } = diffScheduleQuantities(
      {
        phases: currentPhases,
        products: [product({ product_id: 'p1' })],
        cells: [{ phase_id: 'cur-ph1', product_id: 'p1', qty: '72' }],
      },
      {
        phases: [
          ...priorPhases,
          { id: 'prior-ph9', area_group: 'COMMON AREA', sequence: 9, label: null },
        ],
        products: [product({ product_id: 'p1' }), product({ product_id: 'p9' })],
        cells: [
          { phase_id: 'prior-ph1', product_id: 'p1', qty: '72' },
          { phase_id: 'prior-ph9', product_id: 'p9', qty: '5' },
        ],
      },
    );

    // The matched pair is unchanged (silent); the phase COMMON AREA::9 does not exist on
    // this version at all, so nothing honest can be said about its removed quantity.
    expect(changes).toHaveLength(0);
  });
});

describe('buildCellMetaMap (section 9.7a/c)', () => {
  it('keeps a highlight and an override, keyed the same way the qty map is', () => {
    const meta = buildCellMetaMap([
      { phase_id: 'ph1', product_id: 'p1', qty: '927', highlight: '#ffe08a' },
      {
        phase_id: 'ph2',
        product_id: 'p1',
        qty: '66',
        delivery_date_override: '2026-07-23',
      },
    ]);

    expect(meta.get('ph1|p1')).toEqual({ highlight: '#ffe08a', deliveryDateOverride: null });
    expect(meta.get('ph2|p1')).toEqual({
      highlight: null,
      deliveryDateOverride: '2026-07-23',
    });
  });

  it('carries nothing for an ordinary cell, which is most of them', () => {
    const meta = buildCellMetaMap([{ phase_id: 'ph1', product_id: 'p1', qty: '927' }]);
    expect(meta.size).toBe(0);
  });
});

describe('proposalCadenceLabel (section 9.7b)', () => {
  it('names the fortnight cadence when every gap between the highlighted phases agrees', () => {
    expect(
      proposalCadenceLabel([
        { old_date: '2026-07-01' },
        { old_date: '2026-07-15' },
        { old_date: '2026-07-29' },
      ]),
    ).toBe('keeping the fortnight cadence');
  });

  it("falls back to the document's own gaps once they disagree", () => {
    expect(
      proposalCadenceLabel([
        { old_date: '2026-07-01' },
        { old_date: '2026-07-15' },
        { old_date: '2026-08-01' },
      ]),
    ).toBe("keeping the document's own gaps");
  });

  it("says the document's own gaps with fewer than two phases to compare", () => {
    expect(proposalCadenceLabel([{ old_date: '2026-07-01' }])).toBe(
      "keeping the document's own gaps",
    );
  });
});

describe('dateColumns (section 9.8, by-date view)', () => {
  it('leaves an unmoved cell under its own phase date, and never invents an empty column', () => {
    const columns = dateColumns({
      phases: [
        { id: 'ph1', label: 'Level 2 & 7', sequence: 1, delivery_date: '2026-07-01' },
        { id: 'ph2', label: 'Level 8 & 10', sequence: 2, delivery_date: '2026-07-15' },
        // No cell ever lands here - not a phase every product takes.
        { id: 'ph3', label: 'Level 11', sequence: 3, delivery_date: '2026-08-01' },
      ],
      cells: [{ phase_id: 'ph1', product_id: 'p1', qty: '855' }],
    });

    expect(columns).toEqual([
      {
        date: '2026-07-01',
        phaseLabels: ['Level 2 & 7'],
        cells: new Map([['p1', { qty: '855', phaseId: 'ph1', wasDate: undefined }]]),
      },
    ]);
  });

  it('groups two phases sharing a date under one header, in sequence order', () => {
    const columns = dateColumns({
      phases: [
        { id: 'ph2', label: 'Level 8 & 10', sequence: 2, delivery_date: '2026-07-01' },
        { id: 'ph1', label: 'Level 2 & 7', sequence: 1, delivery_date: '2026-07-01' },
      ],
      cells: [
        { phase_id: 'ph1', product_id: 'p1', qty: '135' },
        { phase_id: 'ph2', product_id: 'p2', qty: '48' },
      ],
    });

    expect(columns).toHaveLength(1);
    expect(columns[0].phaseLabels).toEqual(['Level 2 & 7', 'Level 8 & 10']);
  });

  /**
   * The golden shape (section 9.7c, measured on the real R2): SRT382-6's twelve TOWER cells,
   * each accepted onto its own new date, fortnightly from 23/7/2026. The captain's own
   * question (19 Aug) is what this pins - the quantity moves to the new date, it does not
   * stay behind under the old one.
   */
  it('moves an accepted override to its own new date column, was -> now, off the SRT382-6 shape', () => {
    const columns = dateColumns({
      phases: [
        { id: 'ph1', label: 'Level 2 & 7', sequence: 1, delivery_date: '2027-01-07' },
        { id: 'ph2', label: 'Level 8 & 10', sequence: 2, delivery_date: '2027-01-21' },
      ],
      cells: [
        {
          phase_id: 'ph1',
          product_id: 'srt382-6',
          qty: '135',
          delivery_date_override: '2026-07-23',
        },
        {
          phase_id: 'ph2',
          product_id: 'srt382-6',
          qty: '124',
          delivery_date_override: '2026-08-06',
        },
        // A product this note never touched, unmoved, still under its own phase date.
        { phase_id: 'ph1', product_id: 'p1', qty: '927' },
      ],
    });

    expect(columns.map((column) => column.date)).toEqual([
      '2026-07-23',
      '2026-08-06',
      '2027-01-07',
    ]);

    const moved = columns[0];
    expect(moved.phaseLabels).toEqual(['Level 2 & 7']);
    expect(moved.cells.get('srt382-6')).toEqual({
      qty: '135',
      phaseId: 'ph1',
      wasDate: '2027-01-07',
    });

    // The 07/01/2027 column no longer carries SRT382-6's 135 at all - it moved, not copied.
    const original = columns[2];
    expect(original.cells.has('srt382-6')).toBe(false);
    expect(original.cells.get('p1')).toEqual({ qty: '927', phaseId: 'ph1', wasDate: undefined });
  });

  it('falls back to product_index when the column has no resolved product', () => {
    const columns = dateColumns({
      phases: [{ id: 'ph1', label: null, sequence: 1, delivery_date: '2026-07-01' }],
      cells: [{ phase_id: 'ph1', product_id: null, product_index: 2, qty: '927' }],
    });

    expect(columns[0].cells.has('#2')).toBe(true);
  });

  it('drops a cell whose phase cannot be found at all', () => {
    const columns = dateColumns({
      phases: [{ id: 'ph1', label: null, sequence: 1, delivery_date: '2026-07-01' }],
      cells: [{ phase_id: 'ghost', product_id: 'p1', qty: '10' }],
    });

    expect(columns).toHaveLength(0);
  });
});
