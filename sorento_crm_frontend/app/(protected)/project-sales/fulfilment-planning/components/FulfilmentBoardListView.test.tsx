/**
 * The board as a LIST (D2, PLAN-demo-followups-19aug-ladder-v2 "a list view of the board so
 * Approve all can be seen from an overview"): one row per contributing line, across every cell
 * of the board, with the same `onDecide` write path the grid view uses.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  BoardContribution,
  BoardDecision,
  BoardDraft,
} from '../../_shared/types/fulfilmentPlanning.types';
import type { BoardChangeAnnotation } from '../../_shared/lib/boardChangeAnnotations';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { FulfilmentBoardListView } from './FulfilmentBoardListView';
import { suggestedDecisionFor } from '../../_shared/lib/boardAmend';

function contribution(overrides: Partial<BoardContribution> = {}): BoardContribution {
  return {
    key: 'so-1:line-10',
    sales_order_id: 'so-1',
    line_id: 'core-line-10',
    product_id: 'prod-1',
    so_number: 'SO397450',
    customer_name: 'Tuju Residences Sdn Bhd',
    agent_code: 'JEREMY',
    agent_label: 'Jeremy Lee',
    project_label: 'Tuju Residences',
    line_no: 10,
    item_code: 'B2155-NL-BLUE',
    qty: '43',
    qty_outstanding: '43',
    required_date: '2026-09-04',
    unplannable: false,
    rank_score: 0.82,
    rank_factors: [],
    sources: [{ kind: 'buy', qty: '43', reason: 'Nothing free at any location.' }],
    trail: [],
    item_flags: null,
    contested: false,
    covered: false,
    decision: null,
    ...overrides,
  };
}

function renderView(
  overrides: {
    contributions?: BoardContribution[];
    draft?: BoardDraft;
    onDecide?: (key: string, decision: BoardDecision | null) => void;
    onDecideMany?: (keys: string[]) => Promise<{ saved: number; failed: number }>;
    annotations?: Map<string, BoardChangeAnnotation[]>;
    externalSearch?: string;
    focusKey?: string | null;
    onFocusHandled?: () => void;
  } = {},
) {
  const rows = overrides.contributions ?? [contribution()];
  const onDecide = overrides.onDecide ?? vi.fn();
  // D15: the same quiet-bulk path the panel wires up for real, standing in here for it - each
  // key's own suggestion, posted through the same `onDecide` a test already reads, so the
  // existing "bulk quick save" assertions on `onDecide`'s own calls still hold.
  const onDecideMany =
    overrides.onDecideMany ??
    vi.fn(async (keys: string[]) => {
      let saved = 0;
      for (const key of keys) {
        const target = rows.find((entry) => entry.key === key);
        if (!target) continue;
        onDecide(key, suggestedDecisionFor(target));
        saved += 1;
      }
      return { saved, failed: keys.length - saved };
    });
  const utils = render(
    <FulfilmentBoardListView
      contributions={rows}
      draft={overrides.draft ?? {}}
      onDecide={onDecide}
      onDecideMany={onDecideMany}
      annotations={overrides.annotations}
      externalSearch={overrides.externalSearch}
      focusKey={overrides.focusKey}
      onFocusHandled={overrides.onFocusHandled}
    />,
  );
  return { ...utils, onDecide, onDecideMany };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('FulfilmentBoardListView', () => {
  it('renders one row per contributing line with SO, agent, product and proposal', async () => {
    renderView();

    expect(await screen.findByText('SO397450')).toBeInTheDocument();
    // AC-C13 (owner feedback 13 Sep): the line number is folded beside the SO number as
    // "(Line 10)", its own text node inside the same one-line cell - not a stacked "Line 10".
    expect(screen.getByText('(Line 10)')).toBeInTheDocument();
    expect(screen.getByText('JEREMY')).toBeInTheDocument();
    expect(screen.getByText('Tuju Residences Sdn Bhd')).toBeInTheDocument();
    expect(screen.getByText('B2155-NL-BLUE')).toBeInTheDocument();
    expect(screen.getByText('Buy 43')).toBeInTheDocument();
  });

  it('renders one row per line when several contribute', async () => {
    renderView({
      contributions: [
        contribution({ key: 'so-1:line-10', so_number: 'SO397450', line_no: 10 }),
        contribution({ key: 'so-2:line-20', so_number: 'SO397451', line_no: 20 }),
      ],
    });

    expect(await screen.findByText('SO397450')).toBeInTheDocument();
    expect(screen.getByText('SO397451')).toBeInTheDocument();
    expect(screen.getByText('(Line 10)')).toBeInTheDocument();
    expect(screen.getByText('(Line 20)')).toBeInTheDocument();
  });

  // S6 (PLAN-scm-oi-worklist-excel-parity.md R-J, AC-P2/AC-P3): the board's ONE search
  // box, wired through as `externalSearch`, has to actually narrow this view's own rows -
  // today it is threaded through unused by every existing test here, so deleting the prop
  // entirely would still leave this whole file green.
  describe('S6/AC-P2/AC-P3: the boards one search box narrows this view too', () => {
    it('renders only the contributions matching externalSearch, by customer name', async () => {
      renderView({
        contributions: [
          contribution({ key: 'so-1:line-10', so_number: 'SO397450', customer_name: 'Kee Lin Sdn Bhd' }),
          contribution({ key: 'so-2:line-20', so_number: 'SO397451', customer_name: 'Optad Sdn Bhd' }),
        ],
        externalSearch: 'KEE LIN',
      });

      expect(await screen.findByText('SO397450')).toBeInTheDocument();
      expect(screen.queryByText('SO397451')).not.toBeInTheDocument();
    });

    it('matches by SO number, agent code and item code too - the same fields the grid reads', async () => {
      renderView({
        contributions: [
          contribution({ key: 'so-1:line-10', so_number: 'SO397450' }),
          contribution({ key: 'so-2:line-20', so_number: 'SO999999' }),
        ],
        externalSearch: 'SO397450',
      });

      expect(await screen.findByText('SO397450')).toBeInTheDocument();
      expect(screen.queryByText('SO999999')).not.toBeInTheDocument();
    });

    it('renders every row when externalSearch is empty or absent', async () => {
      renderView({
        contributions: [
          contribution({ key: 'so-1:line-10', so_number: 'SO397450' }),
          contribution({ key: 'so-2:line-20', so_number: 'SO397451' }),
        ],
        externalSearch: '',
      });

      expect(await screen.findByText('SO397450')).toBeInTheDocument();
      expect(screen.getByText('SO397451')).toBeInTheDocument();
    });

    it('renders no search box of its own - "Every contributing line" has one search, the boards', async () => {
      renderView();

      await screen.findByText('SO397450');
      expect(screen.queryByPlaceholderText(/search/i)).not.toBeInTheDocument();
      expect(screen.queryByRole('searchbox')).not.toBeInTheDocument();
    });
  });

  /** No revision number on the pill (R6): "Confirmed", full stop. */
  it('shows a pill reading Confirmed for a row already covered by an active decision, with no rev', async () => {
    renderView({
      contributions: [
        contribution({
          covered: true,
          decision: {
            revision_no: 3,
            timely_spo_qty: '0',
            reserve: [],
            borrow: [],
            buy_qty: '43',
          },
        }),
      ],
    });

    const pill = await screen.findByTestId('decision-pill-so-1:line-10');
    expect(pill.textContent).toBe('Confirmed');
  });

  it('calls onDecide with an approved verdict from the expanded row’s Save (pill + panel, not a row button)', async () => {
    const { onDecide } = renderView();

    // No row-level Approve button any more: the row expands into the same panel the grid
    // uses, and its one Save reads the untouched suggestion as an approval.
    // Clicked on the Agent cell, not the Sales order cell - that one is a `Link` that stops
    // the click from bubbling to the row, on purpose (it navigates instead of expanding).
    expect(screen.queryByRole('button', { name: /^approve$/i })).not.toBeInTheDocument();
    await screen.findByText('SO397450');
    fireEvent.click(screen.getByText('JEREMY'));
    fireEvent.click(screen.getByRole('button', { name: 'Save decision' }));

    // D11: the composition rides along with an approval too - the exact shape is
    // `BoardLineDecisionPanel.test.tsx`'s own job, this only checks the verdict still reaches
    // `onDecide` from the row's expanded panel.
    await waitFor(() =>
      expect(onDecide).toHaveBeenCalledWith(
        'so-1:line-10',
        expect.objectContaining({
          verdict: 'approved',
          suspected_system_issue: false,
        }),
      ),
    );
  });

  it('updates the pill when the draft prop carries a decision for the row', async () => {
    const row = contribution();
    const { rerender } = render(
      <FulfilmentBoardListView
        contributions={[row]}
        draft={{}}
        onDecide={vi.fn()}
        onDecideMany={vi.fn()}
      />,
    );

    expect(
      await screen.findByTestId('decision-pill-so-1:line-10'),
    ).toHaveTextContent('Suggested');

    rerender(
      <FulfilmentBoardListView
        contributions={[row]}
        draft={{ [row.key]: { verdict: 'approved' } }}
        onDecide={vi.fn()}
        onDecideMany={vi.fn()}
      />,
    );

    // Saved (S4, R-F), not Approved - the pill reads the plain "has this been dealt with"
    // word once a decision exists, whichever of the two verbs produced it.
    expect(
      await screen.findByTestId('decision-pill-so-1:line-10'),
    ).toHaveTextContent('Saved');
  });

  it('quotes THIS line\u2019s own Available beside the Reserve input (C4)', async () => {
    renderView({
      contributions: [
        contribution({
          fulfilment_location: 'BRW-AM',
          fulfilment_warehouse_id: 'wh-am',
          sources: [
            {
              kind: 'reserve',
              qty: '9',
              location: 'BRW-AM',
              warehouse_id: 'wh-am',
              reason: 'Own group.',
            },
            { kind: 'buy', qty: '34', reason: 'The rest is bought.' },
          ],
          // The figures ride on the contribution, netted of this line's own quantity: the
          // list spans every cell, so there is no cell to read them off.
          locations: [
            {
              location: 'BRW-AM',
              warehouse_id: 'wh-am',
              product_id: 'prod-1',
              qty: '43',
              qty_demand: '43',
              available_qty: '9',
              qty_free: '9',
              qty_free_remaining: '9',
            },
          ],
        }),
      ],
    });

    await screen.findByText('SO397450');
    fireEvent.click(screen.getByText('JEREMY'));

    expect(await screen.findByText('9 available')).toBeInTheDocument();
  });

  it('asks before it closes a row holding an unsaved edit (C5)', async () => {
    // The coder's multi-open rework (8d7b06766): opening ANOTHER row never prompts any
    // more - several rows are meant to be open together - only CLOSING a dirty one does.
    // So row A's own gesture has to be a CLOSE (clicking A again), not opening B.
    renderView({
      contributions: [
        contribution(),
        contribution({ key: 'so-1:line-20', line_no: 20, so_number: 'SO397451' }),
      ],
    });

    await screen.findByText('SO397450');
    fireEvent.click(screen.getAllByText('JEREMY')[0]);
    // An edit nobody has saved: the reason box on the open panel.
    fireEvent.change(screen.getByPlaceholderText('In your own words'), {
      target: { value: 'The group is short' },
    });

    // Close row A (click it again), not open row B.
    fireEvent.click(screen.getAllByText('JEREMY')[0]);

    expect(await screen.findByRole('alertdialog')).toHaveTextContent(
      'Leave this decision unsaved?',
    );
    // Kept open until the question is answered.
    expect(screen.getByText('The group is short')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Discard' }));
    await waitFor(() =>
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument(),
    );
  });

  it('marks an unplannable line rather than offering it a verdict', async () => {
    renderView({ contributions: [contribution({ unplannable: true })] });

    // Both the Suggested and the Verdict cells read "Needs a location" for an unplannable
    // line - the ladder was never walked, so there is nothing else either could say.
    expect(await screen.findAllByText('Needs a location')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument();
  });
});

