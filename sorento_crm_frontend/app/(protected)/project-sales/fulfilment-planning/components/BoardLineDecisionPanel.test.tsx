/**
 * The decision on one contributing line, taken IN THE ROW (PLAN section 3.C, ruling R7).
 *
 * The fixture is the plan's own canonical example (UAC header line, R1): SO404352 line 22,
 * SRTWB7518, BRW-AM on hand 10 with SO383850 holding 1 there (so 9 available, B1), the shared
 * pool at BRW holding 16. The engine's suggestion is Reserve 9 at BRW-AM plus Reserve 15 at
 * BRW (the 24 outstanding, C7/C8's own numbers), so every test below traces to a UAC id.
 */
import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { BoardDecisionPill } from './BoardDecisionPill';
import { BoardLineDecisionPanel } from './BoardLineDecisionPanel';
import type {
  BoardCellLocation,
  BoardContribution,
  BoardDecision,
  BoardLineDecision,
} from '../../_shared/types/fulfilmentPlanning.types';

const KEY = 'so-a|22|SRTWB7518|2026-06-29';

function contributionOf(
  overrides: Partial<BoardContribution> = {},
): BoardContribution {
  return {
    key: KEY,
    sales_order_id: 'so-a',
    so_number: 'SO404352',
    customer_name: 'ABC SDN BHD',
    project_label: null,
    agent_code: 'AG01',
    line_no: 22,
    item_code: 'SRTWB7518',
    qty: '24',
    qty_ordered: '24',
    qty_delivered: '0',
    qty_outstanding: '24',
    project_line_id: 'pl-so-a-22',
    required_date: '2026-06-29',
    is_past: false,
    fulfilment_location: 'BRW-AM',
    fulfilment_warehouse_id: 'wh-BRW-AM',
    unplannable: false,
    priority: null,
    sources: [
      {
        kind: 'reserve',
        qty: '9',
        location: 'BRW-AM',
        warehouse_id: 'wh-BRW-AM',
        reason:
          'Free unclaimed stock at BRW-AM covers this much by the delivery date.',
      },
      {
        kind: 'reserve',
        qty: '15',
        location: 'BRW',
        warehouse_id: 'wh-BRW',
        reason: 'The shared pool at BRW covers this much within its cap.',
      },
    ],
    qty_proposed_reserve: '24',
    qty_proposed_incoming: '0',
    qty_proposed_buy: '0',
    contested: false,
    rank_score: 0,
    rank_factors: [],
    covered: false,
    decision: null,
    order_inquiry: null,
    item_flags: null,
    borrow_candidates: [],
    ...overrides,
  };
}

const LOCATIONS: BoardCellLocation[] = [
  {
    location: 'BRW-AM',
    warehouse_id: 'wh-BRW-AM',
    qty: '0',
    available_qty: '9',
    qty_free: '9',
    qty_free_remaining: '9',
  },
  {
    location: 'BRW',
    warehouse_id: 'wh-BRW',
    qty: '0',
    available_qty: '16',
    qty_free: '16',
    qty_free_remaining: '16',
  },
];

function renderPanel(
  overrides: Partial<BoardContribution> = {},
  decision: BoardDecision | null = null,
) {
  const onDecide = vi.fn();
  const onDirtyChange = vi.fn();
  render(
    <BoardLineDecisionPanel
      contribution={contributionOf(overrides)}
      decision={decision}
      locations={LOCATIONS}
      onDecide={onDecide}
      onDirtyChange={onDirtyChange}
    />,
  );
  return { onDecide, onDirtyChange };
}

describe('BoardLineDecisionPanel: no read-only strip', () => {
  it('does not repeat Ordered, Delivered, Outstanding or Incoming - the row above states them', () => {
    renderPanel({
      qty_ordered: '24',
      qty_delivered: '0',
      qty_outstanding: '24',
    });

    const panel = screen.getByTestId(`line-decision-${KEY}`);
    expect(panel).not.toHaveTextContent('Ordered');
    expect(panel).not.toHaveTextContent('Delivered');
    expect(panel).not.toHaveTextContent('Outstanding');
    expect(panel).not.toHaveTextContent('Incoming by the delivery date');
  });
});

describe('BoardLineDecisionPanel: Reserve inputs carry the server figure beside them (C4, B1)', () => {
  it('opens on the suggestion, and shows what each location has available', () => {
    renderPanel();

    expect(screen.getByLabelText('Reserve at BRW-AM')).toHaveValue(9);
    expect(screen.getByLabelText('Reserve at BRW')).toHaveValue(15);
    const panel = screen.getByTestId(`line-decision-${KEY}`);
    expect(panel).toHaveTextContent('9 available');
    expect(panel).toHaveTextContent('16 available');
  });
});

/**
 * TWO VERBS (C9), because the captain would not press two Saves: "if the suggestion is same as
 * decision then it is approved, if suggestion different from decision then it is amended, so I
 * just click on 1 button". So the comparison takes the verdict, and these tests assert WHICH
 * verdict one press produces rather than which button was chosen.
 */
describe('BoardLineDecisionPanel: the two verbs (C9)', () => {
  it('Save on the untouched suggestion approves it, with no reason and no flag', () => {
    const { onDecide } = renderPanel();

    fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));

    // D11: an approved decision carries the suggested COMPOSITION too, not only the verdict -
    // `so_supply_decision_drafts.decision` is read verbatim by the SO page's own "Decided"
    // column, and a bare `{verdict:'approved'}` read there as no components at all.
    expect(onDecide).toHaveBeenCalledWith(
      expect.objectContaining({
        verdict: 'approved',
        suspected_system_issue: false,
        reserve: expect.arrayContaining([
          expect.objectContaining({ warehouse_id: 'wh-BRW-AM', qty: '9' }),
          expect.objectContaining({ warehouse_id: 'wh-BRW', qty: '15' }),
        ]),
        borrow: [],
        buy_qty: '0',
      }),
    );
  });

  it('Save on a changed composition amends it, once it balances and carries a reason', () => {
    const { onDecide } = renderPanel();

    fireEvent.change(screen.getByLabelText('Reserve at BRW-AM'), {
      target: { value: '5' },
    });
    fireEvent.change(screen.getByLabelText('Reserve at BRW'), {
      target: { value: '19' },
    });
    fireEvent.change(screen.getByLabelText(/^Why this differs/), {
      target: { value: 'The site asked for less from BRW-AM.' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));

    expect(onDecide).toHaveBeenCalledWith(
      expect.objectContaining({
        verdict: 'amended',
        reserve: expect.arrayContaining([
          expect.objectContaining({ warehouse_id: 'wh-BRW-AM', qty: '5' }),
          expect.objectContaining({ warehouse_id: 'wh-BRW', qty: '19' }),
        ]),
        reason: 'The site asked for less from BRW-AM.',
      }),
    );
  });

  it('reject requires a reason, and is disabled without one', () => {
    const { onDecide } = renderPanel();

    const reject = screen.getByRole('button', { name: 'Reject' });
    expect(reject).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/^Why this differs/), {
      target: { value: 'The customer cancelled this line.' },
    });
    expect(reject).toBeEnabled();
    fireEvent.click(reject);

    expect(onDecide).toHaveBeenCalledWith({
      verdict: 'rejected',
      reason: 'The customer cancelled this line.',
      suspected_system_issue: false,
    });
  });
});

