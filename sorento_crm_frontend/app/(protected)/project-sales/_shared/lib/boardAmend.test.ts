/**
 * Amending one board row into a full composition (PLAN 13, the captain: "I should be able to
 * amend the decision and quantity, like I can decide to reserve, or buy, or borrow").
 *
 * The board's amendment used to be ONE number - the Reserve - and everything the planner took
 * off it was pushed into Buy by the caller. That is not a decision, it is half of one: a
 * planner who can see a donor holding the stock cannot say "borrow it", and a planner whose
 * line reserved nothing at its own location had no row to type into at all.
 *
 * So the editor composes the SAME four kinds the per-order sheet composes, on the same
 * `DraftLine` shape and against the same `lineBalance` / `lineBlockers`, and these are the two
 * conversions either side of it.
 */
import { describe, expect, it } from 'vitest';
import {
  amendDraftFrom,
  amendSummary,
  borrowCandidatesOf,
  decisionFromAmendDraft,
  suggestionDraftFrom,
} from './boardAmend';
import { buildBoard, type BoardDemandLine } from './__testsupport__/boardFixture';
import type { BoardContribution } from '../types/fulfilmentPlanning.types';

const TODAY = '2026-08-18';

function line(overrides: Partial<BoardDemandLine> = {}): BoardDemandLine {
  return {
    sales_order_id: 'so-1',
    so_number: 'SO000001',
    line_no: 1,
    item_code: 'WESERP10B',
    qty: '100',
    required_date: '2026-09-04',
    fulfilment_location: 'BRW-BB',
    ...overrides,
  };
}

function contributionOf(
  freeStock: Record<string, string> = {},
  overrides: Partial<BoardDemandLine> = {},
): BoardContribution {
  return buildBoard([line(overrides)], { today: TODAY, freeStock }).cells[0]
    .contributions[0];
}

describe('amendDraftFrom: the proposal, as something a person can edit', () => {
  it('opens on the engine’s own numbers rather than on an empty form', () => {
    const draft = amendDraftFrom(contributionOf({ 'WESERP10B|BRW-BB': '40' }));

    expect(draft.open_qty).toBe('100');
    expect(draft.timely_spo_qty).toBe('0');
    expect(draft.reserve).toEqual([
      {
        key: 'reserve-BRW-BB',
        location: 'BRW-BB',
        warehouse_id: 'wh-BRW-BB',
        qty: '40',
        reason: 'Free unclaimed stock at BRW-BB covers this much by the delivery date.',
      },
    ]);
    expect(draft.borrow).toEqual([]);
    expect(draft.buy_qty).toBe('60');
  });

  it('opens with the line’s own location at zero when the proposal reserved nothing', () => {
    // Ladder v3 (`PLAN-scm-cs-planning-uat.md` section 1b rung 2): the own location is a
    // location of the line's ownership group again, so it is always somewhere the planner
    // may reserve from - and on a wholly-bought line it is the only row there would be.
    const draft = amendDraftFrom(contributionOf({}));

    expect(draft.reserve).toEqual([
      {
        key: 'reserve-BRW-BB',
        location: 'BRW-BB',
        warehouse_id: 'wh-BRW-BB',
        qty: '0',
        reason: '',
      },
    ]);
    expect(draft.buy_qty).toBe('100');
  });

  it('keeps every warehouse the proposal drew on, each with its own id', () => {
    // Own location plus the dealer pool: the pill reads one code, the payload needs two ids.
    const base = contributionOf({});
    const draft = amendDraftFrom({
      ...base,
      qty_proposed_reserve: '70',
      qty_proposed_buy: '30',
      sources: [
        {
          kind: 'reserve',
          qty: '40',
          location: 'BRW-BB',
          warehouse_id: 'wh-own',
          reason: 'Free stock at BRW-BB covers this much.',
        },
        {
          kind: 'reserve',
          qty: '30',
          location: 'BRW',
          warehouse_id: 'wh-pool',
          reason: 'The dealer pool covers the rest.',
        },
        { kind: 'buy', qty: '30', location: null, reason: 'The residual is bought.' },
      ],
    });

    expect(draft.reserve.map((row) => [row.warehouse_id, row.qty])).toEqual([
      ['wh-own', '40'],
      ['wh-pool', '30'],
    ]);
  });

  it('states no reserve row at all for a line whose sales order names no warehouse', () => {
    const draft = amendDraftFrom(contributionOf({}, { fulfilment_location: null }));
    expect(draft.reserve).toEqual([]);
  });

  it('carries the server’s incoming cover through unedited', () => {
    const base = contributionOf({});
    const draft = amendDraftFrom({
      ...base,
      qty_proposed_incoming: '15',
      qty_proposed_reserve: '0',
      qty_proposed_buy: '85',
    });
    expect(draft.timely_spo_qty).toBe('15');
  });

  it('seeds the discontinued flag from the item facts the board stated', () => {
    const base = contributionOf({});
    const draft = amendDraftFrom({
      ...base,
      item_flags: {
        dealer_hot_selling: false,
        dealer_hot_selling_where: [],
        project_hot_selling: false,
        project_hot_selling_where: [],
        dealer_classified: false,
        project_classified: false,
        discontinued: true,
        retail_classification_available: true,
      },
    });
    expect(draft.is_discontinued).toBe(true);
    expect(draft.buy_reason).toBe('');
  });

  it('claims nothing about the lifecycle when the board stated no item facts', () => {
    const base = contributionOf({});
    expect(amendDraftFrom({ ...base, item_flags: null }).is_discontinued).toBe(false);
  });
});

