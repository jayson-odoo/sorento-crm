/**
 * The decision on one contributing line, taken IN THE ROW (PLAN section 3.C, ruling R7).
 *
 * The fixture is the plan's own canonical example (UAC header line, R1): SO404352 line 22,
 * SRTWB7518, BRW-AM on hand 10 with SO383850 holding 1 there (so 9 available, B1), the shared
 * pool at BRW holding 16. The engine's suggestion is Reserve 9 at BRW-AM plus Reserve 15 at
 * BRW (the 24 outstanding, C7/C8's own numbers), so every test below traces to a UAC id.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { BoardLineDecisionPanel } from './BoardLineDecisionPanel';
import type {
  BoardCellLocation,
  BoardContribution,
  BoardDecision,
  BoardLineDecision,
} from '../../_shared/types/fulfilmentPlanning.types';

const KEY = 'so-a|22|SRTWB7518|2026-06-29';

function contributionOf(overrides: Partial<BoardContribution> = {}): BoardContribution {
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
        reason: 'Free unclaimed stock at BRW-AM covers this much by the delivery date.',
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
  { location: 'BRW-AM', warehouse_id: 'wh-BRW-AM', qty: '0', available_qty: '9' },
  { location: 'BRW', warehouse_id: 'wh-BRW', qty: '0', available_qty: '16' },
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

describe('BoardLineDecisionPanel: the read-only strip (C4)', () => {
  it('shows Ordered, Delivered, Outstanding and Incoming off the contribution', () => {
    renderPanel({ qty_ordered: '24', qty_delivered: '0', qty_outstanding: '24' });

    const panel = screen.getByTestId(`line-decision-${KEY}`);
    expect(panel).toHaveTextContent('Ordered');
    expect(panel).toHaveTextContent('Delivered');
    expect(panel).toHaveTextContent('Outstanding');
    expect(panel).toHaveTextContent('Incoming by the delivery date');
    expect(panel).toHaveTextContent('24');
  });

  it('states an absent figure rather than guessing at one', () => {
    renderPanel({ qty_ordered: null, qty_delivered: null });

    const panel = screen.getByTestId(`line-decision-${KEY}`);
    expect(panel).toHaveTextContent('Not stated');
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

describe('BoardLineDecisionPanel: the three verbs (C9)', () => {
  it('approve suggestion takes the engine composition, with no reason and no flag', () => {
    const { onDecide } = renderPanel();

    fireEvent.click(screen.getByRole('button', { name: 'Approve suggestion' }));

    expect(onDecide).toHaveBeenCalledWith({
      verdict: 'approved',
      suspected_system_issue: false,
    });
  });

  it('save amendment posts the composition typed, once it balances and carries a reason', () => {
    const { onDecide } = renderPanel();

    fireEvent.change(screen.getByLabelText('Reserve at BRW-AM'), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText('Reserve at BRW'), { target: { value: '19' } });
    fireEvent.change(screen.getByLabelText(/^Why this differs/), {
      target: { value: 'The site asked for less from BRW-AM.' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Save amendment' }));

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
 * C7, in the UAC's own words: "Editing Reserve BRW-AM from 9 to 5 shows the hint 4 short and
 * Save amendment is disabled; setting BRW to 19 clears the hint, and Save enables once the
 * reason is typed (a composition that differs from the suggestion always needs the reason)."
 */
