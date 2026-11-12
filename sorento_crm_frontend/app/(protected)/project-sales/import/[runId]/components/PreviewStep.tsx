'use client';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useHasPermission } from '@/hooks/usePermissions';
import { RUN_PERMISSION, useProjectImportMutations } from '../../../_shared/hooks/useProjectImport';
import type {
  ProjectImportKind,
  ProjectImportLineKey,
  ProjectImportRun,
} from '../../../_shared/types/projectImport.types';
import { OutcomeTiles, ReportRowsGrid } from './ReportRows';

/**
 * The Preview step (AC-PI-47): the import, run and rolled back. Import itself is the page
 * header's one primary button (mock E), so this body has none.
 */
export function PreviewStep({
  run,
  onOpenLine,
  className,
}: {
  run: ProjectImportRun;
  onOpenLine: (kind: ProjectImportKind, line?: ProjectImportLineKey | null) => void;
  className?: string;
}) {
  const canRun = useHasPermission(RUN_PERMISSION);
  const { preview } = useProjectImportMutations(run.id);
  const review = run.preview_counts?.needs_review ?? 0;

  return (
    <div className={cn('space-y-4', className)}>
      <OutcomeTiles counts={run.preview_counts} />
      <div className="flex flex-wrap items-center justify-end gap-2">
        {review > 0 && (
          <span className="me-auto text-sm text-muted-foreground">
            {`${review} ${review === 1 ? 'row needs' : 'rows need'} review and will be left out.`}
          </span>
        )}
        {canRun && (
          <Button variant="outline" onClick={() => preview.mutate()} disabled={preview.isPending}>
            Preview again
          </Button>
        )}
      </div>
      <ReportRowsGrid
        run={run}
        listingKey="projects.import.view::preview-rows"
        onRowClick={(row) => {
          // The server names the Values tab that unblocks the row (`blocking_kind`).
          if (row.outcome === 'needs_review' && row.blocking_kind) {
            onOpenLine(row.blocking_kind, row.blocking_line ?? null);
          }
        }}
      />
    </div>
  );
}

export default PreviewStep;