describe('amendDraftFrom on a covered line', () => {
  const frozen = {
    revision_no: 2,
    timely_spo_qty: '0',
    reserve: [],
    borrow: [],
    buy_qty: '100',
    buy_reason: 'Last batch for the site, agreed with purchasing.',
  };

  it('seeds the discontinued flag and the buy reason the revision froze', () => {
    const base = contributionOf({}, { decision: frozen });
    const draft = amendDraftFrom({
      ...base,
      item_flags: {
        dealer_hot_selling: false,
        dealer_hot_selling_where: [],
        project_hot_selling: false,
        project_hot_selling_where: [],
        dealer_classified: false,
        project_classified: false,
        discontinued: true,
        retail_classification_available: true,
      },
    });
    expect(draft.is_discontinued).toBe(true);
    expect(draft.buy_reason).toBe('Last batch for the site, agreed with purchasing.');
  });

  it('opens with an empty buy reason when the revision carries none', () => {
    const base = contributionOf({}, { decision: { ...frozen, buy_reason: undefined } });
    expect(amendDraftFrom(base).buy_reason).toBe('');
  });

  it('keeps a group-borrow donor’s fields through Amend and back onto the posted payload (review finding B2)', () => {
    // Dropping these on the round trip re-posts a covered group-borrow line as a plain
    // free-stock donor, which the own-location check (rule 7) then refuses.
    const groupBorrowFrozen = {
      revision_no: 3,
      timely_spo_qty: '0',
      reserve: [],
      borrow: [
        {
          source: 'other_location' as const,
          warehouse_id: 'wh-MWH-BB',
          location: 'MWH-BB',
          donor_project_id: null,
          qty: '90',
          reason: 'Group borrow, auto-proposed.',
          rung: 'group_borrow',
          donor_so_number: 'SO371334',
          donor_line_no: 2,
          donor_agent_code: 'JEREMY',
          same_agent: true,
          donor_core_line_id: 'core-line-1',
          donor_required_date: '2026-09-10',
          order_back_qty: '90',
        },
      ],
      buy_qty: '0',
    };
    const base = contributionOf({}, { decision: groupBorrowFrozen });
    const draft = amendDraftFrom(base);

    expect(draft.borrow).toEqual([
      expect.objectContaining({
        warehouse_id: 'wh-MWH-BB',
        warehouse_code: 'MWH-BB',
        qty: '90',
        donor_core_line_id: 'core-line-1',
        donor_so_number: 'SO371334',
        donor_line_no: 2,
        donor_agent_code: 'JEREMY',
        same_agent: true,
        donor_required_date: '2026-09-10',
      }),
    ]);

    // Re-approved as-is (or re-posted untouched by Amend), the composition still names
    // the SAME donor line - never a re-derived free-stock borrow at the same location.
    const posted = decisionFromAmendDraft(draft, '');
    expect(posted.borrow?.[0]).toEqual(
      expect.objectContaining({
        warehouse_id: 'wh-MWH-BB',
        donor_core_line_id: 'core-line-1',
        donor_so_number: 'SO371334',
        donor_line_no: 2,
        donor_agent_code: 'JEREMY',
        same_agent: true,
        donor_required_date: '2026-09-10',
      }),
    );
  });
});

