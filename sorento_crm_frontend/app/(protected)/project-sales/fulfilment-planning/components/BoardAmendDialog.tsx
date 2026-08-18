'use client';

import * as React from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { amendNeedsReason } from '../../_shared/lib/fulfilmentBoard';
import {
  amendDraftFrom,
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
  BoardContribution,
  BoardDecision,
  BorrowCandidate,
} from '../../_shared/types/fulfilmentPlanning.types';
import { BorrowAddDialog } from './BorrowAddDialog';

/**
 * Amending ONE board line, as a dialog over the breakdown (PLAN 13.4).
 *
 * The captain, 18 August 2026: "the amend is not working, I should be able to amend the
 * decision and quantity, like I can decide to reserve, or buy, or borrow". Two faults, and
 * this fixes both:
 *
 *   - the editor was a panel UNDER a 25-row table inside the breakdown's own scroll region, so
 *     pressing Amend moved nothing the planner could see and the form was simply never found;
 *   - it held ONE input, the Reserve, so two of the four verbs were unreachable and the third
 *     was derived behind their back - everything taken off the Reserve was pushed into Buy.
 *
 * So it is a dialog of its own, over the one it was opened from, and it composes the SAME four
 * kinds the per-order sheet composes, in the SAME order, against the SAME `lineBalance` and
 * `lineBlockers`. The two screens have to agree about what balances, or one of them refuses
 * what the other accepted.
 *
 * EVERY SECTION RENDERS, whatever the answer is: a line with no warehouse says so where its
 * Reserve rows would be, and a line with no donor says so where its Borrow rows would be. A
 * section that disappears reads as a screen that has not finished loading.
 */
