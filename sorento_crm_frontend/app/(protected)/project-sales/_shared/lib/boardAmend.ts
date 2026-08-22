/**
 * One board row, opened as something a person can compose (PLAN 13.4, the captain: "the amend
 * is not working, I should be able to amend the decision and quantity, like I can decide to
 * reserve, or buy, or borrow").
 *
 * The amendment used to be ONE number, the Reserve, with everything taken off it pushed into
 * Buy by the caller. Two of the four verbs were therefore unreachable from the board: a planner
 * looking at a donor holding the stock could not say "borrow it", and a line the engine met
 * entirely from Buy had no Reserve row to type into at all - the form offered a quantity for a
 * component that did not exist.
 *
 * So a board amendment is composed on the SAME `DraftLine` the per-order sheet composes on,
 * against the same `lineBalance` and `lineBlockers`. That is the whole reason this file is a
 * pair of conversions rather than a second editor: the sheet and the board have to agree about
 * what balances, or one screen refuses what the other accepted.
 */
import type {
  BoardBorrowComponent,
  BoardContribution,
  BoardDecision,
  BoardReserveComponent,
  BorrowCandidate,
} from '../types/fulfilmentPlanning.types';
import {
  fromMinor,
  toMinor,
  type DraftBorrow,
  type DraftLine,
  type DraftReserve,
} from './supplyComposition';

/**
 * The engine's proposal for one row, as the editor's opening draft.
 *
 * Seeded from the SERVER's numbers (`qty_proposed_*`) with the source strip as the fallback,
 * for the same reason `confirmLinesFor` reads them: the board proposes what the sheet proposes,
 * pool and all, so re-deriving a composition here would be a second, worse allocator.
 *
 * Ladder v2 (`PLAN-demo-followups-19aug-ladder-v2.md` section E rule 7): the line's own
 * location is NEVER a Reserve source any more, so it is no longer forced into the editor
 * as a row - every Reserve row here is a pool or a group-take sibling the proposal itself
 * named. Group borrow and cross-group borrow (rules 4/5) are now AUTO-PROPOSED too, and
 * arrive as `kind: 'borrow'` sources the same way a Reserve does.
 *
 * ON A COVERED LINE THE FROZEN DECISION WINS, because there is no proposal to seed from: the
 * board proposes nothing for a line an active decision already covers. Amending it opens on
 * what was actually decided - the borrow that was made, the quantity that was bought - so the
 * planner edits their own composition rather than one the engine would have suggested instead.
 */