describe('FulfilmentBoardListView marks a row whose supply is already decided', () => {
  /**
   * The same tick the grid puts on a fully-decided cell, here per row - one row IS one
   * contribution, so it is decided or it is not. The Verdict column already states the
   * revision in words; this is what makes it scannable down a list of two hundred.
   */
  const decided = (revisionNo: number) =>
    contribution({
      covered: true,
      decision: {
        revision_no: revisionNo,
        timely_spo_qty: '0',
        reserve: [],
        borrow: [],
        buy_qty: '43',
      },
    });

  it('ticks the row and names the revision', async () => {
    renderView({ contributions: [decided(3)] });

    const marker = await screen.findByTestId('board-decided-marker');
    expect(marker).toHaveAttribute('title', 'Decided rev 3');
  });

  it('leaves an undecided row unticked', async () => {
    renderView();

    expect(await screen.findByText('SO397450')).toBeInTheDocument();
    expect(screen.queryByTestId('board-decided-marker')).not.toBeInTheDocument();
  });
});

/**
 * DELETED, owner feedback 13 Sep (Slice C board display, AC-C13): this block ("FulfilmentBoard
 * ListView agrees with the grid about the supply bar") pinned `data-testid="supply-bar"` /
 * `data-decided` / `span[data-kind=...]` on the Suggested and Decided cells - exactly what
 * AC-C13 retires ("the Suggested and Decided cells carry no progress bar"; see
 * `FulfilmentBoardListView.test.tsx`'s own "thin rows" describe block below, which pins the
 * bar's ABSENCE instead). The intent this block actually existed for - the list and the grid
 * must never disagree about what was suggested and what was decided - is not lost: it is
 * `describe('FulfilmentBoardListView says what was suggested and what was decided', ...)`
 * below, which already asserts the same two states this block did ("BRW 43 (BRW)" faded /
 * undecided, "Buy 43" solid / decided) as the rendered WORDS rather than as bar attributes,
 * and needs no change for AC-C13 to land.
 */