/**
 * D11 (gap found in D10's report). `_saved_components` (`sales_order_service.py`) reads the
 * SAVED decision JSON verbatim for the SO page's own "Decided" column, and an approval that
 * posted only `{verdict: 'approved'}` read as no components at all - the SO page showed "-"
 * beside a pill that already read Saved. An approved decision now carries the suggested
 * COMPOSITION too, the same way `confirmLinesFor` already derives one for Confirm
 * (`decisionFromAmendDraft(suggestionDraftFrom(contribution), '')`), so the two never disagree
 * about what an approval actually composed.
 */
describe('BoardLineDecisionPanel: an approved draft carries the suggested composition (D11)', () => {
  it('approving a Reserve-only suggestion carries the reserve row and a zero Buy', () => {
    const onDecide = vi.fn();
    render(
      <BoardLineDecisionPanel
        contribution={contributionOf({
          key: 'so-a|7|BRW3|2026-06-29',
          line_no: 7,
          item_code: 'BRW3',
          qty: '3',
          qty_ordered: '3',
          qty_outstanding: '3',
          sources: [
            {
              kind: 'reserve',
              qty: '3',
              location: 'BRW',
              warehouse_id: 'wh-BRW',
              reason: 'The shared pool at BRW covers this line.',
            },
          ],
          qty_proposed_reserve: '3',
          qty_proposed_incoming: '0',
          qty_proposed_buy: '0',
        })}
        decision={null}
        locations={LOCATIONS}
        onDecide={onDecide}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));

    expect(onDecide).toHaveBeenCalledWith(
      expect.objectContaining({
        verdict: 'approved',
        reserve: [expect.objectContaining({ location: 'BRW', qty: '3' })],
        buy_qty: '0',
      }),
    );
  });

  it('approving a Buy-only suggestion carries the Buy quantity and no reserve', () => {
    const onDecide = vi.fn();
    render(
      <BoardLineDecisionPanel
        contribution={contributionOf({
          key: 'so-a|8|BUY3|2026-06-29',
          line_no: 8,
          item_code: 'BUY3',
          qty: '3',
          qty_ordered: '3',
          qty_outstanding: '3',
          sources: [
            {
              kind: 'buy',
              qty: '3',
              location: null,
              warehouse_id: null,
              reason: 'Nothing on hand covers this line.',
            },
          ],
          qty_proposed_reserve: '0',
          qty_proposed_incoming: '0',
          qty_proposed_buy: '3',
        })}
        decision={null}
        locations={LOCATIONS}
        onDecide={onDecide}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));

    expect(onDecide).toHaveBeenCalledWith(
      expect.objectContaining({
        verdict: 'approved',
        reserve: [],
        buy_qty: '3',
      }),
    );
  });

  it('leaves an amended save unchanged - it already composes everything it posts', () => {
    const { onDecide } = renderPanel();

    fireEvent.change(screen.getByLabelText('Reserve at BRW-AM'), {
      target: { value: '5' },
    });
    fireEvent.change(screen.getByLabelText('Reserve at BRW'), {
      target: { value: '19' },
    });
    fireEvent.change(screen.getByLabelText(/^Why this differs/), {
      target: { value: 'The site asked for less from BRW-AM.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));

    expect(onDecide).toHaveBeenCalledWith(
      expect.objectContaining({
        verdict: 'amended',
        reserve: expect.arrayContaining([
          expect.objectContaining({ warehouse_id: 'wh-BRW-AM', qty: '5' }),
          expect.objectContaining({ warehouse_id: 'wh-BRW', qty: '19' }),
        ]),
      }),
    );
  });
});

/**
 * C7, in the UAC's own words: "Editing Reserve BRW-AM from 9 to 5 shows the hint 4 short and
 * Save is disabled; setting BRW to 19 clears the hint, and Save enables once the reason is
 * typed (a composition that differs from the suggestion always needs the reason)."
 *
 * D7 (captain, 3 Sep) supersedes the FIRST half of that: Buy now follows the remainder, so
 * dropping BRW-AM to 5 no longer leaves the line "short" - the 4 it gave up moves into a
 * derived Buy of 4 (`edit()`), which balances the line again. What still refuses Save is the
 * whole-line rule itself: neither location here states a pool allowance (`LOCATIONS` carries
 * no `where: 'site_pool'` row), so 20 from stock beside a Buy of 4 is the mix R-C exists to
 * refuse, and it is refused for that reason rather than for falling short.
 */
describe('BoardLineDecisionPanel: the balance hint and Save gating (C7, D7)', () => {
  it('moves the gap into a derived Buy instead of reading short, and still refuses to save the mix', () => {
    renderPanel();

    fireEvent.change(screen.getByLabelText('Reserve at BRW-AM'), {
      target: { value: '5' },
    });

    expect(
      screen.queryByTestId(`line-decision-hint-${KEY}`),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId(`line-buy-derived-${KEY}`)).toHaveTextContent(
      'Buy 4',
    );
    expect(
      screen.getByText(/either met wholly from stock or wholly bought/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Save decision' }),
    ).toBeDisabled();
  });

  it('shows "N over" once a composition exceeds it', () => {
    renderPanel();

    fireEvent.change(screen.getByLabelText('Reserve at BRW'), {
      target: { value: '30' },
    });

    expect(screen.getByTestId(`line-decision-hint-${KEY}`)).toHaveTextContent(
      '15 over',
    );
  });

  it('clears the hint once the composition balances again, and enables Save once a reason is typed', () => {
    renderPanel();

    fireEvent.change(screen.getByLabelText('Reserve at BRW-AM'), {
      target: { value: '5' },
    });
    fireEvent.change(screen.getByLabelText('Reserve at BRW'), {
      target: { value: '19' },
    });

    expect(
      screen.queryByTestId(`line-decision-hint-${KEY}`),
    ).not.toBeInTheDocument();
    const save = screen.getByRole('button', { name: 'Save decision' });
    expect(save).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/^Why this differs/), {
      target: { value: 'Agreed a smaller own-location share with the site.' },
    });
    expect(save).toBeEnabled();
  });

  it('never needs a reason to save the suggestion as it stands', () => {
    renderPanel();

    // The composition on open IS the suggestion, so the press is an approval: there is
    // nothing to justify, and Save is enabled with nothing typed at all.
    expect(
      screen.getByRole('button', { name: 'Save decision' }),
    ).toBeEnabled();
  });
});

