/**
 * Amending one board line (the captain, 18 August 2026: "the amend is not working, I should be
 * able to amend the decision and quantity, like I can decide to reserve, or buy, or borrow").
 *
 * What was there was a single Reserve box under a 25-row table, which the planner never saw
 * move, and which could express one of the four verbs. What is here is the per-line editor the
 * sheet has always had, opened over the breakdown as its own dialog, in the SAME order the
 * sheet lists the components: incoming, reserve, borrow, buy.
 *
 * The three things pinned hardest, because each was a way the old form said no:
 *
 *   - the line's OWN location is always a Reserve row, even when the engine reserved nothing
 *     there, because that is the amendment a planner most often wants to make;
 *   - a Borrow can be composed at all, with the mandatory reason AC-B09 demands;
 *   - Save is shut while the components do not add up to what is owed, so an amendment cannot
 *     leave a quantity owed by nobody.
 */
import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

import { BoardAmendDialog } from './BoardAmendDialog';
import { buildBoard, type BoardDemandLine } from '../../_shared/lib/__testsupport__/boardFixture';
import type { BoardContribution } from '../../_shared/types/fulfilmentPlanning.types';

const TODAY = '2026-08-18';

const DONOR = {
  source: 'other_location' as const,
  warehouse_code: 'BRW-IB',
  warehouse_id: 'wh-ib',
  free_qty: '25',
  donor_impact: { free_before: '25', free_after_full_borrow: '0', committed_qty: '0' },
};

function demand(overrides: Partial<BoardDemandLine> = {}): BoardDemandLine {
  return {
    sales_order_id: 'so-a',
    so_number: 'SO403765',
    line_no: 1,
    item_code: 'B2155-NL-BLUE',
    qty: '100',
    required_date: '2026-09-04',
    fulfilment_location: 'BRW-BB',
    ...overrides,
  };
}

function contributionOf(
  freeStock: Record<string, string> = {},
  overrides: Partial<BoardContribution> = {},
  demandOverrides: Partial<BoardDemandLine> = {},
): BoardContribution {
  const base = buildBoard([demand(demandOverrides)], { today: TODAY, freeStock }).cells[0]
    .contributions[0];
  return { ...base, ...overrides };
}

function renderDialog(contribution: BoardContribution) {
  const onSave = vi.fn();
  const onCancel = vi.fn();
  render(
    <BoardAmendDialog contribution={contribution} onSave={onSave} onCancel={onCancel} />,
  );
  return { onSave, onCancel };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('BoardAmendDialog: what it is and what it holds', () => {
  it('is a dialog of its own, named for the line it is amending', () => {
    renderDialog(contributionOf({ 'B2155-NL-BLUE|BRW-BB': '40' }));

    const dialog = screen.getByRole('dialog');
    expect(
      within(dialog).getByText('Amend SO403765 · line 1 · B2155-NL-BLUE'),
    ).toBeInTheDocument();
  });

  it('lists the components in the order the sheet lists them', () => {
    renderDialog(contributionOf({ 'B2155-NL-BLUE|BRW-BB': '40' }));

    const labels = screen
      .getAllByTestId('amend-section')
      .map((section) => section.textContent?.split('\n')[0] ?? '');
    expect(labels).toEqual([
      expect.stringContaining('Owed'),
      expect.stringContaining('Incoming by the required date'),
      expect.stringContaining('Reserve'),
      expect.stringContaining('Borrow'),
      expect.stringContaining('Buy'),
    ]);
  });

  it('states the owed quantity and the incoming cover as facts, not as inputs', () => {
    renderDialog(
      contributionOf({ 'B2155-NL-BLUE|BRW-BB': '40' }, {
        qty_proposed_incoming: '10',
        qty_proposed_reserve: '40',
        qty_proposed_buy: '50',
      }),
    );

    expect(screen.getByTestId('amend-owed').textContent).toContain('100');
    expect(screen.getByTestId('amend-incoming').textContent).toContain('10');
    expect(screen.queryByLabelText(/Incoming/)).not.toBeInTheDocument();
  });

  it('opens on the engine’s proposal rather than on an empty form', () => {
    renderDialog(contributionOf({ 'B2155-NL-BLUE|BRW-BB': '40' }));

    expect(screen.getByLabelText('Reserve at BRW-BB')).toHaveValue(40);
    expect(screen.getByLabelText('Buy')).toHaveValue(60);
  });
});

describe('BoardAmendDialog: the Reserve', () => {
  it('offers the line’s own location even when the proposal reserved nothing there', () => {
    // The whole quantity is bought. This is the amendment a planner most wants to make, and
    // the old form had no row for it at all.
    renderDialog(contributionOf({}));

    expect(screen.getByLabelText('Reserve at BRW-BB')).toHaveValue(0);
    expect(screen.getByLabelText('Buy')).toHaveValue(100);
  });

  it('states what was left for this line at its own location', () => {
    renderDialog(
      contributionOf({ 'B2155-NL-BLUE|BRW-BB': '40' }, { available_to_this_line: '627' }),
    );

    expect(screen.getByText('627 left for this line')).toBeInTheDocument();
  });

  it('offers one input per warehouse the proposal drew on', () => {
    renderDialog(
      contributionOf({}, {
        qty_proposed_reserve: '70',
        qty_proposed_buy: '30',
        sources: [
          {
            kind: 'reserve',
            qty: '40',
            location: 'BRW-BB',
            warehouse_id: 'wh-own',
            reason: 'Free stock at BRW-BB covers this much.',
          },
          {
            kind: 'reserve',
            qty: '30',
            location: 'BRW',
            warehouse_id: 'wh-pool',
            reason: 'The dealer pool covers the rest.',
          },
          { kind: 'buy', qty: '30', location: null, reason: 'The residual is bought.' },
        ],
      }),
    );

    expect(screen.getByLabelText('Reserve at BRW-BB')).toHaveValue(40);
    expect(screen.getByLabelText('Reserve at BRW')).toHaveValue(30);
  });

  it('says so when the sales order names no warehouse to reserve at', () => {
    renderDialog(contributionOf({}, {}, { fulfilment_location: null }));
    expect(
      screen.getByText('The sales order states no warehouse for this line.'),
    ).toBeInTheDocument();
  });
});

describe('BoardAmendDialog: the Borrow', () => {
  it('renders the section with a stated absence when no donor holds any', () => {
    renderDialog(contributionOf({ 'B2155-NL-BLUE|BRW-BB': '40' }));
    expect(
      screen.getByText('No other location or project holds free stock of this item.'),
    ).toBeInTheDocument();
  });

  it('takes a borrow from a listed donor, with the reason AC-B09 demands', () => {
    const { onSave } = renderDialog(
      contributionOf({ 'B2155-NL-BLUE|BRW-BB': '40' }, { borrow_candidates: [DONOR] }),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Add a borrow' }));
    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '10' } });
    fireEvent.change(screen.getByLabelText(/^Reason/), {
      target: { value: 'The site next door can wait a week.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add the borrow' }));

    expect(screen.getByLabelText('Borrow from BRW-IB')).toHaveValue(10);

    // 100 owed = 40 reserve + 10 borrow + 60 buy is 10 over, so the Buy comes down by 10.
    fireEvent.change(screen.getByLabelText('Buy'), { target: { value: '50' } });
    fireEvent.change(screen.getByLabelText(/^Why this differs/), {
      target: { value: 'Borrowing rather than buying what is already in the group.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save the amendment' }));

    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        verdict: 'amended',
        borrow: [
          expect.objectContaining({
            source: 'other_location',
            warehouse_id: 'wh-ib',
            qty: '10',
            reason: 'The site next door can wait a week.',
          }),
        ],
        buy_qty: '50',
      }),
    );
  });

  it('offers no donor the confirmation could not name', () => {
    renderDialog(
      contributionOf({ 'B2155-NL-BLUE|BRW-BB': '40' }, {
        borrow_candidates: [
          { source: 'other_location', warehouse_code: 'BRW-IB', free_qty: '25' },
        ],
      }),
    );

    expect(
      screen.getByText('No other location or project holds free stock of this item.'),
    ).toBeInTheDocument();
  });
});