/**
 * AC-D4: Suggested and Decided, side by side, in PLAN section 2's own words.
 *
 * One "Proposal" column used to show the DECISION on a decided line and the PROPOSAL on an
 * undecided one, so the one comparison the planner opens this view to make - did we do what
 * the engine said - could not be made at all.
 */
describe('FulfilmentBoardListView says what was suggested and what was decided', () => {
  const amended = contribution({
    covered: true,
    fulfilment_location: 'BRW-BB',
    proposed: {
      components: [
        { kind: 'reserve', rung: 'pool', qty: '43', location: 'BRW', reason: 'pool' },
      ],
    },
    sources: [{ kind: 'buy', rung: 'buy', qty: '43', reason: 'Bought, as confirmed.' }],
    decision: {
      revision_no: 1,
      timely_spo_qty: '0',
      reserve: [],
      borrow: [],
      buy_qty: '43',
    },
  });

  it('carries both columns', async () => {
    renderView({ contributions: [amended] });

    expect(await screen.findByText('Suggested')).toBeInTheDocument();
    expect(screen.getByText('Decided')).toBeInTheDocument();
  });

  it('states the engine composition on one side and the decision on the other', async () => {
    renderView({ contributions: [amended] });

    expect(await screen.findByText('BRW 43 (BRW)')).toBeInTheDocument();
    expect(screen.getByText('Buy 43')).toBeInTheDocument();
  });

  it('says Not recorded, never "nothing", for a revision that froze no proposal', async () => {
    const old = contribution({
      covered: true,
      sources: [{ kind: 'buy', rung: 'buy', qty: '43', reason: 'Bought, as confirmed.' }],
      decision: {
        revision_no: 1,
        timely_spo_qty: '0',
        reserve: [],
        borrow: [],
        buy_qty: '43',
      },
    });

    renderView({ contributions: [old] });

    expect(await screen.findByText('Not recorded')).toBeInTheDocument();
  });

  it('says Not decided while nobody has decided the line', async () => {
    renderView({
      contributions: [
        contribution({
          proposed: {
            components: [
              { kind: 'reserve', rung: 'pool', qty: '43', location: 'BRW', reason: 'pool' },
            ],
          },
        }),
      ],
    });

    expect(await screen.findByText('Not decided')).toBeInTheDocument();
  });

  /**
   * AC-S3-2 (14 September 2026 ruling). A line carrying a LIVE order inquiry row from the
   * migrated book (#875) is decided on the buying side: `covered` true, `decision` null,
   * because purchasing was told about it before any board existed and there is no frozen
   * composition to print.
   *
   * So the Decided column names the INQUIRY where the composition would be. It read "Not
   * decided" over a line somebody has already been told to buy, which invites a second Buy
   * for the same units - the one reading this criterion exists to stop.
   */
  it('names the order inquiry that decided the line, where the composition would be', async () => {
    renderView({
      contributions: [
        contribution({
          covered: true,
          decision: null,
          proposed: null,
          trail: [],
          sources: [],
          order_inquiry: {
            inquiry_no: 'OI-000418',
            state: 'raised',
            ack_state: 'acknowledged',
          },
        }),
      ],
    });

    expect(await screen.findByText('OI-000418')).toBeInTheDocument();
    expect(screen.queryByText('Not decided')).not.toBeInTheDocument();
  });
});

/**
 * AC-RL-06 (`PLAN-oi-replan-received-links.md`, 17 Sep ruling, "board too"): the SAME
 * word the OI worklist chip carries shows up beside the inquiry number here, so CS
 * reads the stage before confirming - `received` once every document behind the line
 * is fully received, `used` once the row was itself redirected (AC-RL-10). RED: neither
 * word renders yet (grepped `FulfilmentBoardListView.tsx` before writing these -
 * `contributionInquiryDecision` prints only `inquiry_no`).
 */
