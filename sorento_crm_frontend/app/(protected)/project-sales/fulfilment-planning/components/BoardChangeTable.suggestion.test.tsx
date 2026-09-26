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
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { BoardChangeTable } from './BoardChangeTable';
import { annotationOf } from '../../_shared/lib/boardChangeAnnotations';
import type { BoardChangeAnnotation } from '../../_shared/lib/boardChangeAnnotations';
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

/**
 * Owner feedback, 13 September 2026 (AC-C9/AC-C10): the suggestion no longer sits in the
 * board cell itself - it is behind the hazard icon's lightbox. Render the row, click its
 * icon, and read from inside `board-change-dialog`, exactly as a planner would.
 */
function openDialog(id: string, compact = false): HTMLElement {
  const { row, soNumber } = rowOf(id);
  render(<BoardChangeTable annotation={annotationOf(row, soNumber)} compact={compact} />);
  fireEvent.click(screen.getByTestId(`board-change-icon-${row.id}`));
  return screen.getByTestId('board-change-dialog');
}

/** Render one scenario row, open its lightbox, and read its suggestion lines. */
function linesOf(id: string, compact = false): string[] {
  const dialog = openDialog(id, compact);
  return within(dialog)
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
    // Review round C6: lateness is stated ONCE, as the fact/badge - the label itself
    // stays plain ("Keep 134"), never duplicating "late by N days" inside the sentence.
    const dialog = openDialog('pcr-s12');
    const lines = within(dialog).getAllByTestId('board-change-suggestion-line');
    expect(lines.map((line) => line.textContent)).toEqual(['Keep 134']);
    // `getByTestId` itself throws on more than one match, so this also pins "exactly once".
    expect(within(dialog).getByTestId('board-change-late-pcr-s12').textContent).toBe(
      'Late by 3 days',
    );
    expect(within(dialog).queryByTestId('board-change-short-pcr-s12')).toBeNull();
  });

  it('S11: what the pool can cover now is stated, and the rest is shown short', () => {
    // The held Buy IS the shortfall line (rule 8: "the remainder stays a Buy"), so it is
    // one component saying both what is left and that it cannot land in time. Pool share
    // first, the shortfall last, and the shortfall names what it was bought as.
    expect(linesOf('pcr-s11')).toEqual([
      'Pool share 90 at BRW',
      'Short 44 by 22 Aug (was Buy 134)',
    ]);
    // AC-C11: no separate "Short 44" line any more - the suggestion's own label above is
    // the only place the shortfall is said.
    expect(screen.queryByTestId('board-change-short-pcr-s11')).not.toBeInTheDocument();
    expect(
      within(screen.getByTestId('board-change-dialog')).queryByTestId(
        'board-change-late-pcr-s11',
      ),
    ).toBeNull();
  });

  it('S7: a product swap is ONE row - the old product named, the new one sourced', () => {
    const dialog = openDialog('pcr-s7');
    expect(within(dialog).getByTestId('board-change-product-pcr-s7').textContent).toBe(
      'Product changed, was B2155-NL-BLUE',
    );
    expect(
      within(dialog)
        .getAllByTestId('board-change-suggestion-line')
        .map((line) => line.textContent),
      // Review round C4/C5: which product each half is about is now ALSO in the label
      // itself, not only `item_code` on the component - the released half names the OLD
      // product, the sourced half the NEW one.
    ).toEqual([
      'Release 134 B2155-NL-BLUE, free at BRW-IB',
      'Buy 134 B2155-NL-WHITE for 4 Sep',
    ]);
  });

  it('S5: a cancelled line reads Cancelled once and still says where its hold went', () => {
    const dialog = openDialog('pcr-s5');
    // Was the `change-now-qty`/`change-now-decision` table-cell check. The coder's own
    // follow-up (ffeec9576): a cancelled line is a STATEMENT, not three fields each moving
    // to the same place, so the lightbox prints "Cancelled" once - the quantities that
    // moved live in the suggestion lines beneath it instead.
    expect(within(dialog).getByText('Cancelled')).toBeInTheDocument();
    expect(within(dialog).queryByText(/^Qty /)).not.toBeInTheDocument();
    expect(within(dialog).queryByText(/^Date /)).not.toBeInTheDocument();
    expect(within(dialog).queryByText(/^Decision /)).not.toBeInTheDocument();
    expect(
      within(dialog)
        .getAllByTestId('board-change-suggestion-line')
        .map((line) => line.textContent),
      // Dealer hot-selling wins for the reserve as well as for the placed quantity.
    ).toEqual(['Release 50 to dealer pool', 'Reallocate PO-B 84 to dealer pool']);
  });

  it('S1: a top-up joins the held Buy on the same row, and says what it was', () => {
    expect(linesOf('pcr-s1')).toEqual(['Buy 234 (was 134)']);
  });

  it('S8: one date-and-quantity edit yields one Was/Now table and one suggestion (AC-D1)', () => {
    // Both halves of the edit are on the same row: no tie-break picks a winner (AC-C8).
    // AC-D1: the lightbox now prints a `BoardChangeWasNowTable`, not an arrow-line list -
    // RED today, since `BoardChangeSummary` still renders the `fields` list verbatim.
    const dialog = openDialog('pcr-s8');
    const table = within(dialog).getByTestId('board-change-pcr-s8');

    expect(within(table).getByText('Qty')).toBeInTheDocument();
    expect(within(table).getByText('134')).toBeInTheDocument();
    expect(within(table).getByTestId('change-now-qty')).toHaveTextContent('100');
    // AC-D4 (owner ruling, fix round 1): the shared Was/Now table keeps its `dd/mm/yyyy`
    // dates, so the Order Inquiries Qty dialog - which renders the same table - reads
    // exactly as it does today. The year is on both sides either way (AC-RL-01).
    expect(within(table).getByText('04/09/2026')).toBeInTheDocument();
    expect(within(table).getByText('20/11/2026')).toBeInTheDocument();
    // The old arrow-line list is gone from the lightbox entirely.
    expect(
      within(dialog).queryByTestId('board-change-fields-pcr-s8'),
    ).not.toBeInTheDocument();
    expect(
      within(dialog)
        .getAllByTestId('board-change-suggestion-line')
        .map((line) => line.textContent),
      // ONE component: "Reduce reserve 134 to 100" already says what the 34 did.
    ).toEqual(['Reduce reserve 134 to 100']);
  });

  it('prints every line inside the lightbox, with none dropped, whichever icon (compact or not) opened it', () => {
    // The compact icon is the grid cell's own reading (design mandate: usable at 375px);
    // the lightbox it opens is never the thing that gets cut to fit the suggestion into.
    expect(linesOf('pcr-s2', true)).toHaveLength(3);
  });

  it('AC-D6: every rendered suggestion line is words, never a UUID', () => {
    // The engine's own sentence names an SO number, a document number or a warehouse
    // code - never a raw id - for every scenario the fixture carries, S1 through S12.
    const uuidRegex = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
    const ids = Array.from({ length: 12 }, (_, i) => `pcr-s${i + 1}`);
    for (const id of ids) {
      let row: PlanningChangeRow;
      let soNumber: string;
      try {
        ({ row, soNumber } = rowOf(id));
      } catch {
        continue; // a scenario id not present in this fixture build - nothing to check
      }
      const result = render(<BoardChangeTable annotation={annotationOf(row, soNumber)} />);
      fireEvent.click(result.getByTestId(`board-change-icon-${row.id}`));
      const dialog = result.getByTestId('board-change-dialog');
      const lines = within(dialog)
        .queryAllByTestId('board-change-suggestion-line')
        .map((line) => line.textContent ?? '');
      expect(lines.length).toBeGreaterThan(0); // every scenario S1-S12 composes something
      for (const line of lines) {
        expect(line).not.toMatch(uuidRegex);
      }
      result.unmount();
    }
  });

  it('AC-D6/S2: the reallocate line names the target order and document in words', () => {
    // Duplicate of the S2 case above, pinned on its own so a change to the wider S2
    // assertion cannot silently drop the AC-D6 guard with it.
    expect(linesOf('pcr-s2')).toContain('Reallocate PO-A 34 to SO420103 ORDER 50');
  });

  it('says nothing at all when the engine composed no suggestion', () => {
    const { row, soNumber } = rowOf('pcr-s6');
    render(
      <BoardChangeTable annotation={annotationOf({ ...row, suggestion: null }, soNumber)} />,
    );
    fireEvent.click(screen.getByTestId(`board-change-icon-${row.id}`));
    const dialog = screen.getByTestId('board-change-dialog');
    expect(within(dialog).queryByTestId('board-change-suggestion-pcr-s6')).toBeNull();
    expect(within(dialog).queryByTestId('board-change-late-pcr-s6')).toBeNull();
    expect(within(dialog).queryByTestId('board-change-short-pcr-s6')).toBeNull();
  });
});

