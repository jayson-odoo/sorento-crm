/**
 * The board's decision strip, as CARDS (`PLAN-scm-cs-planning-uat.md` section 1e, AC-V7,
 * AC-D2). `_shared/lib/decisionStrip.test.ts` already pins the arithmetic; this file pins
 * the RENDER: the fixed reading order the captain's ruling of 30 Aug 2026 asked for - ladder
 * v7.1's own walk, left = first consideration, right = last option ("own location -> use
 * incoming -> borrow from another order -> borrow incoming -> [borrow other location] ->
 * use BRW -> Buy") - and what a card with nothing on it does.
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

/** Enough kinds carry a quantity that the strip has something to compare. */
const rich = line({
  key: 'rich',
  proposed: {
    components: [
      source({
        kind: 'reserve',
        rung: 'group_take',
        qty: '40',
        location: 'DC1-BB',
      }),
      source({ kind: 'reserve', rung: 'pool', qty: '20', location: 'BRW' }),
      source({
        kind: 'borrow',
        rung: 'cross_group_borrow',
        qty: '15',
        location: 'DC1-NT',
      }),
    ],
  },
  sources: [
    source({
      kind: 'reserve',
      rung: 'group_take',
      qty: '40',
      location: 'DC1-BB',
    }),
    source({ kind: 'reserve', rung: 'pool', qty: '20', location: 'BRW' }),
    source({ kind: 'buy', rung: 'buy', qty: '15', location: null }),
  ],
});

function renderStrip(contributions: BoardContribution[]) {
  const onToggle = vi.fn();
  render(
    <DecisionStrip
      contributions={contributions}
      draft={{}}
      active={null}
      onToggle={onToggle}
    />,
  );
  return { onToggle };
}

