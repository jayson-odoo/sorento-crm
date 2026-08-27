/**
 * BoardDecisionPill (PLAN R6, UAC C2/C3): status only, five labels, no revision number, and a
 * warning flag the draft OR the frozen decision can carry.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { BoardDecisionPill } from './BoardDecisionPill';
import type {
  BoardContribution,
  BoardLineDecision,
} from '../../_shared/types/fulfilmentPlanning.types';

const KEY = 'so-a|1|WESERP10B|2026-08-31';

function contributionOf(overrides: Partial<BoardContribution> = {}): BoardContribution {
  return {
    key: KEY,
    sales_order_id: 'so-a',
    so_number: 'SO403340',
    line_no: 1,
    item_code: 'WESERP10B',
    qty: '100',
    qty_outstanding: '100',
    fulfilment_location: 'BRW-BB',
    fulfilment_warehouse_id: 'wh-BRW-BB',
    unplannable: false,
    sources: [],
    contested: false,
    rank_score: 0,
    rank_factors: [],
    covered: false,
    decision: null,
    ...overrides,
  };
}

describe('BoardDecisionPill: the five labels (C3, R6)', () => {
  it('reads Suggested when nobody has decided anything yet, on the board or in the database', () => {
    render(<BoardDecisionPill contribution={contributionOf()} decision={null} />);
    expect(screen.getByTestId(`decision-pill-${KEY}`)).toHaveTextContent('Suggested');
  });

  it('reads Approved', () => {
    render(
      <BoardDecisionPill
        contribution={contributionOf()}
        decision={{ verdict: 'approved' }}
      />,
    );
    expect(screen.getByTestId(`decision-pill-${KEY}`)).toHaveTextContent('Approved');
  });

  it('reads Amended', () => {
    render(
      <BoardDecisionPill
        contribution={contributionOf()}
        decision={{ verdict: 'amended' }}
      />,
    );
    expect(screen.getByTestId(`decision-pill-${KEY}`)).toHaveTextContent('Amended');
  });

  it('reads Rejected', () => {
    render(
      <BoardDecisionPill
        contribution={contributionOf()}
        decision={{ verdict: 'rejected', reason: 'Cancelled' }}
      />,
    );
    expect(screen.getByTestId(`decision-pill-${KEY}`)).toHaveTextContent('Rejected');
  });

  it('reads Confirmed for a covered line the draft has not touched', () => {
    render(
      <BoardDecisionPill
        contribution={contributionOf({
          covered: true,
          decision: { revision_no: 3, timely_spo_qty: '0', reserve: [], borrow: [], buy_qty: '10' },
        })}
        decision={null}
      />,
    );
    expect(screen.getByTestId(`decision-pill-${KEY}`)).toHaveTextContent('Confirmed');
  });
});

describe('BoardDecisionPill: no "rev" (R6)', () => {
  it('never prints a revision number beside Confirmed', () => {
    render(
      <BoardDecisionPill
        contribution={contributionOf({
          covered: true,
          decision: { revision_no: 3, timely_spo_qty: '0', reserve: [], borrow: [], buy_qty: '10' },
        })}
        decision={null}
      />,
    );
    const pill = screen.getByTestId(`decision-pill-${KEY}`);
    expect(pill.textContent).toBe('Confirmed');
    expect(pill.textContent).not.toContain('rev');
  });
});

describe('BoardDecisionPill: a line with no location', () => {
  it('reads "Needs a location" rather than any verdict', () => {
    render(
      <BoardDecisionPill
        contribution={contributionOf({ unplannable: true, fulfilment_location: null })}
        decision={null}
      />,
    );
    expect(screen.getByText('Needs a location')).toBeInTheDocument();
  });
});

describe('BoardDecisionPill: the warning flag (C10)', () => {
  it('shows the flag from the draft decision', () => {
    render(
      <BoardDecisionPill
        contribution={contributionOf()}
        decision={{ verdict: 'approved', suspected_system_issue: true }}
      />,
    );
    expect(screen.getByTestId(`decision-flag-${KEY}`)).toBeInTheDocument();
  });

  it('shows the flag from the frozen contribution.decision after a reload, with no draft entry', () => {
    const frozen: BoardLineDecision = {
      revision_no: 1,
      timely_spo_qty: '0',
      reserve: [],
      borrow: [],
      buy_qty: '10',
      suspected_system_issue: true,
    };
    render(
      <BoardDecisionPill
        contribution={contributionOf({ covered: true, decision: frozen })}
        decision={null}
      />,
    );
    expect(screen.getByTestId(`decision-flag-${KEY}`)).toBeInTheDocument();
  });

  it('shows no flag at all for an ordinary decision', () => {
    render(
      <BoardDecisionPill
        contribution={contributionOf()}
        decision={{ verdict: 'approved' }}
      />,
    );
    expect(screen.queryByTestId(`decision-flag-${KEY}`)).not.toBeInTheDocument();
  });
});