describe('AC-RL-06 (`PLAN-oi-replan-received-links.md`, 17 Sep ruling): the inquiry cell also reads "received" / "used"', () => {
  it('reads the word "received" beside the inquiry number when every document behind the line is received', async () => {
    renderView({
      contributions: [
        contribution({
          covered: true,
          decision: null,
          proposed: null,
          trail: [],
          sources: [],
          order_inquiry: {
            inquiry_no: 'OI-000418',
            state: 'partly_linked',
            ack_state: 'acknowledged',
            documents: [{ document: 'SPO-2026/01-0143', kind: 'spo', received: true }],
            redirected: false,
          },
        }),
      ],
    });

    expect(await screen.findByText('OI-000418')).toBeInTheDocument();
    expect(screen.getByText('received')).toBeInTheDocument();
  });

  it('reads the word "used" instead when the row was redirected - never "received" alongside it', async () => {
    renderView({
      contributions: [
        contribution({
          covered: true,
          decision: null,
          proposed: null,
          trail: [],
          sources: [],
          order_inquiry: {
            inquiry_no: 'OI-000477',
            state: 'partly_linked',
            ack_state: 'acknowledged',
            documents: [{ document: 'SPO-2026/01-0143', kind: 'spo', received: true }],
            redirected: true,
          },
        }),
      ],
    });

    expect(await screen.findByText('OI-000477')).toBeInTheDocument();
    expect(screen.getByText('used')).toBeInTheDocument();
    expect(screen.queryByText('received')).not.toBeInTheDocument();
  });

  it('reads neither word when the documents are not all received and the row was not redirected', async () => {
    renderView({
      contributions: [
        contribution({
          covered: true,
          decision: null,
          proposed: null,
          trail: [],
          sources: [],
          order_inquiry: {
            inquiry_no: 'OI-000900',
            state: 'raised',
            ack_state: 'acknowledged',
            documents: [{ document: '202607-S0105', kind: 'po', received: false }],
            redirected: false,
          },
        }),
      ],
    });

    expect(await screen.findByText('OI-000900')).toBeInTheDocument();
    expect(screen.queryByText('received')).not.toBeInTheDocument();
    expect(screen.queryByText('used')).not.toBeInTheDocument();
  });

  /**
   * 17 Sep review round: `contributionInquiryDecision` (`supplyVocabulary.ts`) returns
   * `null` unless `covered && !decision`, so the whole inquiry branch - number AND word -
   * never renders on an UNCOVERED line, which is exactly the shape a live Buy proposal
   * sits on (the default `contribution()` fixture: `covered: false`, `sources: [{kind:
   * 'buy', ...}]`). The owner wants the word readable on precisely this line - the one CS
   * is about to confirm a fresh Buy for - so `received`/`used` must read off
   * `contribution.order_inquiry?.documents` directly, never gated on `covered`/`decision`
   * at all. RED: today this contribution prints "Not decided", no word, no inquiry number.
   */
  it('AC-RL-06 amended: reads "received" even when covered is false and the line carries a live Buy proposal', async () => {
    renderView({
      contributions: [
        contribution({
          covered: false,
          decision: null,
          sources: [{ kind: 'buy', qty: '43', reason: 'Nothing free at any location.' }],
          order_inquiry: {
            inquiry_no: 'OI-000901',
            state: 'partly_linked',
            ack_state: 'acknowledged',
            documents: [{ document: 'SPO-2026/01-0143', kind: 'spo', received: true }],
            redirected: false,
          },
        }),
      ],
    });

    // The live Buy proposal keeps showing - this is not a replacement for it.
    expect(await screen.findByText('Buy 43')).toBeInTheDocument();
    expect(screen.getByText('received')).toBeInTheDocument();
  });

  it('AC-RL-06 amended: reads "used" even when covered is false and the row was redirected', async () => {
    renderView({
      contributions: [
        contribution({
          covered: false,
          decision: null,
          sources: [{ kind: 'buy', qty: '20', reason: 'Nothing free at any location.' }],
          order_inquiry: {
            inquiry_no: 'OI-000902',
            state: 'partly_linked',
            ack_state: 'acknowledged',
            documents: [{ document: 'SPO-2026/01-0143', kind: 'spo', received: true }],
            redirected: true,
          },
        }),
      ],
    });

    expect(await screen.findByText('Buy 20')).toBeInTheDocument();
    expect(screen.getByText('used')).toBeInTheDocument();
    expect(screen.queryByText('received')).not.toBeInTheDocument();
  });
});

/**
 * Owner finding, 17 Sep 2026: the block above puts the word in the DECIDED cell, and only
 * when `contributionInquiryDecision` returns non-null - which requires `!contributionDecision(
 * ...)`, i.e. no draft and no decision. On a board where every line is Saved (draft) or
 * Suggested, the Decided cell prints the composition instead and the word never renders at
 * all. AC-RL-06 is amended again: the stage word belongs BESIDE THE PRODUCT, driven directly
 * off `contribution.order_inquiry.documents` / `redirected`, on every line regardless of
 * verdict, draft or decision - never gated on whether the Decided cell has something else to
 * print. RED: the Product cell prints only `item_code` today (see the column's `cell` at
 * `FulfilmentBoardListView.tsx`'s `id: 'product'`); no such word renders there under any
 * fixture, decided or not.
 */
describe('AC-RL-06 (amended 17 Sep): the stage word sits beside the PRODUCT, on every line', () => {
  it('renders "received" as a pill in the Product cell on a SAVED line (Decided cell prints Buy 280), when every document is received', async () => {
    const row = contribution({
      qty: '280',
      qty_outstanding: '280',
      order_inquiry: {
        inquiry_no: 'OI-000950',
        state: 'partly_linked',
        ack_state: 'acknowledged',
        documents: [{ document: 'SPO-2026/02-0009', kind: 'spo', received: true }],
        redirected: false,
      },
    });

    renderView({
      contributions: [row],
      draft: {
        [row.key]: {
          verdict: 'approved',
          revision_no: 1,
          timely_spo_qty: '0',
          reserve: [],
          borrow: [],
          buy_qty: '280',
        },
      },
    });

    // The Decided cell keeps stating the composition - this is not a replacement for it.
    expect(await screen.findByText('Buy 280')).toBeInTheDocument();

    const word = screen.getByText('received');
    expect(word).toBeInTheDocument();
    // "the same shared pill the OI worklist uses" - a `Badge`, not a bare span: the
    // component's own base class names every pill it renders (`badge.tsx`), and a plain
    // `<span>` styled by hand would not carry it.
    expect(word.closest('[class*="rounded-full"]')).not.toBeNull();

    // Beside the PRODUCT: inside the same cell as the item code, not the Decided cell.
    const productCell = screen.getByText(row.item_code).closest('td');
    expect(productCell).not.toBeNull();
    expect(within(productCell as HTMLElement).getByText('received')).toBeInTheDocument();
  });

  it('renders "used" in the Product cell when the row was redirected, alongside a live Buy proposal, no draft', async () => {
    const row = contribution({
      covered: false,
      decision: null,
      sources: [{ kind: 'buy', qty: '96', reason: 'Nothing free at any location.' }],
      order_inquiry: {
        inquiry_no: 'OI-000951',
        state: 'partly_linked',
        ack_state: 'acknowledged',
        documents: [{ document: 'SPO-2026/01-0143', kind: 'spo', received: true }],
        redirected: true,
      },
    });

    renderView({ contributions: [row] });

    expect(await screen.findByText('Buy 96')).toBeInTheDocument();

    const productCell = screen.getByText(row.item_code).closest('td');
    expect(productCell).not.toBeNull();
    expect(within(productCell as HTMLElement).getByText('used')).toBeInTheDocument();
    expect(within(productCell as HTMLElement).queryByText('received')).not.toBeInTheDocument();
  });

  it('renders no word in the Product cell while one of the line’s documents is still open', async () => {
    const row = contribution({
      order_inquiry: {
        inquiry_no: 'OI-000952',
        state: 'partly_linked',
        ack_state: 'acknowledged',
        documents: [
          { document: 'SPO-2026/01-0143', kind: 'spo', received: true },
          { document: '202607-S0105', kind: 'po', received: false },
        ],
        redirected: false,
      },
    });

    renderView({ contributions: [row] });

    const productCell = screen.getByText(row.item_code).closest('td');
    expect(productCell).not.toBeNull();
    expect(within(productCell as HTMLElement).queryByText('received')).not.toBeInTheDocument();
    expect(within(productCell as HTMLElement).queryByText('used')).not.toBeInTheDocument();
  });

  it('(d) an undecided covered line still names the inquiry and its word in the Decided cell (unchanged)', async () => {
    renderView({
      contributions: [
        contribution({
          covered: true,
          decision: null,
          proposed: null,
          trail: [],
          sources: [],
          order_inquiry: {
            inquiry_no: 'OI-000418',
            state: 'partly_linked',
            ack_state: 'acknowledged',
            documents: [{ document: 'SPO-2026/01-0143', kind: 'spo', received: true }],
            redirected: false,
          },
        }),
      ],
    });

    expect(await screen.findByText('OI-000418')).toBeInTheDocument();
    expect(screen.queryByText('Not decided')).not.toBeInTheDocument();
  });
});

