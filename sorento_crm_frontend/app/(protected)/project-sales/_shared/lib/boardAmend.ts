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
 * THE LINE'S OWN LOCATION IS ALWAYS A ROW, even when the proposal reserved nothing there. That
 * is the row a planner most often wants - "there is stock at my own warehouse, reserve it
 * instead of buying" - and it is precisely the one a form built from the proposal alone would
 * not have.
 */
export function amendDraftFrom(contribution: BoardContribution): DraftLine {
  const reserveSources = contribution.sources.filter(
    (source) => source.kind === 'reserve',
  );
  const proposedReserve = numberOr(contribution.qty_proposed_reserve, () =>
    sumSources(contribution, 'reserve'),
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
  // Nothing addressable came back but the server still proposed a Reserve: put it on the
  // line's own location, which is the only warehouse this side can name for it.
  if (rows.length === 0 && proposedReserve > 0 && contribution.fulfilment_warehouse_id) {
    rows.push({
      key: `reserve-${contribution.fulfilment_location ?? contribution.fulfilment_warehouse_id}`,
      location: contribution.fulfilment_location ?? null,
      warehouse_id: contribution.fulfilment_warehouse_id,
      qty: fromMinor(proposedReserve),
      reason: '',
    });
  }
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
    // Dated supply, not a choice: it is shown and never typed, on the board exactly as on the
    // sheet, so an amendment cannot promise incoming stock that is not coming.
    timely_spo_qty: fromMinor(
      numberOr(contribution.qty_proposed_incoming, () =>
        sumSources(contribution, 'timely_spo'),
      ),
    ),
    reserve: rows,
    // The board proposes no Borrow, on either surface: it needs a donor and a reason from a
    // person (AC-B09). The editor is where that person supplies both.
    borrow: [],
    buy_qty: fromMinor(
      numberOr(contribution.qty_proposed_buy, () => sumSources(contribution, 'buy')),
    ),
    buy_reason: '',
    // The board does not state a product's lifecycle, so it never claims one here. The
    // confirmation rechecks it against the product record either way.
    is_discontinued: false,
  };
}

/**
 * The donors this row could borrow from, in the shape `BorrowAddDialog` already speaks.
 *
 * A candidate the server gave no `warehouse_id` for is NOT offered: `ConfirmBorrowComponent`
 * names the donor by id, so offering it would be offering a borrow that cannot be confirmed.
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
      donor_impact: candidate.donor_impact ?? {
        free_before: candidate.free_qty,
        free_after_full_borrow: '0',
        committed_qty: '0',
      },
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
