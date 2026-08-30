/**
 * The proof behind one line: ladder v5's four questions plus Buy
 * (`PLAN-scm-cs-planning-uat.md` section 1e, AC-V1).
 *
 * Three things are pinned here, isolated from the wider cell breakdown
 * (`BoardCellBreakdownDialog.test.tsx` covers the arithmetic through a real board):
 *
 * * FIVE rows, in order, showing the QUESTION and never the engine's internal rung name -
 *   a reader is asked "can we take from the pool?", not shown the word `cross_group_borrow`;
 * * each row answers Yes or No, with what it took and where from;
 * * the queue ("who is in front of me") hangs off the ONE question that has one - question 1,
 *   our own location - because `QueueLink`'s dialog opens exactly that warehouse.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type {
  BoardContribution,
  BoardTrailStep,
} from '../../_shared/types/fulfilmentPlanning.types';

import { BoardTrailPopover } from './BoardTrailPopover';

/** The five rows, in the order the server sends them. Only question 1 carries a queue. */
const TRAIL: BoardTrailStep[] = [
  {
    step: 1,
    kind: 'own',
    question: 'Can we use our location?',
    answer: 'no',
    took: '0',
    from: null,
    location: 'BRW-BB',
    warehouse_id: 'wh-brw-bb',
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
    why: 'The BB group nets -969, so there is nothing left for this line.',
  },
  {
    step: 2,
    kind: 'pool',
    question: 'Can we take from the pool?',
    answer: 'yes',
    took: '43',
    from: 'BRW',
    location: 'BRW',
    warehouse_id: 'wh-brw',
    why: 'Cold at retail, so BRW is offered: 43 left after its own queue ahead of this line; this line takes 43.',
  },
  {
    step: 3,
    kind: 'cross_group_borrow',
    question: 'Can we borrow from another location?',
    answer: 'no',
    took: '0',
    why: 'Fully covered before this rung.',
  },
  {
    step: 4,
    kind: 'group_borrow',
    question: "Can we borrow from the same agent's other order in this group?",
    answer: 'no',
    took: '0',
    why: "SO000009 line 2 holds this in the group. Borrowing from another sales order is a person's pick in Amend.",
  },
  {
    step: 5,
    kind: 'buy',
    question: 'Buy the rest?',
    answer: 'no',
    took: '0',
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

describe('BoardTrailPopover: the four questions and Buy', () => {
  it('shows five rows, in order, reading as questions rather than rung names', () => {
    const contribution = contributionOf();
    render(<BoardTrailPopover contribution={contribution} />);
    openTrail(contribution.key);

    const questions = [
      ...screen.getByTestId(`trail-${contribution.key}`).querySelectorAll('tbody tr[data-step]'),
    ].map((row) => row.querySelectorAll('td')[1]?.textContent);
    expect(questions).toEqual([
      'Can we use our location?',
      'Can we take from the pool?',
      'Can we borrow from another location?',
      "Can we borrow from the same agent's other order in this group?",
      'Buy the rest?',
    ]);
  });

  it('never renders the engine’s internal rung names', () => {
    const contribution = contributionOf();
    render(<BoardTrailPopover contribution={contribution} />);
    openTrail(contribution.key);

    const text = screen.getByTestId(`trail-${contribution.key}`).textContent ?? '';
    for (const internal of ['cross_group_borrow', 'group_borrow', 'group_take', 'Incoming']) {
      expect(text).not.toContain(internal);
    }
  });

  it('answers each question Yes or No, with what it took and where from', () => {
    const contribution = contributionOf();
    render(<BoardTrailPopover contribution={contribution} />);
    openTrail(contribution.key);

    const pool = stepCells(contribution.key, 'pool');
    expect(pool[2]).toBe('Yes');
    expect(pool[3]).toBe('43');
    expect(pool[4]).toBe('BRW');

    const own = stepCells(contribution.key, 'own');
    expect(own[2]).toBe('No');
    expect(own[3]).toBe('0');
    expect(own[4]).toBe('-');
  });

  it('puts the deciding figure in the sentence under the row', () => {
    const contribution = contributionOf();
    render(<BoardTrailPopover contribution={contribution} />);
    openTrail(contribution.key);

    expect(screen.getByTestId(`trail-why-${contribution.key}-own`).textContent).toContain(
      'The BB group nets -969',
    );
  });
});

describe('BoardTrailPopover: the queue hangs off question 1', () => {
  it('opens the whole queue from the question that names it', () => {
    const contribution = contributionOf();
    render(<BoardTrailPopover contribution={contribution} />);
    openTrail(contribution.key);

    const button = screen.getByTestId(`trail-queue-${contribution.key}`);
    expect(button.textContent).toBe('View the queue (6 ahead)');
  });

  it('offers no queue link on any other question', () => {
    const contribution = contributionOf();
    render(<BoardTrailPopover contribution={contribution} />);
    openTrail(contribution.key);

    // One link, on one row: `QueueLink` renders only where `ahead` is non-empty, and no
    // question but the first carries one.
    expect(screen.getAllByTestId(`trail-queue-${contribution.key}`)).toHaveLength(1);
  });
});
