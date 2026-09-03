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
  BoardSource,
  BorrowCandidate,
  ConfirmBorrowComponent,
  ConfirmLine,
} from '../types/fulfilmentPlanning.types';
import {
  fromMinor,
  toMinor,
  type DraftBorrow,
  type DraftLine,
  type DraftReserve,
} from './supplyComposition';
import { ORDER, SHORT_LABELS, rowOf, type SupplyKind } from './supplyVocabulary';

/**
 * Every field a Borrow carries THROUGH a mapper without ever being edited: who it is
 * borrowed from, and (ladder v7.1 step 3, S4) which incoming document it comes off.
 *
 * ONE spread, used by every mapper in the chain, because the chain is four hops long -
 * proposal or frozen decision -> `DraftBorrow` -> `BoardDecision` -> `ConfirmLine` - and a
 * field re-listed at each hop is a field that will one day be listed at three of them. That
 * is exactly what happened: `supply_key` was added to the two seeders and left out of Save
 * and Confirm, so a step-3 borrow reached the server as a free-stock borrow at whatever bin
 * the document is bound for, the placement link came down, and the confirmation re-checked
 * the quantity against on-hand capacity at a bin holding a container that has not landed.
 *
 * Normalised to `null` rather than left `undefined`: the server's schema takes null and the
 * two mean the same thing here, so one of them is enough.
 */
export interface BorrowPassThrough {
  donor_core_line_id: string | null;
  donor_so_number: string | null;
  donor_line_no: number | null;
  donor_agent_code: string | null;
  same_agent: boolean;
  donor_required_date: string | null;
  supply_key: string | null;
  supply_document: string | null;
  arrival_date: string | null;
}

type BorrowFields = { [K in keyof BorrowPassThrough]?: BorrowPassThrough[K] };

export function borrowPassThrough(row: BorrowFields): BorrowPassThrough {
  return {
    donor_core_line_id: row.donor_core_line_id ?? null,
    donor_so_number: row.donor_so_number ?? null,
    donor_line_no: row.donor_line_no ?? null,
    donor_agent_code: row.donor_agent_code ?? null,
    same_agent: row.same_agent ?? false,
    donor_required_date: row.donor_required_date ?? null,
    supply_key: row.supply_key ?? null,
    supply_document: row.supply_document ?? null,
    arrival_date: row.arrival_date ?? null,
  };
}

/**
 * The engine's proposal for one row, as the editor's opening draft.
 *
 * Seeded from the SERVER's numbers (`qty_proposed_*`) with the source strip as the fallback,
 * for the same reason `confirmLinesFor` reads them: the board proposes what the sheet proposes,
 * pool and all, so re-deriving a composition here would be a second, worse allocator.
 *
 * Ladder v3 (`PLAN-scm-cs-planning-uat.md` section 1b rung 2) gives the own location back:
 * it is a location of the line's ownership group, so it is forced into the editor as a row
 * even when the proposal drew nothing there. That row is the amendment a planner most often
 * wants to make - the Buy switch is turned off and the stock they can see is typed in - and
 * without it a wholly-bought line offers nowhere at all to compose an alternative.
 *
 * ON A COVERED LINE THE FROZEN DECISION WINS, because there is no proposal to seed from: the
 * board proposes nothing for a line an active decision already covers. Amending it opens on
 * what was actually decided - the borrow that was made, the quantity that was bought - so the
 * planner edits their own composition rather than one the engine would have suggested instead.
 */
export function amendDraftFrom(contribution: BoardContribution): DraftLine {
  const frozen = contribution.covered ? contribution.decision : null;
  if (frozen) return frozenDraft(contribution, frozen);
  return draftFromSources(contribution, contribution.sources, true);
}

/**
 * THE ENGINE'S SUGGESTION as the editor's draft, whatever the line's own decision says.
 *
 * `amendDraftFrom` opens a covered line on what was DECIDED, which is right for Amend and
 * wrong for an approval: the planner has just asked for the engine's composition back, and on
 * SO404352 line 22 they got the frozen 8 / 16 they were pressing Save to leave.
 *
 * The suggestion is `contributionSuggestion`'s own rule (`supplyVocabulary`) - the proposal
 * FROZEN beside the decision when the revision recorded one, the live ladder otherwise - so
 * the inputs reset to exactly the composition the Suggestion card states.
 *
 * A revision written before the proposal was frozen records none, and `sources` states the
 * decision itself on a covered line: the frozen composition is then all the board holds for
 * that line, so it is what the reset shows rather than an empty form.
 */