/**
 * D14 (the captain: a quick save for the lines that need nothing amended, and a per-line Undo
 * for the one that a quick save was wrong for).
 */
describe('FulfilmentBoardListView: quick save as suggested and per-line undo', () => {
  function threeRows() {
    return [
      contribution({ key: 'so-1:line-10', so_number: 'SO397450', line_no: 10 }),
      contribution({ key: 'so-2:line-20', so_number: 'SO397451', line_no: 20 }),
      contribution({ key: 'so-3:line-30', so_number: 'SO397452', line_no: 30 }),
    ];
  }

  function selectAll() {
    fireEvent.click(
      screen.getByRole('checkbox', { name: 'Select all rows on this page' }),
    );
  }

  it('offers no bulk save button until a row is ticked', async () => {
    renderView({ contributions: threeRows() });

    await screen.findByText('SO397450');
    expect(
      screen.queryByRole('button', { name: /^Save as suggested/ }),
    ).not.toBeInTheDocument();
  });

  it('saves every ticked row with the engine composition and clears the selection', async () => {
    const { onDecide, onDecideMany } = renderView({ contributions: threeRows() });

    await screen.findByText('SO397450');
    selectAll();
    expect(
      await screen.findByRole('button', { name: 'Save as suggested (3)' }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Save as suggested (3)' }));

    // D15: posts through `onDecideMany` (the panel's own quiet-bulk path), never a loop of
    // `onDecide` calls made here - the mock still forwards each key's suggestion to `onDecide`
    // for the assertions below to read, but the PROP actually reached has to be this one.
    expect(onDecideMany).toHaveBeenCalledTimes(1);
    expect(onDecideMany).toHaveBeenCalledWith([
      'so-1:line-10',
      'so-2:line-20',
      'so-3:line-30',
    ]);
    expect(onDecide).toHaveBeenCalledTimes(3);
    for (const call of vi.mocked(onDecide).mock.calls) {
      expect(call[1]).toEqual(
        expect.objectContaining({ verdict: 'approved', buy_qty: '43' }),
      );
    }
    expect(
      screen.queryByRole('button', { name: /^Save as suggested/ }),
    ).not.toBeInTheDocument();
  });

  it('does not offer a covered row a checkbox', async () => {
    renderView({
      contributions: [
        contribution({
          covered: true,
          decision: {
            revision_no: 1,
            timely_spo_qty: '0',
            reserve: [],
            borrow: [],
            buy_qty: '43',
          },
        }),
      ],
    });

    await screen.findByText('SO397450');
    expect(
      screen.getByRole('checkbox', { name: 'Select SO397450 line 10' }),
    ).toBeDisabled();
  });

  it('does not offer an already-saved row a checkbox', async () => {
    const row = contribution();
    renderView({
      contributions: [row],
      draft: { [row.key]: { verdict: 'approved' } },
    });

    await screen.findByText('SO397450');
    expect(
      screen.getByRole('checkbox', { name: 'Select SO397450 line 10' }),
    ).toBeDisabled();
  });

  it('shows no Undo until the row carries a draft', async () => {
    renderView();

    await screen.findByText('SO397450');
    expect(
      screen.queryByRole('button', { name: /^Undo SO/ }),
    ).not.toBeInTheDocument();
  });

  it('Undo on a saved row deletes its draft', async () => {
    const row = contribution();
    const { onDecide } = renderView({
      contributions: [row],
      draft: { [row.key]: { verdict: 'approved' } },
    });

    await screen.findByText('SO397450');
    fireEvent.click(screen.getByRole('button', { name: 'Undo SO397450 line 10' }));

    expect(onDecide).toHaveBeenCalledWith('so-1:line-10', null);
  });
});

/**
 * PLAN-board-change-proposed-pill (AC-1/AC-2/AC-3): a line the board pre-marked itself -
 * `preMarkedKeys` seeding `{ verdict: 'approved', preMarked: true }` into the session draft,
 * with nothing yet saved on the server - reads "Change proposed" and offers no Undo (nothing
 * here has actually been saved to undo). A real saved draft on the same shape still reads
 * "Saved" with its Undo.
 */
describe('FulfilmentBoardListView: a pre-marked row (PLAN-board-change-proposed-pill)', () => {
  it('reads "Change proposed" and shows no Undo for a pre-mark with no server-saved draft', async () => {
    const row = contribution();
    renderView({
      contributions: [row],
      draft: { [row.key]: { verdict: 'approved', preMarked: true } },
    });

    expect(
      await screen.findByTestId(`decision-pill-${row.key}`),
    ).toHaveTextContent('Change proposed');
    expect(
      screen.queryByRole('button', { name: `Undo ${row.so_number} line ${row.line_no}` }),
    ).not.toBeInTheDocument();
  });

  it('still reads "Saved" with its Undo once the line carries a real server-saved draft', async () => {
    const row = contribution({
      draft: {
        decision: { verdict: 'approved' },
        saved_by: 'Eling',
        saved_at: '2026-09-03T01:00:00',
      },
    });
    renderView({
      contributions: [row],
      draft: { [row.key]: { verdict: 'approved', preMarked: true } },
    });

    expect(
      await screen.findByTestId(`decision-pill-${row.key}`),
    ).toHaveTextContent('Saved');
    expect(
      screen.getByRole('button', { name: `Undo ${row.so_number} line ${row.line_no}` }),
    ).toBeInTheDocument();
  });
});

/**
 * D15: a one-click save on the row itself, beside the pill - a planner who agrees with the
 * engine no longer has to open the row and press Save inside it. Exactly one of the two icons
 * (this one, or D14's Undo) ever shows for a given row, since `canQuickSave` already excludes
 * a drafted line.
 */
describe('FulfilmentBoardListView: one-click save on the row (D15)', () => {
  it('offers the save icon on an eligible row', async () => {
    renderView();

    expect(
      await screen.findByRole('button', {
        name: 'Save SO397450 line 10 as suggested',
      }),
    ).toBeInTheDocument();
  });

  it('posts the engine composition through onDecide, as a single line', async () => {
    const row = contribution();
    const { onDecide } = renderView({ contributions: [row] });

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Save SO397450 line 10 as suggested',
      }),
    );

    expect(onDecide).toHaveBeenCalledTimes(1);
    expect(onDecide).toHaveBeenCalledWith(
      row.key,
      expect.objectContaining({ verdict: 'approved', buy_qty: '43' }),
    );
  });

  it('offers no save icon on a covered row', async () => {
    renderView({
      contributions: [
        contribution({
          covered: true,
          decision: {
            revision_no: 1,
            timely_spo_qty: '0',
            reserve: [],
            borrow: [],
            buy_qty: '43',
          },
        }),
      ],
    });

    await screen.findByText('SO397450');
    expect(
      screen.queryByRole('button', { name: /as suggested$/ }),
    ).not.toBeInTheDocument();
  });

  it('shows Undo, never the save icon, once the row carries a draft', async () => {
    const row = contribution();
    renderView({
      contributions: [row],
      draft: { [row.key]: { verdict: 'approved' } },
    });

    await screen.findByText('SO397450');
    expect(
      screen.getByRole('button', { name: 'Undo SO397450 line 10' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /as suggested$/ }),
    ).not.toBeInTheDocument();
  });
});

