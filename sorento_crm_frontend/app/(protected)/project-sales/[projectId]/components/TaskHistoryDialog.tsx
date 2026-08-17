'use client';

import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { useTaskHistory } from '../../_shared/hooks/useProjects';
import type { ProjectTask } from '../../_shared/types/project.types';

/**
 * What happened to this task, read from the audit trail rather than a second log.
 *
 * The server resolves user and status ids to labels before sending, so nothing here
 * shows a UUID. Fields the trail records but nobody reads (timestamps the row keeps
 * anyway, sort order) are filtered out server-side so the timeline stays legible.
 */
export function TaskHistoryDialog({
  projectId,
  task,
  onDone,
}: {
  projectId: string;
  task: ProjectTask;
  onDone: () => void;
}) {
  const history = useTaskHistory(projectId, task.id);
  const entries = history.data ?? [];

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-lg overflow-hidden">
        <DialogHeader>
          <DialogTitle className="truncate" title={task.name}>
            History of &quot;{task.name}&quot;
          </DialogTitle>
          <DialogDescription>Every recorded change, newest first.</DialogDescription>
        </DialogHeader>

        <DialogBody className="max-h-[65vh] overflow-y-auto">
          {history.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : history.isError ? (
            <p className="text-sm text-destructive">
              {history.error instanceof Error
                ? history.error.message
                : 'History could not be loaded.'}
            </p>
          ) : entries.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border px-6 py-8 text-center">
              <h3 className="text-sm font-semibold">Nothing recorded yet</h3>
              <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
                Changes to the status, assignee, dates and the stuck reason land here as
                they happen.
              </p>
            </div>
          ) : (
            <ol className="space-y-3">
              {entries.map((entry, index) => (
                <li key={`${entry.at}-${index}`} className="flex gap-3">
                  <div className="mt-1.5 size-2 shrink-0 rounded-full bg-primary" aria-hidden />
                  <div className="min-w-0 space-y-0.5">
                    <p className="text-sm">
                      <span className="font-medium">{entry.actor_name ?? 'System'}</span>{' '}
                      {describe(entry)}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {formatDateTimeInMalaysia(entry.at)}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

function describe(entry: {
  action: string;
  field?: string | null;
  from_value?: string | null;
  to_value?: string | null;
}): string {
  if (entry.action === 'created') return 'created this task';
  if (entry.action === 'deleted') return 'deleted this task';
  const field = entry.field ?? 'a field';
  if (entry.from_value && entry.to_value) {
    return `changed ${field} from ${entry.from_value} to ${entry.to_value}`;
  }
  if (entry.to_value) return `set ${field} to ${entry.to_value}`;
  if (entry.from_value) return `cleared ${field} (was ${entry.from_value})`;
  return `changed ${field}`;
}
