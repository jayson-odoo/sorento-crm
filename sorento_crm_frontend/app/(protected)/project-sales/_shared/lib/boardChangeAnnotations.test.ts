/**
 * The Was / Now table a changed line reads on its board cell (AC-P3-2, AC-P3-3, AC-P3-12) and
 * the suggestion printed under it (AC-C1).
 *
 * Four things are pinned here and nowhere else: a closed line still lands on a cell, the
 * retired reaction vocabulary (replan / retire / accept) never reaches a string a person
 * reads, the engine's own composed sentences are carried through VERBATIM and in its order,
 * and the pre-mark covers exactly the changed lines.
 */
import { describe, expect, it } from 'vitest';
import {
  annotationOf,
  annotationsByCell,
  cellKeyOf,
  decisionWords,
  preMarkedKeys,
  uncoverChangedLines,
} from './boardChangeAnnotations';
import type { BoardCell, BoardContribution } from '../types/fulfilmentPlanning.types';
import type { PlanningChangeBatch, PlanningChangeRow } from '../types/planningChange.types';

function contribution(over: Partial<BoardContribution>): BoardContribution {
  return {
    key: 'k1',
    sales_order_id: 'so-1',
    so_number: 'SO381895',
    project_sales_order_id: 'pso-1',
    project_line_id: 'pl-1',
    line_no: 1,
    item_code: 'SRTWCX7405-RL-S-PJ',
    qty: '25',
    required_date: '2026-08-19',
    fulfilment_location: 'BRW-IB',
    rank_score: 1,
    sources: [],
    trail: [],
    covered: false,
    unplannable: false,
    contested: false,
    ...over,
  } as BoardContribution;
}

function cell(over: Partial<BoardCell>): BoardCell {
  return {
    item_code: 'SRTWCX7405-RL-S-PJ',
    bucket_key: '2026-08-17',
    total_qty: '25',
    locations: [],
    contributions: [contribution({})],
    unplannable_count: 0,
    contested_count: 0,
    ...over,
  } as BoardCell;
}

function row(over: Partial<PlanningChangeRow>): PlanningChangeRow {
  return {
    id: 'pcr-1',
    project_line_id: 'pl-1',
    line_no: 1,
    item_code: 'SRTWCX7405-RL-S-PJ',
    kind: 'advanced',
    from: { required_date: '2026-08-25', qty: '10', status: 'open' },
    to: { required_date: '2026-08-19', qty: '25', status: 'open' },
    days_moved: -6,
    held: {
      reserve: [],
      borrow: [],
      buy_qty: '10',
      timely_spo_qty: '0',
      revision_no: 2,
    },
    facts: {
      dealer_hot_selling: { value: false, where: [] },
      project_hot_selling: { value: false, where: [] },
      discontinued: false,
      days_moved: -6,
      within_reserve_window: {
        value: true,
        window_days: 60,
        new_date: '2026-08-19',
        window_end: '2026-10-24',
      },
      buy_actioned: { value: false, po_number: null },
    },
    suggestion: null,
    proposal: null,
    inquiry_rows: [],
    decision: null,
    applied_state: 'pending',
    board_link: '/project-sales/fulfilment-planning?orders=SO381895&cell=X|2026-08-19',
    ...over,
  } as PlanningChangeRow;
}

function batchOf(rows: PlanningChangeRow[]): PlanningChangeBatch {
  return {
    id: 'pcb-9',
    created_at: '2026-08-19T09:23:00Z',
    created_by_name: 'Cyndi',
    source: { upload_id: 'imp-1', file_name: 'SO book.xlsx', kind: 'so_book_upload' },
    orders: [
      {
        project_sales_order_id: 'pso-1',
        so_number: 'SO381895',
        revision_no: 2,
        rows,
        is_adopted: true,
      },
    ],
  } as PlanningChangeBatch;
}

