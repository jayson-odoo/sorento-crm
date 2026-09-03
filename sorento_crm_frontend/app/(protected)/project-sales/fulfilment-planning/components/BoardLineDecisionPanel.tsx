'use client';

import * as React from 'react';
import { Check, CheckCircle2, Pencil, Plus, Trash2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import {
  amendNeedsReason,
  matchesSuggestion,
} from '../../_shared/lib/fulfilmentBoard';
import {
  amendDraftFrom,
  amendSummary,
  borrowCandidatesOf,
  decisionFromAmendDraft,
  suggestionDraftFrom,
} from '../../_shared/lib/boardAmend';
import {
  fromMinor,
  lineBalance,
  lineBlockers,
  toMinor,
  type DraftBorrow,
  type DraftLine,
} from '../../_shared/lib/supplyComposition';
import { poolShareLimitsOf } from '../../_shared/lib/poolShare';
import type {
  BoardCellLocation,
  BoardContribution,
  BoardDecision,
  BorrowCandidate,
} from '../../_shared/types/fulfilmentPlanning.types';
import { BoardLadderOptionsTable } from './BoardLadderOptionsTable';
import { BorrowAddDialog } from './BorrowAddDialog';
import { ReserveAddDialog } from './ReserveAddDialog';

/**
 * The decision on one contributing line, taken IN THE ROW (PLAN section 3.C, ruling R7).
 *
 * It used to be a modal over a modal: the row carried Approve / Amend / Reject buttons, and
 * Amend opened `BoardAmendDialog` on top of the breakdown dialog that opened it. Two stacked
 * dialogs put the line the planner is deciding on behind the thing they decide it with, and
 * the row's own facts - what was ordered, what is already delivered, what each location can
 * actually give - were on the layer underneath. So the row expands instead, the same gesture
 * reorder planning's group rows already use, and everything about the decision is in one
 * window with the numbers it is made against.
 *
 * It composes on the SAME `DraftLine` the per-order sheet and the old dialog composed on,
 * against the same `lineBalance` and `lineBlockers` - the sheet and the board have to agree
 * about what balances, or one screen refuses what the other accepted.
 *
 * TWO VERBS, and they are the whole decision: Save (take what is in these inputs) and Reject
 * (take none of it, with a reason). Save used to be two buttons - Approve suggestion beside
 * Save amendment - and the captain, on 28 August: "having 1 button save amendment for me to
 * click when an amendment is needed, and another button Approve when an amendment is not
 * needed, is too much of a work for me to think ... if the suggestion is same as decision then
 * it is approved, if suggestion different from decision then it is amended, so I just click on
 * 1 button". So the COMPARISON takes the verdict, not the planner: a form still holding the
 * engine's composition is approved, and one holding anything else is amended.
 *
 * NO BALANCE EQUATION (R9). The line "24 outstanding = 0 incoming + 9 reserve + ..." restated
 * four inputs the planner had just typed. What they cannot see is whether it ADDS UP, so that
 * is all that is said, as "4 short" or "4 over", and only while it does not.
 */
export function BoardLineDecisionPanel({
  contribution,
  decision,
  locations,
  onDecide,
  onDirtyChange,
}: {
  contribution: BoardContribution;
  /** This line's entry in the board's draft, or null while nobody has decided it here. */
  decision: BoardDecision | null;
  /**
   * The cell's own stock rows, so each Reserve input can say what that location has
   * available beside it. The figure is the SERVER's - the panel never recomputes one.
   */
  locations: BoardCellLocation[];
  /**
   * S4/R-F: saves (or, on `null`, undoes) the decision on the SERVER, not only in this
   * session's draft - `await`ed here so the Save button's own check state (AC-4.1) can wait
   * for it to settle before showing. Resolves `true` on success (S2, code review round 3):
   * a rejected write must not show the check either, and `void` stays for callers that have
   * no result to report (a `?batch=` board pre-marking a row locally, for instance).
   */
  onDecide: (decision: BoardDecision | null) => Promise<boolean> | void;
  /**
   * Whether this panel holds an edit nobody has saved. The dialog opens one row at a time,
   * so it has to ask before it closes this one over the planner's work.
   */
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const [draft, setDraft] = React.useState<DraftLine>(() =>
    draftFor(contribution, decision),
  );
  const [reason, setReason] = React.useState(
    () => decision?.reason ?? contribution.decision?.amend_reason ?? '',
  );
  // The draft's own answer, false included: an untick is a decision, and reading past it to
  // the frozen `true` on a covered line put the tick straight back on screen.
  const [suspected, setSuspected] = React.useState(() =>
    decision
      ? Boolean(decision.suspected_system_issue)
      : Boolean(contribution.decision?.suspected_system_issue),
  );
  /**
   * A line an active decision covers opens READ-ONLY with an Amend button (C11): what is on
   * screen is what the database holds, and an editable form over it invites a planner to
   * change something they have not decided to change yet.
   */
  const [locked, setLocked] = React.useState(
    () => Boolean(contribution.covered) && !decision,
  );
  const [adding, setAdding] = React.useState(false);
  const [addingReserve, setAddingReserve] = React.useState(false);
  /** Untouched since it opened. Saving or approving puts it back, because it is saved now. */
  const [dirty, setDirty] = React.useState(false);
  /**
   * Whether this line's decision is SAVED as the panel stands (S4, AC-4.1; amended by D4,
   * captain 3 Sep).
   *
   * It used to be a 600 ms flash after `onDecide` resolved, and the captain read the flash
   * as the save undoing itself: "shows saved then jumps back". So it is the LINE's state
   * now, not a moment's - the button stays on the check, disabled, for as long as nothing
   * has been edited since, and any edit puts "Save decision" back (`dirty` below is what
   * every input already sets). A line that opens on somebody else's saved draft starts
   * there too: pressing Save on it would write what is already written.
   */
  const [savedOnce, setSavedOnce] = React.useState(() => Boolean(contribution.draft));

  /**
   * N3 (fix round 5): re-seeded whenever the contribution's OWN saved draft changes - a
   * refetch (another planner saved this line elsewhere) or an Undo fired from the pill
   * (`BoardDecisionPill`), neither of which goes through this panel's own `save()` /
   * `reject()`. Seeded at MOUNT only left a panel that stayed open across such a change
   * reading a state the server had already moved on from: Undo cleared the draft server-side
   * while this panel's own `savedOnce` (still `true` from mount) kept the button on "Saved".
   */
  React.useEffect(() => {
    setSavedOnce(Boolean(contribution.draft));
  }, [contribution.draft]);

  /**
   * Saved AND untouched since (D4). `dirty` is set by every input on this panel, so an edit
   * of any kind puts "Save decision" back without this having to know which one moved.
   */
  const saved = savedOnce && !dirty;

  React.useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  // Nothing is left dirty behind a panel that is going away: the row above is closing and the
  // dialog's prompt has already been answered by then.
  React.useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);

  const candidates = React.useMemo<BorrowCandidate[]>(
    () => borrowCandidatesOf(contribution),
    [contribution],
  );

  // Reserve add-location (S3, R-G): any location the cell's own stock rows carry, with free
  // stock left and not already on the Reserve list. The site pool is not filtered out - R-A
  // asks it first, so a planner adding it by hand is asking for exactly what the ladder itself
  // would have asked for.
  const reserveWarehouseIds = React.useMemo(
    () =>
      draft.reserve
        .map((row) => row.warehouse_id)
        .filter((id): id is string => Boolean(id)),
    [draft.reserve],
  );
  const reserveCandidates = React.useMemo(
    () =>
      locations.filter(
        (location) =>
          Boolean(location.warehouse_id) &&
          !reserveWarehouseIds.includes(location.warehouse_id as string) &&
          toMinor(location.qty_free_remaining ?? location.qty_free ?? '0') > 0,
      ),
    [locations, reserveWarehouseIds],
  );

  const balance = lineBalance(draft);
  /**
   * D5: the board CAN check the pool-share carve-out (R-C), because its own cell states each
   * pool's allowance and the pools' net. Without them this panel refused "BRW 62 + Buy 73" -
   * the engine's own suggestion on SO419208 line 3, and a composition the server's confirm
   * has always admitted.
   */
  const poolLimits = React.useMemo(() => poolShareLimitsOf(locations), [locations]);
  const blockers = lineBlockers(draft, poolLimits);
  const needsReason = amendNeedsReason(contribution, draft);
  // Which verdict Save takes, and therefore what it may be pressed for: approving the engine's
  // own composition is never blocked, because there is nothing about it to balance or justify.
  const approving = matchesSuggestion(contribution, draft);
  const canSave =
    blockers.length === 0 && (!needsReason || reason.trim().length > 0);
  const fromStockMinor =
    balance.timelyMinor + balance.reserveMinor + balance.borrowMinor;
  /**
   * WHOLLY bought, which is what the switch means. STATE (B-1, fix round 7), not derived from
   * the numbers - deriving it used to flip the switch ON the instant `fromStockMinor` hit zero,
   * which clearing a reserve box (or typing 0 into it) does on its own now that D7's
   * `editComposition` recomputes `buy_qty` on every keystroke. The switch turning itself on
   * mid-edit unmounted the Reserve section and the Add-location button under the planner, and
   * turning it back OFF afterwards took the "nothing was captured" branch below and wrote
   * zeroes over rows nobody asked to zero.
   *
   * Seeded ONCE from the opening draft - a line that opens already wholly bought (its stock
   * rows already at zero) starts on the switch, the same line `setBuying`'s OFF transition
   * documents - and changed only by `setBuying` itself. No reactive re-seed: the panel already
   * remounts fresh (via `draftFor`, the initializer `draft` itself uses) whenever it is closed
   * and reopened on a different contribution or a different saved draft, which is the only
   * point this needs to move.
   */
  const [buying, setBuyingState] = React.useState(
    () => toMinor(draft.buy_qty) > 0 && fromStockMinor === 0,
  );

  /**
   * Everything that stops the Save EXCEPT the balance, which the hint beside the summary
   * already states in two words. Printing both would say the same refusal twice.
   */
  const otherBlockers = balance.balanced
    ? blockers
    : blockers.filter((blocker) => !blocker.includes('the components are'));

  const edit = (next: DraftLine) => {
    setDraft(next);
    setDirty(true);
  };

  /**
   * D7 (captain, 3 Sep): Buy is never typed on this panel, it FOLLOWS the remainder.
   *
   * "BRW 62 · Buy 73" on SO419208 line 3 (open 135) used to leave `buy_qty` frozen at 73 the
   * instant the BRW reserve was edited down to 60 - the line read short by 2 and Save stayed
   * blocked, because nothing that touches Reserve or Borrow ever recomputed it. Every input
   * that changes the STOCK side of the composition writes through here instead of `edit()`
   * directly: `buy_qty = max(open_qty - reserve - borrow - timely, 0)`, the same arithmetic
   * `lineBalance` already does, read with Buy zeroed out of the total.
   *
   * `setBuying`'s own transitions do NOT call this - they compute their own value for each
   * direction (see there). Deriving here too would undo the OFF transition on a line that
   * opened already wholly bought (a frozen decision, or an all-Buy suggestion): its stock
   * rows are already at zero, and deriving off zero rows hands the whole line straight back
   * to Buy, so the switch could never actually be turned off.
   */
  const editComposition = (next: DraftLine) => {
    const stockOnly = lineBalance({ ...next, buy_qty: '0' });
    edit({
      ...next,
      buy_qty: fromMinor(Math.max(stockOnly.openMinor - stockOnly.totalMinor, 0)),
    });
  };
  const setBorrow = (borrow: DraftBorrow[]) => editComposition({ ...draft, borrow });

  /**
   * The whole line, one way or the other. Never a mix - the confirmation refuses one.
   *
   * Switching Buy ON zeroes the stock side, and switching it OFF puts back exactly what was
   * there: the quantities, the donors and their reasons. The rows alone are not enough - a
   * planner who typed a 9, a 15 and two sentences and then tried the Buy switch got a form of
   * zeroes back, which is a composition they never wrote and the worst possible answer to
   * "what happens if I press this".
   */
  const stockBefore = React.useRef<Pick<
    DraftLine,
    'reserve' | 'borrow' | 'timely_spo_qty'
  > | null>(null);
  const setBuying = (next: boolean) => {
    setBuyingState(next);
    if (next) {
      stockBefore.current = {
        reserve: draft.reserve,
        borrow: draft.borrow,
        timely_spo_qty: draft.timely_spo_qty,
      };
      edit({
        ...draft,
        timely_spo_qty: '0',
        // The rows stay, at zero: they are where the locations are named.
        reserve: draft.reserve.map((row) => ({ ...row, qty: '0' })),
        borrow: [],
        buy_qty: draft.open_qty,
      });
      return;
    }
    const held = stockBefore.current;
    stockBefore.current = null;
    if (held) {
      // D7: the remainder of whatever gets restored, not the flat 0 this used to force - that
      // used to drop the BRW-62/Buy-73 shape's own Buy to nothing the moment the switch was
      // tried and put back, when nothing about the stock side had actually changed.
      editComposition({ ...draft, ...held });
      return;
    }
    // Nothing was captured: the switch was never turned ON in this session, so the line opened
    // already wholly bought and its stock rows are already at zero. Buy explicitly to 0 - not
    // derived, or it would hand the whole line straight back - and let the now-empty rows be
    // typed into.
    edit({ ...draft, buy_qty: '0' });
  };

  /**
   * ONE PRESS, TWO VERDICTS, decided by what the inputs hold rather than by which button was
   * chosen: the engine's composition is an approval, anything else is an amendment.
   *
   * The approval re-seeds from `suggestionDraftFrom`, never `draftFor`: on a covered line the
   * panel opens on what was DECIDED, so resetting to that put the frozen numbers back and
   * called it the suggestion - SO404352 line 22 stayed at 8 / 16 under a pill reading
   * Approved. The reason goes with it, because an approval overrides nothing.
   */
  const save = async () => {
    let ok: boolean | void;
    if (approving) {
      ok = await onDecide({ verdict: 'approved', suspected_system_issue: suspected });
    } else {
      ok = await onDecide({
        ...decisionFromAmendDraft(draft, reason),
        // THE BOOLEAN, never `|| undefined`: `false` is the planner's answer that the numbers
        // are fine, and dropping the key let the frozen `true` behind it read as current.
        suspected_system_issue: suspected,
      });
    }
    // S2 (code review round 3): the check state answers the click, but only for a click that
    // actually landed - `onDecide` returning `false` (a rejected write) must not show a
    // check the server never earned. `undefined` (a caller with nothing to report) reads as
    // success, the same as before this fix.
    //
    // B1 (fix round 5): every "clean" state change - dirty, locked, and the approving branch's
    // reseed to the suggestion - waits for that same guard. Setting them before the `await`
    // meant a REJECTED second save still rendered the button as Saved and disabled: `dirty`
    // was already false and `savedOnce` was already true from the first, successful save, so
    // `saved = savedOnce && !dirty` read true over an edit the server never wrote.
    if (ok === false) return;
    setDirty(false);
    setLocked(false);
    if (approving) {
      setDraft(suggestionDraftFrom(contribution));
      setReason('');
    }
    // S4/AC-4.1: the button answers the click itself, within the interaction, before the
    // pill's own "Saved" and the toast even have to be looked at - and it keeps answering
    // until the line is edited again (D4).
    setSavedOnce(true);
  };

  const reject = () => {
    setDirty(false);
    onDecide({
      verdict: 'rejected',
      reason: reason.trim(),
      suspected_system_issue: suspected,
    });
  };

  const summary = amendSummary(
    decisionFromAmendDraft(draft, reason),
    contribution.fulfilment_location,
  );

  /**
   * A LINE THAT CANNOT BE DECIDED HERE STATES SO, AND OFFERS NOTHING.
   *
   * Its sales order names no fulfilment location, so there is no warehouse to reserve at and
   * the confirmation leaves the line out entirely (`lineFor` returns null for it). An
   * editable panel over that was a trap: the composition could be typed, the pill would read
   * Amended, and the press would silently post nothing for it. The row still opens - the
   * figures are worth reading, and a row that refused to open reads as a broken row - but the
   * only thing it can say is why, and where the fix is.
   */
  if (contribution.unplannable) {
    return (
      <div
        data-testid={`line-decision-${contribution.key}`}
        className="border-t bg-muted/30 px-4 py-3 sm:px-5"
      >
        <div>
          <div className="space-y-1">
            <p className="text-2xs uppercase tracking-wide text-muted-foreground">
              Decision
            </p>
            <p
              data-testid={`line-decision-blocked-${contribution.key}`}
              className="break-words text-sm text-destructive"
            >
              This sales order states no fulfilment location, so this line
              cannot be decided here. Set the location on the sales order, then
              plan it again.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      data-testid={`line-decision-${contribution.key}`}
      className="border-t bg-muted/30 px-4 py-3 sm:px-5"
    >
      {/* WHAT THE LADDER OFFERED, above the editor that amends it (R36, AC-S3-14).
          The same table the trail popover renders, and above rather than beside on purpose:
          it is six columns of dates, and squeezed into the right-hand column it would wrap at
          1280px, let alone at 375. It is what the planner reads BEFORE typing, so it reads
          first. Display only - taking a different option is Amend, in the inputs below. */}
      {(contribution.options?.length ?? 0) > 0 && (
        <div className="mb-3 space-y-1">
          <p className="text-2xs uppercase tracking-wide text-muted-foreground">
            Options
          </p>
          <BoardLadderOptionsTable
            options={contribution.options ?? []}
            contributionKey={contribution.key}
          />
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        {/* THE COMPOSITION. The row above already states the outstanding quantity, so the
            editor carries only what the planner decides. Every section renders whatever the
            answer is: a line with no warehouse says so where its Reserve rows would be, and a
            section that disappears reads as a screen that has not finished loading. */}
        <div className="space-y-3">
          <Block label="Reserve">
            {buying ? (
              <Muted>The whole line is being bought.</Muted>
            ) : (
              <div className="space-y-2">
                {draft.reserve.length === 0 ? (
                  <Muted>The sales order states no warehouse for this line.</Muted>
                ) : (
                  draft.reserve.map((row, index) => {
                    const available = availableAt(
                      locations,
                      row.warehouse_id,
                      row.location,
                    );
                    // The SERVER's own guard refuses a reserve above on-hand at that
                    // location (`_check_reserve_against_on_hand`); this is the same check
                    // read off the same figure, so a planner sees it before Confirm does
                    // (AC-3.3). The row is never removed for it - it stays here, editable.
                    const over =
                      available !== null && toMinor(row.qty) > toMinor(available);
                    return (
                      <div
                        key={row.key}
                        className="flex flex-wrap items-center gap-2"
                      >
                        <Input
                          type="number"
                          min="0"
                          step="any"
                          value={row.qty}
                          disabled={locked}
                          aria-label={`Reserve at ${row.location ?? 'the fulfilment location'}`}
                          onChange={(event) => {
                            const next = [...draft.reserve];
                            next[index] = { ...row, qty: event.target.value };
                            editComposition({ ...draft, reserve: next });
                          }}
                          className="h-8 w-24 tabular-nums"
                        />
                        <span className="text-sm">
                          {row.location ?? 'Location not set'}
                        </span>
                        {/* The SERVER's figure for this location, beside the box it bounds. */}
                        {available !== null && (
                          <span
                            data-testid={`line-reserve-available-${row.key}`}
                            className={cn(
                              'text-sm tabular-nums',
                              over ? 'text-destructive' : 'text-muted-foreground',
                            )}
                          >
                            {over
                              ? `Only ${available} available here`
                              : `${available} available`}
                          </span>
                        )}
                      </div>
                    );
                  })
                )}

                {locked ? null : reserveCandidates.length === 0 ? (
                  <Muted>No other location holds free stock of this item.</Muted>
                ) : (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setAddingReserve(true)}
                  >
                    <Plus className="size-4" aria-hidden />
                    Add location
                  </Button>
                )}
              </div>
            )}
          </Block>

          <Block label="Borrow">
            <div className="space-y-3">
              {buying ? (
                <Muted>The whole line is being bought.</Muted>
              ) : draft.borrow.length === 0 ? (
                <Muted>Nothing is borrowed on this line.</Muted>
              ) : (
                draft.borrow.map((row, index) => (
                  <div key={row.key} className="space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <Input
                        type="number"
                        min="0"
                        step="any"
                        value={row.qty}
                        disabled={locked}
                        aria-label={`Borrow from ${row.donor_project_ref ?? row.warehouse_code}`}
                        onChange={(event) => {
                          const next = [...draft.borrow];
                          next[index] = { ...row, qty: event.target.value };
                          setBorrow(next);
                        }}
                        className="h-8 w-24 tabular-nums"
                      />
                      <span className="min-w-0 truncate text-sm">
                        {row.donor_project_ref
                          ? `${row.donor_project_ref} at ${row.warehouse_code}`
                          : row.warehouse_code}
                      </span>
                      {locked ? null : (
                        <Button
                          type="button"
                          mode="icon"
                          variant="dim"
                          aria-label={`Remove the borrow from ${row.donor_project_ref ?? row.warehouse_code}`}
                          onClick={() =>
                            setBorrow(
                              draft.borrow.filter(
                                (entry) => entry.key !== row.key,
                              ),
                            )
                          }
                        >
                          <Trash2 />
                        </Button>
                      )}
                    </div>
                    <div className="space-y-1">
                      <label
                        className="block text-2xs uppercase tracking-wide text-muted-foreground"
                        htmlFor={`line-borrow-reason-${contribution.key}-${row.key}`}
                      >
                        Reason <span className="text-destructive">*</span>
                      </label>
                      <Textarea
                        id={`line-borrow-reason-${contribution.key}-${row.key}`}
                        rows={2}
                        value={row.reason}
                        disabled={locked}
                        placeholder="In your own words"
                        onChange={(event) => {
                          const next = [...draft.borrow];
                          next[index] = { ...row, reason: event.target.value };
                          setBorrow(next);
                        }}
                      />
                    </div>
                  </div>
                ))
              )}

              {buying || locked ? null : candidates.length === 0 ? (
                <Muted>
                  No other location or project holds free stock of this item.
                </Muted>
              ) : (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setAdding(true)}
                >
                  <Plus className="size-4" aria-hidden />
                  Add a borrow
                </Button>
              )}
            </div>
          </Block>

          <Block label="Buy">
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <Switch
                  id={`line-buy-switch-${contribution.key}`}
                  aria-label="Buy the whole line"
                  checked={buying}
                  disabled={locked}
                  onCheckedChange={setBuying}
                />
                <label
                  htmlFor={`line-buy-switch-${contribution.key}`}
                  className="text-sm text-muted-foreground"
                >
                  {buying
                    ? `Buy the whole ${draft.open_qty}`
                    : 'Buy the whole line'}
                </label>
                {/* D7: what the switch means while it is OFF - the remainder `edit()` derives,
                    never a figure the planner types. Zero is still an answer ("Buy 0"), not a
                    blank: it says the reserve, borrow and incoming already cover the line. */}
                {!buying && (
                  <span
                    data-testid={`line-buy-derived-${contribution.key}`}
                    className="text-sm tabular-nums text-muted-foreground"
                  >
                    {`Buy ${draft.buy_qty}`}
                  </span>
                )}
              </div>
              {/* An order back is a Buy whose supply is ALREADY on order or already shipped,
                  so the row purchasing gets carries verb ORDER BACK. Offered only while the
                  line is being bought: there is no row to mark otherwise. */}
              {buying && (
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Switch
                      id={`line-order-back-${contribution.key}`}
                      aria-label="Order back"
                      checked={draft.order_back}
                      disabled={locked}
                      onCheckedChange={(next) =>
                        edit({
                          ...draft,
                          order_back: next,
                          cited_document: next ? draft.cited_document : '',
                        })
                      }
                    />
                    <label
                      htmlFor={`line-order-back-${contribution.key}`}
                      className="text-sm text-muted-foreground"
                    >
                      Order back
                    </label>
                  </div>
                  {draft.order_back && (
                    <div className="space-y-1">
                      <label
                        className="block text-2xs uppercase tracking-wide text-muted-foreground"
                        htmlFor={`line-cited-document-${contribution.key}`}
                      >
                        Document cited
                      </label>
                      <Input
                        id={`line-cited-document-${contribution.key}`}
                        value={draft.cited_document}
                        disabled={locked}
                        placeholder="202604-S0083 or SPO-2026/08-0061"
                        onChange={(event) =>
                          edit({ ...draft, cited_document: event.target.value })
                        }
                      />
                    </div>
                  )}
                </div>
              )}
              {draft.is_discontinued && (
                <div className="space-y-1">
                  <label
                    className="block text-2xs uppercase tracking-wide text-muted-foreground"
                    htmlFor={`line-buy-reason-${contribution.key}`}
                  >
                    Reason <span className="text-destructive">*</span>
                  </label>
                  <Textarea
                    id={`line-buy-reason-${contribution.key}`}
                    rows={2}
                    value={draft.buy_reason}
                    disabled={locked}
                    placeholder="In your own words"
                    onChange={(event) =>
                      edit({ ...draft, buy_reason: event.target.value })
                    }
                  />
                </div>
              )}
            </div>
          </Block>
        </div>

        {/* WHAT WOULD BE CONFIRMED, and the two verbs. */}
        <div className="space-y-3">
          <div>
            <p className="text-2xs uppercase tracking-wide text-muted-foreground">
              Decision
            </p>
            <p
              data-testid={`line-decision-summary-${contribution.key}`}
              className="break-words text-sm tabular-nums"
            >
              {summary}
            </p>
            {/* Two words, and only while the composition does not add up (R9). */}
            {balance.balanced ? null : (
              <p
                data-testid={`line-decision-hint-${contribution.key}`}
                className="text-sm text-destructive tabular-nums"
              >
                {`${fromMinor(Math.abs(balance.differenceMinor))} ${
                  balance.differenceMinor > 0 ? 'over' : 'short'
                }`}
              </p>
            )}
            {otherBlockers.length > 0 && (
              <ul className="mt-1 space-y-0.5">
                {otherBlockers.map((blocker) => (
                  <li
                    key={blocker}
                    className="break-words text-sm text-destructive"
                  >
                    {blocker}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="space-y-1">
            <label
              className="block text-2xs uppercase tracking-wide text-muted-foreground"
              htmlFor={`line-reason-${contribution.key}`}
            >
              Why this differs
              {needsReason ? (
                <span className="text-destructive"> *</span>
              ) : null}
            </label>
            <Textarea
              id={`line-reason-${contribution.key}`}
              rows={2}
              value={reason}
              disabled={locked}
              placeholder="In your own words"
              onChange={(event) => {
                setReason(event.target.value);
                setDirty(true);
              }}
            />
          </div>

          {/* The planner's other answer (R10): the numbers themselves look wrong. It rides on
              the decision so the flag reaches the same record the composition does. */}
          <label
            className="flex items-start gap-2 text-sm"
            htmlFor={`line-suspect-${contribution.key}`}
          >
            <Checkbox
              id={`line-suspect-${contribution.key}`}
              checked={suspected}
              disabled={locked}
              onCheckedChange={(value) => {
                setSuspected(value === true);
                setDirty(true);
              }}
              className="mt-0.5"
            />
            <span>
              This might be a system problem, flag it for investigation
            </span>
          </label>

          {locked ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => setLocked(false)}
            >
              <Pencil className="size-4" aria-hidden />
              Amend
            </Button>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                size="sm"
                // Disabled ON the saved state too (D4): there is nothing left to save, and a
                // live button under the word "Saved" invites a second write of the same row.
                disabled={saved || (!approving && !canSave)}
                onClick={save}
              >
                {saved ? (
                  <>
                    <CheckCircle2 className="size-4" aria-hidden />
                    Saved
                  </>
                ) : (
                  <>
                    <Check className="size-4" aria-hidden />
                    Save decision
                  </>
                )}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={reason.trim().length === 0}
                title={
                  reason.trim().length === 0
                    ? 'Say why this line is being refused first.'
                    : undefined
                }
                onClick={reject}
              >
                <X className="size-4" aria-hidden />
                Reject
              </Button>
            </div>
          )}
        </div>
      </div>

      {adding && (
        <BorrowAddDialog
          lineNo={contribution.line_no}
          itemCode={contribution.item_code}
          candidates={candidates}
          onDone={() => setAdding(false)}
          onAdd={(candidate: BorrowCandidate, qty, borrowReason) =>
            setBorrow([
              ...draft.borrow,
              {
                key: `borrow-${candidate.warehouse_id}-${draft.borrow.length}`,
                source: candidate.source,
                warehouse_code: candidate.warehouse_code,
                warehouse_id: candidate.warehouse_id,
                donor_project_ref: candidate.donor_project_ref,
                donor_project_id: candidate.donor_project_id,
                qty,
                reason: borrowReason,
                donor_impact: candidate.donor_impact,
                donor_core_line_id: candidate.donor_core_line_id,
                donor_so_number: candidate.donor_so_number,
                donor_line_no: candidate.donor_line_no,
                donor_agent_code: candidate.donor_agent_code,
                same_agent: candidate.same_agent,
              },
            ])
          }
        />
      )}

      {addingReserve && (
        <ReserveAddDialog
          lineNo={contribution.line_no}
          itemCode={contribution.item_code}
          locations={reserveCandidates}
          // S-1 (fix round 7): NOT `open - total` - `total` now includes D7's derived Buy, so
          // on an already-composed line (BRW 62 + Buy 73) it read 0 and the dialog fell back
          // to the location's WHOLE free stock (`ReserveAddDialog.openingQty`). What is left
          // to cover from STOCK is the open quantity minus everything except the Buy.
          openRemainder={fromMinor(
            Math.max(balance.openMinor - (balance.totalMinor - balance.buyMinor), 0),
          )}
          onDone={() => setAddingReserve(false)}
          onAdd={(location, qty) =>
            editComposition({
              ...draft,
              reserve: [
                ...draft.reserve,
                {
                  key: `reserve-${location.warehouse_id}-${draft.reserve.length}`,
                  location: location.location,
                  warehouse_id: location.warehouse_id ?? '',
                  qty,
                  reason: '',
                },
              ],
            })
          }
        />
      )}
    </div>
  );
}

/**
 * The draft this panel opens on: the engine's proposal, with the planner's own amendment
 * laid over it when they have already made one on this board.
 *
 * `amendDraftFrom` is the one seeder (it knows the frozen decision, the own-location row and
 * the fallbacks), so this only replaces the QUANTITIES a saved amendment states. Without the
 * overlay, collapsing an amended row and opening it again showed the engine's numbers under
 * a pill reading Amended.
 */
function draftFor(
  contribution: BoardContribution,
  decision: BoardDecision | null,
): DraftLine {
  const base = amendDraftFrom(contribution);
  if (!decision || decision.verdict !== 'amended' || !decision.reserve)
    return base;

  const byWarehouse = new Map(
    decision.reserve.map((row) => [row.warehouse_id, row.qty]),
  );
  const reserve = base.reserve.map((row) => ({
    ...row,
    qty: byWarehouse.get(row.warehouse_id) ?? '0',
  }));
  for (const row of decision.reserve) {
    if (reserve.some((seeded) => seeded.warehouse_id === row.warehouse_id))
      continue;
    reserve.push({
      key: `reserve-${row.location ?? row.warehouse_id}`,
      location: row.location ?? null,
      warehouse_id: row.warehouse_id,
      qty: row.qty,
      reason: '',
    });
  }

  return {
    ...base,
    reserve,
    borrow: (decision.borrow ?? []).map((row, index) => ({
      key: `borrow-${row.warehouse_id}-${index}`,
      source: row.source,
      warehouse_code: row.warehouse_code ?? '',
      warehouse_id: row.warehouse_id,
      donor_project_ref: row.donor_project_ref ?? null,
      donor_project_id: row.donor_project_id ?? null,
      qty: row.qty,
      reason: row.reason,
      // A donor's position is a fact about NOW; an amendment held in the draft does not
      // carry one, and printing zeroes as "0 free" would say the donor is empty.
      donor_impact: {
        free_before: '0',
        free_after_full_borrow: '0',
        committed_qty: '0',
      },
      donor_core_line_id: row.donor_core_line_id ?? null,
      donor_so_number: row.donor_so_number ?? null,
      donor_line_no: row.donor_line_no ?? null,
      donor_agent_code: row.donor_agent_code ?? null,
      same_agent: row.same_agent ?? false,
      donor_required_date: row.donor_required_date ?? null,
    })),
    timely_spo_qty: decision.timely_spo_qty ?? base.timely_spo_qty,
    buy_qty: decision.buy_qty ?? '0',
    buy_reason: decision.buy_reason ?? '',
    order_back: Boolean(decision.order_back),
    cited_document: decision.cited_document ?? '',
  };
}

/**
 * What a location has available, as the SERVER stated it for this cell. Matched by id first
 * and by code as the fallback, the same order every other lookup on this board uses.
 */
function availableAt(
  locations: BoardCellLocation[],
  warehouseId: string,
  code?: string | null,
): string | null {
  const found =
    locations.find(
      (row) => row.warehouse_id && row.warehouse_id === warehouseId,
    ) ?? (code ? locations.find((row) => row.location === code) : undefined);
  // NOT `available_qty` (B2, code review round 3): it is AutoCount's own SIGNED whole-book
  // figure - negative at a location like MWH-IB (-15514) - so it flagged the ENGINE'S OWN
  // suggestions as oversold. `qty_free_remaining` (falling back to `qty_free` before any
  // proposal has drawn it down) is the figure `reserveCandidates` and this dialog's own
  // `ReserveAddDialog.openingQty` already offer on, so the echo agrees with what a planner
  // was shown when they picked the location. The server's own guard
  // (`_check_reserve_against_on_hand`, on hand minus confirmed holds) stays the authority at
  // Confirm; this is only the echo shown while typing.
  return found?.qty_free_remaining ?? found?.qty_free ?? null;
}

/** One editable section, labelled the way the sheet labels it, so the two read the same. */
function Block({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <p className="mb-1 text-2xs uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

/** Block, not inline: two stated absences in one section must not run into one sentence. */
function Muted({ children }: { children: React.ReactNode }) {
  return (
    <span className="block text-sm text-muted-foreground">{children}</span>
  );
}