export function suggestionDraftFrom(contribution: BoardContribution): DraftLine {
  // On an UNCOVERED line the proposal IS the draft, so there is one seeder, not two.
  if (!contribution.covered) return amendDraftFrom(contribution);
  // `qty_proposed_*` states the ACTIVE DECISION on a covered line (the server's
  // `_apply_frozen`), so the totals come off the suggestion's own components instead.
  return draftFromSources(
    contribution,
    contribution.proposed?.components ?? contribution.sources,
    false,
  );
}

/**
 * One composition, read off supply components: the shared body of the two seeders above.
 *
 * `proposedTotals` says whether the server's `qty_proposed_*` may be trusted for the incoming
 * and Buy figures. It may on a line the engine planned - those are its own totals, and they
 * are the reason the board proposes what the sheet proposes - and it may NOT on a covered
 * line, where the same three fields state what was decided rather than what was suggested.
 */
function draftFromSources(
  contribution: BoardContribution,
  sources: BoardSource[],
  proposedTotals: boolean,
): DraftLine {
  const reserveSources = sources.filter((source) => source.kind === 'reserve');

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
  seedOwnLocation(rows, contribution);

  // A `borrow` source on the proposal is the CROSS-GROUP rung (ladder v3 rung 4), the one
  // borrow the engine still composes on its own: free stock outside the ownership group,
  // within the cap. Group borrow left the engine entirely (AC-L3) and reaches this editor
  // only when a person picks a donor. Either way, a borrow the proposal DID name has to be
  // carried in - dropping it here would lose it the instant Amend was opened.
  const borrowSources = sources.filter(
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
    // The donor and the document, carried whole (`borrowPassThrough`): dropped here they
    // were lost from the posted borrow the moment the composition went through this editor.
    ...borrowPassThrough(source),
  }));

  return {
    project_line_id: contribution.project_line_id ?? '',
    line_no: contribution.line_no,
    item_code: contribution.item_code,
    open_qty: contribution.qty_outstanding ?? contribution.qty,
    // Dated supply, not a choice: it is shown and never typed, on the board exactly as on the
    // sheet, so an amendment cannot promise incoming stock that is not coming.
    timely_spo_qty: fromMinor(
      proposedTotals
        ? numberOr(contribution.qty_proposed_incoming, () =>
            sumSources(sources, 'timely_spo'),
          )
        : sumSources(sources, 'timely_spo'),
    ),
    reserve: rows,
    // The engine's own auto-proposed borrows (group / cross-group), carried into the
    // editor exactly as it composed them; a person still supplies any FURTHER borrow
    // with its own reason (AC-B09).
    borrow: borrowRows,
    buy_qty: fromMinor(
      proposedTotals
        ? numberOr(contribution.qty_proposed_buy, () => sumSources(sources, 'buy'))
        : sumSources(sources, 'buy'),
    ),
    buy_reason: '',
    // The item facts the ladder judged the line on, so a Buy of a discontinued product asks
    // for its reason HERE rather than being refused by the confirmation. Absent flags claim
    // nothing; the confirmation rechecks against the product record either way.
    is_discontinued: Boolean(contribution.item_flags?.discontinued),
    // An engine proposal is never an order back: the ladder proposes a purchase, and only
    // a person can say the quantity is owed against something already on its way.
    order_back: false,
    cited_document: '',
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
  seedOwnLocation(rows, contribution);

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
      // The frozen row already names its donor line and its document; carried through so
      // re-approving it still checks the live commitment and moves the same placement.
      ...borrowPassThrough(row),
    })),
    buy_qty: frozen.buy_qty,
    buy_reason: frozen.buy_reason ?? '',
    is_discontinued: Boolean(contribution.item_flags?.discontinued),
    order_back: Boolean(frozen?.order_back),
    cited_document: frozen?.cited_document ?? '',
  };
}

