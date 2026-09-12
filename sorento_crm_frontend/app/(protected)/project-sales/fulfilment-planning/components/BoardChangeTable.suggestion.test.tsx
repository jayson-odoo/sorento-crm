/**
 * What the board prints for a changed line, scenario by scenario (AC-C1 to AC-C8).
 *
 * Driven off the SAME fixture the screen is built against
 * (`_shared/__mocks__/planningChanges.ts`, one row per scenario S1 to S12 of
 * `documentation/plans/scm/mockups/so-change-management-grill-v4.html`) and through the SAME
 * `annotationOf` the board uses, so a test cannot pass against a row the screen never saw.
 *
 * The assertion is on the rendered SENTENCES, not on a shape: the label is composed
 * server-side and printed verbatim, so what is being pinned here is exactly that the board
 * adds nothing to it and drops nothing from it.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { BoardChangeTable } from './BoardChangeTable';
import { annotationOf } from '../../_shared/lib/boardChangeAnnotations';
import { MOCK_PLANNING_CHANGE_BATCH_PENDING } from '../../_shared/__mocks__/planningChanges';
import type { PlanningChangeRow } from '../../_shared/types/planningChange.types';

/** The scenario row and the sales order it sits on, by row id. */
function rowOf(id: string): { row: PlanningChangeRow; soNumber: string } {
  for (const order of MOCK_PLANNING_CHANGE_BATCH_PENDING.orders) {
    for (const row of order.rows) {
      if (row.id === id) return { row, soNumber: order.so_number };
    }
  }
  throw new Error(`No scenario row ${id} in the pending batch fixture`);
}

/** Render one scenario row exactly as a board cell does, and read its suggestion lines. */
function linesOf(id: string, compact = false): string[] {
  const { row, soNumber } = rowOf(id);
  render(<BoardChangeTable annotation={annotationOf(row, soNumber)} compact={compact} />);
  return screen
    .getAllByTestId('board-change-suggestion-line')
    .map((line) => line.textContent ?? '');
}

describe('the composed suggestion on the board', () => {
  it('S2: reduces the raised row, keeps what is still needed on PO-A and re-deals the rest', () => {
    expect(linesOf('pcr-s2')).toEqual([
      'Reduce Buy 100 to 0',
      'Keep PO-A 100 of 134',
      'Reallocate PO-A 34 to SO420103 ORDER 50',
    ]);
  });

  it('S3: moves part of the reserve to the row that needs it earlier, frees the rest, re-sources the unit', () => {
    expect(linesOf('pcr-s3')).toEqual([
      'Reallocate 80 at BRW-IB to SO420100 ORDER 80',
      'Release 54, free at BRW-IB',
      'SPO 134 on SPO-77 for 20 Nov',
    ]);
  });

  it('S9: a small delay inside the window is Keep, and nothing else', () => {
    expect(linesOf('pcr-s9')).toEqual(['Keep 134']);
  });

  it('S10: a delay past the window releases the reserve and buys again for the new date', () => {
    expect(linesOf('pcr-s10')).toEqual([
      'Release 134, free at BRW-IB',
      'Buy 134 for 15 Mar',
    ]);
  });

  it('S12: a unit nobody can cover in time is kept, and said to be late', () => {
    const { row, soNumber } = rowOf('pcr-s12');
    render(<BoardChangeTable annotation={annotationOf(row, soNumber)} />);
    expect(
      screen.getAllByTestId('board-change-suggestion-line').map((line) => line.textContent),
    ).toEqual(['Keep PO-A 134']);
    expect(screen.getByTestId('board-change-late-pcr-s12').textContent).toBe('Late by 3 days');
    expect(screen.queryByTestId('board-change-short-pcr-s12')).toBeNull();
  });

  it('S11: what the pool can cover now is stated, and the rest is shown short', () => {
    expect(linesOf('pcr-s11')).toEqual(['Reduce Buy 134 to 44', 'Pool share 90 at BRW']);
    expect(screen.getByTestId('board-change-short-pcr-s11').textContent).toBe('Short 44');
    expect(screen.queryByTestId('board-change-late-pcr-s11')).toBeNull();
  });

  it('S7: a product swap is ONE row - the old product named, the new one sourced', () => {
    const { row, soNumber } = rowOf('pcr-s7');
    render(<BoardChangeTable annotation={annotationOf(row, soNumber)} />);
    expect(screen.getByTestId('board-change-product-pcr-s7').textContent).toBe(
      'Product changed, was B2155-NL-BLUE',
    );
    expect(
      screen.getAllByTestId('board-change-suggestion-line').map((line) => line.textContent),
    ).toEqual(['Release 134, free at BRW-IB', 'Buy B2155-NL-WHITE 134 for 4 Sep']);
  });

  it('S5: a cancelled line reads Cancelled in Now and still says where its hold went', () => {
    const { row, soNumber } = rowOf('pcr-s5');
    render(<BoardChangeTable annotation={annotationOf(row, soNumber)} />);
    expect(screen.getByTestId('change-now-qty').textContent).toBe('Cancelled');
    expect(screen.getByTestId('change-now-decision').textContent).toBe('Cancelled');
    expect(
      screen.getAllByTestId('board-change-suggestion-line').map((line) => line.textContent),
    ).toEqual(['Release 50, free at BRW-IB', 'Reallocate PO-B 84 to dealer pool']);
  });

  it('S1: a top-up joins the held Buy on the same row, and says what it was', () => {
    expect(linesOf('pcr-s1')).toEqual(['Buy 234 (was 134)']);
  });

  it('S8: one date-and-quantity edit yields one row and one suggestion', () => {
    const { row, soNumber } = rowOf('pcr-s8');
    render(<BoardChangeTable annotation={annotationOf(row, soNumber)} />);
    // Both halves of the edit are on the same row: no tie-break picks a winner (AC-C8).
    expect(screen.getByTestId('change-now-qty').textContent).toBe('100');
    expect(
      screen.getAllByTestId('board-change-suggestion-line').map((line) => line.textContent),
    ).toEqual(['Reduce reserve 134 to 100', 'Release 34, free at BRW-IB']);
  });

  it('prints every line at 375px compact, inside the board cell, with none dropped', () => {
    // The phone width the cell is drawn at (design mandate: usable at 375px). The suggestion
    // is the row's whole point, so it is never the thing that gets cut to fit.
    expect(linesOf('pcr-s2', true)).toHaveLength(3);
    expect(screen.getByTestId('board-change-pcr-s2').className).toMatch(/text-\[10px\]/);
  });

  it('says nothing at all when the engine composed no suggestion', () => {
    const { row, soNumber } = rowOf('pcr-s6');
    render(
      <BoardChangeTable annotation={annotationOf({ ...row, suggestion: null }, soNumber)} />,
    );
    expect(screen.queryByTestId('board-change-suggestion-pcr-s6')).toBeNull();
    expect(screen.queryByTestId('board-change-late-pcr-s6')).toBeNull();
    expect(screen.queryByTestId('board-change-short-pcr-s6')).toBeNull();
  });
});