/**
 * C10: the flag rides on every verdict, and survives a reload because it is echoed on the
 * contribution's own frozen decision, not only in this session's draft.
 */
describe('BoardLineDecisionPanel: the suspected-system-issue flag (C10)', () => {
  function checkbox() {
    return screen.getByRole('checkbox', {
      name: 'This might be a system problem, flag it for investigation',
    });
  }

  it('carries the flag on an approval (the suggestion, untouched)', () => {
    const { onDecide } = renderPanel();

    fireEvent.click(checkbox());
    fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));

    expect(onDecide).toHaveBeenCalledWith(
      expect.objectContaining({
        verdict: 'approved',
        suspected_system_issue: true,
      }),
    );
  });

  it('carries the flag on a saved amendment', () => {
    const { onDecide } = renderPanel();

    fireEvent.click(checkbox());
    fireEvent.change(screen.getByLabelText('Reserve at BRW-AM'), {
      target: { value: '5' },
    });
    fireEvent.change(screen.getByLabelText('Reserve at BRW'), {
      target: { value: '19' },
    });
    fireEvent.change(screen.getByLabelText(/^Why this differs/), {
      target: { value: 'The availability beside this line looks wrong.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));

    expect(onDecide).toHaveBeenCalledWith(
      expect.objectContaining({
        verdict: 'amended',
        suspected_system_issue: true,
      }),
    );
  });

  it('carries the flag on a rejection', () => {
    const { onDecide } = renderPanel();

    fireEvent.click(checkbox());
    fireEvent.change(screen.getByLabelText(/^Why this differs/), {
      target: { value: 'Cancelled by the customer.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }));

    expect(onDecide).toHaveBeenCalledWith(
      expect.objectContaining({
        verdict: 'rejected',
        suspected_system_issue: true,
      }),
    );
  });

  it('unticking on a covered line clears the flag, in the draft AND on screen', () => {
    // Frozen at the engine's own composition, so the untouched form IS the suggestion and the
    // press is an approval: the flag is the only thing this decision changes.
    const frozen: BoardLineDecision = {
      revision_no: 1,
      confirmed_at: '2026-08-18T02:00:00',
      timely_spo_qty: '0',
      reserve: [
        { warehouse_id: 'wh-BRW-AM', location: 'BRW-AM', qty: '9' },
        { warehouse_id: 'wh-BRW', location: 'BRW', qty: '15' },
      ],
      borrow: [],
      buy_qty: '0',
      suspected_system_issue: true,
    };
    const { onDecide } = renderPanel({ covered: true, decision: frozen });

    fireEvent.click(screen.getByRole('button', { name: 'Amend' }));
    expect(checkbox()).toBeChecked();
    fireEvent.click(checkbox());
    fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));

    // The BOOLEAN, not an absent key: `lineFor` posts `false`, so the pill must read `false`
    // rather than falling through to the frozen `true` and contradicting the body.
    // D11: the composition rides along too, even though only the flag changed.
    expect(onDecide).toHaveBeenCalledWith(
      expect.objectContaining({
        verdict: 'approved',
        suspected_system_issue: false,
        reserve: expect.arrayContaining([
          expect.objectContaining({ warehouse_id: 'wh-BRW-AM', qty: '9' }),
          expect.objectContaining({ warehouse_id: 'wh-BRW', qty: '15' }),
        ]),
        buy_qty: '0',
      }),
    );
  });

  it('shows the checkbox already ticked when the frozen decision carried the flag (persisted after reload)', () => {
    renderPanel({
      covered: true,
      decision: {
        revision_no: 1,
        confirmed_at: '2026-08-18T02:00:00',
        timely_spo_qty: '0',
        reserve: [{ warehouse_id: 'wh-BRW-AM', location: 'BRW-AM', qty: '9' }],
        borrow: [],
        buy_qty: '15',
        suspected_system_issue: true,
      },
    });

    expect(checkbox()).toBeChecked();
  });
});

/**
 * The Buy switch is a DETOUR, not a demolition: a planner trying it has not thrown away the
 * composition they typed, and the panel's own note promises the rows are still theirs when
 * they switch it back.
 */
describe('BoardLineDecisionPanel: Buy on then off restores the composition', () => {
  function buySwitch() {
    return screen.getByRole('switch', { name: 'Buy the whole line' });
  }

  it('puts back the reserve quantities, the borrow and its reason', () => {
    renderPanel({
      borrow_candidates: [
        {
          source: 'other_location',
          warehouse_code: 'MWH-AM',
          warehouse_id: 'wh-MWH-AM',
          donor_project_ref: null,
          donor_project_id: null,
          free_qty: '15',
          donor_impact: {
            free_before: '15',
            free_after_full_borrow: '0',
            committed_qty: '0',
          },
          same_agent: true,
        },
      ],
    });

    fireEvent.change(screen.getByLabelText('Reserve at BRW-AM'), {
      target: { value: '9' },
    });
    fireEvent.change(screen.getByLabelText('Reserve at BRW'), {
      target: { value: '15' },
    });

    fireEvent.click(buySwitch());
    expect(
      screen.getAllByText('The whole line is being bought.').length,
    ).toBeGreaterThan(0);

    fireEvent.click(buySwitch());

    expect(screen.getByLabelText('Reserve at BRW-AM')).toHaveValue(9);
    expect(screen.getByLabelText('Reserve at BRW')).toHaveValue(15);
  });

  it('keeps a borrow row and the reason typed against it', () => {
    renderPanel({
      sources: [
        {
          kind: 'reserve',
          qty: '9',
          location: 'BRW-AM',
          warehouse_id: 'wh-BRW-AM',
          reason: 'Free unclaimed stock at BRW-AM covers this much.',
        },
        {
          kind: 'borrow',
          qty: '15',
          location: 'MWH-AM',
          warehouse_id: 'wh-MWH-AM',
          reason: 'Borrowed from the group.',
        },
      ],
    });

    const borrowInput = screen.getByLabelText('Borrow from MWH-AM');
    expect(borrowInput).toHaveValue(15);

    fireEvent.click(buySwitch());
    expect(
      screen.queryByLabelText('Borrow from MWH-AM'),
    ).not.toBeInTheDocument();

    fireEvent.click(buySwitch());

    expect(screen.getByLabelText('Borrow from MWH-AM')).toHaveValue(15);
    expect(screen.getByLabelText('Reserve at BRW-AM')).toHaveValue(9);
  });
});

/**
 * A line whose sales order names no fulfilment location cannot be decided here at all: the
 * confirmation leaves it out (`lineFor` returns null), so an editable panel over it would let
 * a planner compose something the press silently drops.
 */
describe('BoardLineDecisionPanel: an unplannable line states why, and offers no verb', () => {
  it('renders the figures and the reason, with no inputs and no buttons', () => {
    renderPanel({
      unplannable: true,
      fulfilment_location: null,
      fulfilment_warehouse_id: null,
    });

    expect(
      screen.getByTestId(`line-decision-blocked-${KEY}`),
    ).toHaveTextContent('states no fulfilment location');
    expect(
      screen.queryByRole('button', { name: 'Save decision' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Reject' }),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^Reserve at/)).not.toBeInTheDocument();
    expect(screen.getByTestId(`line-decision-${KEY}`)).not.toHaveTextContent(
      'Outstanding',
    );
  });
});

/**
 * C11: a line an active decision already covers opens locked, with Amend the only way in - the
 * database already holds a decision, and an editable form over it invites an edit nobody has
 * asked to make.
 */
describe('BoardLineDecisionPanel: a covered row opens locked with Amend (C11)', () => {
  const frozen: BoardLineDecision = {
    revision_no: 1,
    confirmed_at: '2026-08-18T02:00:00',
    timely_spo_qty: '0',
    reserve: [{ warehouse_id: 'wh-BRW-AM', location: 'BRW-AM', qty: '9' }],
    borrow: [],
    buy_qty: '15',
  };

  it('offers only Amend, and disables the inputs, while the row is not being edited', () => {
    renderPanel({ covered: true, decision: frozen });

    expect(screen.getByRole('button', { name: 'Amend' })).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Save decision' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Reject' }),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText('Reserve at BRW-AM')).toBeDisabled();
  });

  it('unlocks the same panel once Amend is pressed', () => {
    renderPanel({ covered: true, decision: frozen });

    fireEvent.click(screen.getByRole('button', { name: 'Amend' }));

    expect(screen.getByLabelText('Reserve at BRW-AM')).toBeEnabled();
    expect(
      screen.getByRole('button', { name: 'Save decision' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Amend' }),
    ).not.toBeInTheDocument();
  });

  /**
   * An approval on an unlocked confirmed row is a REAL verdict, and it reaches the draft as
   * one. It looked like it did - the inputs snapped back to the suggestion and the pill read
   * Approved - while `confirmLinesFor` dropped every covered line the planner had not amended,
   * so the press wrote nothing and the reload showed the old revision.
   *
   * The way there is the engine's own numbers: this row was confirmed at 8 from BRW-AM plus 16
   * from the pool while the engine suggests 9 plus 15, so typing those back IS the approval.
   * One button, and the comparison takes the verdict.
   */
  it('takes an approval once the engine’s numbers are typed back on the unlocked row, and the pill reads Saved (S4)', () => {
    const contribution = contributionOf({
      covered: true,
      decision: {
        revision_no: 4,
        confirmed_at: '2026-08-18T02:00:00',
        timely_spo_qty: '0',
        reserve: [
          { warehouse_id: 'wh-BRW-AM', location: 'BRW-AM', qty: '8' },
          { warehouse_id: 'wh-BRW', location: 'BRW', qty: '16' },
        ],
        borrow: [],
        buy_qty: '0',
      },
    });
    const onDecide = vi.fn();
    render(
      <BoardLineDecisionPanel
        contribution={contribution}
        decision={null}
        locations={LOCATIONS}
        onDecide={onDecide}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Amend' }));
    fireEvent.change(screen.getByLabelText('Reserve at BRW-AM'), {
      target: { value: '9' },
    });
    fireEvent.change(screen.getByLabelText('Reserve at BRW'), {
      target: { value: '15' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));

    // D11: the composition rides along with the approval too.
    expect(onDecide).toHaveBeenCalledWith(
      expect.objectContaining({
        verdict: 'approved',
        suspected_system_issue: false,
        reserve: expect.arrayContaining([
          expect.objectContaining({ warehouse_id: 'wh-BRW-AM', qty: '9' }),
          expect.objectContaining({ warehouse_id: 'wh-BRW', qty: '15' }),
        ]),
        buy_qty: '0',
      }),
    );
    // The row the planner is looking at afterwards: Saved (S4, R-F), not the Confirmed the
    // covered flag alone would print, because the draft's verdict outranks what is in the
    // database.
    render(
      <BoardDecisionPill
        contribution={contribution}
        decision={onDecide.mock.calls[0][0] as BoardDecision}
      />,
    );
    expect(screen.getByTestId(`decision-pill-${KEY}`)).toHaveTextContent(
      'Saved',
    );
  });

  /**
   * AMEND OPENS ON WHAT WAS DECIDED, not on the engine's numbers (C9), and saving that is an
   * amendment: SO404352 line 22 was confirmed at 8 from BRW-AM plus 16 from the pool while the
   * engine suggests 9 plus 15, so the two compositions are not the same answer and only the
   * comparison says which verdict the press takes.
   */
  it('opens on the composition the revision froze, and Save on it amends rather than approves', () => {
    const { onDecide } = renderPanel({
      covered: true,
      decision: {
        revision_no: 4,
        confirmed_at: '2026-08-18T02:00:00',
        timely_spo_qty: '0',
        reserve: [
          { warehouse_id: 'wh-BRW-AM', location: 'BRW-AM', qty: '8' },
          { warehouse_id: 'wh-BRW', location: 'BRW', qty: '16' },
        ],
        borrow: [],
        buy_qty: '0',
      },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Amend' }));
    // Amend opens on what was DECIDED: the planner edits their own numbers.
    expect(screen.getByLabelText('Reserve at BRW-AM')).toHaveValue(8);
    expect(screen.getByLabelText('Reserve at BRW')).toHaveValue(16);

    // Re-saving what was already decided needs no reason - it overrides nothing - but it is
    // still not the engine's composition, so the verdict is Amended.
    fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));

    expect(onDecide).toHaveBeenCalledWith(
      expect.objectContaining({
        verdict: 'amended',
        reserve: expect.arrayContaining([
          expect.objectContaining({ warehouse_id: 'wh-BRW-AM', qty: '8' }),
          expect.objectContaining({ warehouse_id: 'wh-BRW', qty: '16' }),
        ]),
      }),
    );
  });
});

/**
 * The saved amendment overlays the engine's suggestion on reopen: collapsing an amended row
 * and opening it again must not show the engine's numbers under a pill reading Amended.
 */
describe('BoardLineDecisionPanel: the saved amendment overlays on reopen', () => {
  it('shows what was amended, not the suggestion, when the draft already holds a decision', () => {
    renderPanel(
      {},
      {
        verdict: 'amended',
        reserve: [
          { warehouse_id: 'wh-BRW-AM', location: 'BRW-AM', qty: '5' },
          { warehouse_id: 'wh-BRW', location: 'BRW', qty: '19' },
        ],
        borrow: [],
        buy_qty: '0',
        timely_spo_qty: '0',
        reason: 'Agreed a smaller own-location share with the site.',
      },
    );

    expect(screen.getByLabelText('Reserve at BRW-AM')).toHaveValue(5);
    expect(screen.getByLabelText('Reserve at BRW')).toHaveValue(19);
    expect(screen.getByLabelText(/^Why this differs/)).toHaveValue(
      'Agreed a smaller own-location share with the site.',
    );
  });
});

/**
 * S3 - Reserve add-location (AC-3.1 to AC-3.3, R-G): "any location with free stock, the site
 * pool included, can be added to Reserve by hand; the server's on-hand check stays the guard."
 *
 * A fixture of its own, distinct from the header fixture above: `contributionOf`'s line is
 * already fully reserved across both `LOCATIONS` rows, so there is nothing left for "Add
 * location" to offer and no existing test here exercises it. This line reserves only 9 of
 * BRW-AM's own 24 outstanding, leaving exactly BRW's whole 16 free to add.
 */
const ADD_KEY = 'so-c|5|SRTWB9001|2026-07-10';

function contributionForAddLocation(
  overrides: Partial<BoardContribution> = {},
): BoardContribution {
  return {
    key: ADD_KEY,
    sales_order_id: 'so-c',
    so_number: 'SO410000',
    customer_name: 'ZZT Sdn Bhd',
    project_label: null,
    agent_code: 'AG02',
    line_no: 5,
    item_code: 'SRTWB9001',
    qty: '25',
    qty_ordered: '25',
    qty_delivered: '0',
    qty_outstanding: '25',
    project_line_id: 'pl-so-c-5',
    required_date: '2026-07-10',
    is_past: false,
    fulfilment_location: 'BRW-AM',
    fulfilment_warehouse_id: 'wh-BRW-AM',
    unplannable: false,
    priority: null,
    sources: [
      {
        kind: 'reserve',
        qty: '9',
        location: 'BRW-AM',
        warehouse_id: 'wh-BRW-AM',
        reason: 'Free unclaimed stock at BRW-AM covers this much by the delivery date.',
      },
    ],
    qty_proposed_reserve: '9',
    qty_proposed_incoming: '0',
    qty_proposed_buy: '0',
    contested: false,
    rank_score: 0,
    rank_factors: [],
    covered: false,
    decision: null,
    order_inquiry: null,
    item_flags: null,
    borrow_candidates: [],
    ...overrides,
  };
}

/** BRW-AM already carries 9 reserved (`available_qty` states the 9 the ONE other line left
 * free, per B1's own reading); BRW is a site pool with its whole 16 still free to add. */
const ADD_LOCATION_FIXTURE: BoardCellLocation[] = [
  {
    location: 'BRW-AM',
    warehouse_id: 'wh-BRW-AM',
    where: 'own',
    qty: '0',
    available_qty: '9',
    qty_free: '9',
    qty_free_remaining: '9',
  },
  {
    location: 'BRW',
    warehouse_id: 'wh-BRW',
    where: 'site_pool',
    qty: '0',
    available_qty: '16',
    qty_free: '16',
    qty_free_remaining: '16',
  },
];

function renderAddLocationPanel(overrides: Partial<BoardContribution> = {}) {
  const onDecide = vi.fn();
  render(
    <BoardLineDecisionPanel
      contribution={contributionForAddLocation(overrides)}
      decision={null}
      locations={ADD_LOCATION_FIXTURE}
      onDecide={onDecide}
    />,
  );
  return { onDecide };
}

describe('BoardLineDecisionPanel: Reserve add-location (S3, AC-3.1 to AC-3.3)', () => {
  it('offers only the free location not already on the Reserve list, and Save carries the new row at its own warehouse (AC-3.1, AC-3.2)', () => {
    const { onDecide } = renderAddLocationPanel();

    fireEvent.click(screen.getByRole('button', { name: 'Add location' }));

    // BRW-AM is already a Reserve row; only BRW is offered.
    expect(screen.getByTestId('reserve-location-table')).toBeInTheDocument();
    expect(screen.queryByTestId('reserve-location-BRW-AM')).not.toBeInTheDocument();
    expect(screen.getByTestId('reserve-location-BRW')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Add the location' }));

    // Seeded to the whole remainder (16 open beyond the 9 already reserved), and editable.
    const added = screen.getByLabelText('Reserve at BRW');
    expect(added).toHaveValue(16);
    fireEvent.change(added, { target: { value: '16' } });

    fireEvent.change(screen.getByLabelText(/^Why this differs/), {
      target: { value: 'BRW can spare the rest of this line.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));

    expect(onDecide).toHaveBeenCalledWith(
      expect.objectContaining({
        verdict: 'amended',
        reserve: expect.arrayContaining([
          expect.objectContaining({ warehouse_id: 'wh-BRW-AM', qty: '9' }),
          expect.objectContaining({ warehouse_id: 'wh-BRW', qty: '16' }),
        ]),
        reason: 'BRW can spare the rest of this line.',
      }),
    );
  });

  it('echoes the server’s own on-hand guard on the newly added row, and keeps the row rather than dropping it (AC-3.3)', () => {
    renderAddLocationPanel();

    fireEvent.click(screen.getByRole('button', { name: 'Add location' }));
    fireEvent.click(screen.getByRole('button', { name: 'Add the location' }));

    fireEvent.change(screen.getByLabelText('Reserve at BRW'), {
      target: { value: '30' },
    });

    expect(screen.getByText('Only 16 available here')).toBeInTheDocument();
    expect(screen.getByLabelText('Reserve at BRW')).toHaveValue(30);
  });

  it('reads the echo off qty_free_remaining, never the signed whole-book available_qty (B2, code review round 3)', () => {
    // MWH-IB style figures: `available_qty` is AutoCount's own signed whole-book number and
    // reads deeply negative even though the location has plenty free for THIS board's own
    // proposals; `qty_free` and `qty_free_remaining` are positive and DIFFER from each other
    // (and from `available_qty`), so a fix that fell back to the wrong one would show either
    // the wrong number or a false "Only N available" on the engine's own suggestion.
    const oversoldWholeBook: BoardCellLocation[] = [
      {
        location: 'BRW-AM',
        warehouse_id: 'wh-BRW-AM',
        where: 'own',
        qty: '0',
        available_qty: '-15514',
        qty_free: '20',
        qty_free_remaining: '9',
      },
      {
        location: 'BRW',
        warehouse_id: 'wh-BRW',
        where: 'site_pool',
        qty: '0',
        available_qty: '-999',
        qty_free: '30',
        qty_free_remaining: '16',
      },
    ];
    render(
      <BoardLineDecisionPanel
        contribution={contributionOf()}
        decision={null}
        locations={oversoldWholeBook}
        onDecide={vi.fn()}
      />,
    );

    // The engine's own suggestion (Reserve 9 at BRW-AM, Reserve 15 at BRW) reads its echo off
    // `qty_free_remaining`, not `available_qty` - no red "Only N available here" anywhere on
    // an unedited, engine-suggested composition.
    expect(screen.getByText('9 available')).toBeInTheDocument();
    expect(screen.getByText('16 available')).toBeInTheDocument();
    expect(screen.queryByText(/-15514/)).not.toBeInTheDocument();
    expect(screen.queryByText(/-999/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Only .* available here/)).not.toBeInTheDocument();
  });

  it('says no other location holds free stock once every candidate is already on the Reserve list', () => {
    renderAddLocationPanel({
      sources: [
        {
          kind: 'reserve',
          qty: '9',
          location: 'BRW-AM',
          warehouse_id: 'wh-BRW-AM',
          reason: 'Free unclaimed stock at BRW-AM covers this much.',
        },
        {
          kind: 'reserve',
          qty: '16',
          location: 'BRW',
          warehouse_id: 'wh-BRW',
          reason: 'The shared pool at BRW covers the rest.',
        },
      ],
    });

    expect(
      screen.getByText('No other location holds free stock of this item.'),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Add location' }),
    ).not.toBeInTheDocument();
  });

  it('offers no Add location while the row is locked - Amend has to be pressed first', () => {
    const frozen: BoardLineDecision = {
      revision_no: 1,
      confirmed_at: '2026-08-18T02:00:00',
      timely_spo_qty: '0',
      reserve: [{ warehouse_id: 'wh-BRW-AM', location: 'BRW-AM', qty: '9' }],
      borrow: [],
      buy_qty: '16',
    };
    renderAddLocationPanel({ covered: true, decision: frozen });

    expect(
      screen.queryByRole('button', { name: 'Add location' }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Amend' }));

    expect(screen.getByRole('button', { name: 'Add location' })).toBeInTheDocument();
  });

  it('offers no Add location while the whole line is being bought', () => {
    renderAddLocationPanel();

    fireEvent.click(screen.getByRole('switch', { name: 'Buy the whole line' }));

    expect(
      screen.queryByRole('button', { name: 'Add location' }),
    ).not.toBeInTheDocument();
  });
});

/**
 * The button answers the click itself (S4, AC-4.1), rather than leaving the planner to
 * notice the pill above it and the toast below it.
 *
 * D4 (captain, 3 Sep): it STAYS answered. The check used to last about 600 ms and then go
 * back to "Save decision", which read as the save reverting - "shows saved then jumps back".
 * The state is now the line's, not a moment's: saved until the line is edited again.
 */
describe('BoardLineDecisionPanel: the Save button says it saved (S4, AC-4.1)', () => {
  it('stays Saved and disabled while the line is untouched', async () => {
    const { onDecide } = renderPanel();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));
    });

    expect(onDecide).toHaveBeenCalledTimes(1);
    const saved = screen.getByRole('button', { name: 'Saved' });
    expect(saved).toBeInTheDocument();
    expect(saved).toBeDisabled();
    expect(
      screen.queryByRole('button', { name: 'Save decision' }),
    ).not.toBeInTheDocument();
  });

  it('goes back to Save decision the moment the planner edits the line again', async () => {
    renderPanel();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));
    });
    expect(screen.getByRole('button', { name: 'Saved' })).toBeInTheDocument();

    // An edit that still BALANCES and carries its reason, so what the button says is about
    // the save being stale and nothing else: 5 + 19 against the line's 24, and a reason.
    fireEvent.change(screen.getByLabelText('Reserve at BRW-AM'), {
      target: { value: '5' },
    });
    fireEvent.change(screen.getByLabelText('Reserve at BRW'), {
      target: { value: '19' },
    });
    fireEvent.change(screen.getByLabelText(/^Why this differs/), {
      target: { value: 'Agreed a smaller own-location share with the site.' },
    });

    const again = screen.getByRole('button', { name: 'Save decision' });
    expect(again).toBeInTheDocument();
    expect(again).toBeEnabled();
  });

  it('opens Saved and disabled on a line somebody has already saved', () => {
    renderPanel({
      draft: {
        decision: { verdict: 'approved' },
        saved_by: 'Eling',
        saved_at: '2026-09-03T02:00:00',
      },
    });

    const saved = screen.getByRole('button', { name: 'Saved' });
    expect(saved).toBeInTheDocument();
    expect(saved).toBeDisabled();
  });

  it('waits for the save to resolve before showing the check', async () => {
    vi.useFakeTimers();
    try {
      let settle: () => void = () => {};
      const onDecide = vi.fn(
        () => new Promise<boolean>((resolve) => {
          settle = () => resolve(true);
        }),
      );
      render(
        <BoardLineDecisionPanel
          contribution={contributionOf()}
          decision={null}
          locations={LOCATIONS}
          onDecide={onDecide}
          onDirtyChange={vi.fn()}
        />,
      );

      fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));
      // In flight: the server has not answered, so the button has nothing to confirm yet.
      expect(
        screen.queryByRole('button', { name: 'Saved' }),
      ).not.toBeInTheDocument();

      await act(async () => {
        settle();
      });

      expect(screen.getByRole('button', { name: 'Saved' })).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('shows no check state when the write did not land (S2, code review round 3)', async () => {
    // `FulfilmentBoardPanel.decide` never lets a save REJECT into this panel - it catches its
    // own write and resolves `false` - so this is the shape a failure actually arrives in.
    const onDecide = vi.fn().mockResolvedValue(false);

    render(
      <BoardLineDecisionPanel
        contribution={contributionOf()}
        decision={null}
        locations={LOCATIONS}
        onDecide={onDecide}
      />,
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));
    });

    expect(onDecide).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: 'Saved' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save decision' })).toBeInTheDocument();
  });

  it('does not lock a re-save as Saved when the server rejects it (B1, fix round 5)', async () => {
    // First save lands; the planner edits again and saves a second time, and THAT write is
    // the one the server refuses. The button must answer the second click, not the first.
    const onDecide = vi
      .fn()
      .mockResolvedValueOnce(true)
      .mockResolvedValueOnce(false);
    const onDirtyChange = vi.fn();

    render(
      <BoardLineDecisionPanel
        contribution={contributionOf()}
        decision={null}
        locations={LOCATIONS}
        onDecide={onDecide}
        onDirtyChange={onDirtyChange}
      />,
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));
    });
    expect(screen.getByRole('button', { name: 'Saved' })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Reserve at BRW-AM'), {
      target: { value: '5' },
    });
    fireEvent.change(screen.getByLabelText('Reserve at BRW'), {
      target: { value: '19' },
    });
    fireEvent.change(screen.getByLabelText(/^Why this differs/), {
      target: { value: 'Agreed a smaller own-location share with the site.' },
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));
    });

    expect(onDecide).toHaveBeenCalledTimes(2);
    expect(
      screen.getByRole('button', { name: 'Save decision' }),
    ).toBeEnabled();
    expect(
      screen.queryByRole('button', { name: 'Saved' }),
    ).not.toBeInTheDocument();
    expect(onDirtyChange).toHaveBeenLastCalledWith(true);
  });

  /**
   * N3 (fix round 5). `savedOnce` used to seed ONLY at mount (`useState(() =>
   * Boolean(contribution.draft))`), so a panel a planner left OPEN across a change that did
   * not come through its own `save()` / `reject()` - a refetch after another planner saved
   * this line, or an Undo fired from the pill (`BoardDecisionPill`) - kept reading whatever
   * was true when it first opened.
   */
  it('re-seeds when the contribution s own draft changes under it, not only at mount', () => {
    const { rerender } = render(
      <BoardLineDecisionPanel
        contribution={contributionOf()}
        decision={null}
        locations={LOCATIONS}
        onDecide={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: 'Save decision' })).toBeInTheDocument();

    // A refetch delivers a draft this panel never wrote itself (another planner's save).
    rerender(
      <BoardLineDecisionPanel
        contribution={contributionOf({
          draft: {
            decision: { verdict: 'approved' },
            saved_by: 'Mei',
            saved_at: '2026-09-03T02:00:00',
          },
        })}
        decision={null}
        locations={LOCATIONS}
        onDecide={vi.fn()}
      />,
    );
    const saved = screen.getByRole('button', { name: 'Saved' });
    expect(saved).toBeInTheDocument();
    expect(saved).toBeDisabled();

    // An Undo fired elsewhere (the pill) clears the draft under the same open panel.
    rerender(
      <BoardLineDecisionPanel
        contribution={contributionOf()}
        decision={null}
        locations={LOCATIONS}
        onDecide={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: 'Save decision' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Saved' })).not.toBeInTheDocument();
  });
});

