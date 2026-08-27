/**
 * The board's decision strip, as CARDS (`PLAN-scm-cs-planning-uat.md` section 1e, AC-V7,
 * AC-D2). `_shared/lib/decisionStrip.test.ts` already pins the arithmetic; this file pins
 * the RENDER: the fixed reading order the captain's second ruling asked for ("own location
 * -> pool -> borrow other location -> borrow other order -> Buy"), and what a card with
 * nothing on it does.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { DecisionStrip } from './DecisionStrip';
import type {
  BoardContribution,
  BoardLineDecision,
  BoardSource,
} from '../../_shared/types/fulfilmentPlanning.types';

function source(over: Partial<BoardSource> = {}): BoardSource {
  return { kind: 'reserve', qty: '10', reason: 'because', ...over };
}

function line(over: Partial<BoardContribution> = {}): BoardContribution {
  return {
    key: 'so-1:10',
    sales_order_id: 'so-1',
    so_number: 'SO416191',
    line_no: 10,
    item_code: 'CB2805A-DIY',
    qty: '13',
    qty_outstanding: '13',
    fulfilment_location: 'BRW-BB',
    unplannable: false,
    rank_score: 0,
    rank_factors: [],
    sources: [],
    trail: [],
    item_flags: null,
    contested: false,
    covered: false,
    decision: null,
    ...over,
  } as BoardContribution;
}

/** Every kind but `incoming` carries a quantity, so the strip has something to compare. */
const rich = line({
  key: 'rich',
  proposed: {
    components: [
      source({ kind: 'reserve', rung: 'group_take', qty: '40', location: 'DC1-BB' }),
      source({ kind: 'reserve', rung: 'pool', qty: '20', location: 'BRW' }),
      source({ kind: 'borrow', rung: 'cross_group_borrow', qty: '15', location: 'DC1-NT' }),
    ],
  },
  sources: [
    source({ kind: 'reserve', rung: 'group_take', qty: '40', location: 'DC1-BB' }),
    source({ kind: 'reserve', rung: 'pool', qty: '20', location: 'BRW' }),
    source({ kind: 'buy', rung: 'buy', qty: '15', location: null }),
  ],
});

function renderStrip(contributions: BoardContribution[]) {
  const onToggle = vi.fn();
  render(
    <DecisionStrip contributions={contributions} draft={{}} active={null} onToggle={onToggle} />,
  );
  return { onToggle };
}

describe('DecisionStrip render order', () => {
  it('reads own, shared, borrow other location, borrow other order, then Buy', () => {
    renderStrip([rich]);

    const cards = screen
      .getAllByTestId(/^decision-strip-(?!changed-)/)
      .map((node) => node.getAttribute('data-testid'));

    // The five the captain named, in the order the ladder asks its questions. `incoming`
    // is absent here because nothing on this board is that kind (section 1e's own ORDER
    // still puts it last, whenever there IS something to total).
    expect(cards).toEqual([
      'decision-strip-own',
      'decision-strip-shared',
      'decision-strip-borrow_other',
      'decision-strip-borrow_order',
      'decision-strip-buy',
    ]);
  });

  it('presses a card and reports which kind was pressed', () => {
    const { onToggle } = renderStrip([rich]);

    screen.getByTestId('decision-strip-shared').click();

    expect(onToggle).toHaveBeenCalledWith('shared');
  });

  // RULED 27 August 2026: the incoming card is HIDDEN at 0 and 0, not disabled in place.
  // The other five stand for the ladder's four questions and Buy, and a zero there is an
  // answer worth holding a position for; `incoming` is not a question. What question 1
  // draws off the water totals under "Use own location", so this card only ever counts
  // decisions frozen under an older ladder - and on a board with none it is a card about
  // nothing.
  it('hides the incoming card entirely when it is 0 and 0', () => {
    renderStrip([rich]);

    expect(screen.queryByTestId('decision-strip-incoming')).not.toBeInTheDocument();
  });

  it('keeps a question card in place, disabled, when it reads 0 and 0', () => {
    // `borrow_order` is question 4, which the engine never proposes - so it is always 0
    // and it always keeps its column, or the four questions stop reading in one order.
    renderStrip([rich]);

    const borrowOrder = screen.getByTestId('decision-strip-borrow_order');
    expect(borrowOrder).toBeInTheDocument();
    expect(borrowOrder).toBeDisabled();
  });

  it('keeps a CONFIRMED v5 water line under own, with no incoming card', () => {
    // The water ruling: question 1 hands part of the group's offer over off the SPO, and
    // the confirmation records that share with question 1's own rung. Both sides of the
    // strip must therefore total it under "Use own location" - the decided side used to
    // hard-code `incoming`, so one line read own 9 / incoming 0 on the suggested side and
    // own 0 / incoming 9 on the decided side, with an amber dot on both cards.
    const confirmed = line({
      key: 'confirmed-water',
      covered: true,
      qty: '9',
      sources: [
        source({
          kind: 'timely_spo',
          rung: 'group_take',
          qty: '9',
          location: 'BRW-SMC',
        }),
      ],
      decision: {
        revision_no: 2,
        timely_spo_qty: '9',
        incoming: [{ location: 'BRW-SMC', qty: '9', rung: 'group_take' }],
        reserve: [],
        borrow: [],
        buy_qty: '0',
      } as BoardLineDecision,
      proposed: {
        components: [
          source({
            kind: 'timely_spo',
            rung: 'group_take',
            qty: '9',
            location: 'BRW-SMC',
          }),
        ],
      },
    } as Partial<BoardContribution>);

    renderStrip([confirmed]);

    expect(screen.queryByTestId('decision-strip-incoming')).not.toBeInTheDocument();
    const own = screen.getByTestId('decision-strip-own');
    expect(own).toHaveTextContent('Suggested9');
    expect(own).toHaveTextContent('Decided9');
    expect(
      screen.queryByTestId('decision-strip-changed-own'),
    ).not.toBeInTheDocument();
  });

  it('shows the incoming card again for a line decided under an older ladder', () => {
    // A frozen `timely_spo` from a v3/v4 decision. The card is what keeps that promise
    // visible, so it comes back the moment there is one to total.
    const frozen = line({
      key: 'frozen',
      covered: true,
      decision: {
        revision_no: 3,
        timely_spo_qty: '12',
        reserve: [],
        borrow: [],
        buy_qty: '0',
      },
      sources: [source({ kind: 'timely_spo', rung: 'incoming', qty: '12', location: 'BRW-BB' })],
    } as Partial<BoardContribution>);

    renderStrip([rich, frozen]);

    expect(screen.getByTestId('decision-strip-incoming')).toBeInTheDocument();
  });
});