/**
 * THE ENGINE'S SUGGESTION, on a line an active decision already covers (C9 / C11).
 *
 * The fixture is the plan's own canonical example: SO404352 line 22, SRTWB7518, confirmed at
 * Reserve 8 from BRW-AM plus 16 from the BRW pool while the engine suggests 9 plus 15. Amend
 * opens on the 8 and the 16 - the planner edits their OWN composition - and Approve suggestion
 * has to put the 9 and the 15 back, which is the whole reason this seeder exists beside
 * `amendDraftFrom`.
 */
describe('suggestionDraftFrom on a covered line', () => {
  const frozen = {
    revision_no: 4,
    confirmed_at: '2026-08-18T02:00:00',
    timely_spo_qty: '0',
    reserve: [
      { warehouse_id: 'wh-BRW-AM', location: 'BRW-AM', qty: '8' },
      { warehouse_id: 'wh-BRW', location: 'BRW', qty: '16' },
    ],
    borrow: [],
    buy_qty: '0',
  };
  const suggestion = [
    {
      kind: 'reserve' as const,
      qty: '9',
      location: 'BRW-AM',
      warehouse_id: 'wh-BRW-AM',
      reason: 'Free unclaimed stock at BRW-AM covers this much by the delivery date.',
    },
    {
      kind: 'reserve' as const,
      qty: '15',
      location: 'BRW',
      warehouse_id: 'wh-BRW',
      reason: 'The shared pool at BRW covers this much within its cap.',
    },
  ];

  /** The covered contribution as the board sends one, with the suggestion beside it. */
  function coveredContribution(overrides: Partial<BoardContribution> = {}): BoardContribution {
    const base = contributionOf(
      {},
      { qty: '24', fulfilment_location: 'BRW-AM', decision: frozen },
    );
    return { ...base, sources: suggestion, ...overrides };
  }

  it('opens on the engine’s numbers, not on the composition the revision froze', () => {
    const draft = suggestionDraftFrom(coveredContribution());

    expect(draft.reserve.map((row) => [row.warehouse_id, row.qty])).toEqual([
      ['wh-BRW-AM', '9'],
      ['wh-BRW', '15'],
    ]);
    expect(draft.buy_qty).toBe('0');
  });

  it('takes the proposal FROZEN beside the decision when the revision recorded one', () => {
    // `sources` states the decision on a covered line (the server's `_apply_frozen`); the
    // suggestion of the day it was confirmed is in `proposed`, and that is the one the
    // Suggestion card shows, so the reset has to agree with it.
    const draft = suggestionDraftFrom(
      coveredContribution({
        sources: [
          {
            kind: 'reserve',
            qty: '8',
            location: 'BRW-AM',
            warehouse_id: 'wh-BRW-AM',
            reason: 'Reserved at BRW-AM in revision 4.',
          },
          {
            kind: 'reserve',
            qty: '16',
            location: 'BRW',
            warehouse_id: 'wh-BRW',
            reason: 'Reserved at BRW in revision 4.',
          },
        ],
        proposed: { components: suggestion },
      }),
    );

    expect(draft.reserve.map((row) => [row.warehouse_id, row.qty])).toEqual([
      ['wh-BRW-AM', '9'],
      ['wh-BRW', '15'],
    ]);
  });

  it('leaves Amend itself on the frozen composition', () => {
    // Two different questions: Amend edits what was decided, Approve suggestion asks for the
    // engine's. Seeding both from the same place is the defect, not the fix.
    const draft = amendDraftFrom(coveredContribution());

    expect(draft.reserve.map((row) => [row.warehouse_id, row.qty])).toEqual([
      ['wh-BRW-AM', '8'],
      ['wh-BRW', '16'],
    ]);
  });

  it('shows the frozen composition when the revision recorded no proposal at all', () => {
    // Written before the proposal was frozen: `sources` is the decision and there is nothing
    // else the board holds for the line, so the reset states that rather than an empty form.
    const base = contributionOf(
      {},
      { qty: '24', fulfilment_location: 'BRW-AM', decision: frozen },
    );
    const draft = suggestionDraftFrom(base);

    expect(draft.reserve.map((row) => [row.warehouse_id, row.qty])).toEqual([
      ['wh-BRW-AM', '8'],
      ['wh-BRW', '16'],
    ]);
  });

  it('is the same draft as Amend on an UNCOVERED line', () => {
    const uncovered = contributionOf({ 'WESERP10B|BRW-BB': '40' });
    expect(suggestionDraftFrom(uncovered)).toEqual(amendDraftFrom(uncovered));
  });
});

