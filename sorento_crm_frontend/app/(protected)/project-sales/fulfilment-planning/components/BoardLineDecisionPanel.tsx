'use client';

import * as React from 'react';
import { Check, Pencil, Plus, Trash2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { amendNeedsReason } from '../../_shared/lib/fulfilmentBoard';
import {
  amendDraftFrom,
  amendSummary,
  borrowCandidatesOf,
  decisionFromAmendDraft,
} from '../../_shared/lib/boardAmend';
import {
  fromMinor,
  lineBalance,
  lineBlockers,
  toMinor,
  type DraftBorrow,
  type DraftLine,
} from '../../_shared/lib/supplyComposition';
import type {
  BoardCellLocation,
  BoardContribution,
  BoardDecision,
  BorrowCandidate,
} from '../../_shared/types/fulfilmentPlanning.types';
import { BorrowAddDialog } from './BorrowAddDialog';

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
 * THREE VERBS, and they are the whole decision: Approve suggestion (take the engine's
 * composition), Save amendment (take the one in these inputs), Reject (take none of it, with
 * a reason). There is no Undo button: approving the suggestion IS the way back, and a fourth
 * verb that only differs from it on an untouched line taught nothing.
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
  onDecide: (decision: BoardDecision | null) => void;
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
  const [locked, setLocked] = React.useState(() => Boolean(contribution.covered) && !decision);
  const [adding, setAdding] = React.useState(false);
  /** Untouched since it opened. Saving or approving puts it back, because it is saved now. */
  const [dirty, setDirty] = React.useState(false);

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

  const balance = lineBalance(draft);
  const blockers = lineBlockers(draft);
  const needsReason = amendNeedsReason(contribution, draft);
  const canSave = blockers.length === 0 && (!needsReason || reason.trim().length > 0);
  // WHOLLY bought, which is what the switch means. A composition carrying stock AND a Buy is
  // a revision frozen before the whole-line rule; it renders in full and `lineBlockers` says
  // it cannot be saved that way.
  const fromStockMinor = balance.timelyMinor + balance.reserveMinor + balance.borrowMinor;
  const buying = toMinor(draft.buy_qty) > 0 && fromStockMinor === 0;

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
  const setBorrow = (borrow: DraftBorrow[]) => edit({ ...draft, borrow });

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
    edit({ ...draft, ...(held ?? {}), buy_qty: '0' });
  };

  /** Back to the engine's own composition, and that is the verdict. */
  const approveSuggestion = () => {
    const fresh = draftFor(contribution, null);
    setDraft(fresh);
    setReason('');
    setDirty(false);
    onDecide({ verdict: 'approved', suspected_system_issue: suspected });
  };

  const saveAmendment = () => {
    setDirty(false);
    setLocked(false);
    onDecide({
      ...decisionFromAmendDraft(draft, reason),
      // THE BOOLEAN, never `|| undefined`: `false` is the planner's answer that the numbers
      // are fine, and dropping the key let the frozen `true` behind it read as current.
      suspected_system_issue: suspected,
    });
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
        <div className="grid gap-4 lg:grid-cols-[minmax(0,10rem)_minmax(0,1fr)]">
          <dl className="space-y-2">
            <Figure label="Ordered" value={contribution.qty_ordered ?? 'Not stated'} />
            <Figure label="Delivered" value={contribution.qty_delivered ?? 'Not stated'} />
            <Figure
              label="Outstanding"
              value={contribution.qty_outstanding ?? contribution.qty}
              strong
            />
          </dl>
          <div className="space-y-1">
            <p className="text-2xs uppercase tracking-wide text-muted-foreground">Decision</p>
            <p
              data-testid={`line-decision-blocked-${contribution.key}`}
              className="break-words text-sm text-destructive"
            >
              This sales order states no fulfilment location, so this line cannot be decided
              here. Set the location on the sales order, then plan it again.
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
      <div className="grid gap-4 lg:grid-cols-[minmax(0,10rem)_minmax(0,1.4fr)_minmax(0,1fr)]">
        {/* WHAT THE LINE IS, read-only. The row above shows the outstanding quantity alone,
            and a planner deciding how to cover it wants the other three beside it. */}
        <dl className="space-y-2">
          <Figure label="Ordered" value={contribution.qty_ordered ?? 'Not stated'} />
          <Figure label="Delivered" value={contribution.qty_delivered ?? 'Not stated'} />
          <Figure
            label="Outstanding"
            value={contribution.qty_outstanding ?? contribution.qty}
            strong
          />
          <Figure label="Incoming by the delivery date" value={draft.timely_spo_qty} />
        </dl>

        {/* THE COMPOSITION. Every section renders whatever the answer is: a line with no
            warehouse says so where its Reserve rows would be, and a section that disappears
            reads as a screen that has not finished loading. */}
        <div className="space-y-3">
          <Block label="Reserve">
            {buying ? (
              <Muted>The whole line is being bought.</Muted>
            ) : draft.reserve.length === 0 ? (
              <Muted>The sales order states no warehouse for this line.</Muted>
            ) : (
              <div className="space-y-2">
                {draft.reserve.map((row, index) => (
                  <div key={row.key} className="flex flex-wrap items-center gap-2">
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
                        edit({ ...draft, reserve: next });
                      }}
                      className="h-8 w-24 tabular-nums"
                    />
                    <span className="text-sm">{row.location ?? 'Location not set'}</span>
                    {/* The SERVER's figure for this location, beside the box it bounds. */}
                    {availableAt(locations, row.warehouse_id, row.location) !== null && (
                      <span className="text-sm text-muted-foreground tabular-nums">
                        {`${availableAt(locations, row.warehouse_id, row.location)} available`}
                      </span>
                    )}
                  </div>
                ))}
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
                            setBorrow(draft.borrow.filter((entry) => entry.key !== row.key))
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
                <Muted>No other location or project holds free stock of this item.</Muted>
              ) : (
                <Button type="button" variant="outline" size="sm" onClick={() => setAdding(true)}>
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
                  {buying ? `Buy the whole ${draft.open_qty}` : 'Buy the whole line'}
                </label>
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
                    onChange={(event) => edit({ ...draft, buy_reason: event.target.value })}
                  />
                </div>
              )}
            </div>
          </Block>
        </div>

        {/* WHAT WOULD BE CONFIRMED, and the three verbs. */}
        <div className="space-y-3">
          <div>
            <p className="text-2xs uppercase tracking-wide text-muted-foreground">Decision</p>
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
                  <li key={blocker} className="break-words text-sm text-destructive">
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
              {needsReason ? <span className="text-destructive"> *</span> : null}
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
            <span>This might be a system problem, flag it for investigation</span>
          </label>

          {locked ? (
            <Button type="button" size="sm" variant="outline" onClick={() => setLocked(false)}>
              <Pencil className="size-4" aria-hidden />
              Amend
            </Button>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" size="sm" onClick={approveSuggestion}>
                <Check className="size-4" aria-hidden />
                Approve suggestion
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={!canSave}
                onClick={saveAmendment}
              >
                Save amendment
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
  if (!decision || decision.verdict !== 'amended' || !decision.reserve) return base;

  const byWarehouse = new Map(decision.reserve.map((row) => [row.warehouse_id, row.qty]));
  const reserve = base.reserve.map((row) => ({
    ...row,
    qty: byWarehouse.get(row.warehouse_id) ?? '0',
  }));
  for (const row of decision.reserve) {
    if (reserve.some((seeded) => seeded.warehouse_id === row.warehouse_id)) continue;
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
      donor_impact: { free_before: '0', free_after_full_borrow: '0', committed_qty: '0' },
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
    locations.find((row) => row.warehouse_id && row.warehouse_id === warehouseId) ??
    (code ? locations.find((row) => row.location === code) : undefined);
  return found?.available_qty ?? null;
}

/** One read-only figure of the left-hand strip. */
function Figure({
  label,
  value,
  strong,
}: {
  label: string;
  value: string;
  strong?: boolean;
}) {
  return (
    <div>
      <dt className="text-2xs uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className={`text-sm tabular-nums${strong ? ' font-medium' : ''}`}>{value}</dd>
    </div>
  );
}

/** One editable section, labelled the way the sheet labels it, so the two read the same. */
function Block({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section>
      <p className="mb-1 text-2xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

/** Block, not inline: two stated absences in one section must not run into one sentence. */
function Muted({ children }: { children: React.ReactNode }) {
  return <span className="block text-sm text-muted-foreground">{children}</span>;
}
