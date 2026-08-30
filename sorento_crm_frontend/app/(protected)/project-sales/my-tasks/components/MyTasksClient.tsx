'use client';

import * as React from 'react';
import Link from 'next/link';
import { AlertTriangle, Clock, TriangleAlert } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useMyTasks } from '../../_shared/hooks/useProjects';
import { bucketTasksByUrgency } from '../../_shared/lib/taskUrgency';
import type { ProjectTask } from '../../_shared/types/project.types';
import { PageHeader } from '@/components/common/PageHeader';

/**
 * One person's open project work, across every project they are on (AC-N9).
 *
 * Bucketed by urgency rather than grouped by project. Opening this screen answers
 * "what do I do now", and a per-project grouping makes that question take three
 * scrolls to answer. The project is on each row so the context is never lost.
 */
export function MyTasksClient() {
  const [includeOwned, setIncludeOwned] = React.useState(true);
  const query = useMyTasks({ include_unassigned_owned: includeOwned, limit: 200 });

  const rows = React.useMemo(() => query.data?.data ?? [], [query.data]);
  const buckets = React.useMemo(() => bucketTasksByUrgency(rows), [rows]);

  return (
    <div className="space-y-5">
      <PageHeader
        title="My tasks"
        actions={
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={includeOwned}
              onChange={(event) => setIncludeOwned(event.target.checked)}
              className="size-4 rounded border-border"
            />
            Include unassigned work on my projects
          </label>
        }
      >
        <p className="text-sm text-muted-foreground">
          Open project work assigned to you, or escalated to you, soonest first.
        </p>
      </PageHeader>

      {query.isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : query.isError ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
          <h2 className="text-sm font-semibold text-destructive">
            Your tasks could not be loaded
          </h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            {query.error instanceof Error ? query.error.message : 'Try again shortly.'}
          </p>
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border px-6 py-12 text-center">
          <h2 className="text-sm font-semibold">Nothing open against your name</h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            Tasks land here when somebody assigns one to you, escalates one to you, or
            when a project you own has work nobody has picked up.
          </p>
          <Button asChild variant="outline" className="mt-4">
            <Link href="/project-sales/pipeline">Open the pipeline</Link>
          </Button>
        </div>
      ) : (
        <div className="space-y-4">
          {buckets.map((bucket) => (
            <Card key={bucket.id}>
              <CardHeader className="flex flex-row items-center justify-between gap-2">
                <CardTitle className="flex items-center gap-2 text-sm">
                  {bucket.id === 'overdue' && (
                    <AlertTriangle className="size-4 text-destructive" aria-hidden />
                  )}
                  {bucket.label}
                </CardTitle>
                <Badge
                  variant={bucket.id === 'overdue' ? 'destructive' : 'secondary'}
                  className="text-[11px]"
                >
                  {bucket.tasks.length}
                </Badge>
              </CardHeader>
              <CardContent>
                <ul className="divide-y divide-border">
                  {bucket.tasks.map((task) => (
                    <MyTaskRow key={task.id} task={task} />
                  ))}
                </ul>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function MyTaskRow({ task }: { task: ProjectTask }) {
  return (
    <li className="flex flex-col gap-1 py-2.5 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
      <div className="min-w-0 space-y-1">
        <p className="truncate text-sm font-medium" title={task.name}>
          {task.name}
        </p>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <Link
            href={`/project-sales/${task.project_id}?tab=tasks`}
            className="truncate text-primary hover:underline"
            title={task.project_title ?? undefined}
          >
            {task.project_code ?? 'Open project'}
            {task.project_title ? ` · ${task.project_title}` : ''}
          </Link>
          {task.category && <span className="truncate">{task.category}</span>}
          {task.due_date && (
            <span
              className={
                task.is_overdue
                  ? 'flex items-center gap-1 font-medium text-destructive'
                  : 'flex items-center gap-1'
              }
            >
              <Clock className="size-3" aria-hidden />
              {formatDate(task.due_date)}
            </span>
          )}
          {task.escalated_to_name && (
            <span className="flex items-center gap-1 text-amber-600 dark:text-amber-500">
              <TriangleAlert className="size-3" aria-hidden />
              Escalated to {task.escalated_to_name}
            </span>
          )}
        </div>
        {task.stuck_reason && (
          <p className="break-words text-xs text-muted-foreground">
            Stuck: {task.stuck_reason}
          </p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Badge variant="outline" className="text-[11px] capitalize">
          {task.task_phase}
        </Badge>
        <Badge variant="secondary" className="text-[11px]">
          {task.status_label ?? 'No status'}
        </Badge>
      </div>
    </li>
  );
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString('en-MY', { day: '2-digit', month: 'short', year: 'numeric' });
}
