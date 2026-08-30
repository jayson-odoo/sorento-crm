/**
 * Stage 1C - one line's supply composition (journey steps 1 and 2).
 *
 * Two rules are pinned hardest. Every section renders whatever the answer is, so no
 * eligible stock, no incoming by the delivery date, no later incoming, no borrow candidate,
 * no reorder level and no classification each state that in place (AC-G02); and the read
 * view and the edit view are the SAME layout, so a confirmed line shows the frozen quantity
 * where the input was, in the same order, under the same headings.
 *
 * Every id in these fixtures is UUID-shaped on purpose: the card addresses warehouses and
 * donor projects by id and names them by code and reference, and the test proves it.
 */
import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { SupplyLine } from '../../_shared/types/fulfilmentPlanning.types';
import { draftFromLine, type DraftLine } from '../../_shared/lib/supplyComposition';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

import { SupplyLineCard } from './SupplyLineCard';

const WH_BRW = 'a1000000-0000-4000-8000-000000000001';
const WH_HQ = 'a1000000-0000-4000-8000-000000000002';
const DONOR_PROJECT = 'b2000000-0000-4000-8000-000000000001';
const LINE_ID = 'c3000000-0000-4000-8000-000000000001';

const SECTIONS = [
  'Incoming by the delivery date',
  'Reserve',
  'Borrow',
  'Buy',
  'Later incoming',
];

function line(overrides: Partial<SupplyLine> = {}): SupplyLine {
  return {
    project_line_id: LINE_ID,
    line_no: 1,
    item_code: 'CB6633',
    description: 'CABANA S/STEEL FLOOR GRATING 6"',
    uom: 'UNIT',
    open_qty: '600',
    required_date: '2026-09-01',
    fulfilment_location: 'BRW-BB',
    is_dealer_hot_selling: false,
    is_project_hot_selling: false,
    dealer_classified: false,
    project_classified: false,
    classification_unavailable: false,
    is_discontinued: false,
    pool_location: 'BRW-BB',
    pool_cap: null,
    pool_reorder_level: '120',
    components: [
      {
        kind: 'timely_spo',
        qty: '100',
        reason: 'SPO-2026-0311 arrives at BRW-BB on 01 Sep 2026, on the delivery date.',
        source_location: 'BRW-BB',
        source_warehouse_id: WH_BRW,
      },
      {
        kind: 'reserve',
        qty: '200',
        reason: 'Free stock at BRW-BB covers the need by the delivery date.',
        source_location: 'BRW-BB',
        source_warehouse_id: WH_BRW,
      },
      { kind: 'buy', qty: '300', reason: 'Remaining uncovered need.' },
    ],
    timely_spo: [{ spo_number: 'SPO-2026-0311', arrival_date: '2026-09-01', qty: '100' }],
    advisory_spo: [{ spo_number: 'SPO-2026-0402', arrival_date: '2026-10-14', qty: '250' }],
    borrow_candidates: [
      {
        source: 'other_location',
        warehouse_code: 'HQ',
        warehouse_id: WH_HQ,
        free_qty: '80',
        donor_impact: {
          free_before: '80',
          free_after_full_borrow: '0',
          committed_qty: '140',
        },
      },
    ],
    ...overrides,
  };
}

const BARE = line({
  components: [{ kind: 'buy', qty: '600', reason: 'Remaining uncovered need.' }],
  timely_spo: [],
  advisory_spo: [],
  borrow_candidates: [],
  pool_location: null,
  pool_reorder_level: null,
});

/**
 * SO406804 line 19 as `/supply` actually returns it (30 Aug 2026): the whole unit off ONE
 * purchase-order line nobody is waiting on, a day after the delivery date, and the five
 * options the ladder answered on the way there.
 */
