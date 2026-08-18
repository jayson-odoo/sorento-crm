'use client';

import * as React from 'react';
import { AlertTriangle, Check, Pencil, X } from 'lucide-react';
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
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { formatDateInMalaysia } from '@/lib/helpers';
import { amendNeedsReason } from '../../_shared/lib/fulfilmentBoard';
import type {
  BoardCell,
  BoardContribution,
  BoardDecision,
  BoardDraft,
} from '../../_shared/types/fulfilmentPlanning.types';

/**
 * The breakdown behind one cell, and the decision on it (PLAN 13, journey step 4).
 *
 * The columns are the captain's own list: which sales order, which customer, which project,
 * the quantity, and where it is proposed to be sourced from. Each row then owes the same
 * explanation the per-line card owes - "23 open = 0 incoming + 0 reserve + 0 borrow + 23 buy"
 * - which is the balance line under every row's sources.
 *
 * Approve / amend / reject are per row, and they write into the board's DRAFT, not into the
 * database (13.4): the decision that is persisted is still the whole sales order's, and the
 * order is what commits. Nothing here claims a cell committed anything.
 *
 * A hand-built list rather than a shared DataGrid on purpose: each row carries a two-line
 * source explanation, a balance line and, while it is being amended, a quantity input and a
 * reason box. That is a record card, not a table row, and forcing it into fixed-height cells
 * would truncate exactly the reasoning the row exists to show.
 */