describe('BoardAmendDialog: the balance, and what it stops', () => {
  it('states the balance and keeps it live as the quantities change', () => {
    renderDialog(contributionOf({ 'B2155-NL-BLUE|BRW-BB': '40' }));

    expect(screen.getByTestId('amend-balance').textContent).toBe(
      '100 owed = 0 incoming + 40 reserve + 0 borrow + 60 buy',
    );

    fireEvent.change(screen.getByLabelText('Reserve at BRW-BB'), { target: { value: '10' } });
    expect(screen.getByTestId('amend-balance').textContent).toBe(
      '100 owed = 0 incoming + 10 reserve + 0 borrow + 60 buy',
    );
  });

  it('will not save a composition that does not add up to what is owed', () => {
    const { onSave } = renderDialog(contributionOf({ 'B2155-NL-BLUE|BRW-BB': '40' }));

    fireEvent.change(screen.getByLabelText('Reserve at BRW-BB'), { target: { value: '10' } });

    expect(screen.getByText(/short of the open quantity by 30/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save the amendment' })).toBeDisabled();
    expect(onSave).not.toHaveBeenCalled();
  });

  it('demands a reason the moment the composition displaces the rule', () => {
    const { onSave } = renderDialog(contributionOf({ 'B2155-NL-BLUE|BRW-BB': '40' }));

    fireEvent.change(screen.getByLabelText('Reserve at BRW-BB'), { target: { value: '10' } });
    fireEvent.change(screen.getByLabelText('Buy'), { target: { value: '90' } });

    const save = screen.getByRole('button', { name: 'Save the amendment' });
    expect(save).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/^Why this differs/), {
      target: { value: 'Keeping 30 for the site that is already late.' },
    });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    expect(onSave).toHaveBeenCalledWith({
      verdict: 'amended',
      reserve_qty: '10',
      timely_spo_qty: '0',
      reserve: [{ warehouse_id: 'wh-BRW-BB', location: 'BRW-BB', qty: '10' }],
      borrow: [],
      buy_qty: '90',
      reason: 'Keeping 30 for the site that is already late.',
    });
  });

  it('takes the proposal as it stands without demanding a reason for agreeing', () => {
    const { onSave } = renderDialog(contributionOf({ 'B2155-NL-BLUE|BRW-BB': '40' }));

    fireEvent.click(screen.getByRole('button', { name: 'Save the amendment' }));

    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        verdict: 'amended',
        reserve: [{ warehouse_id: 'wh-BRW-BB', location: 'BRW-BB', qty: '40' }],
        buy_qty: '60',
        reason: undefined,
      }),
    );
  });

  it('closes without deciding anything on Cancel', () => {
    const { onSave, onCancel } = renderDialog(contributionOf({}));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalled();
    expect(onSave).not.toHaveBeenCalled();
  });
});