export function BoardAmendDialog({
  contribution,
  onSave,
  onCancel,
}: {
  contribution: BoardContribution;
  onSave: (decision: BoardDecision) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = React.useState<DraftLine>(() => amendDraftFrom(contribution));
  // On a line an active decision covers, the reason it was decided for is already written and
  // is carried forward: it is the sentence that explains the composition in the box, and
  // making the planner retype it to re-save their own decision is how a mandatory field
  // becomes a rubber stamp.
  const [reason, setReason] = React.useState(contribution.decision?.amend_reason ?? '');
  const [adding, setAdding] = React.useState(false);

  const candidates = React.useMemo<BorrowCandidate[]>(
    () => borrowCandidatesOf(contribution),
    [contribution],
  );
  const balance = lineBalance(draft);
  const blockers = lineBlockers(draft);
  const needsReason = amendNeedsReason(contribution, draft);
  const canSave = blockers.length === 0 && (!needsReason || reason.trim().length > 0);

  const setBorrow = (borrow: DraftBorrow[]) => setDraft({ ...draft, borrow });

  return (
    <Dialog open onOpenChange={(next) => !next && onCancel()}>
      <DialogContent className="flex max-h-[85vh] w-full flex-col overflow-hidden p-0 sm:max-w-2xl">
        <DialogHeader className="shrink-0 space-y-1 border-b p-4 sm:p-6">
          <DialogTitle className="min-w-0 break-words">
            {`Amend ${contribution.so_number} · line ${contribution.line_no} · ${contribution.item_code}`}
          </DialogTitle>
          <DialogDescription className="min-w-0 break-words">
            {contribution.fulfilment_location
              ? `Fulfil from ${contribution.fulfilment_location}`
              : 'No fulfilment location on the sales order line'}
          </DialogDescription>
        </DialogHeader>

        {/* The only scrolling region, so Save can never be painted over - the same layout
            fault the breakdown dialog was measured with at a 560px window. */}
        <DialogBody className="min-h-0 flex-1 divide-y divide-border overflow-y-auto p-0">
          <Section label="Owed">
            <span data-testid="amend-owed" className="text-sm tabular-nums">
              {draft.open_qty}
            </span>
          </Section>

          {/* Dated supply, not a choice: it is shown and never typed, exactly as on the sheet.
              An amendment cannot promise incoming stock that is not coming. */}
          <Section label="Incoming by the required date">
            <span data-testid="amend-incoming" className="text-sm tabular-nums">
              {draft.timely_spo_qty}
            </span>
          </Section>

          <Section label="Reserve">
            {draft.reserve.length === 0 ? (
              <Muted>The sales order states no warehouse for this line.</Muted>
            ) : (
              <div className="space-y-2">
                {draft.reserve.map((row, index) => (
                  <div key={row.key} className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Input
                        type="number"
                        min="0"
                        step="any"
                        value={row.qty}
                        aria-label={`Reserve at ${row.location ?? 'the fulfilment location'}`}
                        onChange={(event) => {
                          const next = [...draft.reserve];
                          next[index] = { ...row, qty: event.target.value };
                          setDraft({ ...draft, reserve: next });
                        }}
                        className="h-8 w-28 tabular-nums"
                      />
                      <span className="text-sm text-muted-foreground">
                        {row.location ?? 'Location not set'}
                      </span>
                      {/* What was left for THIS line at its own location, which is not the
                          pile's position and is never printed under that label (13.7). */}
                      {isOwn(contribution, row.warehouse_id, row.location) &&
                        contribution.available_to_this_line !== null &&
                        contribution.available_to_this_line !== undefined && (
                          <span className="text-sm text-muted-foreground tabular-nums">
                            {`${contribution.available_to_this_line} left for this line`}
                          </span>
                        )}
                    </div>
                    {row.reason ? (
                      <p className="text-sm text-muted-foreground break-words">{row.reason}</p>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </Section>

          <Section label="Borrow">
            <div className="space-y-3">
              {draft.borrow.length === 0 ? (
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
                        aria-label={`Borrow from ${row.donor_project_ref ?? row.warehouse_code}`}
                        onChange={(event) => {
                          const next = [...draft.borrow];
                          next[index] = { ...row, qty: event.target.value };
                          setBorrow(next);
                        }}
                        className="h-8 w-28 tabular-nums"
                      />
                      <span className="min-w-0 truncate text-sm text-muted-foreground">
                        {row.donor_project_ref
                          ? `${row.donor_project_ref} at ${row.warehouse_code}`
                          : row.warehouse_code}
                      </span>
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
                    </div>
                    <p className="text-sm text-muted-foreground break-words">
                      {/* A donor's position is a fact about NOW, and a borrow frozen into a
                          confirmed decision does not carry one - the board only reads donors
                          for a line it is still proposing a Buy for. All three at zero is that
                          absence, and printing it as "0 free" would say the donor is empty. */}
                      {statedImpact(row.donor_impact)
                        ? `${row.donor_impact.free_before} free before, ${row.donor_impact.free_after_full_borrow} after taking all of it, ${row.donor_impact.committed_qty} committed.`
                        : "The donor's position is not stated here."}
                    </p>
                    <div className="space-y-1">
                      <label
                        className="block text-2xs uppercase tracking-wide text-muted-foreground"
                        htmlFor={`board-borrow-reason-${row.key}`}
                      >
                        Reason <span className="text-destructive">*</span>
                      </label>
                      <Textarea
                        id={`board-borrow-reason-${row.key}`}
                        rows={2}
                        value={row.reason}
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

              {candidates.length === 0 ? (
                <Muted>No other location or project holds free stock of this item.</Muted>
              ) : (
                <Button type="button" variant="outline" size="sm" onClick={() => setAdding(true)}>
                  <Plus className="size-4" aria-hidden />
                  Add a borrow
                </Button>
              )}
            </div>
          </Section>

          <Section label="Buy">
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <Input
                  type="number"
                  min="0"
                  step="any"
                  value={draft.buy_qty}
                  aria-label="Buy"
                  onChange={(event) => setDraft({ ...draft, buy_qty: event.target.value })}
                  className="h-8 w-28 tabular-nums"
                />
                <span className="text-sm text-muted-foreground">To purchase</span>
              </div>
              {/* The same field the per-line card carries (AC-B11): a Buy of a discontinued
                  product needs a reason, and `lineBlockers` shuts Save without one. */}
              {draft.is_discontinued && (
                <div className="space-y-1">
                  <label
                    className="block text-2xs uppercase tracking-wide text-muted-foreground"
                    htmlFor="board-buy-reason"
                  >
                    Reason <span className="text-destructive">*</span>
                  </label>
                  <Textarea
                    id="board-buy-reason"
                    rows={2}
                    value={draft.buy_reason}
                    placeholder="In your own words"
                    onChange={(event) => setDraft({ ...draft, buy_reason: event.target.value })}
                  />
                </div>
              )}
            </div>
          </Section>

          {/* The balance the planner is editing against, and everything that stops the Save. */}
          <div className="space-y-1.5 px-4 py-3 sm:px-6">
            <div data-testid="amend-balance" className="text-sm tabular-nums break-words">
              {`${draft.open_qty} owed = ${fromMinor(balance.timelyMinor)} incoming + ${fromMinor(
                balance.reserveMinor,
              )} reserve + ${fromMinor(balance.borrowMinor)} borrow + ${fromMinor(
                balance.buyMinor,
              )} buy`}
            </div>
            {blockers.length > 0 && (
              <ul className="space-y-0.5">
                {blockers.map((blocker) => (
                  <li key={blocker} className="text-sm text-destructive break-words">
                    {blocker}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Always rendered, mandatory only when the composition actually displaces the rule:
              demanding a reason for agreeing is how a mandatory field becomes a rubber stamp. */}
          <div className="space-y-1 px-4 py-3 sm:px-6">
            <label
              className="block text-2xs uppercase tracking-wide text-muted-foreground"
              htmlFor="board-amend-reason"
            >
              Why this differs from the proposal
              {needsReason ? <span className="text-destructive"> *</span> : null}
            </label>
            <Textarea
              id="board-amend-reason"
              rows={2}
              value={reason}
              placeholder="In your own words"
              onChange={(event) => setReason(event.target.value)}
            />
          </div>
        </DialogBody>

        <DialogFooter className="shrink-0 flex-col gap-2 border-t p-4 sm:flex-row sm:justify-end sm:p-6">
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={!canSave}
            onClick={() => onSave(decisionFromAmendDraft(draft, reason))}
          >
            Save the amendment
          </Button>
        </DialogFooter>

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
                },
              ])
            }
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

/**
 * Whether the donor's position is a figure anybody stated.
 *
 * Zero on all three is how an UNKNOWN arrives (a borrow read back off a frozen decision, whose
 * donor the board is not currently offering), because the shape has no room for an absence. A
 * donor that genuinely held nothing free would never have been offered as a candidate.
 */
function statedImpact(impact: DraftBorrow['donor_impact']): boolean {
  return [impact.free_before, impact.free_after_full_borrow, impact.committed_qty].some(
    (value) => toMinor(value) !== 0,
  );
}

/** Whether a Reserve row is the line's OWN location, by id first and by code as the fallback. */
function isOwn(
  contribution: BoardContribution,
  warehouseId: string,
  location?: string | null,
): boolean {
  if (contribution.fulfilment_warehouse_id) {
    return contribution.fulfilment_warehouse_id === warehouseId;
  }
  return Boolean(location) && location === contribution.fulfilment_location;
}

/** One component, labelled the way the sheet labels it, so the two read the same. */
function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section
      data-testid="amend-section"
      className="grid gap-1 px-4 py-3 sm:grid-cols-[11rem_minmax(0,1fr)] sm:gap-3 sm:px-6"
    >
      <div className="text-2xs uppercase tracking-wide text-muted-foreground sm:pt-1.5">
        {label}
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

/** Block, not inline: two stated absences in one section must not run into one sentence. */
function Muted({ children }: { children: React.ReactNode }) {
  return <span className="block text-sm text-muted-foreground">{children}</span>;
}