/**
 * Owner feedback, 13 September 2026 (Slice C board display, UAC AC-C9 to AC-C11): the inline
 * Was / Now table this file's other describe block pins is retired from the grid cell. A
 * changed line shows one amber hazard icon instead (the same warning triangle already used
 * beside a Rejected verdict); clicking it opens a lightbox naming only what changed, then the
 * composed suggestion verbatim, then the late/short fact exactly once. RED: no icon, no dialog
 * exist yet - `BoardChangeTable` still renders the full inline table unconditionally.
 */
function sampleAnnotation(overrides: Partial<BoardChangeAnnotation> = {}): BoardChangeAnnotation {
  // The captain's own worked example (AC-C10): "Qty 234 -> 334; Date 4 Sep -> 20 Nov;
  // Decision Buy 234 -> Buy 334", on the lane's own canonical demo order (SO419772, line 1).
  return {
    rowId: 'pcr-demo',
    soNumber: 'SO419772',
    lineNo: 1,
    itemCode: 'B2155-NL-BLUE',
    kind: 'qty_up',
    closed: false,
    was: { qty: '234', date: '2026-09-04', decision: 'Buy 234' },
    now: { qty: '334', date: '2026-11-20', decision: 'Buy 334' },
    suggestionLines: ['Buy 334 (was 234)'],
    lateDays: null,
    shortfallQty: null,
    productChangedFrom: null,
    movedTransfer: null,
    projectLineId: 'pl-demo-1',
    ...overrides,
  };
}