const SUPPLY_BORROW = line({
  uom: 'EA',
  open_qty: '4',
  fulfilment_location: 'BRW-IB',
  components: [
    {
      kind: 'borrow',
      qty: '4',
      reason: 'Take 4 on order (PO 202606-S0006 line 5, arriving about 2 Sep 2026)',
      source_location: 'BRW-IB',
      source_warehouse_id: WH_BRW,
      rung: 'supply_borrow',
      cs_reason: null,
      supply_key: 'po:f09bdfcf-7fb7-489c-a8d0-7ce2380c0f05',
      supply_document: 'PO 202606-S0006 line 5',
      arrival_date: '2026-09-02',
    },
  ],
  options: [
    { step: 'use', label: 'Use our locations', whole: false, chosen: false },
    {
      step: 'order_borrow',
      label: 'Borrow on hand from a later order',
      whole: false,
      chosen: false,
    },
    {
      step: 'supply_borrow',
      label: 'Borrow incoming from a later order',
      whole: true,
      fulfil_date: '2026-09-02',
      days_late: 1,
      chosen: true,
    },
    { step: 'pool', label: 'Take from the pool', whole: false, chosen: false },
    {
      step: 'buy',
      label: 'Buy',
      whole: true,
      fulfil_date: '2026-11-28',
      days_late: 88,
      chosen: false,
    },
  ],
  timely_spo: [],
  advisory_spo: [],
  borrow_candidates: [],
});

const onChange = vi.fn();

function renderCard(
  source: SupplyLine,
  options: { frozen?: boolean; draft?: DraftLine } = {},
) {
  const draft = options.draft ?? draftFromLine(source);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SupplyLineCard
        line={source}
        draft={draft}
        frozen={options.frozen ?? false}
        onChange={onChange}
      />
    </QueryClientProvider>,
  );
}