describe('borrowCandidatesOf: only a donor the confirmation can name', () => {
  it('fills the sheet’s candidate shape from the board’s', () => {
    const base = contributionOf({});
    const candidates = borrowCandidatesOf({
      ...base,
      borrow_candidates: [
        {
          source: 'other_location',
          warehouse_code: 'BRW-IB',
          warehouse_id: 'wh-ib',
          free_qty: '25',
          qty_on_hand: '30',
          so_qty: '10',
          spo_qty: '5',
          available_qty: '25',
          qty_free: '25',
          qty_committed: '0',
          need_qty: '10',
          available_after_need: '15',
          recommended: true,
          donor_impact: {
            free_before: '25',
            free_after_full_borrow: '0',
            committed_qty: '0',
          },
        },
      ],
    });

    // The donor's own position travels whole, including where the server ranked it: the
    // dialog tabulates it, and a field dropped here is a field the screen cannot show.
    expect(candidates).toEqual([
      {
        source: 'other_location',
        warehouse_code: 'BRW-IB',
        warehouse_id: 'wh-ib',
        donor_project_ref: null,
        donor_project_id: null,
        free_qty: '25',
        qty_on_hand: '30',
        so_qty: '10',
        spo_qty: '5',
        available_qty: '25',
        qty_free: '25',
        qty_committed: '0',
        need_qty: '10',
        available_after_need: '15',
        recommended: true,
        donor_impact: {
          free_before: '25',
          free_after_full_borrow: '0',
          committed_qty: '0',
        },
        // Ladder v2 (section E): this donor came off the pre-v2 shape, so none of the
        // group-aware facts are stated.
        rung: null,
        donor_so_number: null,
        donor_line_no: null,
        donor_agent_code: null,
        donor_core_line_id: null,
        lower_ranked: false,
        same_agent: false,
        over_cap: false,
        cap_reason: null,
      },
    ]);
  });

  it('states a donor position the server left out as absent, never as zero', () => {
    const base = contributionOf({});

    expect(
      borrowCandidatesOf({
        ...base,
        borrow_candidates: [
          {
            source: 'other_location',
            warehouse_code: 'BRW-IB',
            warehouse_id: 'wh-ib',
            free_qty: '25',
          },
        ],
      })[0],
    ).toMatchObject({
      qty_on_hand: null,
      so_qty: null,
      spo_qty: null,
      available_qty: null,
      qty_free: null,
      qty_committed: null,
      need_qty: null,
      available_after_need: null,
      recommended: false,
    });
  });

  it('leaves out a donor the server gave no warehouse id for, rather than inventing one', () => {
    const base = contributionOf({});
    expect(
      borrowCandidatesOf({
        ...base,
        borrow_candidates: [
          { source: 'other_location', warehouse_code: 'BRW-IB', free_qty: '25' },
        ],
      }),
    ).toEqual([]);
  });
});