export function BoardCellBreakdownDialog({
  cell,
  bucketLabel,
  draft,
  onDecide,
  onClose,
}: {
  cell: BoardCell;
  bucketLabel: string;
  draft: BoardDraft;
  onDecide: (key: string, decision: BoardDecision | null) => void;
  onClose: () => void;
}) {
  const decided = cell.contributions.filter((entry) => draft[entry.key]).length;

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[85vh] w-full overflow-hidden p-0 sm:max-w-4xl">
        <DialogHeader className="border-b p-4 sm:p-6">
          <DialogTitle className="min-w-0 break-words">
            {`${cell.item_code} · ${bucketLabel}`}
          </DialogTitle>
          <DialogDescription className="min-w-0 break-words">
            {`${cell.total_qty} across ${cell.contributions.length} line${
              cell.contributions.length === 1 ? '' : 's'
            }, ${decided} decided`}
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="max-h-[60vh] space-y-3 overflow-y-auto p-4 sm:p-6">
          {/* The source strip again, because the dialog has to stand on its own: a reader who
              opened it from a cell they can no longer see still needs to know one cell can
              draw on several locations. */}
          <div className="flex flex-wrap gap-1.5">
            {cell.locations.map((entry) => (
              <span
                key={entry.location ?? '__none__'}
                className={`${STATUS_PILL_BASE} normal-case ${statusPillClass(
                  entry.location ? 'draft' : 'rejected',
                )}`}
              >
                {`${entry.location ?? 'No location'} · ${entry.qty}`}
              </span>
            ))}
          </div>

          {cell.contributions.map((contribution) => (
            <ContributionRow
              key={contribution.key}
              contribution={contribution}
              decision={draft[contribution.key] ?? null}
              onDecide={(decision) => onDecide(contribution.key, decision)}
            />
          ))}
        </DialogBody>

        <DialogFooter className="gap-2 border-t p-4 sm:p-6">
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** The verbs, as pills, so a decided row reads at a glance in a long list. */
const VERDICT_PALETTE: Record<string, string> = {
  approved: 'active',
  amended: 'submitted',
  rejected: 'rejected',
};

function ContributionRow({
  contribution,
  decision,
  onDecide,
}: {
  contribution: BoardContribution;
  decision: BoardDecision | null;
  onDecide: (decision: BoardDecision | null) => void;
}) {
  const [amending, setAmending] = React.useState(false);
  const proposedReserve = contribution.sources
    .filter((source) => source.kind === 'reserve')
    .reduce((total, source) => total + Number.parseFloat(source.qty || '0'), 0);
  const [reserveQty, setReserveQty] = React.useState(String(proposedReserve));
  const [reason, setReason] = React.useState('');

  const needsReason = amendNeedsReason(contribution, reserveQty);
  const canSaveAmend = !needsReason || reason.trim().length > 0;

  return (
    <article className="rounded-lg border border-border">
      <header className="flex flex-col gap-1 border-b border-border px-3 py-2.5 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium" title={contribution.so_number}>
            {contribution.so_number}
            <span className="text-muted-foreground">{` · line ${contribution.line_no}`}</span>
          </div>
          <div
            className="truncate text-sm text-muted-foreground"
            title={contribution.customer_name ?? ''}
          >
            {contribution.customer_name || 'Customer not recorded'}
          </div>
          <div
            className="truncate text-xs text-muted-foreground"
            title={contribution.project_label ?? ''}
          >
            {contribution.project_label || 'Not named on the order'}
          </div>
        </div>
        <div className="shrink-0 text-sm tabular-nums sm:text-end">
          <div>
            <span className="font-medium">{contribution.qty}</span>
            <span className="text-muted-foreground"> owed</span>
          </div>
          <div className="text-xs text-muted-foreground">
            {contribution.required_date
              ? formatDateInMalaysia(contribution.required_date)
              : 'No required date'}
          </div>
          <div className="text-xs text-muted-foreground">
            {contribution.fulfilment_location ?? 'No location'}
          </div>
        </div>
      </header>

      {/* Why this row is where it is in the queue. A ranking nobody can inspect is a ranking
          nobody will trust, so the score comes with the factors that produced it (PLAN 13.5). */}
      <div className="space-y-1 border-b border-border px-3 py-2.5">
        <div className="flex flex-wrap items-baseline gap-2">
          <span className="text-2xs uppercase tracking-wide text-muted-foreground">Rank</span>
          <span className="text-sm font-medium tabular-nums">
            {contribution.rank_score.toFixed(2)}
          </span>
        </div>
        <div className="flex flex-wrap gap-1">
          {contribution.rank_factors.map((factor) => (
            <span
              key={factor.key}
              className={`rounded px-1 text-[10px] ${
                factor.present
                  ? 'bg-muted text-muted-foreground'
                  : 'bg-muted/50 text-muted-foreground/70 line-through'
              }`}
              title={
                factor.present
                  ? `${factor.key}: value ${factor.value?.toFixed(2)}, weight ${factor.weight}`
                  : `${factor.key}: no value, so it is dropped from the score entirely rather than counted as zero`
              }
            >
              {factor.present
                ? `${factor.key} ${factor.value?.toFixed(2)} x${factor.weight}`
                : `${factor.key} absent`}
            </span>
          ))}
        </div>
      </div>

      <div className="space-y-1.5 border-b border-border px-3 py-2.5">
        <div className="text-2xs uppercase tracking-wide text-muted-foreground">
          Sourced from
        </div>
        {contribution.sources.map((source, index) => (
          <div key={`${source.kind}-${index}`} className="space-y-0.5">
            <div className="text-sm tabular-nums">
              <span className="font-medium">{sourceLabel(source.kind)}</span>
              {` ${source.qty}`}
              {source.location ? (
                <span className="text-muted-foreground">{` at ${source.location}`}</span>
              ) : null}
            </div>
            <p className="text-sm text-muted-foreground break-words">{source.reason}</p>
          </div>
        ))}

        {/* The same arithmetic the per-line card shows, so a row here explains itself to the
            same standard: what is owed, and what meets it. */}
        <div className="text-sm tabular-nums break-words">{balanceLine(contribution)}</div>

        {contribution.contested && (
          <div className="flex items-start gap-1.5 text-sm text-amber-700">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            {/* Deliberately not "a higher-ranked line took it": the stock may equally have gone
                to an EARLIER BUCKET, and the top-ranked row of a cell can be contested for that
                reason. Naming the wrong cause is worse than naming none. */}
            <span>
              Free stock at this location was already committed to earlier demand, so this line is
              bought.
            </span>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 px-3 py-2.5">
        {contribution.unplannable ? (
          <span className="text-sm text-destructive break-words">
            This line cannot be decided here: its sales order states no fulfilment location.
          </span>
        ) : decision && !amending ? (
          <>
            <span
              className={`${STATUS_PILL_BASE} normal-case ${statusPillClass(
                VERDICT_PALETTE[decision.verdict],
              )}`}
            >
              {decision.verdict === 'approved'
                ? 'Approved'
                : decision.verdict === 'amended'
                  ? `Amended to reserve ${decision.reserve_qty}`
                  : 'Rejected'}
            </span>
            {decision.reason ? (
              <span className="min-w-0 text-sm text-muted-foreground break-words">
                {decision.reason}
              </span>
            ) : null}
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => onDecide(null)}
            >
              Undo
            </Button>
          </>
        ) : amending ? (
          <div className="w-full space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <label className="text-2xs uppercase tracking-wide text-muted-foreground">
                Reserve
              </label>
              <Input
                type="number"
                min="0"
                step="any"
                value={reserveQty}
                aria-label={`Reserve for ${contribution.so_number} line ${contribution.line_no}`}
                onChange={(event) => setReserveQty(event.target.value)}
                className="h-8 w-28 tabular-nums"
              />
              <span className="text-sm text-muted-foreground">
                {contribution.fulfilment_location}
              </span>
            </div>
            {needsReason && (
              <div className="space-y-1">
                <label
                  className="block text-2xs uppercase tracking-wide text-muted-foreground"
                  htmlFor={`amend-reason-${contribution.key}`}
                >
                  Reason <span className="text-destructive">*</span>
                </label>
                <Textarea
                  id={`amend-reason-${contribution.key}`}
                  rows={2}
                  value={reason}
                  placeholder="In your own words"
                  onChange={(event) => setReason(event.target.value)}
                />
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                disabled={!canSaveAmend}
                onClick={() => {
                  onDecide({
                    verdict: 'amended',
                    reserve_qty: reserveQty,
                    reason: reason.trim() || undefined,
                  });
                  setAmending(false);
                }}
              >
                Save the amendment
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setAmending(false)}
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <>
            <Button
              type="button"
              size="sm"
              onClick={() => onDecide({ verdict: 'approved' })}
            >
              <Check className="size-4" aria-hidden />
              Approve
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => setAmending(true)}
            >
              <Pencil className="size-4" aria-hidden />
              Amend
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() =>
                onDecide({
                  verdict: 'rejected',
                  reason: 'Rejected on the planning board.',
                })
              }
            >
              <X className="size-4" aria-hidden />
              Reject
            </Button>
          </>
        )}
      </div>
    </article>
  );
}

function sourceLabel(kind: BoardContribution['sources'][number]['kind']): string {
  if (kind === 'reserve') return 'Reserve';
  if (kind === 'timely_spo') return 'Incoming';
  if (kind === 'buy') return 'Buy';
  return 'Cannot be sourced';
}

/** "202 owed = 202 reserve + 0 buy", in the per-line card's own shape. */
function balanceLine(contribution: BoardContribution): string {
  const of = (kind: string) =>
    contribution.sources
      .filter((source) => source.kind === kind)
      .reduce((total, source) => total + Number.parseFloat(source.qty || '0'), 0);
  return `${contribution.qty} owed = ${of('reserve')} reserve + ${of('timely_spo')} incoming + ${of('buy')} buy`;
}