export function amendDraftFrom(contribution: BoardContribution): DraftLine {
  const frozen = contribution.covered ? contribution.decision : null;
  if (frozen) return frozenDraft(contribution, frozen);
  const reserveSources = contribution.sources.filter(
    (source) => source.kind === 'reserve',
  );

  const rows: DraftReserve[] = [];
  for (const source of reserveSources) {
    // A reserve the server did not address cannot be posted, and inventing a warehouse from
    // the location code would be guessing at an id. It is left out; the balance then reads
    // short by that quantity, which is visible and fixable, rather than silently posting
    // something the confirmation must refuse.
    if (!source.warehouse_id) continue;
    rows.push({
      key: `reserve-${source.location ?? source.warehouse_id}`,
      location: source.location ?? null,
      warehouse_id: source.warehouse_id,
      qty: source.qty,
      reason: source.reason,
    });
  }
  // Nothing addressable came back but the server still proposed a Reserve. Ladder v2
  // (section E rule 7) no longer offers the line's own location - the only Reserve
  // sources left are the pool and a group-take sibling, both of which the loop above
  // already carried over by warehouse_id - so there is nowhere left to invent a row at.

  // Ladder v2's group borrow / cross-group borrow rungs (section E rules 4/5) are now
  // AUTO-PROPOSED, unlike the old ladder's Borrow: a source of kind `borrow` on the
  // proposal is something the engine already composed and named a donor for, and
  // dropping it here (as the old "the board proposes no Borrow" comment did) silently
  // lost it the instant Amend was opened.
  const borrowSources = contribution.sources.filter(
    (source) => source.kind === 'borrow' && source.warehouse_id,
  );
  const borrowRows: DraftBorrow[] = borrowSources.map((source, index) => ({
    key: `borrow-${source.location ?? source.warehouse_id}-${index}`,
    source: 'other_location',
    warehouse_code: source.location ?? '',
    warehouse_id: source.warehouse_id as string,
    donor_project_ref: null,
    donor_project_id: null,
    qty: source.qty,
    reason: source.reason,
    donor_impact: { free_before: '0', free_after_full_borrow: '0', committed_qty: '0' },
    donor_core_line_id: source.donor_core_line_id ?? null,
    donor_so_number: source.donor_so_number ?? null,
    donor_line_no: source.donor_line_no ?? null,
    donor_agent_code: source.donor_agent_code ?? null,
    same_agent: source.same_agent ?? false,
  }));

  return {
    project_line_id: contribution.project_line_id ?? '',
    line_no: contribution.line_no,
    item_code: contribution.item_code,
    open_qty: contribution.qty_outstanding ?? contribution.qty,
    // Dated supply, not a choice: it is shown and never typed, on the board exactly as on the
    // sheet, so an amendment cannot promise incoming stock that is not coming.
    timely_spo_qty: fromMinor(
      numberOr(contribution.qty_proposed_incoming, () =>
        sumSources(contribution, 'timely_spo'),
      ),
    ),
    reserve: rows,
    // The engine's own auto-proposed borrows (group / cross-group), carried into the
    // editor exactly as it composed them; a person still supplies any FURTHER borrow
    // with its own reason (AC-B09).
    borrow: borrowRows,
    buy_qty: fromMinor(
      numberOr(contribution.qty_proposed_buy, () => sumSources(contribution, 'buy')),
    ),
    buy_reason: '',
    // The item facts the ladder judged the line on, so a Buy of a discontinued product asks
    // for its reason HERE rather than being refused by the confirmation. Absent flags claim
    // nothing; the confirmation rechecks against the product record either way.
    is_discontinued: Boolean(contribution.item_flags?.discontinued),
  };
}

/**
 * The editor's draft for a line an active decision already covers: the FROZEN composition.
 *
 * The line's own location is still always a Reserve row, for the same reason it is on an
 * undecided line. The donor impact behind a frozen Borrow is whatever the board still knows -
 * the candidate list if that donor is still on it, and zeroes otherwise, exactly as the
 * per-order sheet's own `draftFromLine` does for a frozen borrow: the impact is a fact about
 * the donor NOW, and a decision taken last week does not carry it.
 */