describe('decisionFromAmendDraft: what the draft carries away', () => {
  it('carries the whole composition, not only the Reserve', () => {
    const contribution = contributionOf({ 'WESERP10B|BRW-BB': '40' });
    const draft = amendDraftFrom(contribution);

    const decision = decisionFromAmendDraft(
      {
        ...draft,
        reserve: [{ ...draft.reserve[0], qty: '20' }],
        borrow: [
          {
            key: 'borrow-1',
            source: 'other_location',
            warehouse_code: 'BRW-IB',
            warehouse_id: 'wh-ib',
            donor_project_ref: null,
            donor_project_id: null,
            qty: '10',
            reason: 'The site next door can wait a week.',
            donor_impact: {
              free_before: '25',
              free_after_full_borrow: '15',
              committed_qty: '0',
            },
          },
        ],
        buy_qty: '70',
      },
      'Holding the rest for the late site.',
    );

    expect(decision).toEqual({
      verdict: 'amended',
      reserve_qty: '20',
      timely_spo_qty: '0',
      reserve: [{ warehouse_id: 'wh-BRW-BB', location: 'BRW-BB', qty: '20' }],
      borrow: [
        {
          source: 'other_location',
          warehouse_id: 'wh-ib',
          warehouse_code: 'BRW-IB',
          donor_project_ref: null,
          donor_project_id: null,
          qty: '10',
          reason: 'The site next door can wait a week.',
          donor_core_line_id: null,
          donor_so_number: null,
          donor_line_no: null,
          donor_agent_code: null,
          same_agent: false,
          donor_required_date: null,
        },
      ],
      buy_qty: '70',
      reason: 'Holding the rest for the late site.',
    });
  });

  it('drops a component nobody put a quantity on: a zero decides nothing', () => {
    const draft = amendDraftFrom(contributionOf({}));
    const decision = decisionFromAmendDraft({ ...draft, buy_qty: '100' }, '');

    expect(decision.reserve).toEqual([]);
    expect(decision.borrow).toEqual([]);
    expect(decision.reason).toBeUndefined();
  });

  it('carries the buy reason, trimmed, and leaves it off when nobody gave one', () => {
    const draft = amendDraftFrom(contributionOf({}));
    expect(
      decisionFromAmendDraft({ ...draft, buy_reason: '  Last batch for the site.  ' }, '')
        .buy_reason,
    ).toBe('Last batch for the site.');
    expect(decisionFromAmendDraft({ ...draft, buy_reason: '   ' }, '').buy_reason).toBeUndefined();
  });
});

describe('amendSummary: what the decided row reads', () => {
  /**
   * SECTION 2'S WORDS, the same table the bar under this pill is painted from: a reserve at
   * the line's own group location is "Own", the shared pool is "Shared", and a borrow says
   * which kind of borrow it is. It used to read "Reserve 20 BRW-BB · Borrow 10 · Buy 13"
   * beside an emerald "Own" segment describing the identical quantity.
   */
  it('states the composition in the vocabulary the bar beside it is drawn from', () => {
    expect(
      amendSummary(
        {
          verdict: 'amended',
          reserve: [{ warehouse_id: 'wh-own', location: 'BRW-BB', qty: '20' }],
          borrow: [
            {
              source: 'other_location',
              warehouse_id: 'wh-ib',
              warehouse_code: 'BRW-IB',
              qty: '10',
              reason: 'Agreed with the other site.',
            },
          ],
          buy_qty: '13',
          timely_spo_qty: '0',
        },
        'BRW-BB',
      ),
    ).toBe('Own 20 BRW-BB · Borrow (other) 10 BRW-IB · Buy 13');
  });

  it('splits a reserve that draws on two different kinds of stock', () => {
    // The pool and the agent's own group are two different answers, and the bar already
    // draws them as two segments. One "Reserve" word over both said neither.
    expect(
      amendSummary(
        {
          verdict: 'amended',
          reserve: [
            { warehouse_id: 'wh-pool', location: 'BRW', qty: '71' },
            { warehouse_id: 'wh-dc1', location: 'DC1-BB', qty: '454' },
          ],
          buy_qty: '0',
          timely_spo_qty: '0',
        },
        'BRW-BB',
      ),
    ).toBe('Own 454 DC1-BB · BRW 71 BRW');
  });

  it('names a borrow that states its donor order as a borrow from another order', () => {
    expect(
      amendSummary(
        {
          verdict: 'amended',
          reserve: [],
          borrow: [
            {
              source: 'other_location',
              warehouse_id: 'wh-own',
              warehouse_code: 'BRW-BB',
              qty: '71',
              reason: 'Authorised by the agent.',
              donor_so_number: 'SO415472',
            },
          ],
          buy_qty: '0',
          timely_spo_qty: '0',
        },
        'BRW-BB',
      ),
    ).toBe('Borrow (order) 71 BRW-BB');
  });

  it('falls back to the one number a decision taken before the editor carries', () => {
    expect(amendSummary({ verdict: 'amended', reserve_qty: '12' })).toBe(
      'Amended to reserve 12',
    );
  });
});