/**
 * The line's OWN location as a Reserve row, first, when nothing already names it.
 *
 * Ladder v3 rung 2: the own location is a location of the ownership group again, so it is
 * always somewhere the planner may reserve from. At zero, because the proposal did not draw
 * on it - what it CAN give is the server's answer at confirm, not a figure to guess here.
 */
function seedOwnLocation(rows: DraftReserve[], contribution: BoardContribution): void {
  const ownId = contribution.fulfilment_warehouse_id;
  if (!ownId) return;
  const ownCode = contribution.fulfilment_location;
  const named = rows.some(
    (row) => row.warehouse_id === ownId || (Boolean(ownCode) && row.location === ownCode),
  );
  if (named) return;
  rows.unshift({
    key: `reserve-${ownCode ?? ownId}`,
    location: ownCode ?? null,
    warehouse_id: ownId,
    qty: '0',
    reason: '',
  });
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
      // Section 1b/1c: the group-aware donor facts - which rung this row is, the donor
      // SO line it names, and whether it is ranked below this line or shares this line's
      // agent. No cap verdict since v7.1 (R5): any ownership group may donate.
      rung: candidate.rung ?? null,
      donor_so_number: candidate.donor_so_number ?? null,
      donor_line_no: candidate.donor_line_no ?? null,
      donor_agent_code: candidate.donor_agent_code ?? null,
      donor_core_line_id: candidate.donor_core_line_id ?? null,
      lower_ranked: Boolean(candidate.lower_ranked),
      same_agent: Boolean(candidate.same_agent),
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
      ...borrowPassThrough(row),
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
    // Only carried when the Buy is one: an order back with nothing bought is not an
    // instruction, and a cited document with no order back names nothing.
    order_back: toMinor(draft.buy_qty) > 0 && draft.order_back ? true : undefined,
    cited_document:
      toMinor(draft.buy_qty) > 0 && draft.order_back
        ? draft.cited_document.trim() || undefined
        : undefined,
  };
}

/**
 * The engine's own suggestion, posted exactly as `BoardLineDecisionPanel`'s Save button posts
 * an untouched line (D14, the captain: a quick save from the list or the grid has to be
 * byte-identical to opening the line and pressing Save with nothing changed).
 *
 * `verdict: 'approved'` and reason `''`, because nothing was amended - `decisionFromAmendDraft`
 * on its own always writes `'amended'`, which is right for that function's other callers but
 * wrong for an approval, so this wraps it the same way the panel's `save()` does.
 */
export function suggestedDecisionFor(contribution: BoardContribution): BoardDecision {
  return {
    ...decisionFromAmendDraft(suggestionDraftFrom(contribution), ''),
    verdict: 'approved',
  };
}

/**
 * A composed decision as the LINE ONE CONFIRMATION POSTS, component for component.
 *
 * One mapping for the two verdicts that post a composition rather than a derivation: an
 * amendment as the planner typed it, and an approval of the engine's suggestion on a line an
 * active decision already covers (C9 / C11). The approval used to be derived from
 * `qty_proposed_*` and the source strip, and BOTH state the decision on a covered line, so
 * an approval re-posted the very numbers Save was pressed to leave.
 *
 * A zero-quantity component is dropped: it decides nothing, and the confirmation would drop
 * it anyway. `amend_reason` is whatever the decision carries - an approval carries none,
 * because it is not an override.
 */