function frozenDraft(
  contribution: BoardContribution,
  frozen: NonNullable<BoardContribution['decision']>,
): DraftLine {
  const candidates = borrowCandidatesOf(contribution);
  const rows: DraftReserve[] = frozen.reserve
    .filter((row) => Boolean(row.warehouse_id))
    .map((row) => ({
      key: `reserve-${row.location ?? row.warehouse_id}`,
      location: row.location ?? null,
      warehouse_id: row.warehouse_id,
      qty: row.qty,
      reason: '',
    }));
  const ownId = contribution.fulfilment_warehouse_id;
  const ownCode = contribution.fulfilment_location;
  const hasOwn = rows.some(
    (row) => row.warehouse_id === ownId || (Boolean(ownCode) && row.location === ownCode),
  );
  if (!hasOwn && ownId) {
    rows.unshift({
      key: `reserve-${ownCode ?? ownId}`,
      location: ownCode ?? null,
      warehouse_id: ownId,
      qty: '0',
      reason: '',
    });
  }

  return {
    project_line_id: contribution.project_line_id ?? '',
    line_no: contribution.line_no,
    item_code: contribution.item_code,
    open_qty: contribution.qty_outstanding ?? contribution.qty,
    timely_spo_qty: frozen.timely_spo_qty,
    reserve: rows,
    borrow: frozen.borrow.map((row, index) => ({
      key: `borrow-${row.warehouse_id ?? index}-${index}`,
      source: row.source,
      warehouse_code: row.location ?? '',
      warehouse_id: row.warehouse_id ?? '',
      donor_project_ref: null,
      donor_project_id: row.donor_project_id ?? null,
      qty: row.qty,
      reason: row.reason,
      donor_impact:
        candidates.find((candidate) => candidate.warehouse_id === row.warehouse_id)
          ?.donor_impact ?? {
          free_before: '0',
          free_after_full_borrow: '0',
          committed_qty: '0',
        },
      // Ladder v2 group borrow (section E.4): the frozen row already names its donor
      // line, carried through so re-approving it still checks the live commitment.
      donor_core_line_id: row.donor_core_line_id ?? null,
      donor_so_number: row.donor_so_number ?? null,
      donor_line_no: row.donor_line_no ?? null,
      donor_agent_code: row.donor_agent_code ?? null,
      same_agent: row.same_agent ?? false,
      donor_required_date: row.donor_required_date ?? null,
    })),
    buy_qty: frozen.buy_qty,
    buy_reason: frozen.buy_reason ?? '',
    is_discontinued: Boolean(contribution.item_flags?.discontinued),
  };
}

/**
 * The donors this row could borrow from, in the shape `BorrowAddDialog` already speaks.
 *
 * A candidate the server gave no `warehouse_id` for is NOT offered: `ConfirmBorrowComponent`
 * names the donor by id, so offering it would be offering a borrow that cannot be confirmed.
 *
 * The server's ORDER is kept as it came, and so is `recommended`: the ranking is the server's
 * one opinion about which donor this borrow hurts least (PLAN 13.11), and re-deriving it here
 * would be the second implementation of it.
 */
export function borrowCandidatesOf(contribution: BoardContribution): BorrowCandidate[] {
  return (contribution.borrow_candidates ?? [])
    .filter((candidate) => Boolean(candidate.warehouse_id))
    .map((candidate) => ({
      source: candidate.source,
      warehouse_code: candidate.warehouse_code,
      warehouse_id: candidate.warehouse_id as string,
      donor_project_ref: candidate.donor_project_ref ?? null,
      donor_project_id: candidate.donor_project_id ?? null,
      free_qty: candidate.free_qty,
      qty_on_hand: candidate.qty_on_hand ?? null,
      so_qty: candidate.so_qty ?? null,
      spo_qty: candidate.spo_qty ?? null,
      available_qty: candidate.available_qty ?? null,
      qty_free: candidate.qty_free ?? null,
      qty_committed: candidate.qty_committed ?? null,
      need_qty: candidate.need_qty ?? null,
      available_after_need: candidate.available_after_need ?? null,
      recommended: Boolean(candidate.recommended),
      donor_impact: candidate.donor_impact ?? {
        free_before: candidate.free_qty,
        free_after_full_borrow: '0',
        committed_qty: '0',
      },
      // Ladder v2 (section E): the group-aware donor facts - which rung this row is,
      // the donor SO line it names, whether it is ranked below this line or shares this
      // line's agent, and whether it sits outside the cross-group cap.
      rung: candidate.rung ?? null,
      donor_so_number: candidate.donor_so_number ?? null,
      donor_line_no: candidate.donor_line_no ?? null,
      donor_agent_code: candidate.donor_agent_code ?? null,
      donor_core_line_id: candidate.donor_core_line_id ?? null,
      lower_ranked: Boolean(candidate.lower_ranked),
      same_agent: Boolean(candidate.same_agent),
      over_cap: Boolean(candidate.over_cap),
      cap_reason: candidate.cap_reason ?? null,
    }));
}

