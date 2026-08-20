/**
 * The ladder as it was walked for one line, rung by rung (PLAN 13.5, S4 and S13 of the 19
 * August review findings).
 *
 * Two things are pinned here, isolated from the wider cell breakdown (`BoardCellBreakdownDialog
 * .test.tsx` covers the arithmetic through a real board): every rung carries its own label, in
 * the ladder's own order, and `aheadOf` (the "who is in front of me" reading) renders on the
 * ONE rung that carries a queue - the read-only own-location rung, `reserve_own` - and reads
 * "-" everywhere else, because no other rung queues: the pool nets its own book before it is
 * offered, and incoming and Buy have none.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type {
  BoardContribution,
  BoardTrailStep,
} from '../../_shared/types/fulfilmentPlanning.types';

import { BoardTrailPopover } from './BoardTrailPopover';

/** The seven rungs, ladder v2's own order (section E), each carrying enough to render. Only
 * `reserve_own` names a queue - the fact under test. */
const TRAIL: BoardTrailStep[] = [
  {
    step: 1,
    kind: 'reserve_own',
    location: 'BRW-BB',
    warehouse_id: 'wh-brw-bb',
    opening: '627',
    ahead_qty: '388',
    ahead_lines: 6,
    ahead: [
      {
        so_number: 'SO000002',
        line_no: 3,
        qty: '80',
        required_date: '2026-08-20',
        rank_score: 0.5,
        leading_factor: 'need_by_date',
        same_order: false,
      },
    ],
    ahead_more: 3,
    ahead_by_factor: { need_by_date: 5, line_order: 1 },
    offered: '627',
    taken: '0',
    remaining_after: '43',
    outcome: 'not_eligible',
    why:
      '627 left at BRW-BB after 388 owed to 6 lines ranked ahead of this line. Never ' +
      'reserved: stock at BRW-BB is committed to whichever sales order is queued for it - ' +
      'borrow from another sales order instead.',
  },
  {
    step: 2,
    kind: 'incoming',
    location: 'BRW-BB',
    warehouse_id: 'wh-brw-bb',
    opening: '0',
    offered: '0',
    taken: '0',
    remaining_after: '43',
    outcome: 'nothing_left',
    why: 'No supplier PO arrives by 3 Sep 2026.',
  },
  {
    step: 3,
    kind: 'pool',
    location: 'BRW',
    warehouse_id: 'wh-brw',
    opening: '43',
    offered: '43',
    taken: '43',
    remaining_after: '0',
    outcome: 'took',
    why: 'BRW offers 43; this line takes 43.',
  },
  {
    step: 4,
    kind: 'group_take',
    offered: '0',
    taken: '0',
    remaining_after: '0',
    outcome: 'none_needed',
    why: 'Fully covered before this rung.',
  },
  {
    step: 5,
    kind: 'group_borrow',
    offered: '0',
    taken: '0',
    remaining_after: '0',
    outcome: 'none_needed',
    why: 'Fully covered before this rung.',
  },
  {
    step: 6,
    kind: 'cross_group_borrow',
    offered: '0',
    taken: '0',
    remaining_after: '0',
    outcome: 'none_needed',
    why: 'Fully covered before this rung.',
  },
  {
    step: 7,
    kind: 'buy',
    offered: '0',
    taken: '0',
    remaining_after: '0',
    outcome: 'none_needed',
    why: 'Fully covered before this rung.',
  },
];

function contributionOf(overrides: Partial<BoardContribution> = {}): BoardContribution {
  return {
    key: 'line-1',
    sales_order_id: 'so-1',
    so_number: 'SO000001',
    line_no: 1,
    item_code: 'ZZT-001',
    qty: '43',
    unplannable: false,
    rank_score: 0,
    rank_factors: [],
    sources: [],
    // Null, not a set of flags: no chip renders, and `ClassificationProofPopover` (which
    // needs a react-query client this test does not set up) never mounts.
    item_flags: null,
    covered: false,
    contested: false,
    trail: TRAIL,
    fulfilment_location: 'BRW-BB',
    fulfilment_warehouse_id: 'wh-brw-bb',
    product_id: 'product-1',
    line_id: 'core-line-1',
    ...overrides,
  };
}

function openTrail(key: string) {
  fireEvent.click(screen.getByTestId(`trail-info-${key}`));
}

function stepCells(key: string, kind: string): (string | null)[] {
  return [
    ...screen.getByTestId(`trail-step-${key}-${kind}`).querySelectorAll('td'),
  ].map((node) => node.textContent);
}

describe('BoardTrailPopover: the rung labels', () => {
  it('shows a label per rung, in the ladder’s own order', () => {
    const contribution = contributionOf();
    render(<BoardTrailPopover contribution={contribution} />);
    openTrail(contribution.key);

    const sources = [
      ...screen.getByTestId(`trail-${contribution.key}`).querySelectorAll('tbody tr[data-step]'),
    ].map((row) => row.querySelectorAll('td')[1]?.textContent);
    expect(sources).toEqual([
      'This location (BRW-BB)',
      'Incoming (SPO)',
      'Pool BRW',
      'Group take',
      'Group borrow',
      'Cross-group borrow',
      'Buy',
    ]);
  });

  it('names the own location even when the trail carries no code for a rung', () => {
    const contribution = contributionOf({
      trail: [{ ...TRAIL[3], location: null }],
    });
    render(<BoardTrailPopover contribution={contribution} />);
    openTrail(contribution.key);

    expect(stepCells(contribution.key, 'group_take')[1]).toBe('Group take');
  });
});

describe('BoardTrailPopover: aheadOf renders the queue on the rung that carries it', () => {
  it('names the queue on the read-only own-location rung', () => {
    const contribution = contributionOf();
    render(<BoardTrailPopover contribution={contribution} />);
    openTrail(contribution.key);

    expect(stepCells(contribution.key, 'reserve_own')[3]).toBe('388 across 6 lines');
  });

  it('reads "-" on every other rung, because no other rung queues', () => {
    const contribution = contributionOf();
    render(<BoardTrailPopover contribution={contribution} />);
    openTrail(contribution.key);

    for (const kind of [
      'incoming',
      'pool',
      'group_take',
      'group_borrow',
      'cross_group_borrow',
      'buy',
    ]) {
      expect(stepCells(contribution.key, kind)[3]).toBe('-');
    }
  });

  it('counts a single line ahead in the singular', () => {
    const contribution = contributionOf({
      trail: [{ ...TRAIL[0], ahead_qty: '60', ahead_lines: 1 }, ...TRAIL.slice(1)],
    });
    render(<BoardTrailPopover contribution={contribution} />);
    openTrail(contribution.key);

    expect(stepCells(contribution.key, 'reserve_own')[3]).toBe('60 across 1 line');
  });

  it('opens the whole queue from the rung that names it', () => {
    const contribution = contributionOf();
    render(<BoardTrailPopover contribution={contribution} />);
    openTrail(contribution.key);

    const button = screen.getByTestId(`trail-queue-${contribution.key}`);
    expect(button.textContent).toBe('View the queue (6 ahead)');
  });
});