describe('DecisionStrip render order', () => {
  it('reads the v7.1 walk: own, incoming, borrow order, borrow incoming, BRW, Buy', () => {
    renderStrip([rich]);

    const cards = screen
      .getAllByTestId(/^decision-strip-(?!changed-)/)
      .map((node) => node.getAttribute('data-testid'));

    // LEFT = FIRST CONSIDERATION, RIGHT = LAST OPTION (the captain, 30 Aug 2026). The pool
    // used to sit second, which read as reaching for shared stock before anybody's own
    // order, and two of the walk's steps had no card at all: the group's water totalled
    // under "Use own location", and step 3's document borrow under step 2's.
    //
    // `borrow_other` is here because this fixture's frozen proposal carries a
    // `cross_group_borrow`, and it sits WITH the borrows rather than off on its own: it is
    // a borrow, just one no ladder composes any more.
    expect(cards).toEqual([
      'decision-strip-own',
      'decision-strip-incoming',
      'decision-strip-borrow_order',
      'decision-strip-borrow_incoming',
      'decision-strip-borrow_other',
      'decision-strip-shared',
      'decision-strip-buy',
    ]);
  });

  it('shows the two steps that used to be folded into their neighbours', () => {
    // Both read 0 on this board and both hold their place: `borrow_incoming` reads 0 on
    // EVERY board until S4 lands its candidates, and a step nobody can see is a step
    // nobody knows was asked.
    renderStrip([rich]);

    expect(screen.getByTestId('decision-strip-incoming')).toHaveTextContent(
      'Use incoming',
    );
    expect(
      screen.getByTestId('decision-strip-borrow_incoming'),
    ).toHaveTextContent('Borrow incoming');
    expect(screen.getByTestId('decision-strip-borrow_incoming')).toBeDisabled();
  });

  it('presses a card and reports which kind was pressed', () => {
    const { onToggle } = renderStrip([rich]);

    screen.getByTestId('decision-strip-shared').click();

    expect(onToggle).toHaveBeenCalledWith('shared');
  });

  // RE-RULED 30 August 2026: the card hidden at 0 and 0 is `borrow_other`, not `incoming`.
  // Six of the seven stand for a step of the v7.1 walk and a zero there is an answer worth
  // holding a position for. `cross_group_borrow` is not a step - v7.1 retired it, because
  // another group's FREE stock is step 1's second half now and owes nobody anything - so
  // this card only ever counts decisions frozen under an older ladder, and on a board with
  // none it is a card about nothing.
  it('hides the borrow other location card entirely when it is 0 and 0', () => {
    // A board of ladder v7.1 work only: nothing frozen carries the retired rung.
    renderStrip([
      line({
        key: 'v71-only',
        sources: [
          source({
            kind: 'reserve',
            rung: 'group_take',
            qty: '40',
            location: 'DC1-BB',
          }),
          source({ kind: 'buy', rung: 'buy', qty: '15', location: null }),
        ],
      }),
    ]);

    expect(
      screen.queryByTestId('decision-strip-borrow_other'),
    ).not.toBeInTheDocument();
    // The six steps of the walk stay, zeroes and all.
    expect(screen.getAllByTestId(/^decision-strip-(?!changed-)/)).toHaveLength(
      6,
    );
  });

  it('keeps a step card in place, disabled, when it reads 0 and 0', () => {
    // `borrow_order` is step 2, which nothing on this board took - so it reads 0 and it
    // still keeps its column, or the steps stop reading in one order.
    renderStrip([rich]);

    const borrowOrder = screen.getByTestId('decision-strip-borrow_order');
    expect(borrowOrder).toBeInTheDocument();
    expect(borrowOrder).toBeDisabled();
  });

  it('reads a CONFIRMED water line as incoming on BOTH sides, with no amber dot', () => {
    // The water ruling: step 1 hands part of the group's offer over off the SPO, and the
    // confirmation records that share with step 1's own rung. Both sides of the strip must
    // therefore total it under the SAME card - the decided side used to hard-code the rung,
    // so one line read 9 on one card's suggested half and 9 on another card's decided half,
    // with an amber dot on both.
    //
    // That card is "Use incoming" from 30 Aug 2026 (it was "Use own location"): the
    // component's own kind is `timely_spo`, and a promise resting on a ship is not the same
    // promise as one resting on a floor even though one rung drew them both.
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

    const incoming = screen.getByTestId('decision-strip-incoming');
    expect(incoming).toHaveTextContent('Suggested9');
    expect(incoming).toHaveTextContent('Decided9');
    expect(
      screen.queryByTestId('decision-strip-changed-incoming'),
    ).not.toBeInTheDocument();
    // And NOT under the floor card: the split is the whole point of the second card.
    const own = screen.getByTestId('decision-strip-own');
    expect(own).toHaveTextContent('Suggested0');
    expect(own).toHaveTextContent('Decided0');
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
      sources: [
        source({
          kind: 'timely_spo',
          rung: 'incoming',
          qty: '12',
          location: 'BRW-BB',
        }),
      ],
    } as Partial<BoardContribution>);

    renderStrip([rich, frozen]);

    expect(screen.getByTestId('decision-strip-incoming')).toBeInTheDocument();
  });
});

/**
 * AC-RB2 (`PLAN-scm-oi-handshake.md` section 11): the strip counts the lines purchasing
 * refused, so CS sees the bounce without visiting Order Inquiries.
 *
 * Beside the cards rather than on one: a refusal is not a kind of supply, it is a line with
 * no supply decided at all. Two figures the count is NOT allowed to be: the number of cells
 * (a cell holds several lines) and the number of rows (one line, several inquiry rows).
 */
describe('DecisionStrip: refused lines', () => {
  const refused = (key: string) =>
    line({
      key,
      order_inquiry: {
        inquiry_no: 'OI-000101',
        state: 'raised',
        ack_state: 'rejected',
        rejected_by_name: 'Joey',
        rejected_reason: 'No supplier until November',
      },
    });

  it('counts the refused lines', () => {
    renderStrip([rich, refused('line-a'), refused('line-b')]);

    expect(screen.getByTestId('decision-strip-rejected')).toHaveTextContent(
      '2 rejected',
    );
  });

  it('says nothing when nobody has refused anything', () => {
    renderStrip([rich]);

    expect(screen.queryByTestId('decision-strip-rejected')).toBeNull();
  });

  it('drops back to nothing once CS has answered the refusal', () => {
    // The board clears `ack_state` on a line CS has decided again, so the count follows it
    // down with no second rule of its own.
    renderStrip([
      rich,
      line({
        key: 'answered',
        order_inquiry: {
          inquiry_no: 'OI-000101',
          state: 'raised',
          ack_state: null,
          rejected_by_name: null,
          rejected_reason: null,
        },
      }),
    ]);

    expect(screen.queryByTestId('decision-strip-rejected')).toBeNull();
  });
});
