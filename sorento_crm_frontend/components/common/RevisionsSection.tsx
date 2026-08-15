'use client';

import { type ReactNode } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { hasRevisionLineage } from '@/lib/revision-export';
import { RevisionTimeline, type FormRevisionEntry } from './RevisionTimeline';

/**
 * The body of the "Revisions" TAB on an office detail page (UAC H2 / H2a).
 *
 * ALWAYS rendered while the type has revisions on, with an explicit empty state
 * when there is nothing to show - per the CRUD UX standard a section is never
 * hidden on missing data. Round 6 moved it out of the Details stack and into its
 * own tab so the lineage is one click away instead of a scroll past the whole
 * form; every OTHER section keeps the placement it has today (H2a).
 */
export interface RevisionsSectionProps {
  entries: FormRevisionEntry[] | undefined;
  isLoading?: boolean;
  isError?: boolean;
  /** Office side shows which stage each revision voided (UAC H3). */
  showVoidedStage?: boolean;
  /** Per-entry actions (export this version), supplied by the mounting page. */
  entryActions?: (entry: FormRevisionEntry) => ReactNode;
}

export function RevisionsSection({
  entries,
  isLoading = false,
  isError = false,
  showVoidedStage = true,
  entryActions,
}: RevisionsSectionProps) {
  // The original submission on its own is not lineage - that is the empty state
  // (UAC H2). A second entry IS lineage even at revision 0, because a resubmit
  // after rejection writes a history row without consuming a revision (UAC C4).
  // Same rule the exports apply, read from one place.
  const timelineEntries = entries ?? [];
  const hasLineage = hasRevisionLineage(timelineEntries);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Revisions</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 2 }).map((_, i) => (
              <div key={i} className="flex gap-3">
                <Skeleton className="mt-1 size-3.5 rounded-full" />
                <div className="flex-1 space-y-1">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-3 w-48" />
                </div>
              </div>
            ))}
          </div>
        ) : isError ? (
          <p className="text-sm text-muted-foreground">Could not load revisions.</p>
        ) : !hasLineage ? (
          <p className="text-sm text-muted-foreground">
            No revisions - this is the original submission.
          </p>
        ) : (
          <RevisionTimeline
            entries={timelineEntries}
            showVoidedStage={showVoidedStage}
            entryActions={entryActions}
          />
        )}
      </CardContent>
    </Card>
  );
}