/**
 * S3 (`PLAN-local-supplier-oi-routing.md`, AC-1.1): a `local` Buy raises no Order Inquiry on
 * confirm, marked with a `Local` pill on the Buy option row and in the Suggested / Decided
 * cell. Overseas lines carry no pill.
 */
describe('FulfilmentBoardListView: the Local pill', () => {
  it('renders Local pill in Suggested and Decided for local Buy only', async () => {
    const local = contribution({
      key: 'so-1:line-10',
      so_number: 'SO397450',
      line_no: 10,
      buy_origin: 'local',
    });
    const overseas = contribution({
      key: 'so-2:line-20',
      sales_order_id: 'so-2',
      line_id: 'core-line-20',
      so_number: 'SO500001',
      line_no: 20,
      buy_origin: 'overseas',
    });

    renderView({ contributions: [local, overseas] });

    await screen.findByText('SO397450');
    // Exactly one Local badge, on the local row's Suggested cell.
    expect(screen.getAllByText('Local')).toHaveLength(1);
  });

  it('carries the Local pill into the Decided cell once the row is decided', async () => {
    const local = contribution({ key: 'so-1:line-10', buy_origin: 'local' });
    renderView({
      contributions: [local],
      draft: { [local.key]: { verdict: 'approved' } },
    });

    await screen.findByText('SO397450');
    // Suggested AND Decided both carry the pill now (AC-1.1 says both cells).
    expect(screen.getAllByText('Local').length).toBeGreaterThanOrEqual(2);
  });

  it('shows no Local pill for an overseas line', async () => {
    const overseas = contribution({ key: 'so-1:line-10', buy_origin: 'overseas' });
    renderView({ contributions: [overseas] });

    await screen.findByText('SO397450');
    expect(screen.queryByText('Local')).not.toBeInTheDocument();
  });

  it('shows no Local pill when buy_origin is undefined (PLAN-local-buy-routing-toggle.md: the setting off, `dict.get` answers None/undefined for every Buy)', async () => {
    const noOrigin = contribution({ key: 'so-1:line-10', buy_origin: undefined });
    renderView({ contributions: [noOrigin] });

    await screen.findByText('SO397450');
    expect(screen.queryByText('Local')).not.toBeInTheDocument();
  });
});

/**
 * Owner feedback, 13 September 2026 (Slice C board display, AC-C12): the reorder-planning
 * list's own Expand all / Collapse all (`app/(protected)/scm/reorder/components/
 * PlanLinesGrid.tsx`, "Expand all"/"Collapse all" icon buttons beside its toolbar) is missing
 * here, even though this list carries the same per-row expandable decision panel. RED: no
 * such control exists on this screen today.
 */
