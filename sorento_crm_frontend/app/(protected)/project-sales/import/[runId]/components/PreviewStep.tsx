'use client';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useProjectImportMutations } from '../../../_shared/hooks/useProjectImport';
import type {
  ProjectImportKind,
  ProjectImportRun,
} from '../../../_shared/types/projectImport.types';
import { OutcomeTiles, ReportRowsGrid, blockingKind } from './ReportRows';

/** The Preview step (AC-PI-47): the import, run and rolled back, with Import as the one action. */
export function PreviewStep({
  run,
  onOpenLine,
  className,
}: {
  run: ProjectImportRun;
  onOpenLine: (kind: ProjectImportKind) => void;
  className?: string;
}) {
  const { importRun, preview } = useProjectImportMutations(run.id);
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
        <Button variant="outline" onClick={() => preview.mutate()} disabled={preview.isPending}>
          Preview again
        </Button>
        <Button onClick={() => importRun.mutate()} disabled={importRun.isPending}>
          Import
        </Button>
      </div>
      <ReportRowsGrid
        run={run}
        listingKey="projects.import.view::preview-rows"
        onRowClick={(row) => {
          if (row.outcome !== 'needs_review') return;
          const kind = blockingKind(row);
          if (kind) onOpenLine(kind);
        }}
      />
    </div>
  );
}

export default PreviewStep;