describe('the Was / Now table of a changed line', () => {
  it('states the quantity, the date and the decision on both sides', () => {
    const annotation = annotationOf(row({}), 'SO381895', 'BRW-IB');
    expect(annotation.was).toEqual({
      qty: '10',
      date: '2026-08-25',
      decision: 'Buy 10',
    });
    expect(annotation.now.qty).toBe('25');
    expect(annotation.now.date).toBe('2026-08-19');
    expect(annotation.closed).toBe(false);
  });

  it('reads Closed on a line the book closed, and states no new quantity or date', () => {
    const annotation = annotationOf(
      row({
        id: 'pcr-2',
        project_line_id: 'pl-2',
        line_no: 2,
        kind: 'cancelled',
        from: { required_date: '2026-09-05', qty: '10', status: 'open' },
        to: { required_date: null, qty: null, status: 'closed' },
      }),
      'SO381895',
      'BRW-IB',
    );
    expect(annotation.closed).toBe(true);
    expect(annotation.now.qty).toBeNull();
    expect(annotation.now.date).toBeNull();
    expect(annotation.now.decision).toBeNull();
    expect(annotation.was.qty).toBe('10');
  });

  it('never prints a retired reaction verb - the decision is in board words', () => {
    const annotation = annotationOf(
      row({
        held: {
          reserve: [{ location: 'BRW-IB', warehouse_id: 'wh-1', qty: '40' }],
          borrow: [],
          buy_qty: '0',
          timely_spo_qty: '0',
          revision_no: 2,
        },
        suggestion: {
          components: [
            {
              action: 'keep',
              source: 'reserve',
              qty_now: '40',
              location: 'BRW-IB',
              label: 'Keep 40',
            },
          ],
        },
      }),
      'SO381895',
      'BRW-IB',
    );
    expect(annotation.was.decision).toBe('Use own location 40 from BRW-IB');
    // The machinery, not the suggestion: an action code, a decision value and the three
    // retired verbs are all things the reader has no use for. `Keep 40` IS printed - it is
    // the engine's own sentence about a component, which is the whole point of the row.
    const printed = JSON.stringify(annotation).toLowerCase();
    for (const word of ['replan', 'retire', 'accept', '"keep"', '"board"']) {
      expect(printed).not.toContain(word);
    }
    expect(annotation.suggestionLines).toEqual(['Keep 40']);
  });

  it('carries every composed sentence verbatim, in the order the engine wrote them (S2)', () => {
    const annotation = annotationOf(
      row({
        kind: 'qty_down',
        from: { required_date: '2026-09-04', qty: '234', status: 'open' },
        to: { required_date: '2026-09-04', qty: '100', status: 'open' },
        suggestion: {
          components: [
            {
              action: 'reduce',
              source: 'buy',
              qty_was: '100',
              qty_now: '0',
              label: 'Reduce Buy 100 to 0',
            },
            {
              action: 'keep',
              source: 'po',
              qty_was: '134',
              qty_now: '100',
              document: 'PO-A',
              label: 'Keep PO-A 100 of 134',
            },
            {
              action: 'reallocate',
              source: 'po',
              qty_now: '34',
              document: 'PO-A',
              target: 'SO420103 ORDER 50',
              label: 'Reallocate PO-A 34 to SO420103 ORDER 50',
            },
          ],
        },
      }),
      'SO403765',
    );
    expect(annotation.suggestionLines).toEqual([
      'Reduce Buy 100 to 0',
      'Keep PO-A 100 of 134',
      'Reallocate PO-A 34 to SO420103 ORDER 50',
    ]);
  });

  it('states lateness and shortfall as their own facts, not as a sentence to parse', () => {
    const late = annotationOf(
      row({
        suggestion: {
          components: [
            { action: 'keep', source: 'po', qty_now: '134', document: 'PO-A', label: 'Keep PO-A 134' },
          ],
          late_days: 3,
        },
      }),
      'SO401220',
    );
    expect(late.lateDays).toBe(3);
    expect(late.shortfallQty).toBeNull();

    const short = annotationOf(
      row({
        suggestion: {
          components: [
            { action: 'use_own', source: 'pool_share', qty_now: '90', location: 'BRW', label: 'Pool share 90 at BRW' },
          ],
          shortfall_qty: '44',
        },
      }),
      'SO401220',
    );
    expect(short.shortfallQty).toBe('44');
    expect(short.lateDays).toBeNull();
  });

  it('names the product a product_changed row used to be, and nothing on any other kind', () => {
    const swapped = annotationOf(
      row({
        kind: 'product_changed',
        item_code: 'B2155-NL-WHITE',
        from: {
          required_date: '2026-09-04',
          qty: '134',
          status: 'open',
          item_code: 'B2155-NL-BLUE',
        },
        to: {
          required_date: '2026-09-04',
          qty: '134',
          status: 'open',
          item_code: 'B2155-NL-WHITE',
        },
      }),
      'SO400875',
    );
    expect(swapped.productChangedFrom).toBe('B2155-NL-BLUE');
    expect(swapped.itemCode).toBe('B2155-NL-WHITE');
    expect(annotationOf(row({}), 'SO400875').productChangedFrom).toBeNull();
  });

  it('reads the Now decision off the pre-filled composition, ahead of the re-run proposal', () => {
    // Slice C fills `composition` at build, and Amend edits THAT; printing the proposal
    // ahead of it would show the engine's first answer over the planner's own.
    const annotation = annotationOf(
      row({
        proposal: { sources: [{ kind: 'buy', qty: '25' }] } as never,
        composition: {
          project_line_id: 'pl-1',
          timely_spo_qty: '0',
          reserve: [{ warehouse_id: 'BRW-IB', qty: '25' }],
          borrow: [],
          buy_qty: '0',
        },
      }),
      'SO381895',
      'BRW-IB',
    );
    expect(annotation.now.decision).toBe('Use own location 25 from BRW-IB');
  });

  it('carries the moved-transfer phrase when the batch flagged one', () => {
    const annotation = annotationOf(
      row({ kind: 'cancelled', moved_transfer: '10 moved BRW -> BRW-IB, line cancelled' }),
      'SO381895',
    );
    expect(annotation.movedTransfer).toBe('10 moved BRW -> BRW-IB, line cancelled');
  });
});

