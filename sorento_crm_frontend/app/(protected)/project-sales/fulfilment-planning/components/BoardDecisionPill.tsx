'use client';

import { AlertTriangle } from 'lucide-react';
import { STATUS_PILL_BASE } from '@/lib/status-pill';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import {
  Popover,
  PopoverContent,
  PopoverPortal,
  PopoverTrigger,
} from '@/components/ui/popover';
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
 *
 * SAVED, NOT APPROVED/AMENDED (S4, R-F, markup 2 Sep): once a decision has been SAVED - here,
 * on another device, or by another planner - the pill reads the plain word "Saved" rather
 * than which of the two verbs produced it. Approved vs amended is a fact for the expanded
 * row, which already shows the composition; the cell answers "has this been dealt with",
 * and "Saved" answers it in one word the same way "Suggested" and "Confirmed" do. A
 * REJECTED decision keeps its own label - it commits nothing, and "Saved" would say the
 * opposite of what happened to it.
 */
const VERDICT_PILL: Record<string, string> = {
  // Nobody has said anything about this line yet, and under R11 that is agreement: silence
  // confirms the suggestion. Grey because it is the state a board opens in, not an outcome.
  suggested: 'bg-muted text-muted-foreground',
  saved: 'bg-emerald-100 text-emerald-800',
  rejected: 'bg-red-100 text-red-800',
  // Outlined rather than filled: it is in the DATABASE, not a verdict given on this board,
  // and a solid green beside a solid green approval said the two were the same thing.
  confirmed: 'border border-emerald-400 text-emerald-700',
  // S4/AC-4.4: the line was saved against a suggestion the engine no longer makes. Amber,
  // the same warning tone the rest of the board uses for "look at this before you trust it".
  stale: 'bg-amber-100 text-amber-800',
};

const VERDICT_LABEL: Record<string, string> = {
  suggested: 'Suggested',
  saved: 'Saved',
  rejected: 'Rejected',
  // NO REVISION NUMBER (R6). "Confirmed rev 3" told a planner the record had been written
  // three times, which is not a question anybody asks of this column.
  confirmed: 'Confirmed',
  stale: 'Suggestion changed',
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
  // What was saved, from wherever it came: THIS session's own click first, the server's own
  // row otherwise - a fresh page load has not run the seeding effect yet on the very first
  // paint, and the pill reads right either way rather than flashing Suggested for a frame.
  const draftSource = decision ?? contribution.draft?.decision ?? null;
  const stale = !covered && Boolean(contribution.draft?.stale);

  // N6 (code review round 3): `confirmed > rejected > stale > saved`, the same order
  // `confirmSummaryFor` (`_shared/lib/fulfilmentBoard.ts`) counts by. A REJECTED verdict on
  // a stale line commits nothing either way, and "Rejected" is what the planner actually did
  // about it - reading "Suggestion changed" instead would say something happened that had
  // already been answered.
  let verdict: string;
  if (covered) {
    verdict = 'confirmed';
  } else if (draftSource?.verdict === 'rejected') {
    verdict = 'rejected';
  } else if (stale) {
    verdict = 'stale';
  } else if (draftSource) {
    verdict = 'saved';
  } else {
    verdict = 'suggested';
  }

  // Flagged in this session's draft, or - while nobody has decided it here - flagged on the
  // decision that is already in the database: the icon has to survive a reload, or the doubt
  // reads as answered (R10).
  //
  // THE DRAFT WINS OUTRIGHT, false included. A planner who unticks the box on a confirmed
  // line has answered the question; falling through to the frozen `true` behind it left the
  // warning on screen while the body about to be posted said `false`, so the row and the
  // write disagreed about the one fact the flag exists to carry.
  const suspected = draftSource
    ? Boolean(draftSource.suspected_system_issue)
    : Boolean(contribution.decision?.suspected_system_issue);

  const savedBy = contribution.draft?.saved_by;
  const savedAt = contribution.draft?.saved_at;
  const pill = (
    <span
      data-testid={`decision-pill-${contribution.key}`}
      className={`${STATUS_PILL_BASE} normal-case ${VERDICT_PILL[verdict]}`}
      title={decision?.reason ?? contribution.decision?.amend_reason ?? ''}
    >
      {VERDICT_LABEL[verdict]}
    </span>
  );

  return (
    <div className="flex min-w-0 items-center gap-1">
      {/* Who saved this, and when (AC-4.2: "the pill reads 'Saved' only, the saver's name
          is in the popover"). Only wrapped in a popover once there is something to say - a
          plain `title` is not reachable at 375px, so a small `Popover` carries it instead
          (the `BoardRankPopover` shape). */}
      {savedBy ? (
        <Popover>
          <PopoverTrigger
            asChild
            // Stops here so a click meant for the popover does not also toggle the row this
            // pill sits inside (the board grid and the contributing-lines table both expand
            // on a row click) - the same reason `BoardRankPopover`'s own trigger stops it.
            onClick={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              aria-label={`Saved by ${savedBy}`}
              data-testid={`decision-saved-by-${contribution.key}`}
              className="rounded-sm outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
            >
              {pill}
            </button>
          </PopoverTrigger>
          <PopoverPortal>
            <PopoverContent
              align="start"
              className="w-auto max-w-[92vw] px-3 py-2 text-xs"
              onOpenAutoFocus={(event) => event.preventDefault()}
            >
              {`Saved by ${savedBy}${savedAt ? ` · ${formatDateTimeInMalaysia(savedAt)}` : ''}`}
            </PopoverContent>
          </PopoverPortal>
        </Popover>
      ) : (
        pill
      )}
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