/**
 * D5 (captain, 3 Sep, SO419208 line 3, CSK14A-NL). The engine proposed "BRW 62 + Buy 73" -
 * the site pool's share inside the immediate window, remainder bought (R-B/R-C) - and this
 * panel refused to save its own suggestion, because the client's whole-line rule knew
 * nothing about the carve-out the server's confirm has always applied.
 */
describe('BoardLineDecisionPanel: a pool share beside a Buy is saveable (D5)', () => {
  const POOL_LOCATIONS: BoardCellLocation[] = [
    {
      location: 'BRW-AM',
      warehouse_id: 'wh-BRW-AM',
      qty: '0',
      available_qty: '0',
      qty_free: '0',
      qty_free_remaining: '0',
      where: 'own',
    },
    {
      location: 'BRW',
      warehouse_id: 'wh-BRW',
      qty: '0',
      available_qty: '124',
      qty_free: '124',
      qty_free_remaining: '124',
      where: 'site_pool',
      // What the SERVER says this pool may lend a project line, and the five pools' net.
      available_for_project: '62',
      net: '400',
      net_of: 'pools',
    },
  ];

  function renderSplit() {
    const onDecide = vi.fn();
    render(
      <BoardLineDecisionPanel
        contribution={contributionOf({
          line_no: 3,
          item_code: 'CSK14A-NL',
          qty: '135',
          qty_ordered: '135',
          qty_outstanding: '135',
          // The engine's own totals for this line, which is where the draft's Buy comes from
          // on an uncovered line (`draftFromSources`).
          qty_proposed_reserve: '62',
          qty_proposed_buy: '73',
          sources: [
            {
              kind: 'reserve',
              qty: '62',
              location: 'BRW',
              warehouse_id: 'wh-BRW',
              reason: 'BRW may spare 62 of its pile to a project line.',
              rung: 'pool',
            },
            {
              kind: 'buy',
              qty: '73',
              location: null,
              warehouse_id: null,
              reason: 'The remainder has to be bought.',
              rung: 'buy',
            },
          ],
        })}
        decision={null}
        locations={POOL_LOCATIONS}
        onDecide={onDecide}
      />,
    );
    return { onDecide };
  }

  it('never calls the engine s own split a mix, and saves it', () => {
    renderSplit();

    expect(
      screen.queryByText(/either met wholly from stock or wholly bought/),
    ).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save decision' })).toBeEnabled();
  });

  /**
   * Beyond the allowance the refusal stands, and it names the figure. There is no Buy INPUT
   * on this panel - Buy is the all-or-nothing switch - so an overdrawn split cannot be typed
   * here; the predicate's own tests (`supplyComposition.test.ts`) cover that shape, and this
   * one covers what the panel can actually reach: the pool row moved past its allowance,
   * which leaves the composition short and says so.
   */
  it('still refuses a pool draw beyond what that pool may spare', () => {
    renderSplit();

    fireEvent.change(screen.getByLabelText('Reserve at BRW'), {
      target: { value: '70' },
    });

    expect(screen.getByRole('button', { name: 'Save decision' })).toBeDisabled();
  });
});

