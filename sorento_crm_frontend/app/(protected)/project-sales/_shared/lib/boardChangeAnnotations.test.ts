/**
 * The Was / Now table a changed line reads on its board cell (AC-P3-2, AC-P3-3, AC-P3-12).
 *
 * Three things are pinned here and nowhere else: a closed line still lands on a cell, the
 * batch's own reaction vocabulary never reaches a string a person reads, and the pre-mark
 * covers exactly the changed lines.
 */
import { describe, expect, it } from 'vitest';
import {
  annotationOf,
  annotationsByCell,
  cellKeyOf,
  decisionWords,
  preMarkedKeys,
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
    suggested: 'replan',
    why: 'Advanced 6 days.',
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
        kind: 'closed',
        from: { required_date: '2026-09-05', qty: '10', status: 'open' },
        to: { required_date: null, qty: null, status: 'closed' },
        suggested: 'retire',
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

  it('never prints a reaction verb - the decision is in board words', () => {
    const annotation = annotationOf(
      row({
        held: {
          reserve: [{ location: 'BRW-IB', warehouse_id: 'wh-1', qty: '40' }],
          borrow: [],
          buy_qty: '0',
          timely_spo_qty: '0',
          revision_no: 2,
        },
        suggested: 'release',
      }),
      'SO381895',
      'BRW-IB',
    );
    expect(annotation.was.decision).toBe('Use own location 40 from BRW-IB');
    const printed = JSON.stringify(annotation);
    for (const verb of ['keep', 'release', 'replan', 'reduce', 'retire']) {
      expect(printed.toLowerCase()).not.toContain(`"${verb}"`);
    }
  });

  it('carries the moved-transfer phrase when the batch flagged one', () => {
    const annotation = annotationOf(
      row({ kind: 'closed', moved_transfer: '10 moved BRW -> BRW-IB, line cancelled' }),
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
    ).toBe('Buy 25 · Use own location 40 from BRW-IB');
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
        row({ id: 'pcr-2', project_line_id: 'pl-2', line_no: 2, kind: 'closed' }),
        row({ id: 'pcr-3', project_line_id: 'pl-3', line_no: 3, kind: 'closed' }),
      ]),
      [surviving],
    );
    expect(map.get(key)?.map((entry) => entry.rowId)).toEqual(['pcr-1', 'pcr-2', 'pcr-3']);
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