describe('FulfilmentBoardListView: Expand all / Collapse all (owner feedback 13 Sep, AC-C12)', () => {
  function twoRows() {
    return [
      contribution({ key: 'so-1:line-10', so_number: 'SO397450', line_no: 10 }),
      contribution({
        key: 'so-2:line-20',
        sales_order_id: 'so-2',
        line_id: 'core-line-20',
        so_number: 'SO397451',
        line_no: 20,
      }),
    ];
  }

  it('carries Expand all and Collapse all controls', async () => {
    renderView({ contributions: twoRows() });
    await screen.findByText('SO397450');

    expect(screen.getByTestId('board-list-expand-all')).toBeInTheDocument();
    expect(screen.getByTestId('board-list-collapse-all')).toBeInTheDocument();
  });

  it('Expand all opens every row’s decision panel; Collapse all closes them all', async () => {
    renderView({ contributions: twoRows() });
    await screen.findByText('SO397450');

    fireEvent.click(screen.getByTestId('board-list-expand-all'));
    expect(
      await screen.findAllByRole('button', { name: 'Save decision' }),
    ).toHaveLength(2);

    fireEvent.click(screen.getByTestId('board-list-collapse-all'));
    await waitFor(() =>
      expect(
        screen.queryAllByRole('button', { name: 'Save decision' }),
      ).toHaveLength(0),
    );
  });

  /**
   * The same unsaved-edit question every other way of closing an open row already asks
   * (C5, `decisionRowExpansion.tsx`'s own `requestClose`/`AlertDialog`) - Collapse all is
   * one more way to close a row, so it goes through the same guard rather than silently
   * discarding a composition nobody asked to throw away.
   */
  it('Collapse all with one panel holding an unsaved edit asks once, via the existing confirm-discard prompt', async () => {
    renderView({ contributions: twoRows() });
    await screen.findByText('SO397450');

    fireEvent.click(screen.getByTestId('board-list-expand-all'));
    await screen.findAllByRole('button', { name: 'Save decision' });

    // An edit nobody has saved, on ONE of the two open panels - both are open after Expand
    // all, so the placeholder is no longer unique on the page.
    fireEvent.change(screen.getAllByPlaceholderText('In your own words')[0], {
      target: { value: 'The group is short' },
    });

    fireEvent.click(screen.getByTestId('board-list-collapse-all'));

    expect(await screen.findByRole('alertdialog')).toHaveTextContent(
      'Leave this decision unsaved?',
    );
    // Asked ONCE - not once per open row (Radix hides the background from the accessibility
    // tree while the modal is open, so what happens behind it is checked before and after,
    // never while it is up).
    expect(screen.getAllByRole('alertdialog')).toHaveLength(1);

    // Keep editing: the question is answered "no", so BOTH panels stay open, untouched.
    fireEvent.click(screen.getByRole('button', { name: 'Keep editing' }));
    await waitFor(() =>
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument(),
    );
    expect(
      screen.getAllByRole('button', { name: 'Save decision' }),
    ).toHaveLength(2);
    expect(screen.getAllByPlaceholderText('In your own words')[0]).toHaveValue(
      'The group is short',
    );

    // Collapse all again, and this time answer Discard.
    fireEvent.click(screen.getByTestId('board-list-collapse-all'));
    fireEvent.click(await screen.findByRole('button', { name: 'Discard' }));
    await waitFor(() =>
      expect(
        screen.queryAllByRole('button', { name: 'Save decision' }),
      ).toHaveLength(0),
    );
  });

  it('Collapse all with no dirty panel collapses silently, with no prompt', async () => {
    renderView({ contributions: twoRows() });
    await screen.findByText('SO397450');

    fireEvent.click(screen.getByTestId('board-list-expand-all'));
    await screen.findAllByRole('button', { name: 'Save decision' });

    fireEvent.click(screen.getByTestId('board-list-collapse-all'));

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.queryAllByRole('button', { name: 'Save decision' }),
      ).toHaveLength(0),
    );
  });
});

/**
 * Owner feedback, 13 September 2026 (Slice C board display, AC-C13): a row today is TWO
 * text lines tall - the Sales order cell split the SO number and "Line N" onto separate
 * `div`s - and the Suggested / Decided cells each carried a `SupplyBar` (this file's own,
 * now-deleted "agrees with the grid about the supply bar" describe block used to pin its
 * presence). Built: the SO cell is `<span>SO397450</span> <span>(Line 10)</span>` in one
 * flex row (AC-C13's own "SOxxx (Line 1)" wording, kept as two spans rather than one string
 * since the SO number alone is still what `getByText('SO397450')` and search match - the
 * file's other tests rely on the bare number staying its own text node) - so the cell's
 * whole textContent reads "SO397450 (Line 10)" even though no SINGLE node holds that exact
 * string, and "Line 10" without its parentheses is nowhere on the page at all.
 */
describe('FulfilmentBoardListView: thin rows (owner feedback 13 Sep, AC-C13)', () => {
  it('reads the Sales order cell as "<SO> (Line <n>)" on one line', async () => {
    renderView({
      contributions: [contribution({ so_number: 'SO419772', line_no: 1 })],
    });

    const soNumber = await screen.findByText('SO419772');
    expect(soNumber.parentElement?.textContent).toBe('SO419772 (Line 1)');
    // "Line 1" without its parentheses is not its own text node anywhere on the page.
    expect(screen.queryByText('Line 1')).not.toBeInTheDocument();
  });

  it('draws no progress bar in the Suggested or Decided cells', async () => {
    renderView();
    await screen.findByText('SO397450');

    expect(screen.queryByTestId('supply-bar')).not.toBeInTheDocument();
    expect(document.querySelector('[role="progressbar"]')).toBeNull();
  });
});

/**
 * R3 (captain's ruling, 13 Sep board-display round, scenario S5): a cancelled changed line
 * has a home on the list - Outstanding 0, the change icon in the Outstanding column, a
 * "Cancelled" verdict, and no quick-Save control (there is nothing left to decide FOR).
 *
 * `BoardContribution` carries no `cancelled` field yet (grepped `fulfilmentPlanning.types
 * .ts` - absent), so this fixture adds it ad hoc; `BoardDecisionPill` has no branch for it
 * either (only `unplannable` short-circuits), and `canQuickSave` (`_shared/lib/boardAmend
 * .ts`) does not exclude a cancelled contribution - both are the genuine reds below. The
 * change ICON itself is expected to already work: `changedFieldsOf` (`boardChangeAnnotations
 * .ts`) returns a single `qty` field for a `closed: true` annotation, which
 * `FulfilmentBoardListView`'s own `changeIcons` reads to place it in the 'outstanding'
 * column - kept as an assertion here as a guard, not a claim of red.
 */
describe('FulfilmentBoardListView - a cancelled changed line (R3, S5)', () => {
  const S5_LINE_ID = 'line-s5';
  const S5_ROW_ID = 'row-s5';

  function s5Annotation(): BoardChangeAnnotation {
    return {
      rowId: S5_ROW_ID,
      soNumber: 'SO400884',
      lineNo: 1,
      itemCode: 'CB4702',
      kind: 'cancelled',
      closed: true,
      was: { qty: '72', date: '2026-12-28', decision: 'Reserve 72 BRW-BB' },
      now: { qty: null, date: null, decision: null },
      suggestionLines: ['Release 72 to BRW-BB pool'],
      lateDays: null,
      shortfallQty: null,
      productChangedFrom: null,
      movedTransfer: null,
      projectLineId: S5_LINE_ID,
    };
  }

  function s5Contribution(): BoardContribution {
    return {
      ...contribution({
        key: 'so-s5:line-1',
        so_number: 'SO400884',
        line_no: 1,
        item_code: 'CB4702',
        project_line_id: S5_LINE_ID,
        qty: '0',
        qty_outstanding: '0',
        covered: false,
        unplannable: false,
        decision: null,
      }),
      // Not yet on `BoardContribution` - the field the board-side fix is expected to add
      // (the captain's ruling names it `cancelled`; rename here if the coder picks a
      // different key).
      cancelled: true,
    } as BoardContribution & { cancelled: boolean };
  }

  it('lists a cancelled changed line with Outstanding 0, a Cancelled verdict, the change icon, and no Save control', async () => {
    renderView({
      contributions: [s5Contribution()],
      annotations: new Map([[S5_LINE_ID, [s5Annotation()]]]),
    });

    const row = (await screen.findByText('SO400884')).closest('tr') as HTMLElement;
    expect(row).not.toBeNull();

    // Outstanding qty column: 0.
    expect(within(row).getByText('0')).toBeInTheDocument();

    // The change icon, in the Outstanding column (`data-column="outstanding"`), per
    // `changedFieldsOf`'s single `qty` field for a closed/cancelled annotation.
    const icon = within(row).getByTestId(`board-change-icon-${S5_ROW_ID}`);
    expect(icon).toHaveAttribute('data-column', 'outstanding');

    // Verdict column: the plain word "Cancelled" - not "Suggested", which is what
    // `BoardDecisionPill` falls through to today with no `cancelled` branch.
    const pill = within(row).getByTestId('decision-pill-so-s5:line-1');
    expect(pill.textContent).toBe('Cancelled');

    // No quick-Save control: there is nothing left on this line to decide FOR.
    expect(
      within(row).queryByRole('button', { name: /Save SO400884 line 1 as suggested/i }),
    ).not.toBeInTheDocument();
  });

  // "Counts a cancelled line in Confirm (N)" is a `confirmSummaryFor` unit test, not a list-
  // view render test - `Confirm (N)` is not this component's own header, and `BoardDecided
  // Marker` (the tick this file's other pattern would have reached for) answers a different
  // question ("is this cell/row already covered by an active decision") that a cancelled,
  // uncovered line does not touch either way. See `_shared/lib/fulfilmentBoard.test.ts`,
  // `describe('confirmSummaryFor: a cancelled changed line (R3, 13 Sep board-display round)')`.
});