describe('decisionWords', () => {
  it('is null when there is nothing held', () => {
    expect(decisionWords([])).toBeNull();
  });

  it('names the location and the quantity per location', () => {
    expect(
      decisionWords(
        [
          { kind: 'reserve', qty: '40', location: 'BRW-IB' },
          { kind: 'buy', qty: '25' },
        ],
        'BRW-IB',
      ),
    ).toBe('Use own location 40 from BRW-IB · Buy 25');
  });
});

describe('annotationsByCell', () => {
  const surviving = cell({});
  const key = cellKeyOf(surviving);

  it('puts a changed line on the cell its own line contributes to', () => {
    const map = annotationsByCell(batchOf([row({})]), [surviving]);
    expect(map.get(key)?.map((entry) => entry.rowId)).toEqual(['pcr-1']);
  });

  it('puts a closed line on the surviving cell of the same product on the same order', () => {
    const map = annotationsByCell(
      batchOf([
        row({}),
        row({ id: 'pcr-2', project_line_id: 'pl-2', line_no: 2, kind: 'cancelled' }),
        row({ id: 'pcr-3', project_line_id: 'pl-3', line_no: 3, kind: 'cancelled' }),
      ]),
      [surviving],
    );
    expect(map.get(key)?.map((entry) => entry.rowId)).toEqual(['pcr-1', 'pcr-2', 'pcr-3']);
  });

  it('lands a proposal-less row on its OWN cell, not the first cell of its product', () => {
    // The second instalment of the same product on the same order. Only a `replan` row
    // carries a proposal, so reading the line off the proposal alone sent every other
    // changed line to the (SO, item) fallback - the FIRST cell of that product - and the
    // second instalment's Was / Now table landed on the first instalment's cell.
    const second = cell({
      bucket_key: '2026-09-07',
      contributions: [contribution({ key: 'k2', project_line_id: 'pl-2', line_no: 2 })],
    });
    const map = annotationsByCell(
      batchOf([
        row({ proposal: null }),
        row({
          id: 'pcr-2',
          project_line_id: 'pl-2',
          line_no: 2,
          kind: 'qty_down',
          proposal: null,
        }),
      ]),
      [surviving, second],
    );
    expect(map.get(key)?.map((entry) => entry.rowId)).toEqual(['pcr-1']);
    expect(map.get(cellKeyOf(second))?.map((entry) => entry.rowId)).toEqual(['pcr-2']);
  });

  it('drops a row whose product is nowhere on the board', () => {
    const map = annotationsByCell(
      batchOf([row({ id: 'pcr-9', project_line_id: 'pl-9', item_code: 'NOT-HERE' })]),
      [surviving],
    );
    expect(map.size).toBe(0);
  });

  it('is empty without a batch', () => {
    expect(annotationsByCell(null, [surviving]).size).toBe(0);
  });
});