export function confirmLineFrom(
  projectLineId: string,
  decision: BoardDecision,
): ConfirmLine {
  const borrow: ConfirmBorrowComponent[] = (decision.borrow ?? [])
    .filter((row) => toMinor(row.qty) > 0)
    .map((row) => ({
      source: row.source,
      warehouse_id: row.warehouse_id,
      donor_project_id: row.donor_project_id ?? null,
      qty: row.qty,
      reason: row.reason,
      // Round-tripped so the confirmation checks this row against what it is actually
      // taking from - the donor line's live commitment, or the document's own open
      // balance - and never against free stock at a bin.
      ...borrowPassThrough(row),
    }));
  return {
    project_line_id: projectLineId,
    timely_spo_qty: fromMinor(toMinor(decision.timely_spo_qty ?? '0')),
    reserve: (decision.reserve ?? [])
      .filter((row) => toMinor(row.qty) > 0)
      .map((row) => ({ warehouse_id: row.warehouse_id, qty: row.qty })),
    borrow,
    buy_qty: fromMinor(toMinor(decision.buy_qty ?? '0')),
    buy_reason: decision.buy_reason?.trim() || undefined,
    // Frozen with the line. Every other component carries the sentence of the RULE that
    // produced it, and those explain a decision nobody took once a person overrode them.
    amend_reason: decision.reason,
    // The doubt beside the verdict (R10). Sent on every verdict, not only an amendment:
    // "I did what it said and I think the numbers are wrong" is the case worth chasing.
    suspected_system_issue: decision.suspected_system_issue ?? false,
  };
}

/**
 * What an amended row reads on the board, IN SECTION 2'S WORDS.
 *
 * "Amended to reserve 20" was true and no longer sufficient: the same amendment can now borrow
 * and buy, and a pill naming one of the three describes a decision the planner did not take.
 *
 * The words come from `SHORT_LABELS` (`supplyVocabulary`), the same table the bar under this
 * pill, the legend and the popover's cards read - PLAN section 2 is ONE vocabulary, and this
 * sentence used to speak a second one ("Reserve 454 DC1-BB" beside an emerald "Own" segment
 * describing the identical quantity). A reserve is split per kind rather than lumped: the
 * agent's own group and the shared pool are two different answers and the bar already draws
 * them as two segments.
 *
 * `ownLocation` is the line's own warehouse code, which is what tells own-group stock from the
 * pool for a component carrying no rung. Without it a reserve is read the widest way `rowOf`
 * allows, never as the agent's own.
 */
export function amendSummary(decision: BoardDecision, ownLocation?: string | null): string {
  if (!decision.reserve && !decision.borrow && decision.buy_qty === undefined) {
    return `Amended to reserve ${decision.reserve_qty ?? '0'}`;
  }
  // Per kind, in the vocabulary's own reading order, so two rows are comparable.
  const places = new Map<SupplyKind, string[]>();
  const push = (kind: SupplyKind | null, text: string) => {
    if (!kind) return;
    const existing = places.get(kind);
    if (existing) existing.push(text);
    else places.set(kind, [text]);
  };

  for (const row of (decision.reserve ?? []).filter((entry) => toMinor(entry.qty) > 0)) {
    push(
      rowOf({ kind: 'reserve', qty: row.qty, location: row.location }, ownLocation),
      `${row.qty}${row.location ? ` ${row.location}` : ''}`,
    );
  }
  for (const row of (decision.borrow ?? []).filter((entry) => toMinor(entry.qty) > 0)) {
    push(
      rowOf(
        {
          kind: 'borrow',
          // No rung on this shape by design: an amendment's borrow is a person's pick, not a
          // rung the engine fired. The donor sales order is what tells the two borrows apart.
          qty: row.qty,
          location: row.warehouse_code ?? null,
          donor_so_number: row.donor_so_number,
        },
        ownLocation,
      ),
      `${row.qty}${row.warehouse_code ? ` ${row.warehouse_code}` : ''}`,
    );
  }
  const incoming = toMinor(decision.timely_spo_qty ?? '0');
  if (incoming > 0) push('incoming', fromMinor(incoming));
  const buy = toMinor(decision.buy_qty ?? '0');
  if (buy > 0) push('buy', fromMinor(buy));

  const parts = ORDER.filter((kind) => places.has(kind)).map(
    (kind) => `${SHORT_LABELS[kind]} ${(places.get(kind) ?? []).join(' + ')}`,
  );
  return parts.length > 0 ? parts.join(' · ') : 'Amended to nothing';
}

/** The server's figure when it sent one, else the fallback. Absent is not zero. */
function numberOr(value: string | null | undefined, fallback: () => number): number {
  return value === null || value === undefined ? fallback() : toMinor(value);
}

function sumSources(sources: BoardSource[], kind: string): number {
  return sources
    .filter((source) => source.kind === kind)
    .reduce((total, source) => total + toMinor(source.qty), 0);
}
