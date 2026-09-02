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

    expect(onDecide).toHaveBeenCalledWith({
      verdict: 'approved',
      suspected_system_issue: false,
    });
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
 * C7, in the UAC's own words: "Editing Reserve BRW-AM from 9 to 5 shows the hint 4 short and
 * Save is disabled; setting BRW to 19 clears the hint, and Save enables once the reason is
 * typed (a composition that differs from the suggestion always needs the reason)."
 */
describe('BoardLineDecisionPanel: the balance hint and Save gating (C7)', () => {
  it('shows "N short" once a composition falls under the outstanding quantity', () => {
    renderPanel();

    fireEvent.change(screen.getByLabelText('Reserve at BRW-AM'), {
      target: { value: '5' },
    });

    expect(screen.getByTestId(`line-decision-hint-${KEY}`)).toHaveTextContent(
      '4 short',
    );
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

    expect(onDecide).toHaveBeenCalledWith({
      verdict: 'approved',
      suspected_system_issue: false,
    });
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
 * notice the pill above it and the toast below it. Fake timers, because what is asserted is
 * that the check state ENDS - a 600ms state nobody clears is a button stuck on "Saved".
 */
describe('BoardLineDecisionPanel: the Save button says it saved (S4, AC-4.1)', () => {
  it('shows a check for about 600 ms once the save resolves, then goes back', async () => {
    vi.useFakeTimers();
    try {
      const { onDecide } = renderPanel();

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));
      });

      expect(onDecide).toHaveBeenCalledTimes(1);
      expect(screen.getByRole('button', { name: 'Saved' })).toBeInTheDocument();
      expect(
        screen.queryByRole('button', { name: 'Save decision' }),
      ).not.toBeInTheDocument();

      act(() => {
        vi.advanceTimersByTime(600);
      });

      expect(
        screen.getByRole('button', { name: 'Save decision' }),
      ).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
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
});