/**
 * D7 (captain, 3 Sep, SO419208 line 3, CSK14A-NL). "BRW 62 · Buy 73", open 135: editing the
 * BRW reserve down to 60 used to leave `draft.buy_qty` frozen at 73 - short by 2, and blocked
 * - because Buy was never anything but the all-or-nothing switch. Buy is now the remainder,
 * derived inside `edit()` on every change and shown read-only beside the switch, so the line
 * stays composable while the reserve is being adjusted rather than needing the switch at all.
 */
describe('BoardLineDecisionPanel: Buy follows the remainder of the line (D7)', () => {
  const POOL_LOCATIONS: BoardCellLocation[] = [
    {
      location: 'BRW-AM',
      warehouse_id: 'wh-BRW-AM',
      qty: '0',
      available_qty: '0',
      qty_free: '0',
      qty_free_remaining: '0',
      where: 'own',
    },
    {
      location: 'BRW',
      warehouse_id: 'wh-BRW',
      qty: '0',
      available_qty: '124',
      qty_free: '124',
      qty_free_remaining: '124',
      where: 'site_pool',
      available_for_project: '62',
      net: '400',
      // `poolShareLimitsOf` bounds a split by `net_raw`, never the display-only `net` (N1,
      // fix round 5) - without it the five-pool net reads 0 and an edited, otherwise legal,
      // split is refused for a reason that has nothing to do with what D7 is testing.
      net_raw: '400',
      net_of: 'pools',
    },
  ];

  function renderRemainder(locations: BoardCellLocation[] = POOL_LOCATIONS) {
    const onDecide = vi.fn();
    render(
      <BoardLineDecisionPanel
        contribution={contributionOf({
          line_no: 3,
          item_code: 'CSK14A-NL',
          qty: '135',
          qty_ordered: '135',
          qty_outstanding: '135',
          qty_proposed_reserve: '62',
          qty_proposed_buy: '73',
          sources: [
            {
              kind: 'reserve',
              qty: '62',
              location: 'BRW',
              warehouse_id: 'wh-BRW',
              reason: 'BRW may spare 62 of its pile to a project line.',
              rung: 'pool',
            },
            {
              kind: 'buy',
              qty: '73',
              location: null,
              warehouse_id: null,
              reason: 'The remainder has to be bought.',
              rung: 'buy',
            },
          ],
        })}
        decision={null}
        locations={locations}
        onDecide={onDecide}
      />,
    );
    return { onDecide };
  }

  it('reads "Buy 75" and drops the short blocker once the reserve is edited down to 60', () => {
    renderRemainder();

    expect(screen.getByTestId(`line-buy-derived-${KEY}`)).toHaveTextContent(
      'Buy 73',
    );

    fireEvent.change(screen.getByLabelText('Reserve at BRW'), {
      target: { value: '60' },
    });

    expect(screen.getByTestId(`line-buy-derived-${KEY}`)).toHaveTextContent(
      'Buy 75',
    );
    expect(
      screen.queryByText(/short of the open quantity/),
    ).not.toBeInTheDocument();

    // The composition now differs from the engine's own suggestion (62 became 60), so Save
    // still needs the reason C7 already requires of any amendment - once it has one, the
    // 60/75 split is a legal pool-share carve-out (D5) and nothing else blocks it.
    fireEvent.change(screen.getByLabelText(/^Why this differs/), {
      target: { value: 'The site can only spare 60 today.' },
    });
    expect(
      screen.getByRole('button', { name: 'Save decision' }),
    ).toBeEnabled();
  });

  it('carries the derived buy_qty of 75 on Save', async () => {
    const { onDecide } = renderRemainder();

    fireEvent.change(screen.getByLabelText('Reserve at BRW'), {
      target: { value: '60' },
    });
    fireEvent.change(screen.getByLabelText(/^Why this differs/), {
      target: { value: 'The site can only spare 60 today.' },
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));
    });

    expect(onDecide).toHaveBeenCalledWith(
      expect.objectContaining({
        verdict: 'amended',
        buy_qty: '75',
        reserve: expect.arrayContaining([
          expect.objectContaining({ warehouse_id: 'wh-BRW', qty: '60' }),
        ]),
      }),
    );
  });

  it('reads "Buy 0" and drops the Buy component once the reserve covers the whole line', () => {
    renderRemainder();

    fireEvent.change(screen.getByLabelText('Reserve at BRW'), {
      target: { value: '135' },
    });

    expect(screen.getByTestId(`line-buy-derived-${KEY}`)).toHaveTextContent(
      'Buy 0',
    );
    // `amendSummary` only prints a Buy segment for a positive quantity (`boardAmend.ts`), so
    // the Decision text on the right names no Buy component either.
    expect(
      screen.getByTestId(`line-decision-summary-${KEY}`),
    ).not.toHaveTextContent('Buy');
  });

  /**
   * B-1 (fix round 7). `buying` used to be DERIVED from the numbers
   * (`toMinor(draft.buy_qty) > 0 && fromStockMinor === 0`), so clearing the BRW box (or typing
   * 0) made `buy_qty` follow the whole open quantity and `fromStockMinor` hit zero in the same
   * render - the switch read ON, and the Reserve section and the Add-location button unmounted
   * under the planner mid-edit. It is STATE now, seeded once from the opening draft and changed
   * only by the switch itself.
   */
  it('B-1: clearing or zeroing the Reserve box never flips the switch on, and turning it on then off restores what was typed', () => {
    // A third, free location beside BRW-AM (0 free) and BRW (already reserved), so
    // "Add location" has something to offer and its own unmount is part of what this proves.
    renderRemainder([
      ...POOL_LOCATIONS,
      {
        location: 'MWH-IB',
        warehouse_id: 'wh-MWH-IB',
        qty: '0',
        available_qty: '400',
        qty_free: '400',
        qty_free_remaining: '400',
        where: 'own',
      },
    ]);

    const reserveInput = screen.getByLabelText('Reserve at BRW');
    const switchControl = screen.getByRole('switch', {
      name: 'Buy the whole line',
    });

    fireEvent.change(reserveInput, { target: { value: '' } });
    expect(switchControl).not.toBeChecked();
    expect(screen.getByTestId(`line-buy-derived-${KEY}`)).toHaveTextContent(
      'Buy 135',
    );
    expect(screen.getByLabelText('Reserve at BRW')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Add location' }),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Reserve at BRW'), {
      target: { value: '0' },
    });
    expect(switchControl).not.toBeChecked();
    expect(screen.getByTestId(`line-buy-derived-${KEY}`)).toHaveTextContent(
      'Buy 135',
    );
    expect(screen.getByLabelText('Reserve at BRW')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Reserve at BRW'), {
      target: { value: '60' },
    });
    expect(screen.getByTestId(`line-buy-derived-${KEY}`)).toHaveTextContent(
      'Buy 75',
    );

    fireEvent.click(switchControl);
    expect(
      screen.getAllByText('The whole line is being bought.'),
    ).toHaveLength(2);

    fireEvent.click(switchControl);
    // The `stockBefore` path (D7): the 60 that was typed comes back, never a zero.
    expect(screen.getByLabelText('Reserve at BRW')).toHaveValue(60);
    expect(screen.getByTestId(`line-buy-derived-${KEY}`)).toHaveTextContent(
      'Buy 75',
    );
  });
});