describe('the change indicator, lightbox and one shortfall line (owner feedback 13 Sep)', () => {
  it('AC-C9: a changed line shows one amber hazard icon in the grid cell, not the inline Was/Now block', () => {
    const { row, soNumber } = rowOf('pcr-s1');
    render(<BoardChangeTable annotation={annotationOf(row, soNumber)} />);

    expect(screen.getByTestId('board-change-icon-pcr-s1')).toBeInTheDocument();
    // The inline table this file's OTHER describe block still pins is gone in its place.
    expect(screen.queryByTestId('board-change-pcr-s1')).not.toBeInTheDocument();
  });

  it('AC-D1/AC-D2: clicking the icon opens a dialog titled "What changed, <SO> (Line <n>)", showing a Was/Now table (Decision row kept) then the suggestion verbatim', async () => {
    // AC-D1: the arrow-line list this test used to pin ("Qty 234 → 334", ...) is gone -
    // `BoardChangeSummary` now renders `BoardChangeWasNowTable` in its place, Decision row
    // kept. RED today: `board-change-pcr-demo` does not exist in the dialog yet.
    render(<BoardChangeTable annotation={sampleAnnotation()} />);

    fireEvent.click(screen.getByTestId('board-change-icon-pcr-demo'));
    const dialog = await screen.findByTestId('board-change-dialog');

    expect(within(dialog).getByText('What changed, SO419772 (Line 1)')).toBeInTheDocument();
    // Every field changed in this sample, so the Was/Now table shows Qty, Date AND Decision.
    const table = within(dialog).getByTestId('board-change-pcr-demo');
    expect(within(table).getByText('234')).toBeInTheDocument();
    expect(within(table).getByTestId('change-now-qty')).toHaveTextContent('334');
    // AC-D4 (owner ruling, fix round 1): the shared Was/Now table keeps its `dd/mm/yyyy`
    // dates, so the Order Inquiries Qty dialog - which renders the same table - reads
    // exactly as it does today. The year is on both sides either way (AC-RL-01).
    expect(within(table).getByText('04/09/2026')).toBeInTheDocument();
    expect(within(table).getByText('20/11/2026')).toBeInTheDocument();
    // Decision row is KEPT (AC-D1 says so explicitly - unlike the Order Inquiries table,
    // which drops it with `omitDecision`).
    expect(within(table).getByText('Buy 234')).toBeInTheDocument();
    expect(within(table).getByTestId('change-now-decision')).toHaveTextContent('Buy 334');
    // The old arrow-line list is gone from the lightbox entirely.
    expect(
      within(dialog).queryByTestId('board-change-fields-pcr-demo'),
    ).not.toBeInTheDocument();
    // Then the composed suggestion, verbatim - the server's own sentence, unchanged.
    expect(within(dialog).getByText('Buy 334 (was 234)')).toBeInTheDocument();
  });

  /**
   * Radix's `Dialog.Content` auto-generates an `aria-describedby` pointing at a
   * `Dialog.Description` it expects to exist, and warns on the console when nothing with
   * that id is rendered - `DialogContent` here carries a `DialogHeader`/`DialogTitle` and a
   * `DialogBody`, but no `DialogDescription` (grepped `BoardChangeTable.tsx` - absent), so
   * the dialog's own `aria-describedby` resolves to nothing on the page.
   */
  it('carries an aria-describedby that resolves to a real element, so Radix stops warning', async () => {
    render(<BoardChangeTable annotation={sampleAnnotation()} />);

    fireEvent.click(screen.getByTestId('board-change-icon-pcr-demo'));
    const dialog = await screen.findByRole('dialog');

    const describedBy = dialog.getAttribute('aria-describedby');
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy as string)).not.toBeNull();
  });

  it('AC-D2: an unchanged field gets no row at all in the Was/Now table - never a row of dashes', async () => {
    // Only the date moved this time; qty and decision are the SAME on both sides.
    render(
      <BoardChangeTable
        annotation={sampleAnnotation({
          rowId: 'pcr-demo-date-only',
          was: { qty: '134', date: '2026-09-04', decision: 'Keep 134' },
          now: { qty: '134', date: '2026-09-25', decision: 'Keep 134' },
          suggestionLines: ['Keep 134'],
        })}
      />,
    );

    fireEvent.click(screen.getByTestId('board-change-icon-pcr-demo-date-only'));
    const dialog = await screen.findByTestId('board-change-dialog');
    const table = within(dialog).getByTestId('board-change-pcr-demo-date-only');

    // AC-D4 (owner ruling, fix round 1): the shared Was/Now table keeps its `dd/mm/yyyy`
    // dates, so the Order Inquiries Qty dialog - which renders the same table - reads
    // exactly as it does today. The year is on both sides either way (AC-RL-01).
    expect(within(table).getByText('04/09/2026')).toBeInTheDocument();
    expect(within(table).getByText('25/09/2026')).toBeInTheDocument();
    // No row at all for Qty or Decision - not a dash, not a hidden row still in the DOM.
    expect(within(table).queryByText('Qty')).not.toBeInTheDocument();
    expect(within(table).queryByText('Decision')).not.toBeInTheDocument();
    expect(within(table).queryByText('134')).not.toBeInTheDocument();
    expect(within(table).queryByText('Keep 134')).not.toBeInTheDocument();
  });

  it('AC-D2: the dialog description stays "Only the fields that moved, then the suggestion." unchanged', async () => {
    render(<BoardChangeTable annotation={sampleAnnotation()} />);

    fireEvent.click(screen.getByTestId('board-change-icon-pcr-demo'));
    const dialog = await screen.findByTestId('board-change-dialog');

    expect(
      within(dialog).getByText('Only the fields that moved, then the suggestion.'),
    ).toBeInTheDocument();
  });

  it('AC-D3: the dialog stays capped at max-w-[min(28rem,calc(100vw-2rem))] so the table fits at 375px with no horizontal scroll', async () => {
    render(<BoardChangeTable annotation={sampleAnnotation()} />);

    fireEvent.click(screen.getByTestId('board-change-icon-pcr-demo'));
    const dialog = await screen.findByTestId('board-change-dialog');

    expect(dialog.className).toMatch(/max-w-\[min\(28rem,calc\(100vw-2rem\)\)\]/);
  });

  it('AC-C10: Escape and the Close button both close the dialog', async () => {
    // Both closings are AWAITED. A Radix dialog's exit is asynchronous - the content stays
    // mounted through the exit animation and the aria-hidden unwind - so a single macrotask
    // tick is a race, not a wait: it holds on a developer machine and loses on a loaded CI
    // runner. This test failed exactly that way on CI twice before (4 and 5 Sep) and was
    // fixed the same way, test only.
    render(<BoardChangeTable annotation={sampleAnnotation()} />);

    fireEvent.click(screen.getByTestId('board-change-icon-pcr-demo'));
    const dialog = await screen.findByTestId('board-change-dialog');
    fireEvent.keyDown(dialog, { key: 'Escape', code: 'Escape' });
    await waitFor(() =>
      expect(screen.queryByTestId('board-change-dialog')).not.toBeInTheDocument(),
    );

    fireEvent.click(screen.getByTestId('board-change-icon-pcr-demo'));
    const reopened = await screen.findByTestId('board-change-dialog');
    fireEvent.click(within(reopened).getByRole('button', { name: 'Close' }));
    await waitFor(() =>
      expect(screen.queryByTestId('board-change-dialog')).not.toBeInTheDocument(),
    );
  });

  it('AC-C11: a shortfall renders exactly once, and the retired standalone Short paragraph is gone', async () => {
    const { row, soNumber } = rowOf('pcr-s11');
    render(<BoardChangeTable annotation={annotationOf(row, soNumber)} />);

    fireEvent.click(screen.getByTestId('board-change-icon-pcr-s11'));
    const dialog = await screen.findByTestId('board-change-dialog');

    // `getByText` itself throws on more than one match, so this pins "exactly once".
    expect(
      within(dialog).getByText('Short 44 by 22 Aug (was Buy 134)'),
    ).toBeInTheDocument();
    // The old inline block's own separate "Short 44" paragraph must not exist ANYWHERE -
    // not duplicated inside the dialog, not left behind outside it.
    expect(screen.queryByTestId('board-change-short-pcr-s11')).not.toBeInTheDocument();
  });
});

