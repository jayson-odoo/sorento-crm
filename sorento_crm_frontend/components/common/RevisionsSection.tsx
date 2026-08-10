'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { RevisionTimeline, type FormRevisionEntry } from './RevisionTimeline';

/**
 * The "Revisions" panel on an office detail page (UAC H2 / H2a).
 *
 * ALWAYS rendered, with an explicit empty state when there is nothing to show -
 * per the CRUD UX standard a section is never hidden on missing data. It is an
 * ADDITION: attachments, chat and every existing section keep the placement they
 * have today (H2a), so this mounts as its own panel and moves nothing.
 */
export interface RevisionsSectionProps {
  entries: FormRevisionEntry[] | undefined;
  isLoading?: boolean;
  isError?: boolean;
  /** Office side shows which stage each revision voided (UAC H3). */
  showVoidedStage?: boolean;
}

export function RevisionsSection({
  entries,
  isLoading = false,
  isError = false,
  showVoidedStage = true,
}: RevisionsSectionProps) {
  // The original submission on its own is not lineage - that is the empty state
  // (UAC H2). A second entry IS lineage even at revision 0, because a resubmit
  // after rejection writes a history row without consuming a revision (UAC C4).
  const timelineEntries = entries ?? [];
  const hasLineage =
    timelineEntries.length > 1 ||
    timelineEntries.some((entry) => (entry.revision_no ?? 0) > 0);

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
          <RevisionTimeline entries={timelineEntries} showVoidedStage={showVoidedStage} />
        )}
      </CardContent>
    </Card>
  );
}
