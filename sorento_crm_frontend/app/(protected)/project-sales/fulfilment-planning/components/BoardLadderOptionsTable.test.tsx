/**
 * The five options behind one unit (R36, AC-S3-14), rendered from the SERVER's payload.
 *
 * Phase 2: `lib/ladderOptionsMock.ts` is gone and the board carries `options[]` for real, so
 * what this pins is the contract at the boundary rather than a fixture's shape:
 *
 * * the rows arrive in STEP ORDER and the client never sorts them - a table that re-sorted
 *   would put a different option at the top from the one the engine walked first;
 * * at most ONE row is chosen, and the pill says which;
 * * a blank is a blank: `days_late` 0 and a null date render as nothing, because a column of
 *   noughts reads as arithmetic to check rather than as the exception it exists to show;
 * * `options` absent (a frozen snapshot, written before v7.1) renders NOTHING, rather than an
 *   empty five-row table claiming a walk nobody made.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { BoardLadderOption } from '../../_shared/types/fulfilmentPlanning.types';

import { BoardLadderOptionsTable } from './BoardLadderOptionsTable';

/** The server's own order, deliberately NOT alphabetical and NOT sorted by date. */
const OPTIONS: BoardLadderOption[] = [
  {
    step: 'use',
    label: 'Use our locations',
    whole: false,
    fulfil_date: null,
    days_late: null,
    debt_so_number: null,
    debt_month: null,
    chosen: false,
  },
  {
    step: 'order_borrow',
    label: 'Borrow on hand from a later order',
    whole: true,
    fulfil_date: '2026-09-02',
    days_late: 0,
    debt_so_number: 'SO414285',
    debt_month: '2026-11',
    chosen: true,
  },
  {
    step: 'supply_borrow',
    label: 'Borrow incoming from a later order',
    whole: false,
    fulfil_date: null,
    days_late: null,
    debt_so_number: null,
    debt_month: null,
    chosen: false,
  },
  {
    step: 'pool',
    label: 'Take from the pool',
    whole: false,
    fulfil_date: null,
    days_late: null,
    debt_so_number: null,
    debt_month: null,
    chosen: false,
  },
  {
    step: 'buy',
    label: 'Buy',
    whole: true,
    fulfil_date: '2026-11-27',
    days_late: 32,
    debt_so_number: null,
    debt_month: null,
    chosen: false,
  },
];

const KEY = 'contrib-1';

function rowSteps(): string[] {
  return Array.from(
    screen.getByTestId(`ladder-options-${KEY}`).querySelectorAll('tbody tr'),
  ).map((row) => row.getAttribute('data-testid') ?? '');
}

describe('BoardLadderOptionsTable', () => {
  it('renders the payload order unsorted, one row per step', () => {
    render(<BoardLadderOptionsTable options={OPTIONS} contributionKey={KEY} />);

    expect(rowSteps()).toEqual([
      `ladder-option-${KEY}-use`,
      `ladder-option-${KEY}-order_borrow`,
      `ladder-option-${KEY}-supply_borrow`,
      `ladder-option-${KEY}-pool`,
      `ladder-option-${KEY}-buy`,
    ]);
  });

  it('marks exactly one option as chosen', () => {
    render(<BoardLadderOptionsTable options={OPTIONS} contributionKey={KEY} />);

    expect(screen.getAllByTestId(`ladder-option-chosen-${KEY}`)).toHaveLength(1);
    expect(
      screen
        .getByTestId(`ladder-option-${KEY}-order_borrow`)
        .querySelector(`[data-testid="ladder-option-chosen-${KEY}"]`),
    ).not.toBeNull();
  });

  it('names the donor and the month a borrow puts the debt in, and nobody else', () => {
    render(<BoardLadderOptionsTable options={OPTIONS} contributionKey={KEY} />);

    expect(
      screen.getByTestId(`ladder-option-debt-${KEY}-order_borrow`).textContent,
    ).toContain('SO414285');
    expect(
      screen.getByTestId(`ladder-option-debt-${KEY}-order_borrow`).textContent,
    ).toContain('Nov 2026');
    expect(screen.getByTestId(`ladder-option-debt-${KEY}-buy`).textContent).toBe(
      '-',
    );
  });

  it('renders a blank for 0 days late and a dash for a step that offered nothing', () => {
    render(<BoardLadderOptionsTable options={OPTIONS} contributionKey={KEY} />);

    expect(
      screen.getByTestId(`ladder-option-late-${KEY}-order_borrow`).textContent,
    ).toBe('');
    expect(screen.getByTestId(`ladder-option-late-${KEY}-use`).textContent).toBe(
      '',
    );
    expect(screen.getByTestId(`ladder-option-date-${KEY}-use`).textContent).toBe(
      '-',
    );
    expect(
      screen.getByTestId(`ladder-option-late-${KEY}-buy`).textContent,
    ).toBe('32');
  });

  it('says Yes or No to whole, per step', () => {
    render(<BoardLadderOptionsTable options={OPTIONS} contributionKey={KEY} />);

    expect(
      screen.getByTestId(`ladder-option-whole-${KEY}-order_borrow`).textContent,
    ).toBe('Yes');
    expect(
      screen.getByTestId(`ladder-option-whole-${KEY}-supply_borrow`).textContent,
    ).toBe('No');
  });

  it('renders nothing at all when the payload carries no options', () => {
    const { container } = render(
      <BoardLadderOptionsTable options={[]} contributionKey={KEY} />,
    );

    expect(container.firstChild).toBeNull();
    expect(screen.queryByTestId(`ladder-options-${KEY}`)).toBeNull();
  });
});
