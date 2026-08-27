'use client';

import { AlertTriangle } from 'lucide-react';
import { STATUS_PILL_BASE } from '@/lib/status-pill';
import type {
  BoardContribution,
  BoardDecision,
} from '../../_shared/types/fulfilmentPlanning.types';

/**
 * How far one line has got, in one word (R6).
 *
 * ONE pill for both readings of the board - the cell breakdown's contributing-lines table and
 * the list view - because they are two views of one draft and a reader toggles between them
 * to find the same line. Two pills that merely resembled each other would drift the first
 * time either changed.
 *
 * STATUS ONLY. It used to print the whole composition ("Reserve 20 BRW-BB · Borrow 10 · Buy
 * 13") and, on a confirmed line, the revision number as well - a sentence in a fixed-width
 * cell, truncated at the term that mattered. The composition is in the expanded row and on
 * the Sourced from column beside it; what the cell is scanned for is how far the line has got.
 */
const VERDICT_PILL: Record<string, string> = {
  // Nobody has said anything about this line yet, and under R11 that is agreement: silence
  // confirms the suggestion. Grey because it is the state a board opens in, not an outcome.
  suggested: 'bg-muted text-muted-foreground',
  approved: 'bg-emerald-100 text-emerald-800',
  amended: 'bg-blue-100 text-blue-800',
  rejected: 'bg-red-100 text-red-800',
  // Outlined rather than filled: it is in the DATABASE, not a verdict given on this board,
  // and a solid green beside a solid green approval said the two were the same thing.
  confirmed: 'border border-emerald-400 text-emerald-700',
};

const VERDICT_LABEL: Record<string, string> = {
  suggested: 'Suggested',
  approved: 'Approved',
  amended: 'Amended',
  rejected: 'Rejected',
  // NO REVISION NUMBER (R6). "Confirmed rev 3" told a planner the record had been written
  // three times, which is not a question anybody asks of this column.
  confirmed: 'Confirmed',
};

export function BoardDecisionPill({
  contribution,
  decision,
}: {
  contribution: BoardContribution;
  /** This line's entry in the board's draft, or null while nobody has decided it here. */
  decision: BoardDecision | null;
}) {
  if (contribution.unplannable) {
    return (
      <span
        className="block truncate text-sm text-destructive"
        title="This line cannot be decided here: its sales order states no fulfilment location."
      >
        Needs a location
      </span>
    );
  }

  const covered = Boolean(contribution.covered) && !decision;
  const verdict = covered ? 'confirmed' : (decision?.verdict ?? 'suggested');
  // Flagged in this session's draft, or flagged on the decision that is already in the
  // database - the icon has to survive a reload, or the doubt reads as answered (R10).
  const suspected = Boolean(
    decision?.suspected_system_issue ?? contribution.decision?.suspected_system_issue,
  );

  return (
    <div className="flex min-w-0 items-center gap-1">
      <span
        data-testid={`decision-pill-${contribution.key}`}
        className={`${STATUS_PILL_BASE} normal-case ${VERDICT_PILL[verdict]}`}
        title={decision?.reason ?? contribution.decision?.amend_reason ?? ''}
      >
        {VERDICT_LABEL[verdict]}
      </span>
      {suspected ? (
        <AlertTriangle
          data-testid={`decision-flag-${contribution.key}`}
          aria-label="Flagged as a possible system problem"
          className="size-3.5 shrink-0 text-amber-600"
        />
      ) : null}
    </div>
  );
}