describe('preMarkedKeys', () => {
  it('marks exactly the lines the batch changed', () => {
    const contributions = [
      contribution({ key: 'k1', project_line_id: 'pl-1' }),
      contribution({ key: 'k2', project_line_id: 'pl-other' }),
    ];
    expect(preMarkedKeys(batchOf([row({})]), contributions)).toEqual(['k1']);
  });

  it('never marks a line whose sales order states no location', () => {
    const contributions = [contribution({ key: 'k1', project_line_id: 'pl-1', unplannable: true })];
    expect(preMarkedKeys(batchOf([row({})]), contributions)).toEqual([]);
  });
});


describe('uncoverChangedLines', () => {
  /**
   * The defect this pins, measured live on SO381895 (26 August 2026): a covered line's
   * `sources` and `qty_proposed_*` are its FROZEN composition rebuilt, so uncovering it
   * without carrying the batch's own proposal left the cell offering to confirm 10 against
   * a line the book had opened for 25 - which the server refuses, at the last step, after
   * the planner has pressed Confirm.
   */
  const frozen = contribution({
    key: 'k1',
    project_line_id: 'pl-1',
    qty: '25',
    covered: true,
    decision: { revision_no: 2, components: [] },
    sources: [{ kind: 'buy', qty: '10' }],
    qty_proposed_buy: '10',
  } as unknown as Partial<BoardContribution>);
  const board = { cells: [cell({ contributions: [frozen] })], contributions: [frozen] };
  const withProposal = batchOf([
    row({
      proposal: {
        ...contribution({ key: 'built-earlier', project_line_id: 'pl-1', qty: '25' }),
        sources: [{ kind: 'buy', qty: '25' }],
        qty_proposed_buy: '25',
      } as BoardContribution,
    }),
  ]);

  it('carries the batch proposal onto the line and stops calling it covered', () => {
    const out = uncoverChangedLines(board, withProposal);
    const line = out.contributions[0];
    expect(line.covered).toBe(false);
    expect(line.decision).toBeNull();
    expect(line.qty_proposed_buy).toBe('25');
    expect(line.key).toBe('k1');
    expect(out.cells[0].contributions[0].qty_proposed_buy).toBe('25');
  });

  it('leaves a line the batch never named exactly as it was', () => {
    const other = contribution({ key: 'k9', project_line_id: 'pl-other', covered: true });
    const out = uncoverChangedLines(
      { cells: [cell({ contributions: [other] })], contributions: [other] },
      withProposal,
    );
    expect(out.contributions[0].covered).toBe(true);
  });

  it('is the board itself without a batch', () => {
    expect(uncoverChangedLines(board, null)).toBe(board);
  });
});
