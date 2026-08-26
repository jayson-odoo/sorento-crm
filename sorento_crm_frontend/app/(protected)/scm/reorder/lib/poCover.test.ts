import { describe, expect, it } from 'vitest';
import {
  describePoBook,
  isProjectOnlyLine,
  poOffset,
  type PoReceipt,
} from './poCover';

/**
 * S15: "if there is outstanding PO already then why should i buy" - the PO book offsets
 * the buy SUGGESTION (never the engine's netting), and the receipts travel with it.
 */

const receipt = (over: Partial<PoReceipt> = {}): PoReceipt => ({
  po_number: 'PO-2026/07-0002',
  status: 'active',
  expected_date: '2026-08-10',
  remaining: 504,
  ...over,
});

describe('poOffset', () => {
  it('a PO that covers the whole shortage leaves nothing to buy', () => {
    expect(poOffset(200, 504)).toEqual({ usePo: 200, buy: 0 });
  });

  it('a partial PO leaves the remainder as the buy', () => {
    expect(poOffset(200, 120)).toEqual({ usePo: 120, buy: 80 });
  });

  it('no PO leaves the buy untouched', () => {
    expect(poOffset(200, 0)).toEqual({ usePo: 0, buy: 200 });
  });

  it('never applies more PO than the shortage needs', () => {
    expect(poOffset(0, 504)).toEqual({ usePo: 0, buy: 0 });
  });
});

describe('describePoBook', () => {
  it('names each order with its quantity and promise date', () => {
    expect(describePoBook([receipt()])).toEqual([
      '504 still to come on PO-2026/07-0002, expected 2026-08-10.',
    ]);
  });

  it('an order with no promise date says so rather than inventing one', () => {
    expect(describePoBook([receipt({ expected_date: null })])).toEqual([
      '504 still to come on PO-2026/07-0002, no promised date.',
    ]);
  });
});

describe('isProjectOnlyLine', () => {
  /**
   * P8: a project row's purchase order is consumed by the Order Inquiry's own links, so
   * offering it on the plan as well nets the same units twice. ALL project is the test,
   * not "any project" - a mixed cell has a retail need that nothing else nets against a PO.
   */
  const line = (project: number | null, retail: number | null) =>
    ({ rec: { project_committed: project, retail_committed: retail } }) as Parameters<
      typeof isProjectOnlyLine
    >[0];

  it('is a project row when every unit of its demand is project', () => {
    expect(isProjectOnlyLine(line(9857, 0))).toBe(true);
  });

  it('is not one when it carries any retail demand at all', () => {
    expect(isProjectOnlyLine(line(9857, 5))).toBe(false);
  });

  it('is not one when it carries no demand at all - a level-driven row still may use a PO', () => {
    expect(isProjectOnlyLine(line(0, 0))).toBe(false);
  });

  it('reads a legacy row that states neither figure as not-project, never as project', () => {
    expect(isProjectOnlyLine(line(null, null))).toBe(false);
  });
});
