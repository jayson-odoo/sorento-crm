'use client';

import * as React from 'react';
import Link from 'next/link';
import { LoaderCircle, Pencil } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { confirmLinesFor } from '../../_shared/lib/fulfilmentBoard';
import type {
  BoardDecision,
  ConfirmLine,
} from '../../_shared/types/fulfilmentPlanning.types';
import type {
  PlanningChangeDecision,
  PlanningChangeRow,
} from '../../_shared/types/planningChange.types';
import { BoardAmendDialog } from '../../fulfilment-planning/components/BoardAmendDialog';

const SEGMENT_BASE =
  'inline-flex h-7 items-center px-2.5 text-xs font-medium border border-input first:rounded-s-md last:rounded-e-md -ms-px first:ms-0 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

/**
 * The one decision per row (AC-R04).
 *
 * A row carrying a `proposal` (`replan`/`qty_up` - always the case for either, section 0) gets a
 * DIFFERENT three-way control than a row acting on an existing decision: `Confirm as proposed` |
 * `Amend` | `Leave on the board`. This is the captain's own fix, live 19 August 2026 - "I can't
 * really amend also right to set the borrow, clicking accept here has no effect": a replan row's
 * old `Accept` recorded a decision Apply never executed, because Apply always excluded a
 * `replan`-suggested line from the confirmation regardless of what was accepted. `Confirm`/`Amend`
 * compose a real `ConfirmLine` - the SAME shape and, for `Amend`, the SAME editor
 * (`BoardAmendDialog`) the board's own Confirm posts - so accepting a replan row here actually
 * writes something at Apply.
 *
 * A row with no `proposal` keeps the original Accept / Keep as is / Open on the board control,
 * unchanged: it is acting on an EXISTING decision, not composing a fresh one.
 *
 * Rows outside review render no control at all, per the state they are actually in:
 * - no active decision and no proposal -> "Not decided" (should not occur in practice: every
 *    changed planned line without a decision is `replan` and therefore carries a proposal, but
 *    the fallback stays honest if the board ever fails to build one);
 * - `superseded` (AC-R11) -> "Superseded on the board", disabled;
 * - `applied` / `failed` -> the outcome, disabled, with the reason on hover.
 */
export function PlanningChangeDecisionControl({
  row,
  onChange,
  pending,
  boardHref,
}: {
  row: PlanningChangeRow;
  onChange: (decision: PlanningChangeDecision, composition?: ConfirmLine) => void;
  pending?: boolean;
  boardHref: string;
}) {
  if (row.applied_state === 'superseded') {
    return (
      <span
        className="text-sm text-muted-foreground"
        title={row.applied_reason ?? 'A later board edit replaced this suggestion.'}
      >
        Superseded on the board
      </span>
    );
  }

  if (row.applied_state === 'applied') {
    return (
      <span className="text-sm font-medium text-emerald-700" title={row.why}>
        Applied
      </span>
    );
  }

  if (row.applied_state === 'failed') {
    return (
      <span
        className="text-sm font-medium text-destructive"
        title={row.applied_reason ?? 'This order could not be written.'}
      >
        Failed
      </span>
    );
  }

  if (row.proposal) {
    return (
      <ComposeControl row={row} onChange={onChange} pending={pending} />
    );
  }

  if (row.held === null && row.decision === null) {
    return <span className="text-sm text-muted-foreground">Not decided</span>;
  }

  return (
    <div className="inline-flex items-center">
      {pending && <LoaderCircle className="me-1.5 size-3.5 animate-spin text-muted-foreground" />}
      <div className="inline-flex" role="group" aria-label={`Decision for line ${row.line_no}`}>
        <button
          type="button"
          disabled={pending}
          onClick={() => onChange('accept')}
          className={cn(
            SEGMENT_BASE,
            row.decision === 'accept'
              ? 'bg-primary text-primary-foreground border-primary'
              : 'bg-background hover:bg-muted',
          )}
        >
          Accept
        </button>
        <button
          type="button"
          disabled={pending}
          onClick={() => onChange('keep')}
          className={cn(
            SEGMENT_BASE,
            row.decision === 'keep'
              ? 'bg-primary text-primary-foreground border-primary'
              : 'bg-background hover:bg-muted',
          )}
        >
          Keep as is
        </button>
        <Link
          href={boardHref}
          onClick={() => onChange('board')}
          className={cn(
            SEGMENT_BASE,
            row.decision === 'board'
              ? 'bg-primary text-primary-foreground border-primary'
              : 'bg-background hover:bg-muted',
          )}
        >
          Open on the board
        </Link>
      </div>
    </div>
  );
}

