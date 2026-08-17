/**
 * Stage 1C - one line's supply composition (journey steps 1 and 2).
 *
 * Two rules are pinned hardest. Every section renders whatever the answer is, so no
 * eligible stock, no incoming by the required date, no later incoming, no borrow candidate,
 * no reorder level and no classification each state that in place (AC-G02); and the read
 * view and the edit view are the SAME layout, so a confirmed line shows the frozen quantity
 * where the input was, in the same order, under the same headings.
 *
 * Every id in these fixtures is UUID-shaped on purpose: the card addresses warehouses and
 * donor projects by id and names them by code and reference, and the test proves it.
 */
import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
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
  'Incoming by the required date',
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
    classification_unavailable: false,
    is_discontinued: false,
    pool_location: 'BRW-BB',
    pool_cap: null,
    pool_reorder_level: '120',
    components: [
      {
        kind: 'timely_spo',
        qty: '100',
        reason: 'SPO-2026-0311 arrives at BRW-BB on 01 Sep 2026, on the required date.',
        source_location: 'BRW-BB',
        source_warehouse_id: WH_BRW,
      },
      {
        kind: 'reserve',
        qty: '200',
        reason: 'Free stock at BRW-BB covers the need by the required date.',
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

const onChange = vi.fn();

function renderCard(
  source: SupplyLine,
  options: { frozen?: boolean; draft?: DraftLine } = {},
) {
  const draft = options.draft ?? draftFromLine(source);
  return render(
    <SupplyLineCard
      line={source}
      draft={draft}
      frozen={options.frozen ?? false}
      onChange={onChange}
    />,
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

  it('states the required date and the fulfilment location', () => {
    renderCard(line());

    expect(within(section('Required')).getByText('01/09/2026')).toBeInTheDocument();
    expect(within(section('Fulfil from')).getByText('BRW-BB')).toBeInTheDocument();
  });

  it('states an absent date, location and description rather than dropping them', () => {
    renderCard(
      line({ required_date: null, fulfilment_location: null, description: null }),
    );

    expect(screen.getByText('No date')).toBeInTheDocument();
    expect(screen.getByText('Not set')).toBeInTheDocument();
    expect(screen.getByText('No description')).toBeInTheDocument();
  });

  it('shows each proposed component beside the reason its rule wrote (AC-B14)', () => {
    renderCard(line());

    expect(
      screen.getByText(
        'SPO-2026-0311 arrives at BRW-BB on 01 Sep 2026, on the required date.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Free stock at BRW-BB covers the need by the required date.'),
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

    const incoming = within(section('Incoming by the required date'));
    expect(incoming.getByText('SPO-2026-0311')).toBeInTheDocument();
    expect(incoming.getByText('· 100 · 01/09/2026')).toBeInTheDocument();
  });

  // -------------------------------------------------------------- empty states
  it('says nothing arrives by the required date rather than dropping the section', () => {
    renderCard(BARE);

    expect(
      within(section('Incoming by the required date')).getByText(
        'No incoming arrives by the required date.',
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
      later.getByText('Advisory: it arrives after the required date and covers nothing.'),
    ).toBeInTheDocument();
  });

  it('shows the hot-selling cap evidence: the pool, its level and where the draw stops', () => {
    renderCard(
      line({
        is_dealer_hot_selling: true,
        pool_cap: '40',
        pool_reorder_level: '80',
      }),
    );

    expect(screen.getByText('Hot selling')).toBeInTheDocument();
    expect(
      screen.getByText(
        'BRW-BB, reorder level 80. Dealer stock is out; the pool draw stops at 40.',
      ),
    ).toBeInTheDocument();
  });

  it('says the retail classification is unavailable rather than reading as not hot selling', () => {
    renderCard(line({ classification_unavailable: true }));

    expect(screen.getByText('Unavailable')).toBeInTheDocument();
    expect(screen.queryByText('Not hot selling')).not.toBeInTheDocument();
  });

  it('says a line with a classification and no A class is not hot selling', () => {
    renderCard(line());

    expect(screen.getByText('Not hot selling')).toBeInTheDocument();
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
              reason: 'SPO-2026-0311 arrives at BRW-BB on the required date.',
              source_location: 'BRW-BB',
              source_warehouse_id: WH_BRW,
            },
            {
              kind: 'reserve',
              qty: '200',
              reason: 'Free stock at BRW-BB covers the need by the required date.',
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
