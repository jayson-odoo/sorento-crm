'use client';

import * as React from 'react';
import { History, Package, Pencil, Plus, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { formatDateInMalaysia } from '@/lib/helpers';
import { useSampleMutations, useSamples } from '../../_shared/hooks/useProjects';
import type { Project, ProjectSample } from '../../_shared/types/project.types';
import { SampleDialog } from './SampleDialog';

/**
 * Samples sent to the developer, each against the version it was priced from (AC-F1).
 *
 * The version is shown on every row, not tucked away: a sample approved against v1 when
 * the customer now holds v3 is the single most expensive thing to discover late, and
 * "superseded" is stated rather than implied by a missing badge.
 */
export function SamplesPanel({ project }: { project: Project }) {
  const samples = useSamples(project.id);
  const { remove } = useSampleMutations(project.id);

  const [creating, setCreating] = React.useState(false);
  const [editing, setEditing] = React.useState<ProjectSample | null>(null);
  const [deleting, setDeleting] = React.useState<ProjectSample | null>(null);

  const rows = React.useMemo(() => samples.data ?? [], [samples.data]);
  const supersededCount = rows.filter((row) => !row.is_version_current).length;

  return (
    <>
      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <CardTitle className="text-sm">Sample submissions</CardTitle>
          </div>
          {project.can_edit && (
            <Button type="button" size="sm" onClick={() => setCreating(true)}>
              <Plus className="size-4" aria-hidden />
              Record a sample
            </Button>
          )}
        </CardHeader>

        <CardContent className="space-y-3">
          {supersededCount > 0 && (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Badge variant="secondary" className="gap-1">
                <History className="size-3" aria-hidden />
                {`${supersededCount} against a superseded version`}
              </Badge>
            </div>
          )}

          {samples.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : samples.isError ? (
            <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-8 text-center">
              <h3 className="text-sm font-semibold text-destructive">
                Samples could not be loaded
              </h3>
              <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                {samples.error instanceof Error ? samples.error.message : 'Try again shortly.'}
              </p>
            </div>
          ) : rows.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border px-6 py-10 text-center">
              <h3 className="text-sm font-semibold">No samples sent yet</h3>
              <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                A sample has to name the quotation version it was priced from, so price a
                scope first if nothing is quoted.
              </p>
              {project.can_edit && (
                <Button type="button" className="mt-4" onClick={() => setCreating(true)}>
                  <Plus className="size-4" aria-hidden />
                  Record the first sample
                </Button>
              )}
            </div>
          ) : (
            <ul className="space-y-2">
              {rows.map((sample) => (
                <li
                  key={sample.id}
                  className="flex flex-col gap-2 rounded-lg border border-border px-3 py-2.5 sm:flex-row sm:items-start"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="flex items-center gap-1 text-sm font-medium">
                        <Package className="size-3.5 text-muted-foreground" aria-hidden />
                        {sample.scope_label ?? 'Unnamed scope'}
                        {sample.version_no ? ` v${sample.version_no}` : ''}
                      </span>
                      {sample.is_version_current ? (
                        <Badge variant="outline" className="text-[11px]">
                          Current version
                        </Badge>
                      ) : (
                        <Badge variant="secondary" className="text-[11px]">
                          Version superseded
                        </Badge>
                      )}
                    </div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-x-3 text-xs text-muted-foreground">
                      <span>
                        {sample.submitted_on
                          ? `Sent ${formatDateInMalaysia(sample.submitted_on)}`
                          : 'No date recorded'}
                      </span>
                      {sample.submitted_by_name && <span>by {sample.submitted_by_name}</span>}
                    </div>
                    {sample.developer_feedback ? (
                      <p className="mt-1.5 text-xs">
                        <span className="font-medium">Developer said:</span>{' '}
                        {sample.developer_feedback}
                      </p>
                    ) : (
                      <p className="mt-1.5 text-xs text-muted-foreground">
                        No feedback recorded yet.
                      </p>
                    )}
                    {sample.salesperson_notes && (
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {sample.salesperson_notes}
                      </p>
                    )}
                  </div>

                  {project.can_edit && (
                    <div className="flex shrink-0 gap-1">
                      <Button
                        mode="icon"
                        variant="ghost"
                        size="sm"
                        onClick={() => setEditing(sample)}
                        aria-label={`Edit the ${sample.scope_label ?? 'sample'} submission`}
                      >
                        <Pencil className="size-3.5" />
                      </Button>
                      <Button
                        mode="icon"
                        variant="ghost"
                        size="sm"
                        onClick={() => setDeleting(sample)}
                        aria-label={`Delete the ${sample.scope_label ?? 'sample'} submission`}
                      >
                        <Trash2 className="size-3.5 text-destructive" />
                      </Button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {(creating || editing) && (
        <SampleDialog
          project={project}
          sample={editing}
          onDone={() => {
            setCreating(false);
            setEditing(null);
          }}
        />
      )}

      <ConfirmDeleteDialog
        open={Boolean(deleting)}
        onOpenChange={(next) => !next && setDeleting(null)}
        title="Confirm delete"
        description={
          deleting
            ? `Delete this sample submission and the developer feedback recorded on it? This action cannot be undone.`
            : ''
        }
        onDelete={async () => {
          if (!deleting) return;
          await remove.mutateAsync(deleting.id);
        }}
        onSuccess={() => setDeleting(null)}
        successMessage="Sample deleted"
      />
    </>
  );
}