/** `Confirm as proposed` | `Amend` | `Leave on the board`, for a row carrying a `proposal`. */
function ComposeControl({
  row,
  onChange,
  pending,
}: {
  row: PlanningChangeRow;
  onChange: (decision: PlanningChangeDecision, composition?: ConfirmLine) => void;
  pending?: boolean;
}) {
  const [amending, setAmending] = React.useState(false);
  const proposal = row.proposal;
  if (!proposal) return null;

  const handleAmendSave = (decision: BoardDecision) => {
    const composed = confirmLinesFor(
      [proposal],
      proposal.sales_order_id,
      { [proposal.key]: decision },
    )[0];
    if (!composed) {
      toast.error(
        'This composition could not be posted - check the warehouse and the Buy reason.',
      );
      return;
    }
    onChange('amend', composed);
    setAmending(false);
  };

  return (
    <div className="space-y-1">
      <div className="inline-flex items-center">
        {pending && (
          <LoaderCircle className="me-1.5 size-3.5 animate-spin text-muted-foreground" />
        )}
        <div className="inline-flex" role="group" aria-label={`Decision for line ${row.line_no}`}>
          <button
            type="button"
            disabled={pending}
            onClick={() => onChange('confirm')}
            className={cn(
              SEGMENT_BASE,
              row.decision === 'confirm'
                ? 'bg-primary text-primary-foreground border-primary'
                : 'bg-background hover:bg-muted',
            )}
          >
            Confirm as proposed
          </button>
          <button
            type="button"
            disabled={pending}
            onClick={() => setAmending(true)}
            className={cn(
              SEGMENT_BASE,
              row.decision === 'amend'
                ? 'bg-primary text-primary-foreground border-primary'
                : 'bg-background hover:bg-muted',
            )}
          >
            Amend
          </button>
          <button
            type="button"
            disabled={pending}
            onClick={() => onChange(null)}
            className={cn(
              SEGMENT_BASE,
              row.decision === null
                ? 'bg-primary text-primary-foreground border-primary'
                : 'bg-background hover:bg-muted',
            )}
          >
            Leave on the board
          </button>
        </div>
      </div>
      {row.decision === 'amend' && row.composition && (
        <p className="flex items-start gap-1 text-xs text-muted-foreground">
          <span className="min-w-0 break-words">
            {`Amended: ${compositionSummary(row.composition, row)}`}
          </span>
          <button
            type="button"
            onClick={() => setAmending(true)}
            className="inline-flex shrink-0 items-center gap-0.5 text-primary hover:underline"
          >
            <Pencil className="size-3" aria-hidden />
            Edit
          </button>
        </p>
      )}
      {amending && (
        <BoardAmendDialog
          contribution={proposal}
          onCancel={() => setAmending(false)}
          onSave={handleAmendSave}
        />
      )}
    </div>
  );
}

/**
 * The warehouse a `ConfirmLine` component addresses, by CODE (no UUIDs in the UI) - read off
 * whatever this row already knows a warehouse's code from: the proposal's own sources and
 * borrow candidates, the line's own fulfilment location, or what an active decision already
 * held there. A warehouse none of those name still renders, just without a code.
 */
function warehouseLabels(row: PlanningChangeRow): Map<string, string> {
  const map = new Map<string, string>();
  for (const source of row.proposal?.sources ?? []) {
    if (source.warehouse_id && source.location) map.set(source.warehouse_id, source.location);
  }
  for (const candidate of row.proposal?.borrow_candidates ?? []) {
    if (candidate.warehouse_id && candidate.warehouse_code) {
      map.set(candidate.warehouse_id, candidate.warehouse_code);
    }
  }
  if (row.proposal?.fulfilment_warehouse_id && row.proposal.fulfilment_location) {
    map.set(row.proposal.fulfilment_warehouse_id, row.proposal.fulfilment_location);
  }
  for (const reserve of row.held?.reserve ?? []) {
    if (reserve.warehouse_id) map.set(reserve.warehouse_id, reserve.location);
  }
  for (const borrow of row.held?.borrow ?? []) {
    if (borrow.warehouse_id) map.set(borrow.warehouse_id, borrow.location);
  }
  return map;
}

/** `Reserve 40 at BRW-BB · Borrow 20 from MWH-IB · Buy 6`, what Apply will actually post. */
function compositionSummary(composition: ConfirmLine, row: PlanningChangeRow): string {
  const labels = warehouseLabels(row);
  const parts: string[] = [];
  if (composition.timely_spo_qty && composition.timely_spo_qty !== '0') {
    parts.push(`Incoming ${composition.timely_spo_qty}`);
  }
  const reserve = composition.reserve.filter((item) => item.qty !== '0');
  if (reserve.length > 0) {
    parts.push(
      `Reserve ${reserve
        .map((item) => `${item.qty} at ${labels.get(item.warehouse_id) ?? 'its location'}`)
        .join(' + ')}`,
    );
  }
  const borrow = composition.borrow.filter((item) => item.qty !== '0');
  if (borrow.length > 0) {
    parts.push(
      `Borrow ${borrow
        .map((item) => `${item.qty} from ${labels.get(item.warehouse_id) ?? 'a donor'}`)
        .join(' + ')}`,
    );
  }
  if (composition.buy_qty && composition.buy_qty !== '0') {
    parts.push(`Buy ${composition.buy_qty}`);
  }
  return parts.length > 0 ? parts.join(' · ') : 'nothing';
}

export default PlanningChangeDecisionControl;