/**
 * S-1 (fix round 7). `ReserveAddDialog`'s opening quantity is the line's remainder capped at
 * the location's free stock (`openingQty`); D7 made `totalMinor` include the derived Buy, so
 * `open - totalMinor` read 0 on an already-composed line and the dialog fell back to the
 * location's WHOLE free stock instead. The remainder has to exclude the Buy component itself.
 */
describe('BoardLineDecisionPanel: Add-location seeds the remainder, not the whole free stock (S-1, fix round 7)', () => {
  it('seeds 73 on a bin with 400 free, on a line already carrying BRW 62 + derived Buy 73', () => {
    const onDecide = vi.fn();
    render(
      <BoardLineDecisionPanel
        contribution={contributionOf({
          line_no: 3,
          item_code: 'CSK14A-NL',
          qty: '135',
          qty_ordered: '135',
          qty_outstanding: '135',
          qty_proposed_reserve: '62',
          qty_proposed_buy: '73',
          sources: [
            {
              kind: 'reserve',
              qty: '62',
              location: 'BRW',
              warehouse_id: 'wh-BRW',
              reason: 'BRW may spare 62 of its pile to a project line.',
              rung: 'pool',
            },
            {
              kind: 'buy',
              qty: '73',
              location: null,
              warehouse_id: null,
              reason: 'The remainder has to be bought.',
              rung: 'buy',
            },
          ],
        })}
        decision={null}
        locations={[
          {
            location: 'BRW',
            warehouse_id: 'wh-BRW',
            qty: '0',
            available_qty: '124',
            qty_free: '124',
            qty_free_remaining: '124',
            where: 'site_pool',
            available_for_project: '62',
            net: '400',
            net_raw: '400',
            net_of: 'pools',
          },
          {
            location: 'MWH-IB',
            warehouse_id: 'wh-MWH-IB',
            qty: '0',
            available_qty: '400',
            qty_free: '400',
            qty_free_remaining: '400',
            where: 'own',
          },
        ]}
        onDecide={onDecide}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Add location' }));

    expect(screen.getByLabelText('Quantity')).toHaveValue(73);
  });
});