/** The row for one section, so an input and an empty state can be told apart. */
function section(label: string): HTMLElement {
  const heading = screen.getByText(label);
  const row = heading.parentElement;
  if (!row) throw new Error(`No section row for ${label}`);
  return row as HTMLElement;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('SupplyLineCard', () => {
  it('names the line by number and item code, with its description and open quantity', () => {
    renderCard(line());

    expect(screen.getByText('Line 1 · CB6633')).toBeInTheDocument();
    expect(screen.getByText('CABANA S/STEEL FLOOR GRATING 6"')).toBeInTheDocument();
    expect(screen.getByText('600 UNIT')).toBeInTheDocument();
  });

  it('states the delivery date and the fulfilment location', () => {
    renderCard(line());

    expect(within(section('Delivery date')).getByText('01/09/2026')).toBeInTheDocument();
    expect(within(section('Fulfil from')).getByText('BRW-BB')).toBeInTheDocument();
  });

  it('states an absent date, location and description rather than dropping them', () => {
    renderCard(
      line({ required_date: null, fulfilment_location: null, description: null }),
    );

    expect(screen.getByText('No date')).toBeInTheDocument();
    // The location comes off the core sales-order line and is never defaulted, so its
    // absence names the record that is missing it rather than reading as a blank setting.
    expect(screen.getByText('Not on the sales order line')).toBeInTheDocument();
    expect(screen.getByText('No description')).toBeInTheDocument();
  });

  it('shows an unplannable line named and blocked, with the reason and no editor', () => {
    renderCard(
      line({
        unplannable_reason: 'No reconciled AutoCount line, so there is no open quantity to promise.',
        components: [],
      }),
    );

    expect(screen.getByText('Line 1 · CB6633')).toBeInTheDocument();
    expect(
      screen.getByText('No reconciled AutoCount line, so there is no open quantity to promise.'),
    ).toBeInTheDocument();
    // The line's own location is still stated: it is the reconciliation that is missing.
    expect(screen.getByText('BRW-BB')).toBeInTheDocument();
    for (const label of SECTIONS) expect(screen.queryByText(label)).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Buy on line 1')).not.toBeInTheDocument();
  });

  it('shows a line with no fulfilment location the same way, naming the sales order as the way out', () => {
    renderCard(line({ fulfilment_location: null, fulfilment_location_missing: true, components: [] }));

    expect(
      screen.getByText(
        'No fulfilment location on the sales order line, so nothing can be composed for it.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('Not on the sales order line')).toBeInTheDocument();
    expect(screen.queryByLabelText('Buy on line 1')).not.toBeInTheDocument();
  });

  it('shows each proposed component beside the reason its rule wrote (AC-B14)', () => {
    renderCard(line());

    expect(
      screen.getByText(
        'SPO-2026-0311 arrives at BRW-BB on 01 Sep 2026, on the delivery date.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Free stock at BRW-BB covers the need by the delivery date.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Remaining uncovered need.')).toBeInTheDocument();
  });

  it('states the balance it is being edited against', () => {
    renderCard(line());

    expect(
      screen.getByText('600 open = 100 incoming + 200 reserve + 0 borrow + 300 buy'),
    ).toBeInTheDocument();
  });

  it('names the incoming that covers the line, with its arrival date', () => {
    renderCard(line());

    const incoming = within(section('Incoming by the delivery date'));
    expect(incoming.getByText('SPO-2026-0311')).toBeInTheDocument();
    expect(incoming.getByText('· 100 · 01/09/2026')).toBeInTheDocument();
  });

  // -------------------------------------------------------------- empty states
  it('says nothing arrives by the delivery date rather than dropping the section', () => {
    renderCard(BARE);

    expect(
      within(section('Incoming by the delivery date')).getByText(
        'No incoming arrives by the delivery date.',
      ),
    ).toBeInTheDocument();
  });

  it('says there is no eligible free stock, and where it looked', () => {
    renderCard(BARE);

    expect(
      within(section('Reserve')).getByText('No eligible free stock to reserve at BRW-BB.'),
    ).toBeInTheDocument();
  });

  it('says nothing is borrowed and that nobody holds any', () => {
    renderCard(BARE);

    const borrow = within(section('Borrow'));
    expect(borrow.getByText('Nothing is borrowed on this line.')).toBeInTheDocument();
    expect(
      borrow.getByText('No other location or project holds free stock of this item.'),
    ).toBeInTheDocument();
    expect(borrow.queryByRole('button', { name: /add a borrow/i })).not.toBeInTheDocument();
  });

  it('says there is no later incoming rather than leaving the section blank', () => {
    renderCard(BARE);

    expect(
      within(section('Later incoming')).getByText(
        'No later incoming for this item at this location.',
      ),
    ).toBeInTheDocument();
  });

  it('says no pool is configured for the location', () => {
    renderCard(BARE);

    expect(
      screen.getByText('No pool is configured for this location.'),
    ).toBeInTheDocument();
  });

  it('says a pool with no reorder level has none, rather than reading as zero', () => {
    renderCard(line({ pool_reorder_level: null }));

    expect(screen.getByText('BRW-BB, no reorder level set.')).toBeInTheDocument();
  });

  // ----------------------------------------------------------------- evidence
  it('labels later incoming advisory and says it covers nothing (AC-B03)', () => {
    renderCard(line());

    const later = within(section('Later incoming'));
    expect(later.getByText('SPO-2026-0402')).toBeInTheDocument();
    expect(
      later.getByText('Advisory: it arrives after the delivery date and covers nothing.'),
    ).toBeInTheDocument();
  });

  it('shows dealer hot-selling evidence: the pool, its level, and that it is not offered', () => {
    renderCard(
      line({
        is_dealer_hot_selling: true,
        pool_cap: null,
        pool_reorder_level: '80',
      }),
    );

    expect(screen.getByText('Dealer hot-selling')).toBeInTheDocument();
    expect(
      screen.getByText('BRW-BB, reorder level 80. Dealer hot-selling: the pool is not offered.'),
    ).toBeInTheDocument();
  });

  it('shows project hot-selling evidence: the pool is offered while it stays available', () => {
    renderCard(
      line({
        is_project_hot_selling: true,
        pool_cap: null,
        pool_reorder_level: '80',
      }),
    );

    expect(screen.getByText('Project hot-selling')).toBeInTheDocument();
    expect(
      screen.getByText(
        'BRW-BB, reorder level 80. Project hot-selling: the pool is offered while it stays available.',
      ),
    ).toBeInTheDocument();
  });

  it('says the item is not classified rather than reading as not hot selling', () => {
    renderCard(line({ classification_unavailable: true }));

    expect(screen.getByText('Not classified')).toBeInTheDocument();
    expect(screen.queryByText('Not hot-selling')).not.toBeInTheDocument();
  });

  it('says a line with a classification and no A class on either demand class is not hot-selling', () => {
    renderCard(line());

    expect(screen.getByText('Not hot-selling')).toBeInTheDocument();
  });

  it('says cold at retail for a classified, non-hot retail letter', () => {
    renderCard(line({ dealer_classified: true }));

    expect(screen.getByText('Cold at retail')).toBeInTheDocument();
    expect(screen.queryByText('Dealer hot-selling')).not.toBeInTheDocument();
  });

  it('says cold at project for a classified, non-hot project letter', () => {
    renderCard(line({ project_classified: true }));

    expect(screen.getByText('Cold at project')).toBeInTheDocument();
    expect(screen.queryByText('Project hot-selling')).not.toBeInTheDocument();
  });

  it('never prints the word ABC or classification jargon anywhere on the card', () => {
    const { container } = renderCard(line({ dealer_classified: true }));

    expect(container.textContent).not.toMatch(/ABC/);
  });

  // -------------------------------------------------------------- the editing
  it('sends the typed reserve quantity up, leaving the rest of the draft alone', () => {
    const source = line();
    renderCard(source);

    fireEvent.change(screen.getByLabelText('Reserve at BRW-BB on line 1'), {
      target: { value: '150' },
    });

    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as DraftLine;
    expect(next.reserve[0].qty).toBe('150');
    expect(next.buy_qty).toBe('300');
  });

  it('sends the typed buy quantity up', () => {
    renderCard(line());

    fireEvent.change(screen.getByLabelText('Buy on line 1'), { target: { value: '350' } });

    expect((onChange.mock.calls[0][0] as DraftLine).buy_qty).toBe('350');
  });

  it('offers the borrow dialog only when somebody holds free stock of the item', () => {
    renderCard(line());

    expect(screen.getByRole('button', { name: /add a borrow/i })).toBeInTheDocument();
  });

  it('states a borrow donor impact, and takes a reason for it in place', () => {
    const source = line({
      open_qty: '100',
      components: [
        {
          kind: 'borrow',
          qty: '40',
          reason: 'Free stock at HQ, outside the reserve pool for this location.',
          source_location: 'HQ',
          source_warehouse_id: WH_HQ,
        },
        { kind: 'buy', qty: '60', reason: 'Remaining uncovered need.' },
      ],
    });
    const draft = draftFromLine(source);
    draft.borrow[0].donor_impact = {
      free_before: '80',
      free_after_full_borrow: '40',
      committed_qty: '140',
    };
    renderCard(source, { draft });

    expect(
      screen.getByText('80 free before, 40 after taking all of it, 140 committed.'),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Borrow from HQ on line 1'), {
      target: { value: '30' },
    });
    expect((onChange.mock.calls[0][0] as DraftLine).borrow[0].qty).toBe('30');
  });

  it('carries a group-borrow donor’s identity through Add a borrow into the draft (ladder v2 section E.4)', () => {
    // Gap the ladder v2 coder disclosed: the dialog already names the donor SO and its
    // agent, but the card's own `onAdd` used to drop those fields on the floor, so the
    // confirm payload never named the donor and no order-back was raised for it.
    const DONOR_LINE = 'd4000000-0000-4000-8000-000000000001';
    const source = line({
      open_qty: '100',
      components: [{ kind: 'buy', qty: '100', reason: 'Remaining uncovered need.' }],
      borrow_candidates: [
        {
          source: 'other_location',
          warehouse_code: 'BRW-BB',
          warehouse_id: WH_BRW,
          free_qty: '40',
          donor_impact: { free_before: '40', free_after_full_borrow: '0', committed_qty: '40' },
          rung: 'group_borrow',
          donor_so_number: 'SO371334',
          donor_line_no: 2,
          donor_agent_code: 'JEREMY',
          donor_core_line_id: DONOR_LINE,
          same_agent: false,
        },
      ],
    });
    renderCard(source);

    fireEvent.click(screen.getByRole('button', { name: /add a borrow/i }));
    expect(screen.getByText('SO371334 line 2')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '40' } });
    fireEvent.change(screen.getByLabelText(/^Reason/), {
      target: { value: 'Group borrow, auto-proposed.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add the borrow' }));

    const added = (onChange.mock.calls[0][0] as DraftLine).borrow[0];
    expect(added).toMatchObject({
      donor_core_line_id: DONOR_LINE,
      donor_so_number: 'SO371334',
      donor_line_no: 2,
      donor_agent_code: 'JEREMY',
      same_agent: false,
    });
  });

  it('removes a borrow from the line', () => {
    const source = line({
      open_qty: '40',
      components: [
        {
          kind: 'borrow',
          qty: '40',
          reason: 'Free stock at HQ, outside the reserve pool for this location.',
          source_location: 'HQ',
          source_warehouse_id: WH_HQ,
        },
      ],
    });
    renderCard(source);

    fireEvent.click(
      screen.getByRole('button', { name: 'Remove the borrow from HQ on line 1' }),
    );

    expect((onChange.mock.calls[0][0] as DraftLine).borrow).toEqual([]);
  });

  // ------------------------------------------- ladder v7.1 step 3: borrow incoming (S4)
  it('states the DOCUMENT a step-3 borrow comes off, not a donor’s stock position', () => {
    // SO406804 line 19 on the dev book: the row printed `0 free before, 0 after taking all
    // of it, 0 committed` - three true zeroes about a bin, and nothing at all about the
    // container being taken, which is not on any shelf yet.
    renderCard(SUPPLY_BORROW);

    const document = screen.getByTestId(`borrow-document-borrow-${LINE_ID}-0`);
    expect(
      within(document).getByText('PO 202606-S0006 line 5, 4 EA, arriving 02/09/2026'),
    ).toBeInTheDocument();
    // Nobody is waiting on it, so there is no order to name and no debt month to state.
    expect(
      within(document).getByText('Free: nobody is waiting on this document.'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/free before,/)).not.toBeInTheDocument();
  });

  it('names the donor order and the month its debt lands in, when one holds the document', () => {
    renderCard(
      line({
        uom: 'EA',
        open_qty: '50',
        components: [
          {
            kind: 'borrow',
            qty: '50',
            reason:
              'Borrow 50 arriving 15 Sep 2026 (SPO 202607-S0105) from SO414285 line 4 ' +
              '(JEREMY, due 12 Nov 2026); its debt lands in Nov 2026',
            source_location: 'BRW-IB',
            source_warehouse_id: WH_BRW,
            rung: 'supply_borrow',
            donor_so_number: 'SO414285',
            donor_line_no: 4,
            donor_agent_code: 'JEREMY',
            donor_required_date: '2026-11-12',
            supply_key: 'spo:9f2c1a44-1111-4c11-8c11-111111111111',
            supply_document: 'SPO 202607-S0105',
            arrival_date: '2026-09-15',
          },
        ],
        timely_spo: [],
        advisory_spo: [],
        borrow_candidates: [],
      }),
    );

    const document = screen.getByTestId(`borrow-document-borrow-${LINE_ID}-0`);
    expect(
      within(document).getByText('SPO 202607-S0105, 50 EA, arriving 15/09/2026'),
    ).toBeInTheDocument();
    expect(
      within(document).getByText(
        'From SO414285 line 4 (JEREMY), due 12/11/2026; its debt lands in Nov 2026.',
      ),
    ).toBeInTheDocument();
  });

  it('opens a step-3 borrow on the engine’s own sentence, so the Confirm is not blocked', () => {
    renderCard(SUPPLY_BORROW);

    const reason = screen.getByLabelText(/^Reason/) as HTMLTextAreaElement;
    expect(reason.value).toBe(
      'Take 4 on order (PO 202606-S0006 line 5, arriving about 2 Sep 2026)',
    );
    expect(screen.queryByText(/needs a reason/)).not.toBeInTheDocument();
  });

  it('renders the ladder’s five options from the /supply payload, marking the chosen one', () => {
    renderCard(SUPPLY_BORROW);

    const table = screen.getByTestId(`ladder-options-${LINE_ID}`);
    expect(
      within(table).getByText('Borrow incoming from a later order'),
    ).toBeInTheDocument();
    expect(within(table).getByText('Buy')).toBeInTheDocument();
    expect(
      within(table).getByTestId(`ladder-option-date-${LINE_ID}-supply_borrow`),
    ).toHaveTextContent('02/09/2026');
    expect(
      within(table).getByTestId(`ladder-option-late-${LINE_ID}-supply_borrow`),
    ).toHaveTextContent('1');
    // Exactly one row is the engine's proposal, and it is the step it composed from.
    expect(within(table).getAllByText('Chosen')).toHaveLength(1);
    expect(
      within(
        within(table).getByTestId(`ladder-option-${LINE_ID}-supply_borrow`),
      ).getByText('Chosen'),
    ).toBeInTheDocument();
  });

  it('says nothing about options on a line the payload states none for', () => {
    renderCard(line());

    expect(screen.queryByText('Options')).not.toBeInTheDocument();
  });

  it('warns that a discontinued product is discontinued and takes its reason (AC-B11)', () => {
    renderCard(line({ is_discontinued: true }));

    expect(
      screen.getByText('This product is discontinued. Buying it takes a reason.'),
    ).toBeInTheDocument();
    expect(within(section('Buy')).getByRole('textbox')).toBeInTheDocument();
  });

  it('asks for no buy reason on a product that is still made', () => {
    renderCard(line());

    expect(within(section('Buy')).queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('states what blocks this line, naming it', () => {
    const source = line();
    const draft = draftFromLine(source);
    draft.buy_qty = '200';
    renderCard(source, { draft });

    expect(
      screen.getByText('Line 1, CB6633: the components are short of the open quantity by 100.'),
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------- the frozen view
  it('shows the frozen composition in the same sections, in the same order, as the editor', () => {
    const source = line();
    const { unmount } = renderCard(source);
    const editing = SECTIONS.map((label) => screen.getByText(label).textContent);
    unmount();

    renderCard(
      line({
        frozen: {
          open_qty: '600',
          components: [
            {
              kind: 'timely_spo',
              qty: '100',
              reason: 'SPO-2026-0311 arrives at BRW-BB on the delivery date.',
              source_location: 'BRW-BB',
              source_warehouse_id: WH_BRW,
            },
            {
              kind: 'reserve',
              qty: '200',
              reason: 'Free stock at BRW-BB covers the need by the delivery date.',
              source_location: 'BRW-BB',
              source_warehouse_id: WH_BRW,
            },
            { kind: 'buy', qty: '300', reason: 'Remaining uncovered need.' },
          ],
        },
      }),
      { frozen: true },
    );

    expect(SECTIONS.map((label) => screen.getByText(label).textContent)).toEqual(editing);
    // The quantity stands where the input was: nothing to type into.
    expect(screen.queryByLabelText('Buy on line 1')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Reserve at BRW-BB on line 1')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /add a borrow/i })).not.toBeInTheDocument();
  });

  it('states the quantity the revision was balanced against, not the live one', () => {
    renderCard(
      line({
        open_qty: '700',
        frozen: {
          open_qty: '600',
          components: [{ kind: 'buy', qty: '600', reason: 'Remaining uncovered need.' }],
        },
      }),
      { frozen: true },
    );

    // The header and the one frozen component both read 600: the live 700 is nowhere.
    expect(screen.getAllByText('600 UNIT').length).toBeGreaterThan(0);
    expect(screen.queryByText('700 UNIT')).not.toBeInTheDocument();
    expect(screen.getByText('600 open = 600 composed')).toBeInTheDocument();
  });

  it('says None in a frozen section the revision decided nothing for', () => {
    renderCard(
      line({
        frozen: {
          open_qty: '600',
          components: [{ kind: 'buy', qty: '600', reason: 'Remaining uncovered need.' }],
        },
      }),
      { frozen: true },
    );

    expect(within(section('Reserve')).getByText('None')).toBeInTheDocument();
    expect(within(section('Borrow')).getByText('None')).toBeInTheDocument();
  });

  it('renders the reason CS typed beside the rule reason, on the borrow and on the buy', () => {
    renderCard(
      line({
        frozen: {
          open_qty: '600',
          components: [
            {
              kind: 'borrow',
              qty: '40',
              reason: 'Held by PRJ-0052 Seri Emas Phase 2.',
              source_location: 'JB',
              source_warehouse_id: WH_HQ,
              donor_project_ref: 'PRJ-0052 Seri Emas Phase 2',
              donor_project_id: DONOR_PROJECT,
              cs_reason: 'Their hand-over is in December.',
            },
            {
              kind: 'buy',
              qty: '560',
              reason: 'Remaining uncovered need.',
              cs_reason: 'Customer accepted the last production batch in writing.',
            },
          ],
        },
      }),
      { frozen: true },
    );

    expect(screen.getByText('Held by PRJ-0052 Seri Emas Phase 2.')).toBeInTheDocument();
    expect(screen.getByText('Their hand-over is in December.')).toBeInTheDocument();
    expect(
      screen.getByText('Customer accepted the last production batch in writing.'),
    ).toBeInTheDocument();
    // The donor is named by its reference, at its location.
    expect(screen.getByText(/for PRJ-0052 Seri Emas Phase 2/)).toBeInTheDocument();
  });

  it('keeps the later incoming section on a frozen line: it is evidence, not a decision', () => {
    renderCard(
      line({
        frozen: { open_qty: '600', components: [] },
      }),
      { frozen: true },
    );

    expect(within(section('Later incoming')).getByText('SPO-2026-0402')).toBeInTheDocument();
  });

  it('states no blocker on a frozen line: it is a decision that stands', () => {
    renderCard(
      line({
        open_qty: '700',
        frozen: {
          open_qty: '600',
          components: [{ kind: 'buy', qty: '600', reason: 'Remaining uncovered need.' }],
        },
      }),
      { frozen: true },
    );

    expect(screen.queryByText(/short of the open quantity/)).not.toBeInTheDocument();
  });

  it('renders no UUID-looking id anywhere on the card, editing or frozen', () => {
    const { container, unmount } = renderCard(line());
    expect(container.textContent).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i);
    unmount();

    const frozen = renderCard(
      line({
        frozen: {
          open_qty: '600',
          components: [
            {
              kind: 'borrow',
              qty: '600',
              reason: 'Held by PRJ-0052 Seri Emas Phase 2.',
              source_location: 'JB',
              source_warehouse_id: WH_HQ,
              donor_project_ref: 'PRJ-0052 Seri Emas Phase 2',
              donor_project_id: DONOR_PROJECT,
              cs_reason: 'Their hand-over is in December.',
            },
          ],
        },
      }),
      { frozen: true },
    );
    expect(frozen.container.textContent).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i);
  });
});