/**
 * BOARD-CONFIRM-LEFT-OUT, AC-7: the Verdict header used to carry `accessorFn: () => ''`, so
 * every row sorted equal and the header offered no sort at all. It reads the same state the
 * pill renders (`verdictOf`, `BoardDecisionPill`) - never a second derivation - ranked
 * Suggested, Saved, Confirmed, Rejected in the UAC's own words.
 */
describe('FulfilmentBoardListView: the Verdict column sorts (AC-7)', () => {
  it('clicking the Verdict header sorts Suggested before Saved before Confirmed', async () => {
    const suggestedLine = contribution({
      key: 'so-1:line-1',
      so_number: 'SO000001',
      line_no: 1,
    });
    const savedLine = contribution({
      key: 'so-1:line-2',
      so_number: 'SO000002',
      line_no: 2,
    });
    const confirmedLine = contribution({
      key: 'so-1:line-3',
      so_number: 'SO000003',
      line_no: 3,
      covered: true,
    });

    // Deliberately NOT already in rank order, so the click has something to prove.
    renderView({
      contributions: [confirmedLine, suggestedLine, savedLine],
      draft: { [savedLine.key]: { verdict: 'approved' } },
    });

    await screen.findByText('SO000001');
    expect(
      screen.getAllByText(/^SO00000[1-3]$/).map((el) => el.textContent),
    ).toEqual(['SO000003', 'SO000001', 'SO000002']);

    fireEvent.click(screen.getByRole('button', { name: 'Verdict' }));

    await waitFor(() =>
      expect(
        screen.getAllByText(/^SO00000[1-3]$/).map((el) => el.textContent),
      ).toEqual(['SO000001', 'SO000002', 'SO000003']),
    );
  });
});

/**
 * BOARD-CONFIRM-LEFT-OUT, fix round 1 (AC-5): a jump that lands on whatever page happens to
 * be open is a dead link once an order runs past the 25-row first page - common on a large
 * order. `focusKey` now moves `PanelDataGrid`'s own page to wherever the row actually sits, in
 * the SAME (default, unsorted) row order the pager reads.
 */
describe('FulfilmentBoardListView: the banner reaches a line beyond page 1 (AC-5, fix round 1)', () => {
  it('jumps to the page holding focusKey when it sits beyond the first 25 rows', async () => {
    const rows = Array.from({ length: 30 }, (_, index) =>
      contribution({
        key: `so-1:line-${index + 1}`,
        so_number: `SO${String(index + 1).padStart(6, '0')}`,
        line_no: index + 1,
      }),
    );
    // The 28th row: index 27, page floor(27 / 25) = page 2 (0-based page 1).
    const target = rows[27];

    renderView({ contributions: rows, focusKey: target.key });

    expect(
      await screen.findByTestId(`line-decision-${target.key}`),
    ).toBeInTheDocument();
  });
});

/**
 * BOARD-CONFIRM-LEFT-OUT, fix round 2 (reviewer, S3): the scroll effect used to mark itself
 * done (the ref, and `onFocusHandled`) the instant the row was OPEN (`openKeys`), not the
 * instant it was actually FOUND in the DOM - open and rendered are not the same moment while a
 * search is still narrowing the list out from under it (B1) or the page has not landed yet
 * (fix round 1). Marking it done regardless left nothing to retry on once the row actually
 * showed up.
 */
describe('FulfilmentBoardListView: the focus effect waits for the row to actually render (fix round 2, S3)', () => {
  it('does not report focus handled for a row not yet in the list, then reports it once when the row appears', async () => {
    const other = contribution({
      key: 'so-1:line-1',
      so_number: 'SO000001',
      line_no: 1,
    });
    const target = contribution({
      key: 'so-1:line-2',
      so_number: 'SO000002',
      line_no: 2,
    });
    const onFocusHandled = vi.fn();
    const onDecide = vi.fn();
    const onDecideMany = vi.fn();

    const { rerender } = render(
      <FulfilmentBoardListView
        contributions={[other]}
        draft={{}}
        onDecide={onDecide}
        onDecideMany={onDecideMany}
        focusKey={target.key}
        onFocusHandled={onFocusHandled}
      />,
    );

    await screen.findByText('SO000001');
    expect(screen.queryByTestId(`line-decision-${target.key}`)).not.toBeInTheDocument();
    expect(onFocusHandled).not.toHaveBeenCalled();

    // The row appears - the same board read a moment later would hand down.
    rerender(
      <FulfilmentBoardListView
        contributions={[other, target]}
        draft={{}}
        onDecide={onDecide}
        onDecideMany={onDecideMany}
        focusKey={target.key}
        onFocusHandled={onFocusHandled}
      />,
    );

    expect(
      await screen.findByTestId(`line-decision-${target.key}`),
    ).toBeInTheDocument();
    await waitFor(() => expect(onFocusHandled).toHaveBeenCalledTimes(1));
  });
});
