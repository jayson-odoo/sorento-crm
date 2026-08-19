'use client';

import Link from 'next/link';
import { LoaderCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import type {
  PlanningChangeDecision,
  PlanningChangeRow,
} from '../../_shared/types/planningChange.types';

const SEGMENT_BASE =
  'inline-flex h-7 items-center px-2.5 text-xs font-medium border border-input first:rounded-s-md last:rounded-e-md -ms-px first:ms-0 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

/**
 * The one decision per row (AC-R04): Accept the suggestion, Keep the plan as is, or go decide
 * it by hand on the board. Hand-rolled rather than the shared `ToggleGroup` because the third
 * segment is a real navigation `Link`, not a toggle value - `ToggleGroupItem` has no `asChild`
 * seam for that in this repo, and three plain buttons sharing one border is the whole of what
 * a segmented control is.
 *
 * Rows outside review render no control at all, per the state they are actually in:
 *  - no active decision (AC-R03) -> "Not decided", nothing to accept or keep;
 *  - `superseded` (AC-R11) -> "Superseded on the board", disabled;
 *  - `applied` / `failed` -> the outcome, disabled, with the reason on hover.
 */
export function PlanningChangeDecisionControl({
  row,
  onChange,
  pending,
  boardHref,
}: {
  row: PlanningChangeRow;
  onChange: (decision: PlanningChangeDecision) => void;
  pending?: boolean;
  boardHref: string;
}) {
  if (row.held === null && row.decision === null) {
    return <span className="text-sm text-muted-foreground">Not decided</span>;
  }

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

export default PlanningChangeDecisionControl;