describe('BoardLineDecisionPanel: the balance hint and Save gating (C7)', () => {
  it('shows "N short" once a composition falls under the outstanding quantity', () => {
    renderPanel();

    fireEvent.change(screen.getByLabelText('Reserve at BRW-AM'), { target: { value: '5' } });

    expect(screen.getByTestId(`line-decision-hint-${KEY}`)).toHaveTextContent('4 short');
    expect(screen.getByRole('button', { name: 'Save amendment' })).toBeDisabled();
  });

  it('shows "N over" once a composition exceeds it', () => {
    renderPanel();

    fireEvent.change(screen.getByLabelText('Reserve at BRW'), { target: { value: '30' } });

    expect(screen.getByTestId(`line-decision-hint-${KEY}`)).toHaveTextContent('15 over');
  });

  it('clears the hint once the composition balances again, and enables Save once a reason is typed', () => {
    renderPanel();

    fireEvent.change(screen.getByLabelText('Reserve at BRW-AM'), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText('Reserve at BRW'), { target: { value: '19' } });

    expect(screen.queryByTestId(`line-decision-hint-${KEY}`)).not.toBeInTheDocument();
    const save = screen.getByRole('button', { name: 'Save amendment' });
    expect(save).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/^Why this differs/), {
      target: { value: 'Agreed a smaller own-location share with the site.' },
    });
    expect(save).toBeEnabled();
  });

  it('never needs a reason to approve the suggestion as it stands', () => {
    renderPanel();

    // The composition on open IS the suggestion, so Approve needs nothing typed.
    expect(screen.getByRole('button', { name: 'Approve suggestion' })).toBeEnabled();
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

  it('carries the flag on an approval', () => {
    const { onDecide } = renderPanel();

    fireEvent.click(checkbox());
    fireEvent.click(screen.getByRole('button', { name: 'Approve suggestion' }));

    expect(onDecide).toHaveBeenCalledWith(
      expect.objectContaining({ verdict: 'approved', suspected_system_issue: true }),
    );
  });

  it('carries the flag on a saved amendment', () => {
    const { onDecide } = renderPanel();

    fireEvent.click(checkbox());
    fireEvent.change(screen.getByLabelText('Reserve at BRW-AM'), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText('Reserve at BRW'), { target: { value: '19' } });
    fireEvent.change(screen.getByLabelText(/^Why this differs/), {
      target: { value: 'The availability beside this line looks wrong.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save amendment' }));

    expect(onDecide).toHaveBeenCalledWith(
      expect.objectContaining({ verdict: 'amended', suspected_system_issue: true }),
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
      expect.objectContaining({ verdict: 'rejected', suspected_system_issue: true }),
    );
  });

  it('unticking on a covered line clears the flag, in the draft AND on screen', () => {
    const frozen: BoardLineDecision = {
      revision_no: 1,
      confirmed_at: '2026-08-18T02:00:00',
      timely_spo_qty: '0',
      reserve: [{ warehouse_id: 'wh-BRW-AM', location: 'BRW-AM', qty: '9' }],
      borrow: [],
      buy_qty: '15',
      suspected_system_issue: true,
    };
    const { onDecide } = renderPanel({ covered: true, decision: frozen });

    fireEvent.click(screen.getByRole('button', { name: 'Amend' }));
    expect(checkbox()).toBeChecked();
    fireEvent.click(checkbox());
    fireEvent.click(screen.getByRole('button', { name: 'Approve suggestion' }));

    // The BOOLEAN, not an absent key: `lineFor` posts `false`, so the pill must read `false`
    // rather than falling through to the frozen `true` and contradicting the body.
    expect(onDecide).toHaveBeenCalledWith({
      verdict: 'approved',
      suspected_system_issue: false,
    });
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

    fireEvent.change(screen.getByLabelText('Reserve at BRW-AM'), { target: { value: '9' } });
    fireEvent.change(screen.getByLabelText('Reserve at BRW'), { target: { value: '15' } });

    fireEvent.click(buySwitch());
    expect(screen.getAllByText('The whole line is being bought.').length).toBeGreaterThan(0);

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
    expect(screen.queryByLabelText('Borrow from MWH-AM')).not.toBeInTheDocument();

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
    renderPanel({ unplannable: true, fulfilment_location: null, fulfilment_warehouse_id: null });

    expect(screen.getByTestId(`line-decision-blocked-${KEY}`)).toHaveTextContent(
      'states no fulfilment location',
    );
    expect(screen.queryByRole('button', { name: 'Approve suggestion' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save amendment' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reject' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^Reserve at/)).not.toBeInTheDocument();
    // The figures are still worth reading: this is a row, not a wall.
    expect(screen.getByTestId(`line-decision-${KEY}`)).toHaveTextContent('Outstanding');
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
    expect(screen.queryByRole('button', { name: 'Approve suggestion' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save amendment' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reject' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('Reserve at BRW-AM')).toBeDisabled();
  });

  it('unlocks the same panel once Amend is pressed', () => {
    renderPanel({ covered: true, decision: frozen });

    fireEvent.click(screen.getByRole('button', { name: 'Amend' }));

    expect(screen.getByLabelText('Reserve at BRW-AM')).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Save amendment' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Amend' })).not.toBeInTheDocument();
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