/**
 * What the editor hands back to the draft: the WHOLE composition, not a summary of it.
 *
 * `reserve_qty` travels alongside because a decision taken before this editor existed carries
 * only that, and the pill falls back to it. A zero-quantity component is dropped: it decides
 * nothing, and the confirmation would drop it anyway.
 */
export function decisionFromAmendDraft(draft: DraftLine, reason: string): BoardDecision {
  const reserve: BoardReserveComponent[] = draft.reserve
    .filter((row) => toMinor(row.qty) > 0)
    .map((row) => ({
      warehouse_id: row.warehouse_id,
      location: row.location ?? null,
      qty: fromMinor(toMinor(row.qty)),
    }));
  const borrow: BoardBorrowComponent[] = draft.borrow
    .filter((row) => toMinor(row.qty) > 0)
    .map((row) => ({
      source: row.source,
      warehouse_id: row.warehouse_id,
      warehouse_code: row.warehouse_code,
      donor_project_ref: row.donor_project_ref ?? null,
      donor_project_id: row.donor_project_id ?? null,
      qty: fromMinor(toMinor(row.qty)),
      reason: row.reason.trim(),
      donor_core_line_id: row.donor_core_line_id ?? null,
      donor_so_number: row.donor_so_number ?? null,
      donor_line_no: row.donor_line_no ?? null,
      donor_agent_code: row.donor_agent_code ?? null,
      same_agent: row.same_agent ?? false,
      donor_required_date: row.donor_required_date ?? null,
    }));
  return {
    verdict: 'amended',
    reserve_qty: fromMinor(
      reserve.reduce((total, row) => total + toMinor(row.qty), 0),
    ),
    timely_spo_qty: fromMinor(toMinor(draft.timely_spo_qty)),
    reserve,
    borrow,
    buy_qty: fromMinor(toMinor(draft.buy_qty)),
    buy_reason: draft.buy_reason.trim() || undefined,
    reason: reason.trim() || undefined,
  };
}

/**
 * What an amended row reads on the board, in the words the composition was made in.
 *
 * "Amended to reserve 20" was true and no longer sufficient: the same amendment can now borrow
 * and buy, and a pill naming one of the three describes a decision the planner did not take.
 */
export function amendSummary(decision: BoardDecision): string {
  if (!decision.reserve && !decision.borrow && decision.buy_qty === undefined) {
    return `Amended to reserve ${decision.reserve_qty ?? '0'}`;
  }
  const parts: string[] = [];
  const incoming = toMinor(decision.timely_spo_qty ?? '0');
  if (incoming > 0) parts.push(`Incoming ${fromMinor(incoming)}`);
  const reserve = (decision.reserve ?? []).filter((row) => toMinor(row.qty) > 0);
  if (reserve.length > 0) {
    parts.push(
      `Reserve ${reserve
        .map((row) => `${row.qty}${row.location ? ` ${row.location}` : ''}`)
        .join(' + ')}`,
    );
  }
  const borrowed = (decision.borrow ?? []).reduce(
    (total, row) => total + toMinor(row.qty),
    0,
  );
  if (borrowed > 0) parts.push(`Borrow ${fromMinor(borrowed)}`);
  const buy = toMinor(decision.buy_qty ?? '0');
  if (buy > 0) parts.push(`Buy ${fromMinor(buy)}`);
  return parts.length > 0 ? parts.join(' · ') : 'Amended to nothing';
}

/** The server's figure when it sent one, else the fallback. Absent is not zero. */
function numberOr(value: string | null | undefined, fallback: () => number): number {
  return value === null || value === undefined ? fallback() : toMinor(value);
}

function sumSources(contribution: BoardContribution, kind: string): number {
  return contribution.sources
    .filter((source) => source.kind === kind)
    .reduce((total, source) => total + toMinor(source.qty), 0);
}
