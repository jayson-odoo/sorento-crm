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
import type { BoardContribution, BoardSource } from '../../_shared/types/fulfilmentPlanning.types';

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

    // The five the captain named, in the order the ladder asks its questions - `incoming`
    // trails them (section 1e's own ORDER: it is history, not a rung the engine walks).
    expect(cards).toEqual([
      'decision-strip-own',
      'decision-strip-shared',
      'decision-strip-borrow_other',
      'decision-strip-borrow_order',
      'decision-strip-buy',
      'decision-strip-incoming',
    ]);
  });

  it('presses a card and reports which kind was pressed', () => {
    const { onToggle } = renderStrip([rich]);

    screen.getByTestId('decision-strip-shared').click();

    expect(onToggle).toHaveBeenCalledWith('shared');
  });

  it('keeps the incoming card in the strip, disabled, at 0 and 0', () => {
    // Nothing here is `incoming` - the LIVE ladder never composes it (AC-V2) and no
    // decided line on this board is frozen under an older one.
    renderStrip([rich]);

    const incoming = screen.getByTestId('decision-strip-incoming');
    expect(incoming).toBeInTheDocument();
    expect(incoming).toBeDisabled();
  });

  // CAPTAIN'S OPEN QUESTION, not a defect this suite fixes: the brief this test was
  // written against says a 0/0 card is HIDDEN. `DecisionStrip.tsx`'s own docstring rules
  // the opposite on purpose ("A CARD READING NOTHING IS DISABLED RATHER THAN HIDDEN ...
  // it keeps its place, because a card that came and went would move every card beside
  // it" - `SupplyKindCard.tsx` lines 15-18 say the same thing). Marked failing so the
  // discrepancy is visible rather than silently asserting the code's own behaviour under
  // a docstring that claims the brief's.
  it.fails(
    'hides the incoming card entirely when it is 0 and 0 (captain\'s ruling per the brief; ' +
      'current code disables it in place instead - DecisionStrip.tsx / SupplyKindCard.tsx, ' +
      'both by deliberate docstring, not oversight)',
    () => {
      renderStrip([rich]);

      expect(screen.queryByTestId('decision-strip-incoming')).not.toBeInTheDocument();
    },
  );
});