/**
 * AC-D5's own half of the lightbox, pinned against the mutations the reviewer found still
 * green in fix round 1 (SF-1, SF-3, SF-4, fix round 2): the ONE icon a line with several
 * pending changes draws opens a body that lists EVERY one of them, newest first, each with
 * its own facts under it - a body that rendered only the newest, or only the oldest, or that
 * read the facts off one change and printed them once, passed the suite before.
 */
describe('AC-D5: the lightbox behind one icon lists every pending change for the line', () => {
  function grouped(rowId: string, overrides: Partial<BoardChangeAnnotation> = {}) {
    return sampleAnnotation({
      rowId,
      suggestionLines: [],
      ...overrides,
    });
  }

  /** Renders the grouped icon and opens it. */
  function openGrouped(annotations: BoardChangeAnnotation[]): HTMLElement {
    render(<BoardChangeTable annotations={annotations} />);
    fireEvent.click(screen.getByTestId(`board-change-icon-${annotations[0].rowId}`));
    return screen.getByTestId('board-change-dialog');
  }

  it('SF-1: renders one Was/Now table PER change, with the newest first', () => {
    const dialog = openGrouped([
      // The caller hands them over oldest first, the order a batch's rows arrive in.
      grouped('pcr-group-older', {
        was: { qty: '50', date: '2026-09-01', decision: 'Buy 50' },
        now: { qty: '50', date: '2026-09-05', decision: 'Buy 50' },
      }),
      grouped('pcr-group-newer', {
        was: { qty: '50', date: '2026-09-05', decision: 'Buy 50' },
        now: { qty: '50', date: '2026-09-10', decision: 'Buy 50' },
        suggestionLines: ['Keep 50 for 10 Sep'],
      }),
    ]);

    const tables = within(dialog).getAllByTestId(/^board-change-pcr-group-/);
    expect(tables).toHaveLength(2);
    // Newest first: the change a planner is answering is the last one to have happened.
    expect(tables[0]).toHaveAttribute('data-testid', 'board-change-pcr-group-newer');
    expect(tables[1]).toHaveAttribute('data-testid', 'board-change-pcr-group-older');
    // Both dates the line moved through are readable, not only the newest pair.
    expect(within(dialog).getByText('01/09/2026')).toBeInTheDocument();
    expect(within(dialog).getByText('10/09/2026')).toBeInTheDocument();
    // ONE suggestion, off the newest change alone - an older row's has been superseded.
    expect(
      within(dialog).getAllByTestId('board-change-suggestion-line').map((l) => l.textContent),
    ).toEqual(['Keep 50 for 10 Sep']);
  });

  it('SF-3: a change in the group that moved nothing says so in words, instead of an empty table', () => {
    const dialog = openGrouped([
      // Same on both sides: `changedFieldsOf` finds nothing, so this one has no table.
      grouped('pcr-group-still', {
        was: { qty: '50', date: '2026-09-01', decision: 'Buy 50' },
        now: { qty: '50', date: '2026-09-01', decision: 'Buy 50' },
      }),
      grouped('pcr-group-moved', {
        was: { qty: '50', date: '2026-09-01', decision: 'Buy 50' },
        now: { qty: '70', date: '2026-09-01', decision: 'Buy 70' },
      }),
    ]);

    expect(
      within(dialog).getByText(
        'The book moved this line without changing its quantity, its date or its decision.',
      ),
    ).toBeInTheDocument();
    // The unmoved change draws no box at all; the moved one still does.
    expect(
      within(dialog).queryByTestId('board-change-pcr-group-still'),
    ).not.toBeInTheDocument();
    expect(
      within(dialog).getByTestId('board-change-pcr-group-moved'),
    ).toBeInTheDocument();
  });

  it('SF-4: each change keeps its OWN product swap, held share, lateness and movement - the older one is not dropped', () => {
    const dialog = openGrouped([
      grouped('pcr-group-first', {
        was: { qty: '50', date: '2026-09-01', decision: 'Buy 50' },
        now: { qty: '40', date: '2026-09-01', decision: 'Buy 40' },
        productChangedFrom: 'B2155-NL-WHITE',
        movedTransfer: '10 moved BRW -> BRW-IB, line reduced',
        whereItWent: ['Reallocate 202607-S0080 3 to pool'],
        lateDays: 4,
      }),
      grouped('pcr-group-second', {
        was: { qty: '40', date: '2026-09-01', decision: 'Buy 40' },
        now: { qty: '40', date: '2026-10-01', decision: 'Buy 40' },
      }),
    ]);

    // Read off the OLDER change, which is not the one the suggestion comes from.
    expect(
      within(dialog).getByTestId('board-change-product-pcr-group-first'),
    ).toHaveTextContent('Product changed, was B2155-NL-WHITE');
    expect(
      within(dialog).getByTestId('board-change-moved-pcr-group-first'),
    ).toHaveTextContent('10 moved BRW -> BRW-IB, line reduced');
    expect(
      within(dialog).getByTestId('board-change-where-pcr-group-first'),
    ).toHaveTextContent('Reallocate 202607-S0080 3 to pool');
    expect(
      within(dialog).getByTestId('board-change-late-pcr-group-first'),
    ).toHaveTextContent('Late by 4 days');
    // And they sit under THAT change's own block, not loose at the end of the body.
    const firstBlock = within(dialog).getByTestId('board-change-block-pcr-group-first');
    expect(
      within(firstBlock).getByTestId('board-change-product-pcr-group-first'),
    ).toBeInTheDocument();
    // The newer change said none of those things, so it prints none of them.
    expect(
      within(dialog).queryByTestId('board-change-product-pcr-group-second'),
    ).not.toBeInTheDocument();
    expect(
      within(dialog).queryByTestId('board-change-late-pcr-group-second'),
    ).not.toBeInTheDocument();
  });

  it('SF-4: stacked blocks are separated by a hairline rule, and a single change gets none', () => {
    const dialog = openGrouped([
      grouped('pcr-rule-older', {
        now: { qty: '300', date: '2026-11-20', decision: 'Buy 300' },
      }),
      grouped('pcr-rule-newer'),
    ]);

    // Newest first, so the SECOND block on screen is the one carrying the separator.
    expect(
      within(dialog).getByTestId('board-change-block-pcr-rule-newer').className,
    ).not.toMatch(/border-t/);
    expect(
      within(dialog).getByTestId('board-change-block-pcr-rule-older').className,
    ).toMatch(/\bborder-t\b/);
  });
});
